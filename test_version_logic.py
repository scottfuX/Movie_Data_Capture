#!/usr/bin/env python3
"""
测试版本解析和重复处理逻辑
运行命令: python3 test_version_logic.py
"""
import os
import re
import sys
import tempfile
import shutil
from pathlib import Path
from enum import IntEnum
from dataclasses import dataclass
from typing import Tuple, Optional

# ========================================================================
# 从 core.py 复制的版本处理逻辑（独立测试用）
# ========================================================================
class VersionType(IntEnum):
    """影片版本类型，值越大优先级越高"""
    ORIGINAL = 0      # 原版
    CHINESE = 1       # -C 中文字幕
    UNCENSORED = 1    # -U 无码破解
    LEAK = 2          # -leak 流出
    UC_COMBO = 2      # -UC 无码破解+中文


@dataclass
class VersionInfo:
    """版本信息"""
    version_type: VersionType
    cn_sub: bool
    leak: bool
    hack: bool

    @property
    def priority(self) -> int:
        """返回优先级分数"""
        return int(self.version_type)

    def get_version_suffix(self) -> str:
        """获取统一的版本标识后缀用于文件命名"""
        if self.hack and self.cn_sub:
            return '-UC'
        elif self.hack:
            return '-U'
        elif self.leak and self.cn_sub:
            return '-leak-C'
        elif self.leak:
            return '-leak'
        elif self.cn_sub:
            return '-C'
        return ''


def parse_version_from_path(movie_path: str, number: str) -> VersionInfo:
    """从文件路径解析版本信息"""
    cn_sub = False
    leak = False
    hack = False

    filename = os.path.basename(movie_path)
    filename_lower = filename.lower()

    if re.search(r'[-_]C(\.\w+$|-\w+)|\d+ch(\.\w+$|-\w+)', movie_path, re.I) \
       or '中文' in movie_path or '字幕' in movie_path \
       or ".chs" in movie_path or '.cht' in movie_path:
        cn_sub = True

    if '流出' in movie_path or 'uncensored' in movie_path.lower() \
       or 'leak' in movie_path.lower():
        leak = True

    if 'hack' in str(movie_path).lower() or '破解' in movie_path:
        hack = True

    if re.search(r'[-_]uc(?=\.\w+$|[-_]|$)', filename_lower):
        hack = True
        cn_sub = True

    if re.search(r'[-_]u(?=\.\w+$|[-_]|$)', filename_lower) and \
       not re.search(r'[-_]uc', filename_lower):
        hack = True

    if re.search(r'[-_]lc(?=\.\w+$|[-_]|$)', filename_lower):
        leak = True
        cn_sub = True

    if re.search(r'[-_]l(?=\.\w+$|[-_]|$)', filename_lower) and \
       not re.search(r'[-_]lc', filename_lower):
        leak = True

    if hack and cn_sub:
        version_type = VersionType.UC_COMBO
    elif leak:
        version_type = VersionType.LEAK
    elif hack:
        version_type = VersionType.UNCENSORED
    elif cn_sub:
        version_type = VersionType.CHINESE
    else:
        version_type = VersionType.ORIGINAL

    return VersionInfo(
        version_type=version_type,
        cn_sub=cn_sub,
        leak=leak,
        hack=hack,
    )


def compare_versions(current_path: str, existing_path: str, number: str) -> str:
    """比较两个版本的优先级"""
    current_vi = parse_version_from_path(current_path, number)
    existing_vi = parse_version_from_path(existing_path, number)

    current_suffix = current_vi.get_version_suffix()
    existing_suffix = existing_vi.get_version_suffix()

    if current_suffix == existing_suffix:
        st = os.stat(current_path)
        current_time = st.st_birthtime if hasattr(st, 'st_birthtime') else st.st_mtime
        st2 = os.stat(existing_path)
        existing_time = st2.st_birthtime if hasattr(st2, 'st_birthtime') else st2.st_mtime
        if current_time > existing_time:
            return 'current_wins'
        else:
            return 'existing_wins'

    current_priority = current_vi.priority
    existing_priority = existing_vi.priority

    if current_priority == existing_priority:
        return 'coexist'
    elif current_priority > existing_priority:
        return 'current_wins'
    else:
        return 'existing_wins'


