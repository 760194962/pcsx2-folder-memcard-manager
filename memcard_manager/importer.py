"""把存档文件（PSU / MAX / CBS / SPS / XPS / PSV）导入文件夹卡。

写出的布局与 PCSX2 自己保存时一致：存档目录里放文件本体，另外有
``_pcsx2_index``（文件顺序与时间戳）、``_pcsx2_meta/<文件名>``（原始目录项）
和 ``_pcsx2_meta_directory``。
"""

import calendar
import os
import re
import shutil

from .foldercard import META_PREFIX
from .i18n import tr
from .ps2dirent import pack_entry, unpack_time
from .saveformats import read_save_file

_HOST_BAD = re.compile(r'[\\/:*?"<>|%\x00-\x1f]')
_YAML_PLAIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


class SaveExists(Exception):
    """目标存档已存在。"""


def _decode(name):
    try:
        return name.decode("utf-8")
    except UnicodeDecodeError:
        return name.decode("cp932", "replace")


def host_name(name):
    """PS2 名字 -> 宿主文件系统上的名字（非法字符与结尾的点/空格换成 _）。"""
    s = _HOST_BAD.sub("_", _decode(name))
    stripped = s.rstrip(" .")
    s = stripped + "_" * (len(s) - len(stripped))
    return s or "_"


def _to_time_t(b):
    y, mo, d, h, mi, s = unpack_time(b)
    try:
        return max(calendar.timegm((y, mo, d, h, mi, s)), 0)
    except (ValueError, OverflowError):
        return 0


def _yaml_key(name):
    if _YAML_PLAIN.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def import_save(path, card_dir, overwrite=False):
    """导入一个存档文件，返回存档目录名。已存在且 overwrite=False 时抛 SaveExists。"""
    root, files = read_save_file(path)
    return write_folder_save(root, files, card_dir, overwrite)


def write_folder_save(root, files, card_dir, overwrite=False, remove_existing=shutil.rmtree):
    """把 (目录 Entry, [文件 Entry]) 写成文件夹卡里的一个存档目录，返回目录名。

    目标已存在时：overwrite=False 抛 SaveExists，否则先用 remove_existing 删掉旧目录。
    """
    save_host = host_name(root.name)
    if save_host.startswith(META_PREFIX):
        raise ValueError(tr("存档名不合法: %s", _decode(root.name)))

    seen = {}
    for f in files:
        h = host_name(f.name)
        if h.startswith(META_PREFIX):
            raise ValueError(tr("文件名不合法: %s", _decode(f.name)))
        if h.lower() in seen:
            raise ValueError(tr("清理非法字符后文件名冲突: %s / %s", seen[h.lower()], _decode(f.name)))
        seen[h.lower()] = _decode(f.name)
        f.host = h

    dest = os.path.join(card_dir, save_host)
    if os.path.exists(dest):
        if not overwrite:
            raise SaveExists(save_host)
        remove_existing(dest)
    os.makedirs(os.path.join(dest, "_pcsx2_meta"))

    def wr(path, data):
        with open(path, "wb") as fp:
            fp.write(data)

    index = ["$ROOT:", "  timeCreated: %d" % _to_time_t(root.created),
             "  timeModified: %d" % _to_time_t(root.modified)]
    for order, f in enumerate(files, 1):
        wr(os.path.join(dest, f.host), f.data)
        wr(os.path.join(dest, "_pcsx2_meta", f.host),
           pack_entry(f.mode, f.size, f.created, f.modified, f.name, f.attr))
        index += ["%s:" % _yaml_key(f.host), "  order: %d" % order,
                  "  timeCreated: %d" % _to_time_t(f.created),
                  "  timeModified: %d" % _to_time_t(f.modified)]
    wr(os.path.join(dest, "_pcsx2_meta_directory"),
       pack_entry(root.mode, root.size, root.created, root.modified, root.name, root.attr))
    with open(os.path.join(dest, "_pcsx2_index"), "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(index) + "\n")
    return save_host
