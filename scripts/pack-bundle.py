"""将用户选择的 Bundle 文件夹打包为 ZIP；不调用 API、不确认科研记录。"""
import argparse
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    folder = args.folder.resolve(strict=True)
    if not folder.is_dir():
        parser.error("folder 必须是目录")
    output = args.output.resolve()
    if output == folder or folder in output.parents:
        parser.error("输出 ZIP 必须位于 Bundle 文件夹之外")
    paths = sorted(folder.rglob("*"))
    files = []
    for path in paths:
        if path.is_symlink() or folder not in path.resolve().parents:
            parser.error("Bundle 不允许链接到所选目录之外")
        if path.is_file():
            files.append(path)
    if len(files) > 256 or sum(path.stat().st_size for path in files) > 100 * 1024 * 1024:
        parser.error("文件数量或大小超过导入上限")
    # Exclusive creation avoids replacing an existing archive.
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(folder).as_posix())
    print(f"Bundle 已打包：{output}；请在项目导入页预览后人工确认。")


if __name__ == "__main__":
    main()
