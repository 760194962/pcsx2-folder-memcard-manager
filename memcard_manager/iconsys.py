"""解析 icon.sys，取出存档标题（即记忆卡浏览器里显示的 Description）。

icon.sys 固定 964 字节，开头 "PS2D"；标题是 68 字节的 Shift-JIS 文本，
header 里有一个字节偏移指示在哪里换行（标题分两行显示）。
"""

import struct
import unicodedata

ICON_SYS_SIZE = 964
_MAGIC = b"PS2D"

_STRUCT = struct.Struct("<4sHHII"
                        "4I4I4I4I"        # 背景颜色
                        "4f4f4f"          # 光源方向
                        "4f4f4f4f"        # 光源颜色
                        "68s64s64s64s512s")
assert _STRUCT.size == ICON_SYS_SIZE


def _decode(raw):
    # cp932 是 Shift-JIS 的 Microsoft 扩展，覆盖游戏标题里常见的符号
    return unicodedata.normalize("NFKC", raw.decode("cp932", errors="replace")).strip()


def parse_title(data):
    """返回 (第一行, 第二行)；不是合法 icon.sys 时返回 None。"""
    if len(data) < ICON_SYS_SIZE:
        return None
    fields = _STRUCT.unpack(data[:ICON_SYS_SIZE])
    if fields[0] != _MAGIC:
        return None
    linebreak = fields[2]
    raw = fields[-5].split(b"\0", 1)[0]
    if 0 < linebreak < len(raw):
        return _decode(raw[:linebreak]), _decode(raw[linebreak:])
    return _decode(raw), ""


def description(data):
    """把两行标题合并成一行，用于列表显示。"""
    t = parse_title(data)
    if not t:
        return ""
    return " ".join(p for p in t if p)
