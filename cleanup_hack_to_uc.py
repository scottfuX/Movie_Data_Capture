#!/usr/bin/env python3
"""
清理脚本：
1. 将 -hack 文件重命名为 -UC
2. 将标准命名图片 (fanart.jpg/poster.jpg/thumb.jpg) 重命名为与视频同名
3. 更新 NFO 文件中的图片引用路径

用法:
  python cleanup_hack_to_uc.py [目标目录]                       # dry-run: 仅处理 hack 目录
  python cleanup_hack_to_uc.py [目标目录] --execute              # 执行 hack 目录处理
  python cleanup_hack_to_uc.py [目标目录] --fix-all-images       # dry-run: 处理所有目录的图片
  python cleanup_hack_to_uc.py [目标目录] --fix-all-images --execute  # 执行所有目录图片处理

默认目标目录: /Volumes/152XXXX5503/rest/movie-QiBing/JAV_output
"""

import os
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime


DEFAULT_TARGET = "/Volumes/152XXXX5503/rest/movie-QiBing/JAV_output"

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.wmv', '.flv', '.rmvb', '.mov', '.ts', '.iso', '.strm'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}
NFO_EXT = '.nfo'
IMAGE_TYPES = ['fanart', 'poster', 'thumb']
SKIP_DIRS = {'extrafanart', '.actors'}