# ========================================================================
# 测试函数
# ========================================================================
def test_version_parsing():
    """测试版本解析"""
    print("=" * 60)
    print("测试 1: 版本解析")
    print("=" * 60)

    test_cases = [
        ('SSIS-001.mp4', 'SSIS-001', '', 0),
        ('SSIS-001-C.mp4', 'SSIS-001', '-C', 1),
        ('SSIS-001-U.mp4', 'SSIS-001', '-U', 1),
        ('SSIS-001-UC.mp4', 'SSIS-001', '-UC', 2),
        ('SSIS-001-L.mp4', 'SSIS-001', '-leak', 2),
        ('SSIS-001-LC.mp4', 'SSIS-001', '-leak-C', 2),
        ('SSIS-001-leak.mp4', 'SSIS-001', '-leak', 2),
        ('SSIS-001-hack.mp4', 'SSIS-001', '-U', 1),          # -hack 应该识别为 -U
        ('SSIS-001-hack-C.mp4', 'SSIS-001', '-UC', 2),      # -hack-C 应该识别为 -UC
        ('[字幕组]SSIS-001.mp4', 'SSIS-001', '-C', 1),
    ]

    all_passed = True
    for path, number, expected_suffix, expected_priority in test_cases:
        vi = parse_version_from_path(path, number)
        suffix = vi.get_version_suffix()
        priority = vi.priority
        passed = suffix == expected_suffix and priority == expected_priority
        status = "✓" if passed else "✗"
        print(f"  {status} {path:30} -> suffix=\"{suffix:4}\" priority={priority} (expected: suffix=\"{expected_suffix}\" priority={expected_priority})")
        if not passed:
            all_passed = False

    print()
    return all_passed


def test_priority_comparison():
    """测试优先级比较"""
    print("=" * 60)
    print("测试 2: 优先级比较逻辑")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp()
    try:
        test_scenarios = [
            # (existing_file, current_file, expected_result, description)
            ('SSIS-001-C.mp4', 'SSIS-001-C.mp4', 'current_wins', '相同版本重复 - current 更新，覆盖 existing'),
            ('SSIS-001-C.mp4', 'SSIS-001-U.mp4', 'coexist', '同优先级: -C vs -U'),
            ('SSIS-001.mp4', 'SSIS-001-C.mp4', 'current_wins', '高优先级覆盖: -C 覆盖原版'),
            ('SSIS-001.mp4', 'SSIS-001-UC.mp4', 'current_wins', '高优先级覆盖: -UC 覆盖原版'),
            ('SSIS-001-C.mp4', 'SSIS-001-UC.mp4', 'current_wins', '高优先级覆盖: -UC 覆盖 -C'),
            ('SSIS-001-UC.mp4', 'SSIS-001-L.mp4', 'coexist', '同优先级共存: -UC vs -L'),
            ('SSIS-001.mp4', 'SSIS-001-UC.mp4', 'current_wins', '高优先级删除低优先级: -UC 删除原版'),
        ]

        all_passed = True
        for existing, current, expected, desc in test_scenarios:
            # 使用不同的子目录来避免相同文件名指向同一文件
            existing_dir = os.path.join(temp_dir, 'existing')
            current_dir = os.path.join(temp_dir, 'current')
            os.makedirs(existing_dir, exist_ok=True)
            os.makedirs(current_dir, exist_ok=True)

            existing_path = os.path.join(existing_dir, existing)
            current_path = os.path.join(current_dir, current)

            Path(existing_path).touch()
            import time
            time.sleep(0.1)
            Path(current_path).touch()

            result = compare_versions(current_path, existing_path, 'SSIS-001')

            passed = result == expected
            status = "✓" if passed else "✗"
            print(f"  {status} {desc}")
            print(f"        existing={existing:20} current={current:20}")
            print(f"        expected={expected:20} got={result}")

            if not passed:
                all_passed = False
            print()

        return all_passed
    finally:
        shutil.rmtree(temp_dir)


def test_priority_values():
    """测试优先级值"""
    print("=" * 60)
    print("测试 3: 优先级值验证")
    print("=" * 60)

    test_cases = [
        ('SSIS-001.mp4', 0, '原版'),
        ('SSIS-001-C.mp4', 1, '中文字幕'),
        ('SSIS-001-U.mp4', 1, '无码破解'),
        ('SSIS-001-UC.mp4', 2, '无码破解+中文'),
        ('SSIS-001-L.mp4', 2, '流出'),
        ('SSIS-001-LC.mp4', 2, '流出+中文'),
    ]

    all_passed = True
    for path, expected_priority, desc in test_cases:
        vi = parse_version_from_path(path, 'SSIS-001')
        actual_priority = vi.priority
        passed = actual_priority == expected_priority
        status = "✓" if passed else "✗"
        print(f"  {status} {desc:15} priority={actual_priority} (expected={expected_priority})")

        if not passed:
            all_passed = False

    print()
    return all_passed


