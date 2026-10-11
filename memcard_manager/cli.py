"""命令行入口。"""

import argparse
import sys

from .cardops import pcsx2_running
from .cards import open_card
from .foldercard import looks_like_folder_card
from .importer import SaveExists
from .saveformats import EXPORT_FORMATS, read_save_file


def fmt_kb(n):
    return "%dK" % (n // 1024)


def cli(args):
    try:
        card = open_card(args.card)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if card.kind == "folder" and not looks_like_folder_card(card.path):
        print("提示: %s 里没有 _pcsx2_superblock，可能不是文件夹卡本身。" % card.path,
              file=sys.stderr)
    if args.imports:
        if pcsx2_running():
            print("警告: PCSX2 正在运行，它可能会覆盖刚导入的存档。建议先关闭 PCSX2。",
                  file=sys.stderr)
        failed = 0
        for p in args.imports:
            try:
                root, files = read_save_file(p)
                print("OK  %s -> %s" % (p, card.write(root, files, args.force, recycle=False)))
            except SaveExists as e:
                failed += 1
                print("跳过 %s: 存档 %s 已存在（用 --force 覆盖）" % (p, e), file=sys.stderr)
            except Exception as e:  # noqa
                failed += 1
                print("失败 %s: %s" % (p, e), file=sys.stderr)
        return 1 if failed else 0

    try:
        saves = card.list_saves()
    except (OSError, ValueError) as e:
        print("无法读取记忆卡: %s" % e, file=sys.stderr)
        return 2
    if not saves:
        print("没有找到任何存档目录。", file=sys.stderr)
        return 1

    if not args.out and not args.all and not args.save:
        print("%-26s %6s  %-16s  %s" % ("Directory", "Size", "Modified", "Description"))
        for s in saves:
            print("%-26s %6s  %-16s  %s" % (s.display_name, fmt_kb(s.card_size),
                                            s.modified_str, s.description))
        if card.free is not None:
            print("\n剩余空间: %s" % fmt_kb(card.free))
        print("\n加 -o 输出目录 并用 --all 或 -s 名字 来导出（-f max 导出为 MAX）。")
        return 0

    if not args.out:
        print("请用 -o 指定输出文件夹。", file=sys.stderr)
        return 2

    if args.all:
        chosen = saves
    else:
        wanted = set(args.save or [])
        chosen = [s for s in saves if s.host_name in wanted or s.display_name in wanted]
        missing = wanted - {s.host_name for s in chosen} - {s.display_name for s in chosen}
        if missing:
            print("找不到: %s" % ", ".join(sorted(missing)), file=sys.stderr)
            return 2

    failed = 0
    for s in chosen:
        try:
            p = card.export(s, args.out, args.format)
            print("OK  %s -> %s" % (s.display_name, p))
        except Exception as e:  # noqa
            failed += 1
            print("失败 %s: %s" % (s.display_name, e), file=sys.stderr)
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="memcard_manager",
        description="浏览 PS2 记忆卡（PCSX2 文件夹卡、.ps2 / .vm2 镜像）里的存档，"
                    "并导入/导出 .psu / .max 等（非官方工具）")
    ap.add_argument("card", nargs="?",
                    help="文件夹卡（如 memcards/Folder.ps2）或记忆卡镜像文件；不填则打开图形界面")
    ap.add_argument("-o", "--out", help="导出文件夹")
    ap.add_argument("-f", "--format", choices=EXPORT_FORMATS, default="psu",
                    help="导出格式（默认 psu）")
    ap.add_argument("-s", "--save", action="append", help="要导出的存档目录名（可重复）")
    ap.add_argument("--all", action="store_true", help="导出全部存档")
    ap.add_argument("-i", "--import", dest="imports", action="append", metavar="FILE",
                    help="把存档导入记忆卡（.psu .max .cbs .sps .xps .psv，可重复）")
    ap.add_argument("--force", action="store_true", help="导入时覆盖同名存档")
    args = ap.parse_args(argv)

    if not args.card:
        from .gui import main as gui_main
        return gui_main()
    return cli(args)


if __name__ == "__main__":
    sys.exit(main())
