"""PS2 记忆卡目录项（512 字节）与时间戳的打包，文件夹卡的元数据文件用的就是这个格式。"""

import re
import struct
import time

from .i18n import tr

ENTRY_SIZE = 512

# 与 PCSX2 MemoryCardFileEntry 的默认值一致
DEFAULT_DIR_MODE = 0x8427
DEFAULT_FILE_MODE = 0x8497


def pack_time(t):
    """time_t(UTC) -> 8 字节 PS2 时间戳。

    PCSX2 在 time_t 与卡上时间字段之间用 gmtime/timegm 互转，这里保持一致，
    所以卡上存的是什么数字，导出的存档里就是什么数字。
    """
    g = time.gmtime(max(int(t), 0))
    return struct.pack("<BBBBBBH", 0, g.tm_sec, g.tm_min, g.tm_hour,
                       g.tm_mday, g.tm_mon, g.tm_year)


def unpack_time(b):
    """8 字节 PS2 时间戳 -> (year, month, day, hour, minute, second)。"""
    _unused, sec, minute, hour, day, month, year = struct.unpack("<BBBBBBH", b)
    return year, month, day, hour, minute, sec


def format_time(b):
    y, mo, d, h, mi, _s = unpack_time(b)
    if y == 0:
        return ""
    return "%04d-%02d-%02d %02d:%02d" % (y, mo, d, h, mi)


def pack_entry(mode, size, created, modified, name, attr=0):
    if len(name) > 31:
        raise ValueError(tr("名字超过 31 字节: %r", name))
    b = bytearray(ENTRY_SIZE)
    struct.pack_into("<II", b, 0, mode, size)
    b[8:16] = created
    b[24:32] = modified
    struct.pack_into("<I", b, 32, attr)
    b[64:64 + len(name)] = name
    return bytes(b)


_WIN_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(name):
    s = _WIN_BAD.sub("_", name).rstrip(" .")
    return s or "save"
