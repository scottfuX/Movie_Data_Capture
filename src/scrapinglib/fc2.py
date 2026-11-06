# -*- coding: utf-8 -*-

import re
from lxml import etree
from urllib.parse import urljoin

from . import httprequest
from .parser import Parser


def get_fc2_article_id(number):
    normalized = str(number).upper().replace('_', '-')
    match = re.search(r'FC2-(?:FC2PPV-|PPV-)?(\d+)', normalized)
    if match:
        return match.group(1)
    if re.fullmatch(r'\d+', normalized):
        return normalized
    return None


class Fc2(Parser):
    source = 'fc2'

    expr_title = '/html/head/title/text()'
    expr_studio = '//*[@id="top"]/div[1]/section[1]/div/section/div[2]/ul/li[3]/a/text()'
    expr_release = '//*[@id="top"]/div[1]/section[1]/div/section/div[2]/div[2]/p/text()'
    expr_runtime = "//p[@class='items_article_info']/text()"
    expr_director = '//*[@id="top"]/div[1]/section[1]/div/section/div[2]/ul/li[3]/a/text()'
    expr_actor = '//*[@id="top"]/div[1]/section[1]/div/section/div[2]/ul/li[3]/a/text()'
    expr_cover = "//div[@class='items_article_MainitemThumb']/span/img/@src"
    expr_extrafanart = '//ul[@class="items_article_SampleImagesArea"]/li/a/@href'
    expr_tags = "//a[@class='tag tagTag']/text()"

    def extraInit(self):
        self.imagecut = 0
        self.allow_number_change = True

    def search(self, number):
        article_id = get_fc2_article_id(number)
        if not article_id:
            return 404
        self.number = article_id
        if self.specifiedUrl:
            self.detailurl = self.specifiedUrl
        else:
            self.detailurl = 'https://adult.contents.fc2.com/article/' + self.number + '/'

        from adc_function import load_cookies
        cookies, _ = load_cookies('fc2.json')
        if cookies:
            self.cookies = cookies
        response = httprequest.get(
            self.detailurl, cookies=self.cookies, proxies=self.proxies,
            extra_headers=self.extraheader, verify=self.verify, return_type='object'
        )
        if response.status_code != 200 or not response.content:
            return 404
        if 'login' in str(response.url).lower():
            return 404

        self.htmlcode = response.text
        htmltree = etree.HTML(self.htmlcode)
        if htmltree is None or not self.getCover(htmltree):
            return 404
        return self.dictformat(htmltree)

    def getNum(self, htmltree):
        return 'FC2-' + self.number

    def getRelease(self, htmltree):
        return super().getRelease(htmltree).strip(" ['販売日 : ']").replace('/','-')

    def getActors(self, htmltree):
        actors = super().getActors(htmltree)
        if not actors:
            actors = '素人'
        return actors

    def getCover(self, htmltree):
        cover = super().getCover(htmltree)
        if not cover and self.getTreeElement(htmltree, self.expr_release):
            cover = self.getTreeElement(htmltree, '//meta[@property="og:image"]/@content')
        return urljoin('https://adult.contents.fc2.com', cover) if cover else ''

    def getTrailer(self, htmltree):
        video_pather = re.compile(r'\'[a-zA-Z0-9]{32}\'')
        video = video_pather.findall(self.htmlcode)
        if video:
            try:
                video_url = video[0].replace('\'', '')
                video_url = 'https://adult.contents.fc2.com/api/v2/videos/' + self.number + '/sample?key=' + video_url
                url_json = eval(self.getHtml(video_url))['path'].replace('\\', '')
                return url_json
            except:
                return ''
        else:
            return ''
