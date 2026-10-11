"""文件夹卡之间的存档操作：复制、删除、对比。"""

import hashlib
import os
import shutil
import subprocess
import sys

from .foldercard import META_PREFIX
from .importer import SaveExists

SAME, DIFF, ONLY, UNREADABLE = "same", "diff", "only", "unreadable"


def _save_path(card_dir, host_name):
    if (not host_name or host_name in (".", "..") or host_name.startswith(META_PREFIX)
            or os.sep in host_name or (os.altsep and os.altsep in host_name)):
        raise ValueError("存档名不合法: %r" % host_name)
    return os.path.abspath(os.path.join(card_dir, host_name))


def _recycle(path):
    """移到 Windows 回收站。"""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, path + "\0", None,
                         FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
                         False, None, None)
    r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if r != 0 or op.fAnyOperationsAborted:
        raise OSError("移到回收站失败（错误码 %#x）: %s" % (r, path))


def can_recycle():
    return sys.platform == "win32"


def pcsx2_running():
    """PCSX2 是否在运行。它运行时会占用并回写文件夹卡，此时改卡可能丢数据。"""
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pcsx2*", "/NH", "/FO", "CSV"],
                                 capture_output=True, text=True, errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return "pcsx2" in out.lower()
        return subprocess.run(["pgrep", "-i", "pcsx2"], capture_output=True).returncode == 0
    except OSError:
        return False


def delete_save(card_dir, host_name, recycle=True):
    """删除一个存档目录。Windows 上默认移到回收站，其他系统永久删除。"""
    path = _save_path(card_dir, host_name)
    if not os.path.isdir(path):
        raise FileNotFoundError("找不到存档: %s" % host_name)
    if recycle and can_recycle():
        _recycle(path)
    else:
        shutil.rmtree(path)


def copy_save(src_card, host_name, dst_card, overwrite=False, recycle=True):
    """把存档目录（连同 PCSX2 元数据）原样复制到另一张卡。

    目标已存在且 overwrite=False 时抛 SaveExists；覆盖时旧存档按 delete_save 处理。
    """
    src = _save_path(src_card, host_name)
    dst = _save_path(dst_card, host_name)
    if os.path.normcase(os.path.abspath(src_card)) == os.path.normcase(os.path.abspath(dst_card)):
        raise ValueError("源和目标是同一张卡")
    if os.path.exists(dst):
        if not overwrite:
            raise SaveExists(host_name)
        delete_save(dst_card, host_name, recycle)
    shutil.copytree(src, dst)
    return host_name


def digest_files(files):
    """存档内容的指纹：[(文件名 bytes, 内容 bytes)] 按顺序，不含时间戳。

    文件夹卡和镜像卡用同一个算法，所以两种卡之间也能对比。"""
    h = hashlib.sha1()
    for name, data in files:
        h.update(name + b"\0")
        h.update(len(data).to_bytes(8, "little"))
        h.update(data)
    return h.hexdigest()


def digest(save):
    """文件夹卡里一个存档的指纹。"""
    def files():
        for f in save.files:
            with open(f.host_path, "rb") as fp:
                yield f.name, fp.read()
    return digest_files(files())


def compare(digests_a, digests_b):
    """对比两张卡。参数是 {存档名: 指纹}，返回两个 {存档名: SAME/DIFF/ONLY/UNREADABLE}。

    指纹为 None 表示这个存档读不了（例如文件被 PCSX2 占用）：两边都有时标为 UNREADABLE，
    只有一边有时仍然是 ONLY。"""
    st_a, st_b = {}, {}
    for name in digests_a.keys() | digests_b.keys():
        if name not in digests_b:
            st_a[name] = ONLY
        elif name not in digests_a:
            st_b[name] = ONLY
        elif digests_a[name] is None or digests_b[name] is None:
            st_a[name] = st_b[name] = UNREADABLE
        else:
            st_a[name] = st_b[name] = SAME if digests_a[name] == digests_b[name] else DIFF
    return st_a, st_b
