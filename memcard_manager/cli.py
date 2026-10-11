"""命令行入口。"""

import argparse
import sys

from .foldercard import list_saves, looks_like_folder_card
from .psu import export_save


def fmt_kb(n):
    return "%dK" % (n // 1024)


def cli(args):
    card = args.card
    if not looks_like_folder_card(card):
        print("提示: %s 里没有 _pcsx2_superblock，可能不是 Folder 卡本身的文件夹。" % card,
              file=sys.stderr)
    try:
        saves = list_saves(card)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        print("无法读取 Folder 卡: %s" % e, file=sys.stderr)
        return 2
    if not saves:
        print("没有找到任何存档目录。", file=sys.stderr)
        return 1

    if not args.out and not args.all and not args.save:
        print("%-26s %6s  %-16s  %s" % ("Directory", "Size", "Modified", "Description"))
        for s in saves:
            print("%-26s %6s  %-16s  %s" % (s.display_name, fmt_kb(s.card_size),
                                            s.modified_str, s.description))
        print("\n加 -o 输出目录 并用 --all 或 -s 名字 来导出为 PSU。")
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
            p = export_save(s, args.out)
            print("OK  %s -> %s" % (s.display_name, p))
        except Exception as e:  # noqa
            failed += 1
            print("失败 %s: %s" % (s.display_name, e), file=sys.stderr)
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="memcard_manager",
        description="浏览 PCSX2 Folder 记忆卡里的存档，并导出为 .psu（非官方工具）")
    ap.add_argument("card", nargs="?", help="Folder 卡文件夹（如 memcards/Folder.ps2）；不填则打开图形界面")
    ap.add_argument("-o", "--out", help="PSU 输出文件夹")
    ap.add_argument("-s", "--save", action="append", help="要导出的存档目录名（可重复）")
    ap.add_argument("--all", action="store_true", help="导出全部存档")
    args = ap.parse_args(argv)

    if not args.card:
        from .gui import main as gui_main
        return gui_main()
    return cli(args)


if __name__ == "__main__":
    sys.exit(main())