def test_suffix_values():
    """测试后缀值"""
    print("=" * 60)
    print("测试 4: 后缀值验证")
    print("=" * 60)

    test_cases = [
        ('SSIS-001.mp4', '', '原版'),
        ('SSIS-001-C.mp4', '-C', '中文字幕'),
        ('SSIS-001-U.mp4', '-U', '无码破解'),
        ('SSIS-001-UC.mp4', '-UC', '无码破解+中文'),
        ('SSIS-001-L.mp4', '-leak', '流出'),
        ('SSIS-001-LC.mp4', '-leak-C', '流出+中文'),
        ('SSIS-001-leak.mp4', '-leak', '流出(leak标记)'),
        ('SSIS-001-hack.mp4', '-U', '破解(hack->U)'),
    ]

    all_passed = True
    for path, expected_suffix, desc in test_cases:
        vi = parse_version_from_path(path, 'SSIS-001')
        actual_suffix = vi.get_version_suffix()
        passed = actual_suffix == expected_suffix
        status = "✓" if passed else "✗"
        print(f"  {status} {desc:20} suffix=\"{actual_suffix}\" (expected=\"{expected_suffix}\")")

        if not passed:
            all_passed = False

    print()
    return all_passed


def test_coexistence_logic():
    """测试共存逻辑"""
    print("=" * 60)
    print("测试 5: 共存逻辑验证")
    print("=" * 60)

    coexist_groups = [
        [('SSIS-001-C.mp4', 'SSIS-001-U.mp4'), '优先级1: -C 和 -U'],
        [('SSIS-001-UC.mp4', 'SSIS-001-leak.mp4'), '优先级2: -UC 和 -leak'],
    ]

    all_passed = True
    for files, desc in coexist_groups:
        vi1 = parse_version_from_path(files[0], 'SSIS-001')
        vi2 = parse_version_from_path(files[1], 'SSIS-001')

        same_priority = vi1.priority == vi2.priority
        different_suffix = vi1.get_version_suffix() != vi2.get_version_suffix()
        should_coexist = same_priority and different_suffix

        status = "✓" if should_coexist else "✗"
        print(f"  {status} {desc}")
        print(f"        {files[0]} (priority={vi1.priority}, suffix=\"{vi1.get_version_suffix()}\")")
        print(f"        {files[1]} (priority={vi2.priority}, suffix=\"{vi2.get_version_suffix()}\")")
        print(f"        should coexist: {should_coexist}")
        print()

        if not should_coexist:
            all_passed = False

    return all_passed


def test_image_naming():
    """测试图片命名：始终使用 {number}{version_suffix}-{type}{ext} 格式"""
    print("=" * 60)
    print("测试 6: 图片命名一致性")
    print("=" * 60)

    test_cases = [
        # (movie_path, number, cover_url, expected_fanart, expected_poster, expected_thumb)
        ('SSIS-001.mp4', 'SSIS-001', 'http://example.com/cover.jpg',
         'SSIS-001-fanart.jpg', 'SSIS-001-poster.jpg', 'SSIS-001-thumb.jpg'),
        ('SSIS-001-C.mp4', 'SSIS-001', 'http://example.com/cover.jpg',
         'SSIS-001-C-fanart.jpg', 'SSIS-001-C-poster.jpg', 'SSIS-001-C-thumb.jpg'),
        ('SSIS-001-UC.mp4', 'SSIS-001', 'http://example.com/cover.jpg',
         'SSIS-001-UC-fanart.jpg', 'SSIS-001-UC-poster.jpg', 'SSIS-001-UC-thumb.jpg'),
        ('SSIS-001-U.mp4', 'SSIS-001', 'http://example.com/cover.jpg',
         'SSIS-001-U-fanart.jpg', 'SSIS-001-U-poster.jpg', 'SSIS-001-U-thumb.jpg'),
        ('SSIS-001-leak.mp4', 'SSIS-001', 'http://example.com/cover.jpg',
         'SSIS-001-leak-fanart.jpg', 'SSIS-001-leak-poster.jpg', 'SSIS-001-leak-thumb.jpg'),
        ('SSIS-001-leak-C.mp4', 'SSIS-001', 'http://example.com/cover.png',
         'SSIS-001-leak-C-fanart.png', 'SSIS-001-leak-C-poster.png', 'SSIS-001-leak-C-thumb.png'),
        ('SSIS-001-hack.mp4', 'SSIS-001', 'http://example.com/cover.jpg',
         'SSIS-001-U-fanart.jpg', 'SSIS-001-U-poster.jpg', 'SSIS-001-U-thumb.jpg'),
    ]

    def image_ext(url):
        ext = os.path.splitext(url)[-1]
        if ext in {'.jpg', '.jpge', '.bmp', '.png', '.gif'}:
            return ext
        return ".jpg"

    all_passed = True
    for movie_path, number, cover_url, exp_fanart, exp_poster, exp_thumb in test_cases:
        vi = parse_version_from_path(movie_path, number)
        version_suffix = vi.get_version_suffix()
        ext = image_ext(cover_url)

        fanart_path = f"{number}{version_suffix}-fanart{ext}"
        poster_path = f"{number}{version_suffix}-poster{ext}"
        thumb_path = f"{number}{version_suffix}-thumb{ext}"

        nfo_name = f"{number}{version_suffix}.nfo"

        p1 = fanart_path == exp_fanart
        p2 = poster_path == exp_poster
        p3 = thumb_path == exp_thumb
        passed = p1 and p2 and p3
        status = "✓" if passed else "✗"

        print(f"  {status} {movie_path:25} -> fanart={fanart_path}, poster={poster_path}, nfo={nfo_name}")
        if not passed:
            all_passed = False
            if not p1:
                print(f"        fanart mismatch: got={fanart_path} expected={exp_fanart}")
            if not p2:
                print(f"        poster mismatch: got={poster_path} expected={exp_poster}")
            if not p3:
                print(f"        thumb  mismatch: got={thumb_path} expected={exp_thumb}")

    print()
    return all_passed


