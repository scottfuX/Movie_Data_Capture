import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lxml import etree
from PIL import Image

import adc_function
import core
import image_processing
from image_processing import cutImage
from scrapinglib.api import Scraping
from scrapinglib.fc2 import Fc2, get_fc2_article_id
from scrapinglib.javdb import Javdb
from number_parser import get_number


def make_image_bytes(image_format='JPEG'):
    buffer = BytesIO()
    image = Image.new('RGB', (4, 3), (32, 64, 96))
    image.save(buffer, format=image_format)
    image.close()
    return buffer.getvalue()


def make_response(content, status=200, content_type='image/jpeg'):
    return SimpleNamespace(
        ok=status < 400,
        status_code=status,
        content=content,
        headers={'Content-Type': content_type},
        url='https://example.com/image.jpg',
    )


class ImageValidationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_html_is_rejected_without_creating_file(self):
        conf = SimpleNamespace(proxy=lambda: SimpleNamespace(retry=1))
        with patch.object(core.config, 'getInstance', return_value=conf), \
                patch.object(core, 'get_html', return_value=make_response(b'<!DOCTYPE html>', content_type='text/html')), \
                patch.object(core, 'moveFailedFolder') as move_failed:
            result = core.download_file_with_filename(
                'https://example.com/cover', 'bad.jpg', str(self.root), 'movie.mp4'
            )
        self.assertEqual(result, 'failed')
        self.assertFalse((self.root / 'bad.jpg').exists())
        move_failed.assert_called_once_with('movie.mp4')

    def test_http_error_is_rejected(self):
        conf = SimpleNamespace(proxy=lambda: SimpleNamespace(retry=1))
        with patch.object(core.config, 'getInstance', return_value=conf), \
                patch.object(core, 'get_html', return_value=make_response(make_image_bytes(), status=403)), \
                patch.object(core, 'moveFailedFolder'):
            result = core.download_file_with_filename(
                'https://example.com/cover', 'denied.jpg', str(self.root), 'movie.mp4'
            )
        self.assertEqual(result, 'failed')
        self.assertFalse((self.root / 'denied.jpg').exists())

    def test_valid_image_is_saved(self):
        conf = SimpleNamespace(proxy=lambda: SimpleNamespace(retry=1))
        with patch.object(core.config, 'getInstance', return_value=conf), \
                patch.object(core, 'get_html', return_value=make_response(make_image_bytes('PNG'), content_type='image/png')), \
                patch.object(core, 'moveFailedFolder') as move_failed:
            result = core.download_file_with_filename(
                'https://example.com/cover', 'good.png', str(self.root), 'movie.mp4'
            )
        self.assertNotEqual(result, 'failed')
        self.assertTrue(adc_function.is_valid_image_file(self.root / 'good.png'))
        move_failed.assert_not_called()

    def test_existing_invalid_image_is_downloaded_again(self):
        target = self.root / 'thumb.jpg'
        target.write_bytes(b'<html>not an image</html>')
        valid_bytes = make_image_bytes()

        def fake_download(url, filename, path, filepath, headers):
            (Path(path) / filename).write_bytes(valid_bytes)

        conf = SimpleNamespace(
            download_only_missing_images=lambda: True,
            jellyfin=lambda: True,
        )
        with patch.object(core.config, 'getInstance', return_value=conf), \
                patch.object(core, 'download_file_with_filename', side_effect=fake_download) as download:
            result = core.image_download(
                'https://example.com/cover', 'fanart.jpg', 'thumb.jpg', str(self.root), 'movie.mp4'
            )
        self.assertTrue(result)
        download.assert_called_once()
        self.assertTrue(adc_function.is_valid_image_file(target))

    def test_existing_valid_image_is_not_downloaded_again(self):
        target = self.root / 'thumb.jpg'
        target.write_bytes(make_image_bytes())
        conf = SimpleNamespace(
            download_only_missing_images=lambda: True,
            jellyfin=lambda: True,
        )
        with patch.object(core.config, 'getInstance', return_value=conf), \
                patch.object(core, 'download_file_with_filename') as download:
            result = core.image_download(
                'https://example.com/cover', 'fanart.jpg', 'thumb.jpg', str(self.root), 'movie.mp4'
            )
        self.assertTrue(result)
        download.assert_not_called()

    def test_parallel_download_validates_images(self):
        html_target = self.root / 'parallel-html.jpg'
        image_target = self.root / 'parallel-image.jpg'
        with patch.object(adc_function, 'get_html', return_value=make_response(b'<html>')):
            result = adc_function.download_one_file(('https://example.com/html', html_target, None))
        self.assertIsNone(result)
        self.assertFalse(html_target.exists())

        with patch.object(adc_function, 'get_html', return_value=make_response(make_image_bytes())):
            result = adc_function.download_one_file(('https://example.com/image', image_target, None))
        self.assertEqual(result, str(image_target))
        self.assertTrue(adc_function.is_valid_image_file(image_target))

    def test_cut_image_replaces_invalid_existing_poster(self):
        (self.root / 'fanart.jpg').write_bytes(make_image_bytes())
        (self.root / 'poster.jpg').write_bytes(b'<html>not an image</html>')
        conf = SimpleNamespace(
            face_aspect_ratio=lambda: 2,
            face_aways_imagecut=lambda: False,
            download_only_missing_images=lambda: True,
        )
        with patch.object(image_processing.config, 'getInstance', return_value=conf):
            cutImage(0, str(self.root), 'fanart.jpg', 'poster.jpg')
        self.assertTrue(adc_function.is_valid_image_file(self.root / 'poster.jpg'))

    def test_rgba_watermark_is_encoded_as_valid_jpeg(self):
        target = self.root / 'rgba.jpg'
        image = Image.new('RGBA', (64, 64), (32, 64, 96, 128))
        image.save(target, format='PNG')
        image.close()
        with Image.open(target) as source:
            core.add_to_pic(str(target), source, 9, 0, 1)
        with Image.open(target) as result:
            result.load()
            self.assertEqual(result.format, 'JPEG')
            self.assertEqual(result.mode, 'RGB')


