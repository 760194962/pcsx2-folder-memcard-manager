"""存档文件格式交给 mymcplusplus（MyMC++）处理，这里只负责和 Folder 卡之间的转换。

导入：PSU / MAX / CBS / SPS / XPS / PSV（按文件内容自动识别）
导出：PSU / MAX
"""

import os
import struct
import sys

from mymcplusplus import ps2mc_dir
from mymcplusplus.save import format_ems, format_max_drive, ps2save

from . import iconsys
from .ps2dirent import safe_filename

EXPORT_FORMATS = {"psu": format_ems, "max": format_max_drive}
IMPORT_EXTS = ("*.psu", "*.max", "*.cbs", "*.sps", "*.xps", "*.psv")

_TOD = struct.Struct("<xBBBBBH")  # 与 ps2mc_dir 的 ToD 布局相同


class Entry:
    """一个目录项。时间戳是卡上的 8 字节原样数据，mode 是完整的 32 位。"""

    def __init__(self, mode, size, created, modified, attr, name, data=b""):
        self.mode = mode
        self.size = size
        self.created = created
        self.modified = modified
        self.attr = attr
        self.name = name
        self.data = data


def _from_mymc(ent, data=b""):
    # mymcplusplus 把 32 位 mode 拆成两个 16 位字段（ent[0], ent[1]）
    return Entry(ent[0] | (ent[1] << 16), ent[2], _TOD.pack(*ent[3]), _TOD.pack(*ent[6]),
                 ent[7], ent[8], data)


def _to_mymc(mode, size, created, modified, attr, name):
    if len(name) > 31:
        raise ValueError("名字超过 31 字节: %r" % (name,))
    return [mode & 0xFFFF, mode >> 16, size, _TOD.unpack(created),
            0, 0, _TOD.unpack(modified), attr, name]


class _IconTitle:
    def __init__(self, title):
        self.title = title

    def get_title(self, _encoding):
        return self.title, ""


class _FolderSave(ps2save.PS2SaveFile):
    """mymcplusplus 写 MAX 时会把 icon.sys 标题强制编码成 ASCII，日文标题会出错；
    这里改用我们自己解析出的标题，去掉非 ASCII 字符。"""

    def __init__(self, title):
        super().__init__()
        self._title = title

    def get_icon_sys(self):
        return _IconTitle(self._title)


def _ensure_stderr():
    # mymcplusplus 压缩/解压 MAX 时往 stderr 写进度；pythonw 启动时 stderr 是 None
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def to_save_file(root, files):
    """(目录 Entry, [文件 Entry]) -> mymcplusplus 的 PS2SaveFile。"""
    title = ""
    for f in files:
        if f.name.lower() == b"icon.sys":
            title = iconsys.description(f.data)
    sf = _FolderSave(title.encode("ascii", "ignore").decode("ascii")[:31])
    sf.set_directory(_to_mymc(root.mode, len(files), root.created, root.modified,
                              root.attr, root.name))
    for i, f in enumerate(files):
        sf.set_file(i, _to_mymc(f.mode, len(f.data), f.created, f.modified, f.attr, f.name),
                    f.data)
    return sf


def from_save_file(sf):
    """mymcplusplus 的 PS2SaveFile -> (目录 Entry, [文件 Entry])。"""
    files = [_from_mymc(*sf.get_file(i)) for i in range(len(sf))]
    root = _from_mymc(sf.get_directory())
    root.size = len(files) + 2  # 卡上目录项的大小包含 "." 和 ".."
    for f in files:
        if not ps2mc_dir.mode_is_file(f.mode & 0xFFFF):
            raise ValueError("存档里含有子目录，不支持: %s" % f.name.decode("utf-8", "replace"))
    return root, files


def folder_entries(save):
    """foldercard.Save -> (目录 Entry, [文件 Entry])，读出文件内容。"""
    files = []
    for f in save.files:
        with open(f.host_path, "rb") as fp:
            data = fp.read()
        files.append(Entry(f.mode, len(data), f.created, f.modified, f.attr, f.name, data))
    root = Entry(save.mode, len(files) + 2, save.created, save.modified, save.attr, save.name)
    return root, files


def write_save_file(root, files, out_dir, fmt="psu", basename=None):
    """把 (目录 Entry, [文件 Entry]) 写成 fmt（psu / max），返回输出文件路径。"""
    if fmt not in EXPORT_FORMATS:
        raise ValueError("不支持的导出格式: %s" % fmt)
    sf = to_save_file(root, files)
    _ensure_stderr()
    os.makedirs(out_dir, exist_ok=True)
    name = basename or root.name.decode("utf-8", "replace")
    out_path = os.path.join(out_dir, safe_filename(name) + "." + fmt)
    with open(out_path, "wb") as fp:
        EXPORT_FORMATS[fmt].save(sf, fp)
    return out_path


def export_save(save, out_dir, fmt="psu"):
    """把 foldercard.Save 导出成 fmt（psu / max），返回输出文件路径。"""
    root, files = folder_entries(save)
    return write_save_file(root, files, out_dir, fmt, save.display_name)


def read_save_file(path):
    """读一个存档文件，返回 (目录 Entry, [文件 Entry])。格式不对时抛 ValueError。"""
    _ensure_stderr()
    with open(path, "rb") as fp:
        fmt = ps2save.poll_format(fp)
        if fmt is None:
            raise ValueError("无法识别的存档格式")
        fp.seek(0)
        sf = ps2save.PS2SaveFile()
        try:
            fmt.load(sf, fp)
            return from_save_file(sf)
        except (ps2save.Error, struct.error, EOFError) as e:
            raise ValueError(str(e)) from e
