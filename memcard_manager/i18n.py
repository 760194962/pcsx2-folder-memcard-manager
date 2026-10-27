"""界面文字的中英切换。

代码里直接写中文原文，用 tr("中文", 参数...) 取当前语言的文字；英文译文在下面的 EN 表里，
以中文原文为 key。语言在启动时决定：设置里的 "language"（zh / en），否则跟随系统，
系统不是中文时用英文。
"""

import locale
import os
import sys

from .config import load_config

LANGUAGES = ("zh", "en")


def system_language():
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            # 主语言 ID 0x04 = 中文（简体、繁体都算）。显示语言或区域格式有一个是中文就用中文：
            # 不少人用英文版 Windows，但区域设成中国 / 台湾 / 香港
            ids = (k.GetUserDefaultUILanguage(), k.GetUserDefaultLCID())
            return "zh" if any(i & 0x3FF == 0x04 for i in ids) else "en"
        except (AttributeError, OSError):
            pass
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(name)
        if value:
            return "zh" if value.lower().startswith("zh") else "en"
    loc = locale.getlocale()[0] or ""
    return "zh" if loc.lower().startswith(("zh", "chinese")) else "en"


def configured_language():
    """设置里选的语言；"auto" 或没选时为 None。"""
    lang = load_config().get("language")
    return lang if lang in LANGUAGES else None


LANG = configured_language() or system_language()


def set_language(lang):
    global LANG
    LANG = lang


def tr(text, *args):
    if LANG == "en":
        text = EN.get(text, text)
    return text % args if args else text


