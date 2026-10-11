"""两种记忆卡的统一接口：

* FolderCard —— PCSX2 的文件夹卡（一个文件夹）
* ImageCard  —— 记忆卡镜像文件：PCSX2 的 .ps2、PS3 的 .vm2（未加密）、.mcd / .bin 等，
  通过 mymcplusplus 读写；带不带 ECC 都可以

存档在两者之间用 (目录 Entry, [文件 Entry]) 传递，见 saveformats.Entry。
"""

import io
import os
import shutil
import struct
from contextlib import contextmanager, redirect_stdout

from mymcplusplus import ps2mc, ps2mc_dir

from . import cardops, iconsys
from .foldercard import list_saves as _list_folder_saves
from .importer import SaveExists, write_folder_save
from .ps2dirent import ENTRY_SIZE, format_time
from .saveformats import folder_entries, from_save_file, to_save_file, write_save_file

IMAGE_EXTS = ("*.ps2", "*.vm2", "*.mcd", "*.mc2", "*.bin")
_TOD = struct.Struct("<xBBBBBH")


def open_card(path):
    """按路径类型打开：文件夹 -> FolderCard，文件 -> ImageCard。"""
    if os.path.isdir(path):
        return FolderCard(path)
    if os.path.isfile(path):
        return ImageCard(path)
    raise FileNotFoundError("找不到记忆卡: %s" % path)


class FolderCard:
    kind = "folder"
    kind_label = "文件夹卡"

    def __init__(self, path):
        self.path = path
        self.free = None    # 文件夹卡没有固定容量（PCSX2 会按游戏筛选存档）

    def list_saves(self):
        return _list_folder_saves(self.path)

    def read(self, save):
        return folder_entries(save)

    def write(self, root, files, overwrite=False, recycle=True):
        def remove(path):
            cardops.delete_save(os.path.dirname(path), os.path.basename(path), recycle)
        return write_folder_save(root, files, self.path, overwrite, remove)

    def delete(self, save, recycle=True):
        cardops.delete_save(self.path, save.host_name, recycle)

    def copy_from(self, src, save, overwrite=False, recycle=True):
        if isinstance(src, FolderCard):
            # 文件夹卡之间整个目录原样复制，PCSX2 的元数据一个不丢
            return cardops.copy_save(src.path, save.host_name, self.path, overwrite, recycle)
        root, files = src.read(save)
        return self.write(root, files, overwrite, recycle)

    def export(self, save, out_dir, fmt):
        root, files = self.read(save)
        return write_save_file(root, files, out_dir, fmt, save.display_name)

    def digests(self, saves):
        """{存档名: 指纹}；读不了的存档（例如文件被 PCSX2 锁住）指纹为 None。"""
        out = {}
        for s in saves:
            try:
                out[s.name] = cardops.digest(s)
            except OSError:
                out[s.name] = None
        return out

    def folder_of(self, save=None):
        return save.host_dir if save else self.path


class ImageSave:
    """镜像卡里的一个存档，属性名与 foldercard.Save 一致，界面可以通用。"""

    def __init__(self, ent, card_size, description):
        self.name = ent[8]
        self.display_name = self.host_name = self.name.decode("ascii", "replace")
        self.mode = ent[0] | (ent[1] << 16)
        self.attr = ent[7]
        self.created = _TOD.pack(*ent[3])
        self.modified = _TOD.pack(*ent[6])
        self.card_size = card_size
        self.description = description
        self.host_dir = None

    @property
    def modified_str(self):
        return format_time(self.modified)


class ImageCard:
    kind = "image"
    kind_label = "镜像卡"

    def __init__(self, path):
        self.path = path
        self.free = None
        self._backed_up = False

    @property
    def backup_path(self):
        return self.path + ".bak"

    @contextmanager
    def _mc(self, write=False):
        if write and not self._backed_up:
            # 本次打开后第一次修改前，整张卡备份一份
            shutil.copy2(self.path, self.backup_path)
            self._backed_up = True
        f = open(self.path, "r+b" if write else "rb")
        mc = None
        try:
            try:
                # 判断有没有 ECC 时，MyMC++ 会打印调试信息 "corrected 1"，这里吞掉
                with redirect_stdout(io.StringIO()):
                    mc = ps2mc.ps2mc(f)
            except ps2mc.error as e:
                raise ValueError("不是可识别的 PS2 记忆卡镜像（加密的 .vme/.vm2 不支持）: %s" % e)
            yield mc
        finally:
            if mc is not None:
                try:
                    if write:
                        mc.flush()  # 出错时也把已做的修改刷回去，保持 FAT 与目录一致
                finally:
                    mc.close()
            f.close()

    @staticmethod
    def _path(save_or_name):
        name = save_or_name if isinstance(save_or_name, str) else save_or_name.display_name
        return "/" + name

    def list_saves(self):
        saves = []
        with self._mc() as mc:
            d = mc.dir_open("/")
            try:
                ents = list(d)
            finally:
                d.close()
            for ent in ents:
                if not ps2mc_dir.mode_is_dir(ent[0]) or ent[8] in (b".", b".."):
                    continue
                path = "/" + ent[8].decode("ascii", "replace")
                icon = mc.get_icon_sys(path)
                saves.append(ImageSave(ent, mc.dir_size(path),
                                       iconsys.description(icon) if icon else ""))
            self.free = mc.get_free_space()
        saves.sort(key=lambda s: s.display_name)
        return saves

    def read(self, save):
        with self._mc() as mc:
            return from_save_file(mc.export_save_file(self._path(save)))

    def write(self, root, files, overwrite=False, recycle=True):
        try:
            name = root.name.decode("ascii")
        except UnicodeDecodeError:
            raise ValueError("镜像卡只支持 ASCII 存档名: %r" % root.name)
        sf = to_save_file(root, files)
        with self._mc(write=True) as mc:
            path = self._path(name)
            exists = mc.get_mode(path) is not None
            if exists and not overwrite:
                raise SaveExists(name)
            cl = mc.cluster_size
            need = -(-(len(files) + 2) * ENTRY_SIZE // cl) * cl
            need += sum(-(-len(f.data) // cl) * cl for f in files)
            free = mc.get_free_space() + (mc.dir_size(path) if exists else 0)
            if need > free:
                raise ValueError("镜像卡空间不足：需要 %dK，可用 %dK" % (need // 1024, free // 1024))
            if exists:
                mc.rmdir(path)
            mc.import_save_file(sf, False)
        return name

    def delete(self, save, recycle=True):
        with self._mc(write=True) as mc:
            mc.rmdir(self._path(save))

    def copy_from(self, src, save, overwrite=False, recycle=True):
        if os.path.normcase(os.path.abspath(src.path)) == os.path.normcase(os.path.abspath(self.path)):
            raise ValueError("源和目标是同一张卡")
        root, files = src.read(save)
        return self.write(root, files, overwrite, recycle)

    def export(self, save, out_dir, fmt):
        root, files = self.read(save)
        return write_save_file(root, files, out_dir, fmt, save.display_name)

    def digests(self, saves):
        out = {}
        with self._mc() as mc:
            for s in saves:
                try:
                    sf = mc.export_save_file(self._path(s))
                    out[s.name] = cardops.digest_files(
                        (sf.get_file(i)[0][8], sf.get_file(i)[1]) for i in range(len(sf)))
                except (OSError, ps2mc.error):
                    out[s.name] = None  # 存档损坏等，单独标出来，不影响其他存档的对比
        return out

    def folder_of(self, save=None):
        return os.path.dirname(os.path.abspath(self.path))
