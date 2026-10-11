"""PSU (EMS) 格式的写出，以及 PS2 目录项 / 时间戳的打包。

PSU 就是把记忆卡上的目录项（512 字节，布局与 PS2 记忆卡完全相同）
依次排列：目录自身、"."、".."，然后每个文件一个条目，条目后面紧跟
文件内容并补零到 1024 字节对齐。
"""

import re
import struct
import time

ENTRY_SIZE = 512
ALIGN = 1024

# 与 PCSX2 MemoryCardFileEntry 的默认值一致
DEFAULT_DIR_MODE = 0x8427
DEFAULT_FILE_MODE = 0x8497


def pack_time(t):
    """time_t(UTC) -> 8 字节 PS2 时间戳。

    PCSX2 在 time_t 与卡上时间字段之间用 gmtime/timegm 互转，这里保持一致，
    所以卡上存的是什么数字，PSU 里就是什么数字。
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
        raise ValueError("名字超过 31 字节: %r" % (name,))
    b = bytearray(ENTRY_SIZE)
    struct.pack_into("<II", b, 0, mode, size)
    b[8:16] = created
    b[24:32] = modified
    struct.pack_into("<I", b, 32, attr)
    b[64:64 + len(name)] = name
    return bytes(b)


def write_psu(save, fp):
    """把一个 foldercard.Save 写成 PSU。"""
    n_entries = len(save.files) + 2  # 含 "." 和 ".."
    fp.write(pack_entry(save.mode, n_entries, save.created, save.modified,
                        save.name, save.attr))
    fp.write(pack_entry(DEFAULT_DIR_MODE, 0, save.created, save.modified, b"."))
    fp.write(pack_entry(DEFAULT_DIR_MODE, 0, save.created, save.modified, b".."))

    for f in save.files:
        with open(f.host_path, "rb") as src:
            data = src.read()
        fp.write(pack_entry(f.mode, len(data), f.created, f.modified, f.name, f.attr))
        if data:
            fp.write(data)
            pad = (-len(data)) % ALIGN
            if pad:
                fp.write(b"\0" * pad)


_WIN_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(name):
    s = _WIN_BAD.sub("_", name).rstrip(" .")
    return s or "save"


def export_save(save, out_dir):
    import os
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, safe_filename(save.display_name) + ".psu")
    with open(out_path, "wb") as fp:
        write_psu(save, fp)
    return out_path