EN = {
    # ---- 主窗口 ----
    "PS2 记忆卡管理器": "PS2 Memory Card Manager",
    "插槽 %s": "Slot %s",
    "插槽 %s — %s": "Slot %s — %s",
    "文件夹卡": "Folder card",
    "镜像卡": "Card image",
    "文件夹卡…": "Folder card…",
    "镜像卡…": "Card image…",
    "刷新": "Refresh",
    "未打开": "No card open",
    "导入…": "Import…",
    "导出…": "Export…",
    "删除": "Delete",
    "打开文件夹": "Open folder",
    "打开存档文件夹": "Open save folder",
    "在资源管理器中显示镜像": "Show image in Explorer",
    "复制到插槽 %s": "Copy to slot %s",
    "复制到 B →": "Copy to B →",
    "← 复制到 A": "← Copy to A",
    "导出格式": "Export format",
    "对比": "Compare",
    "相同": "Same",
    "不同": "Different",
    "仅此卡": "Only here",
    "无法读取": "Unreadable",
    "%d 个存档，已用 %dK": "%d saves, %dK used",
    "，剩余 %dK": ", %dK free",
    "%d 个存档无法读取，没能对比（文件可能被 PCSX2 占用）":
        "%d saves could not be read and were not compared (PCSX2 may be holding the files)",
    "对比失败: %s": "Compare failed: %s",

    # ---- 图标预览 ----
    "需要 numpy 才能预览图标（pip install numpy）": "Icon preview needs numpy (pip install numpy)",
    "选中存档即可预览它的 3D 图标": "Select a save to preview its 3D icon",
    "（无标题）": "(no title)",
    "图标: %s": "Icon: %s",
    "动画图标": "Animated icon",
    "图标渲染失败: %s": "Icon rendering failed: %s",

    # ---- 对话框 ----
    "提示": "Note",
    "PCSX2 正在运行": "PCSX2 is running",
    "检测到 PCSX2 正在运行。\n\n"
    "PCSX2 运行时会占用文件夹卡并在退出或换卡时回写，"
    "这时修改卡里的存档可能被覆盖、复制不完整，甚至损坏存档。\n\n"
    "建议先关闭 PCSX2 再操作。仍要继续吗？":
        "PCSX2 is running.\n\n"
        "While it runs, PCSX2 holds the Folder card and writes it back when it exits or "
        "swaps cards, so changes made now may be overwritten, copied incompletely or even "
        "corrupt the saves.\n\n"
        "It is best to close PCSX2 first. Continue anyway?",
    "\n\n失败:\n": "\n\nFailed:\n",
    "选择插槽 %s 的文件夹卡（例如 Folder.ps2）": "Choose the Folder card for slot %s (e.g. Folder.ps2)",
    "选择插槽 %s 的记忆卡镜像": "Choose a memory card image for slot %s",
    "PS2 记忆卡镜像": "PS2 memory card images",
    "所有文件": "All files",
    "读取失败": "Could not read the card",
    "读取失败: %s": "Could not read the card: %s",
    "这个文件夹里没有 _pcsx2_superblock，可能不是文件夹卡本身。\n"
    "应选择类似 memcards/Folder.ps2 这样的文件夹。":
        "This folder has no _pcsx2_superblock, so it may not be the Folder card itself.\n"
        "Choose a folder like memcards/Folder.ps2.",
    "请先在插槽 %s 的列表中选择存档。": "Select saves in slot %s first.",
    "选择导出文件夹（格式: %s）": "Choose the export folder (format: %s)",
    "\n…（共 %d 个）": "\n… (%d in total)",
    "文件已存在": "Files already exist",
    "导出文件夹里已有 %d 个同名文件：\n\n%s\n\n"
    "是：覆盖这些文件\n否：跳过它们，只导出其余的\n取消：不导出":
        "The export folder already has %d files with the same names:\n\n%s\n\n"
        "Yes: overwrite them\nNo: skip them and export the rest\nCancel: export nothing",
    "已导出 %d 个 %s 到:\n%s": "Exported %d %s files to:\n%s",
    "\n\n跳过了 %d 个已存在的文件。": "\n\nSkipped %d existing files.",
    "导出完成": "Export finished",
    "请先打开插槽 %s 的记忆卡。": "Open a memory card in slot %s first.",
    "选择要导入到插槽 %s 的存档": "Choose saves to import into slot %s",
    "PS2 存档": "PS2 saves",
    "存档已存在": "Save already exists",
    "插槽 %s 里已有存档 %s，要覆盖吗？": "Slot %s already has the save %s. Overwrite it?",
    "插槽 %s 里已有存档 %s，要覆盖吗？\n（旧存档会被替换，整张卡已备份为 .bak）":
        "Slot %s already has the save %s. Overwrite it?\n"
        "(The old save will be replaced; the whole card has been backed up to .bak.)",
    "插槽 %s 里已有存档 %s，要覆盖吗？\n（旧存档会移到回收站）":
        "Slot %s already has the save %s. Overwrite it?\n"
        "(The old save will be moved to the Recycle Bin.)",
    "插槽 %s 里已有存档 %s，要覆盖吗？\n（旧存档会被删除）":
        "Slot %s already has the save %s. Overwrite it?\n(The old save will be deleted.)",
    "导入完成": "Import finished",
    "已导入 %d 个存档到插槽 %s。": "Imported %d saves into slot %s.",
    "删除存档": "Delete saves",
    "要从插槽 %s 删除以下存档吗？（首次修改前会把整张卡备份为 .bak）\n\n%s":
        "Delete the following saves from slot %s? "
        "(The whole card is backed up to .bak before the first change.)\n\n%s",
    "要把插槽 %s 的以下存档移到回收站吗？\n\n%s":
        "Move the following saves from slot %s to the Recycle Bin?\n\n%s",
    "要从插槽 %s 永久删除以下存档吗？（无法恢复）\n\n%s":
        "Permanently delete the following saves from slot %s? This cannot be undone.\n\n%s",
    "部分存档删除失败。": "Some saves could not be deleted.",
    "复制": "Copy",
    "已复制 %d 个存档到插槽 %s。": "Copied %d saves to slot %s.",

    # ---- 命令行 ----
    "提示: %s 里没有 _pcsx2_superblock，可能不是文件夹卡本身。":
        "Note: %s has no _pcsx2_superblock, so it may not be the Folder card itself.",
    "警告: PCSX2 正在运行，它可能会覆盖刚导入的存档。建议先关闭 PCSX2。":
        "Warning: PCSX2 is running and may overwrite the imported saves. Close PCSX2 first.",
    "跳过 %s: 存档 %s 已存在（用 --force 覆盖）":
        "Skipped %s: save %s already exists (use --force to overwrite)",
    "跳过 %s: %s 已存在（用 --force 覆盖）":
        "Skipped %s: %s already exists (use --force to overwrite)",
    "失败 %s: %s": "Failed %s: %s",
    "无法读取记忆卡: %s": "Could not read the memory card: %s",
    "没有找到任何存档目录。": "No saves found.",
    "\n剩余空间: %s": "\nFree space: %s",
    "\n加 -o 输出目录 并用 --all 或 -s 名字 来导出（-f max 导出为 MAX）。":
        "\nTo export, add -o OUTPUT_DIR and --all or -s NAME (-f max for MAX).",
    "请用 -o 指定输出文件夹。": "Use -o to choose the output folder.",
    "找不到: %s": "Not found: %s",
    "浏览 PS2 记忆卡（PCSX2 文件夹卡、.ps2 / .vm2 镜像）里的存档，"
    "并导入/导出 .psu / .max 等（非官方工具）":
        "Browse the saves on PS2 memory cards (PCSX2 Folder cards, .ps2 / .vm2 images) "
        "and import/export .psu / .max and more (unofficial tool)",
    "文件夹卡（如 memcards/Folder.ps2）或记忆卡镜像文件；不填则打开图形界面":
        "Folder card (e.g. memcards/Folder.ps2) or memory card image; opens the GUI when omitted",
    "导出文件夹": "export folder",
    "导出格式（默认 psu）": "export format (default psu)",
    "要导出的存档目录名（可重复）": "save directory name to export (repeatable)",
    "导出全部存档": "export all saves",
    "把存档导入记忆卡（.psu .max .cbs .sps .xps .psv，可重复）":
        "import a save file into the card (.psu .max .cbs .sps .xps .psv, repeatable)",
    "覆盖已存在的：导入时覆盖同名存档，导出时覆盖同名文件":
        "overwrite existing saves when importing and existing files when exporting",

    # ---- 错误信息 ----
    "找不到记忆卡: %s": "Memory card not found: %s",
    "找不到文件夹: %s": "Folder not found: %s",
    "找不到存档: %s": "Save not found: %s",
    "存档名不合法: %r": "Invalid save name: %r",
    "存档名不合法: %s": "Invalid save name: %s",
    "文件名不合法: %s": "Invalid file name: %s",
    "清理非法字符后文件名冲突: %s / %s": "File names clash after replacing illegal characters: %s / %s",
    "名字超过 31 字节: %r": "Name is longer than 31 bytes: %r",
    "源和目标是同一张卡": "Source and destination are the same card",
    "移到回收站失败（错误码 %#x）: %s": "Could not move to the Recycle Bin (error %#x): %s",
    "不是可识别的 PS2 记忆卡镜像（加密的 .vme/.vm2 不支持）: %s":
        "Not a recognised PS2 memory card image (encrypted .vme/.vm2 are not supported): %s",
    "镜像卡只支持 ASCII 存档名: %r": "Card images only support ASCII save names: %r",
    "镜像卡空间不足：需要 %dK，可用 %dK": "Not enough space on the card image: %dK needed, %dK free",
    "存档里含有子目录，不支持: %s": "Saves with subdirectories are not supported: %s",
    "不支持的导出格式: %s": "Unsupported export format: %s",
    "无法识别的存档格式": "Unrecognised save file format",
    "没有图标文件": "No icon file",
    "图标文件无法解析: %s": "Could not parse the icon file: %s",
    "图标里没有模型": "The icon has no model",
}
