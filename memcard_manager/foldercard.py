"""读取 PCSX2 的文件夹卡。

读取方式与 PCSX2 自己加载文件夹卡时一致：

* 每个存档目录里的 ``_pcsx2_index`` (YAML) 提供文件顺序与时间戳
* ``_pcsx2_meta/<文件名>`` 是 512 字节的原始目录项，保存真实文件名、mode、attr
  （PCSX2 会把 Windows 不允许的字符换成 ``_``，真名只存在这里）
* ``_pcsx2_meta_directory`` 是存档目录自身的原始目录项

没有这些元数据文件（例如从实机拷出来的普通存档文件夹）时，
退回到使用文件系统时间与默认 mode。
"""

import os
import struct

from . import iconsys
from .i18n import tr
from .ps2dirent import (DEFAULT_DIR_MODE, DEFAULT_FILE_MODE, ENTRY_SIZE,
                  format_time, pack_time)
from .yamlmini import parse_index

META_PREFIX = "_pcsx2_"
CLUSTER = 1024  # PS2 记忆卡簇大小


def read_meta_entry(path):
    """读 _pcsx2_meta / _pcsx2_meta_directory。不足 0x60 字节视为无效（与 PCSX2 相同）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read(ENTRY_SIZE)
    except OSError:
        return None
    if len(raw) < 0x60:
        return None
    raw = raw.ljust(ENTRY_SIZE, b"\0")
    mode = struct.unpack_from("<I", raw, 0)[0]
    attr = struct.unpack_from("<I", raw, 32)[0]
    name = raw[64:96].split(b"\0", 1)[0]
    return {
        "mode": mode,
        "created": raw[8:16],
        "modified": raw[24:32],
        "attr": attr,
        "name": name,
    }


class SaveFile:
    def __init__(self, host_path, name, size, mode, attr, created, modified):
        self.host_path = host_path
        self.name = name            # bytes，真实文件名
        self.size = size
        self.mode = mode
        self.attr = attr
        self.created = created      # 8 bytes
        self.modified = modified    # 8 bytes


class Save:
    def __init__(self, host_dir, host_name, name, mode, attr, created, modified, files):
        self.host_dir = host_dir
        self.host_name = host_name
        self.name = name            # bytes，真实目录名
        self.mode = mode
        self.attr = attr
        self.created = created
        self.modified = modified
        self.files = files

    @property
    def display_name(self):
        return self.name.decode("utf-8", "replace")

    @property
    def total_size(self):
        """文件内容字节数合计。"""
        return sum(f.size for f in self.files)

    @property
    def card_size(self):
        """在记忆卡上占用的字节数（与 mymc 的 Size 列一致）。

        每个文件按 1KB 簇向上取整，再加上目录项（含 "." 和 ".."，每项 512 字节）
        按簇向上取整。
        """
        data = sum(-(-f.size // CLUSTER) * CLUSTER for f in self.files)
        dirents = -(-((len(self.files) + 2) * ENTRY_SIZE) // CLUSTER) * CLUSTER
        return data + dirents

    @property
    def modified_str(self):
        return format_time(self.modified)

    @property
    def description(self):
        """icon.sys 里的标题；没有或不合法时为空。"""
        for f in self.files:
            if f.name.lower() == b"icon.sys":
                try:
                    with open(f.host_path, "rb") as fp:
                        return iconsys.description(fp.read(iconsys.ICON_SYS_SIZE))
                except OSError:
                    return ""
        return ""


def _host_name_bytes(name):
    return name.encode("utf-8")


def read_save(card_dir, host_name):
    save_dir = os.path.join(card_dir, host_name)
    index = parse_index(os.path.join(save_dir, "_pcsx2_index"))
    root = index.get("$ROOT") or index.get("%ROOT") or {}
    if not isinstance(root, dict):
        root = {}

    dir_meta = read_meta_entry(os.path.join(save_dir, "_pcsx2_meta_directory"))
    st_dir = os.stat(save_dir)

    if dir_meta:
        d_mode, d_attr = dir_meta["mode"], dir_meta["attr"]
        d_name = dir_meta["name"] or _host_name_bytes(host_name)
        d_created, d_modified = dir_meta["created"], dir_meta["modified"]
    else:
        d_mode, d_attr = DEFAULT_DIR_MODE, 0
        d_name = _host_name_bytes(host_name)
        d_created = pack_time(root.get("timeCreated", st_dir.st_mtime))
        d_modified = pack_time(root.get("timeModified", st_dir.st_mtime))

    legacy, indexed = [], []
    for fname in os.listdir(save_dir):
        if fname.startswith(META_PREFIX):
            continue
        fpath = os.path.join(save_dir, fname)
        if not os.path.isfile(fpath):
            continue  # PS2 存档里没有子目录，忽略
        st = os.stat(fpath)
        node = index.get(fname)
        node_d = node if isinstance(node, dict) else {}
        meta = read_meta_entry(os.path.join(save_dir, "_pcsx2_meta", fname))

        if meta:
            mode, attr = meta["mode"], meta["attr"]
            name = meta["name"] or _host_name_bytes(fname)
            created, modified = meta["created"], meta["modified"]
        else:
            mode, attr = DEFAULT_FILE_MODE, 0
            name = _host_name_bytes(fname)
            created = pack_time(node_d.get("timeCreated", st.st_mtime))
            modified = pack_time(node_d.get("timeModified", st.st_mtime))

        sf = SaveFile(fpath, name, st.st_size, mode, attr, created, modified)
        if isinstance(node_d.get("order"), int):
            indexed.append((node_d["order"], fname, sf))
        else:
            legacy.append((fname, sf))

    # 没有 index 的文件排在前面（与 PCSX2 对旧版文件夹卡的处理一致）
    legacy.sort(key=lambda x: (x[0].lower(), x[0]))
    indexed.sort(key=lambda x: (x[0], x[1]))
    files = [sf for _, sf in legacy] + [sf for _, _, sf in indexed]
    return Save(save_dir, host_name, d_name, d_mode, d_attr, d_created, d_modified, files)


def list_saves(card_dir):
    if not os.path.isdir(card_dir):
        raise FileNotFoundError(tr("找不到文件夹: %s", card_dir))
    saves = []
    for host_name in sorted(os.listdir(card_dir)):
        p = os.path.join(card_dir, host_name)
        if host_name.startswith(META_PREFIX) or not os.path.isdir(p):
            continue
        saves.append(read_save(card_dir, host_name))
    return saves


def looks_like_folder_card(card_dir):
    return os.path.isfile(os.path.join(card_dir, "_pcsx2_superblock"))