def get_video_stem(dir_obj: Path) -> str:
    """从目录中找到视频文件并返回其 stem（去除 -CDN 多分片部分）"""
    for f in sorted(dir_obj.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
            stem = f.stem
            stem = re.sub(r'-CD\d+$', '', stem, flags=re.IGNORECASE)
            return stem
    return ''


def has_standard_images(dir_obj: Path) -> bool:
    """检查目录中是否有标准命名的图片 (fanart.jpg, poster.jpg, thumb.jpg)"""
    for img_type in IMAGE_TYPES:
        for ext in IMAGE_EXTS:
            if (dir_obj / f"{img_type}{ext}").is_file():
                return True
    return False


def rename_hack_files(dir_obj: Path, hack_files: list, dry_run: bool, log_lines: list) -> int:
    """将目录中的 -hack 文件重命名为 -UC"""
    rename_count = 0

    video_files = []
    nfo_files = []
    image_files = []
    other_files = []

    for f in hack_files:
        suffix = Path(f).suffix.lower()
        if suffix in VIDEO_EXTS:
            video_files.append(f)
        elif suffix == NFO_EXT:
            nfo_files.append(f)
        elif suffix in IMAGE_EXTS:
            image_files.append(f)
        else:
            other_files.append(f)

    for filename in video_files + nfo_files + image_files + other_files:
        old_path = dir_obj / filename
        new_name = re.sub(r'-hack', '-UC', filename, flags=re.IGNORECASE)

        if new_name == filename:
            continue

        new_path = dir_obj / new_name

        if new_path.exists():
            msg = f"  [SKIP] {filename} -> {new_name} (目标已存在)"
            print(msg)
            log_lines.append(msg)
            continue

        msg = f"  [HACK->UC] {filename} -> {new_name}"
        print(msg)
        log_lines.append(msg)
        rename_count += 1

        if not dry_run:
            try:
                old_path.rename(new_path)
            except Exception as e:
                err_msg = f"  [ERROR] 重命名失败: {e}"
                print(err_msg)
                log_lines.append(err_msg)
                rename_count -= 1

    return rename_count


def rename_standard_images(dir_obj: Path, video_stem: str, dry_run: bool, log_lines: list) -> int:
    """将 fanart.jpg/poster.jpg/thumb.jpg 重命名为 {video_stem}-fanart.jpg 等"""
    rename_count = 0

    for img_type in IMAGE_TYPES:
        for ext in IMAGE_EXTS:
            old_img = dir_obj / f"{img_type}{ext}"
            if not old_img.is_file():
                continue

            new_name = f"{video_stem}-{img_type}{ext}"
            new_img = dir_obj / new_name

            if old_img.name == new_name:
                continue

            if new_img.exists():
                msg = f"  [SKIP-IMG] {old_img.name} -> {new_name} (目标已存在)"
                print(msg)
                log_lines.append(msg)
                continue

            msg = f"  [IMG-RENAME] {old_img.name} -> {new_name}"
            print(msg)
            log_lines.append(msg)
            rename_count += 1

            if not dry_run:
                try:
                    old_img.rename(new_img)
                except Exception as e:
                    err_msg = f"  [ERROR] 图片重命名失败: {e}"
                    print(err_msg)
                    log_lines.append(err_msg)
                    rename_count -= 1

    return rename_count


def update_nfo_refs(dir_obj: Path, video_stem: str, dry_run: bool, log_lines: list):
    """更新 NFO 文件：-hack → -UC，标准图片名 → 带 number 前缀的图片名"""
    for nfo_file in dir_obj.glob('*.nfo'):
        try:
            content = nfo_file.read_text(encoding='utf-8')
            new_content = content

            new_content = re.sub(r'-hack', '-UC', new_content, flags=re.IGNORECASE)

            for img_type in IMAGE_TYPES:
                for ext in ['.jpg', '.jpeg', '.png']:
                    plain_ref = f">{img_type}{ext}<"
                    numbered_ref = f">{video_stem}-{img_type}{ext}<"
                    new_content = new_content.replace(plain_ref, numbered_ref)

            if content != new_content:
                if not dry_run:
                    nfo_file.write_text(new_content, encoding='utf-8')
                msg = f"  [NFO-UPDATE] {nfo_file.name} 引用已更新"
                print(msg)
                log_lines.append(msg)
        except Exception as e:
            err_msg = f"  [ERROR] NFO 更新失败 {nfo_file}: {e}"
            print(err_msg)
            log_lines.append(err_msg)


def has_cdx_nfo(dir_obj: Path) -> bool:
    """检查目录中是否有带 -CDx/_CDx 后缀的 NFO 文件"""
    for f in dir_obj.glob('*.nfo'):
        if re.search(r'[-_]CD\d+', f.stem, re.IGNORECASE):
            return True
    return False


def rename_cdx_nfo(dir_obj: Path, video_stem: str, dry_run: bool, log_lines: list) -> int:
    """将带 -CDx/_CDx 的 NFO 文件重命名为不带 CDx 的版本"""
    rename_count = 0

    for nfo_file in dir_obj.glob('*.nfo'):
        if not re.search(r'[-_]CD\d+', nfo_file.stem, re.IGNORECASE):
            continue

        new_name = re.sub(r'[-_]CD\d+', '', nfo_file.name, flags=re.IGNORECASE)
        new_path = dir_obj / new_name

        if nfo_file.name == new_name:
            continue

        if new_path.exists():
            msg = f"  [SKIP-NFO] {nfo_file.name} -> {new_name} (目标已存在，删除旧CDx版本)"
            print(msg)
            log_lines.append(msg)
            if not dry_run:
                try:
                    nfo_file.unlink()
                    rename_count += 1
                except Exception as e:
                    err_msg = f"  [ERROR] 删除旧 NFO 失败: {e}"
                    print(err_msg)
                    log_lines.append(err_msg)
            else:
                rename_count += 1
            continue

        msg = f"  [NFO-CDx-RENAME] {nfo_file.name} -> {new_name}"
        print(msg)
        log_lines.append(msg)
        rename_count += 1

        if not dry_run:
            try:
                nfo_file.rename(new_path)
            except Exception as e:
                err_msg = f"  [ERROR] NFO 重命名失败: {e}"
                print(err_msg)
                log_lines.append(err_msg)
                rename_count -= 1

    return rename_count


def scan_directories(root_dir: Path, fix_all_images: bool):
    """扫描需要处理的目录"""
    dirs_to_process = {}

    for dirpath, dirnames, filenames in os.walk(str(root_dir)):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        hack_files = [f for f in filenames if '-hack' in f.lower()]

        dir_obj = Path(dirpath)
        needs_img = False
        needs_cdx_nfo = False

        has_video = any(Path(f).suffix.lower() in VIDEO_EXTS for f in filenames)

        if fix_all_images or hack_files:
            if has_video:
                needs_img = has_standard_images(dir_obj)

        if fix_all_images and has_video:
            needs_cdx_nfo = has_cdx_nfo(dir_obj)

        if hack_files or needs_img or needs_cdx_nfo:
            dirs_to_process[dirpath] = {
                'hack_files': hack_files,
                'needs_img_rename': needs_img,
                'needs_cdx_nfo_rename': needs_cdx_nfo,
            }

    return dirs_to_process


def process_directory(dir_path: str, info: dict, dry_run: bool, log_lines: list) -> int:
    """处理单个目录：hack 重命名 + 图片重命名 + CDx NFO 重命名 + NFO 内容更新"""
    dir_obj = Path(dir_path)
    total = 0

    if info['hack_files']:
        total += rename_hack_files(dir_obj, info['hack_files'], dry_run, log_lines)

    video_stem = get_video_stem(dir_obj)
    if not video_stem:
        return total

    if info['needs_img_rename']:
        total += rename_standard_images(dir_obj, video_stem, dry_run, log_lines)

    if info.get('needs_cdx_nfo_rename'):
        total += rename_cdx_nfo(dir_obj, video_stem, dry_run, log_lines)

    if info['hack_files'] or info['needs_img_rename'] or info.get('needs_cdx_nfo_rename'):
        update_nfo_refs(dir_obj, video_stem, dry_run, log_lines)

    return total


def main():
    parser = argparse.ArgumentParser(
        description="清理脚本：-hack → -UC + 统一图片命名与视频一致")
    parser.add_argument("target_dir", nargs="?", default=DEFAULT_TARGET,
                        help=f"目标目录 (默认: {DEFAULT_TARGET})")
    parser.add_argument("--execute", action="store_true",
                        help="实际执行（不加则为 dry-run 预览）")
    parser.add_argument("--fix-all-images", action="store_true",
                        help="处理所有目录中的标准图片命名（不限于 hack 目录）")
    args = parser.parse_args()

    root = Path(args.target_dir)
    dry_run = not args.execute

    if not root.exists():
        print(f"[ERROR] 目录不存在: {root}")
        sys.exit(1)

    mode_str = "DRY-RUN 预览模式" if dry_run else "执行模式"
    scope_str = "所有目录" if args.fix_all_images else "仅 -hack 目录"
    print(f"{'=' * 60}")
    print(f"清理脚本: -hack -> -UC + 统一图片命名")
    print(f"目标目录: {root}")
    print(f"处理范围: {scope_str}")
    print(f"运行模式: {mode_str}")
    print(f"{'=' * 60}")
    print(f"\n正在扫描目录...")

    dirs_to_process = scan_directories(root, args.fix_all_images)

    if not dirs_to_process:
        print("\n未找到需要处理的目录。")
        return

    hack_count = sum(1 for d in dirs_to_process.values() if d['hack_files'])
    img_count = sum(1 for d in dirs_to_process.values() if d['needs_img_rename'])
    cdx_count = sum(1 for d in dirs_to_process.values() if d.get('needs_cdx_nfo_rename'))
    print(f"\n找到 {len(dirs_to_process)} 个需处理的目录")
    if hack_count:
        print(f"  - {hack_count} 个目录含 -hack 文件")
    if img_count:
        print(f"  - {img_count} 个目录需重命名标准图片")
    if cdx_count:
        print(f"  - {cdx_count} 个目录含带 -CDx 的 NFO 需重命名")
    print()

    log_lines = []
    total_renamed = 0

    for dir_path, info in sorted(dirs_to_process.items()):
        rel_path = os.path.relpath(dir_path, str(root))
        tags = []
        if info['hack_files']:
            tags.append("hack")
        if info['needs_img_rename']:
            tags.append("img")
        if info.get('needs_cdx_nfo_rename'):
            tags.append("cdx-nfo")
        header = f"[DIR] {rel_path}/ [{','.join(tags)}]"
        print(header)
        log_lines.append(header)

        renamed = process_directory(dir_path, info, dry_run, log_lines)
        total_renamed += renamed
        print()

    print(f"{'=' * 60}")
    if dry_run:
        print(f"预览完成。共 {total_renamed} 项操作将执行。")
        cmd = f'python cleanup_hack_to_uc.py "{args.target_dir}"'
        if args.fix_all_images:
            cmd += " --fix-all-images"
        cmd += " --execute"
        print(f"如要执行，请运行：\n  {cmd}")
    else:
        print(f"执行完成。共重命名 {total_renamed} 个文件。")

    script_dir = Path(__file__).parent
    log_path = script_dir / f"cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(str(log_path), 'w', encoding='utf-8') as f:
            f.write(f"清理日志 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"目标目录: {root}\n")
            f.write(f"范围: {scope_str}\n")
            f.write(f"模式: {mode_str}\n")
            f.write(f"{'=' * 60}\n\n")
            f.write('\n'.join(log_lines))
            f.write(f"\n\n{'=' * 60}\n")
            f.write(f"总计: {total_renamed} 项操作\n")
        print(f"\n日志已保存到: {log_path}")
    except Exception as e:
        print(f"\n[WARN] 无法写入日志文件: {e}")


if __name__ == "__main__":
    main()