class VersionTagTests(unittest.TestCase):
    def test_ltx_version_priority_and_suffix(self):
        conf = SimpleNamespace(
            duplicate_enable_version_check=lambda: True,
            duplicate_priority_ltx_uc=lambda: 4,
            duplicate_priority_ltx_u=lambda: 3,
            duplicate_priority_uc=lambda: 2,
        )
        cases = {
            'ABF-391-LTX-UC.mp4': ('-LTX-UC', 4),
            'ABF-391-LTX-U.mp4': ('-LTX-U', 3),
            'ABF-391-LTX.mp4': ('-LTX-U', 3),
            'ABF-391-UC.mp4': ('-UC', 2),
        }
        with patch.object(core.config, 'getInstance', return_value=conf):
            for filename, expected in cases.items():
                with self.subTest(filename=filename):
                    version = core.parse_version_from_path(filename, 'ABF-391')
                    self.assertEqual(
                        (version.get_version_suffix(), version.priority), expected
                    )

    def test_ltx_number_extraction(self):
        cases = {
            'SNOS-449-LTX-UC.mp4': 'SNOS-449',
            'SNOS-449-LTX-U.mp4': 'SNOS-449',
            '489155.com@[LTX模型破解]SNOS-449-LTX-UC-CD1.mp4': 'SNOS-449',
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(get_number(False, filename), expected)

    def test_pre_scrape_normalization_and_collision_protection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            uc_movie = root / 'ABF-391-UC.mp4'
            uc_movie.write_bytes(b'uc')
            subtitle = root / 'ABF-391-UC.chs.srt'
            subtitle.write_text('subtitle', encoding='utf-8')
            ltx_movie = root / 'SNOS-449-LTX.mkv'
            ltx_movie.write_bytes(b'ltx')
            conf = SimpleNamespace(sub_rule=lambda: {'.srt', '.ass'})

            with patch.object(core.config, 'getInstance', return_value=conf):
                normalized_uc = Path(core.normalize_ltx_version_tag(str(uc_movie)))
                normalized_ltx = Path(core.normalize_ltx_version_tag(str(ltx_movie)))
                unchanged = core.normalize_ltx_version_tag(str(normalized_uc))

            self.assertEqual(normalized_uc.name, 'ABF-391-LTX-UC.mp4')
            self.assertEqual(normalized_ltx.name, 'SNOS-449-LTX-U.mkv')
            self.assertEqual(unchanged, str(normalized_uc))
            self.assertTrue(normalized_uc.is_file())
            self.assertTrue(normalized_ltx.is_file())
            self.assertTrue((root / 'ABF-391-LTX-UC.chs.srt').is_file())
            self.assertFalse(uc_movie.exists())
            self.assertFalse(subtitle.exists())

            conflict_source = root / 'MIAB-137-UC.mp4'
            conflict_target = root / 'MIAB-137-LTX-UC.mp4'
            conflict_source.write_bytes(b'source')
            conflict_target.write_bytes(b'existing')
            with patch.object(core.config, 'getInstance', return_value=conf), \
                    self.assertRaises(FileExistsError):
                core.normalize_ltx_version_tag(str(conflict_source))
            self.assertEqual(conflict_source.read_bytes(), b'source')
            self.assertEqual(conflict_target.read_bytes(), b'existing')

    def test_scraping_entries_normalize_before_core(self):
        import main

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            uc_movie = root / 'ABF-391-UC.mp4'
            uc_movie.touch()
            ltx_movie = root / 'SNOS-449-LTX.mkv'
            ltx_movie.touch()
            conf = SimpleNamespace(
                debug=lambda: False,
                number_regexs=lambda: '',
                sub_rule=lambda: {'.srt'},
            )
            threads = [main.threading.current_thread().name]
            with patch.object(main.config, 'getInstance', return_value=conf), \
                    patch.object(main, 'core_main') as scrape:
                main.create_data_and_move(str(uc_movie), False, False, None, threads)
                main.create_data_and_move_with_custom_number(
                    str(ltx_movie), 'SNOS-449', None, None, None
                )

            self.assertEqual(threads, [])
            self.assertEqual(
                scrape.call_args_list[0].args[:2],
                (str(root / 'ABF-391-LTX-UC.mp4'), 'ABF-391'),
            )
            self.assertEqual(
                scrape.call_args_list[1].args[:2],
                (str(root / 'SNOS-449-LTX-U.mkv'), 'SNOS-449'),
            )
            self.assertTrue((root / 'ABF-391-LTX-UC.mp4').is_file())
            self.assertTrue((root / 'SNOS-449-LTX-U.mkv').is_file())


class SourceRegressionTests(unittest.TestCase):
    def test_site_model_prefix_number_extraction(self):
        cases = {
            '489155.com@[LTX模型破解]SNOS-449-UC.mp4': 'SNOS-449',
            'example.com@[LTX模型破解]ABF-391-UC.mp4': 'ABF-391',
            'example.org@[Model]XYZ-123-C.mp4': 'XYZ-123',
            '489155.com@[Group][Other]MIAB-137-UC.mp4': 'MIAB-137',
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(get_number(False, filename), expected)

    def test_fc2_article_id_extraction(self):
        cases = {
            'FC2-1050737': '1050737',
            'FC2-PPV-2806478': '2806478',
            'FC2-FC2PPV-2806478-1': '2806478',
            'fc2-fc2ppv-4833053': '4833053',
            '1050737': '1050737',
            'FC2-': None,
            'FC2-汝工作室': None,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(get_fc2_article_id(value), expected)

    def test_fc2_empty_cover_does_not_become_homepage(self):
        parser = Fc2()
        parser.init()
        tree = etree.HTML('<html><head><title>FC2 home</title></head><body></body></html>')
        self.assertEqual(parser.getCover(tree), '')

    def test_fc2_redirect_is_rejected(self):
        response = SimpleNamespace(status_code=302, content=b'', url='https://adult.contents.fc2.com/article/1050737/')
        parser = Fc2()
        parser.init()
        with patch('adc_function.load_cookies', return_value=(None, None)), \
                patch('scrapinglib.fc2.httprequest.get', return_value=response):
            result = parser.search('FC2-1050737')
        self.assertEqual(result, 404)

    def test_fc2_fallback_includes_javdb(self):
        sources = Scraping().checkAdultSources('fc2,avsox,javdb', 'FC2-1050737')
        self.assertEqual(sources, ['fc2', 'avsox', 'javdb'])

    def test_fc2_query_alias_preserves_original_number(self):
        original = 'FC2-FC2PPV-2806478-1'
        queried = []

        class FakeJavdb:
            def scrape(self, number, scraping):
                queried.append(number)
                return json.dumps({
                    'number': number,
                    'title': 'metadata',
                    'actor': ['素人'],
                    'cover': 'https://example.com/cover.jpg',
                    'cover_small': '',
                })

        with patch('scrapinglib.api.importlib.import_module', return_value=SimpleNamespace(Javdb=FakeJavdb)):
            result = Scraping().searchAdult(original, ['javdb'])
        self.assertEqual(queried, ['FC2-2806478'])
        self.assertEqual(result['number'], original)

    def test_fc2_missing_article_id_is_rejected(self):
        with patch('scrapinglib.api.importlib.import_module') as import_module:
            result = Scraping().searchAdult('FC2-', ['javdb'])
        self.assertIsNone(result)
        import_module.assert_not_called()

    def test_javdb_current_actor_markup(self):
        tree = etree.HTML(
            '<span class="value">'
            '<a href="/actors/1" class="actor-female">Female</a>'
            '<a href="/actors/2">Male</a>'
            '</span>'
        )
        parser = Javdb()
        parser.init()
        parser.number = 'FNS-249'
        with patch('scrapinglib.javdb.config.getInstance') as get_config:
            get_config.return_value.actor_gender.return_value = 'female'
            self.assertEqual(parser.getActors(tree), ['Female'])

    def test_javdb_legacy_actor_markup(self):
        tree = etree.HTML(
            '<span class="value">'
            '<a href="/actors/1">Female</a><strong class="symbol female"></strong>'
            '<a href="/actors/2">Male</a><strong class="symbol male"></strong>'
            '</span>'
        )
        parser = Javdb()
        parser.init()
        parser.number = 'ABF-391'
        with patch('scrapinglib.javdb.config.getInstance') as get_config:
            get_config.return_value.actor_gender.return_value = 'female'
            self.assertEqual(parser.getActors(tree), ['Female'])

    def test_javdb_missing_gender_does_not_raise(self):
        tree = etree.HTML('<span class="value"><a href="/actors/1">Unknown</a></span>')
        parser = Javdb()
        parser.init()
        parser.number = 'TEST-001'
        with patch('scrapinglib.javdb.config.getInstance') as get_config:
            get_config.return_value.actor_gender.return_value = 'female'
            self.assertEqual(parser.getActors(tree), [])


if __name__ == '__main__':
    unittest.main()