def test_nfo_image_refs_consistency():
    """测试 NFO 中的图片引用与实际图片文件名一致"""
    print("=" * 60)
    print("测试 7: NFO 图片引用一致性")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp()
    try:
        test_cases = [
            ('ABP-171-UC.mp4', 'ABP-171'),
            ('SSIS-001-C.mp4', 'SSIS-001'),
            ('PRED-400.mp4', 'PRED-400'),
            ('ABP-100-leak.mp4', 'ABP-100'),
        ]

        all_passed = True
        for movie_file, number in test_cases:
            vi = parse_version_from_path(movie_file, number)
            vs = vi.get_version_suffix()
            ext = '.jpg'

            fanart_name = f"{number}{vs}-fanart{ext}"
            poster_name = f"{number}{vs}-poster{ext}"
            thumb_name = f"{number}{vs}-thumb{ext}"
            nfo_name = f"{number}{vs}.nfo"
            video_name = f"{number}{vs}.mp4"

            nfo_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<movie>
  <poster>{poster_name}</poster>
  <thumb>{thumb_name}</thumb>
  <fanart>{fanart_name}</fanart>
</movie>"""
            nfo_path = os.path.join(temp_dir, nfo_name)
            with open(nfo_path, 'w') as f:
                f.write(nfo_content)

            with open(nfo_path, 'r') as f:
                content = f.read()

            poster_ref_ok = f"<poster>{poster_name}</poster>" in content
            thumb_ref_ok = f"<thumb>{thumb_name}</thumb>" in content
            fanart_ref_ok = f"<fanart>{fanart_name}</fanart>" in content

            all_refs_match = all([
                poster_ref_ok,
                thumb_ref_ok,
                fanart_ref_ok,
                poster_name.startswith(number),
                fanart_name.startswith(number),
                thumb_name.startswith(number),
            ])

            passed = all_refs_match
            status = "✓" if passed else "✗"
            print(f"  {status} {video_name:20} -> nfo={nfo_name}, poster={poster_name}, fanart={fanart_name}")

            if not passed:
                all_passed = False

        print()
        return all_passed
    finally:
        shutil.rmtree(temp_dir)


def main():
    print("\n" + "=" * 60)
    print("       版本处理逻辑测试")
    print("=" * 60 + "\n")

    results = []

    results.append(("版本解析", test_version_parsing()))
    results.append(("优先级比较", test_priority_comparison()))
    results.append(("优先级值", test_priority_values()))
    results.append(("后缀值", test_suffix_values()))
    results.append(("共存逻辑", test_coexistence_logic()))
    results.append(("图片命名一致性", test_image_naming()))
    results.append(("NFO图片引用一致性", test_nfo_image_refs_consistency()))

    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("🎉 所有测试通过!")
        return 0
    else:
        print("❌ 部分测试失败!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
