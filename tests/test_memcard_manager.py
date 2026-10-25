import importlib.util
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mymcplusplus import ps2mc  # noqa: E402

from memcard_manager import cardops, iconsys  # noqa: E402
from memcard_manager.cards import FolderCard, ImageCard, open_card  # noqa: E402
from memcard_manager.saveformats import read_save_file  # noqa: E402
from memcard_manager.foldercard import list_saves, read_save  # noqa: E402
from memcard_manager.importer import SaveExists, import_save  # noqa: E402
from memcard_manager.importer import host_name  # noqa: E402
from memcard_manager.ps2dirent import ENTRY_SIZE, format_time, pack_time  # noqa: E402
from memcard_manager.saveformats import export_save  # noqa: E402
from memcard_manager.yamlmini import parse_index  # noqa: E402

ALIGN = 1024  # PSU 里文件内容按 1KB 对齐


def wr(path, data):
    mode = "w" if isinstance(data, str) else "wb"
    with open(path, mode) as f:
        f.write(data)


def make_meta(mode, name, attr=0, created=(0, 5, 4, 3, 2, 1, 2025),
              modified=(0, 9, 8, 7, 6, 5, 2026)):
    b = bytearray(512)
    struct.pack_into("<II", b, 0, mode, 0)
    b[8:16] = struct.pack("<BBBBBBH", *created)
    b[24:32] = struct.pack("<BBBBBBH", *modified)
    struct.pack_into("<I", b, 32, attr)
    b[64:64 + len(name)] = name
    return bytes(b)


def make_icon_sys(line1, line2=""):
    raw1, raw2 = line1.encode("cp932"), line2.encode("cp932")
    return iconsys._STRUCT.pack(
        b"PS2D", 0, len(raw1) if raw2 else 0, 0, 0,
        *([0] * 16), *([0.0] * 12), *([0.0] * 16),
        raw1 + raw2, b"icon.ico", b"", b"", b"")


def parse_psu(path):
    with open(path, "rb") as f:
        d = f.read()
    i, out = 0, []
    while i < len(d):
        e = d[i:i + ENTRY_SIZE]
        i += ENTRY_SIZE
        mode, size = struct.unpack_from("<II", e, 0)
        name = e[64:96].split(b"\0")[0]
        body = b""
        if mode & 0x10 and size:
            body = d[i:i + size]
            i += (size + ALIGN - 1) // ALIGN * ALIGN
        out.append({"mode": mode, "size": size, "name": name, "body": body,
                    "created": e[8:16], "modified": e[24:32]})
    return out


class CardTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.card = os.path.join(self.tmp, "Folder.ps2")
        os.makedirs(self.card)
        wr(os.path.join(self.card, "_pcsx2_superblock"), b"\0" * 512)
        rnd = random.Random(1)
        self.rnd = rnd

        # A: PCSX2 风格，block YAML + meta（被清理的文件名、空文件、非对齐文件）
        a = os.path.join(self.card, "BASLUS-20209JEREMY")
        os.makedirs(os.path.join(a, "_pcsx2_meta"))
        self.icon_a = make_icon_sys("ＩＣＯ")
        wr(os.path.join(a, "icon.sys"), self.icon_a)
        self.ico_a = rnd.randbytes(5000)
        wr(os.path.join(a, "ICON.ico"), self.ico_a)
        wr(os.path.join(a, "empty.bin"), b"")
        self.sav_a = rnd.randbytes(2048)
        wr(os.path.join(a, "data_1_2.sav"), self.sav_a)  # 真名 data:1|2.sav
        wr(os.path.join(a, "_pcsx2_meta", "data_1_2.sav"), 
            make_meta(0x8497, b"data:1|2.sav"))
        wr(os.path.join(a, "_pcsx2_meta_directory"), 
            make_meta(0x8427, b"BASLUS-20209JEREMY"))
        wr(os.path.join(a, "_pcsx2_index"), 
            "$ROOT:\n  timeCreated: 1700000000\n  timeModified: 1700001000\n"
            "icon.sys:\n  order: 1\n  timeCreated: 1700000100\n  timeModified: 1700000200\n"
            "ICON.ico:\n  order: 2\n  timeCreated: 1700000100\n  timeModified: 1700000200\n"
            "empty.bin:\n  order: 4\n  timeCreated: 1700000300\n  timeModified: 1700000400\n"
            "data_1_2.sav:\n  order: 3\n  timeCreated: 1700000500\n  timeModified: 1700000600\n")

        # B: flow 风格 index，无 meta，两行标题
        b = os.path.join(self.card, "BASCUS-97436GAMEDATA")
        os.makedirs(b)
        wr(os.path.join(b, "icon.sys"), make_icon_sys("ＧＴ４", "Ｏｎｌｉｎｅ"))
        wr(os.path.join(b, "GAME.DAT"), rnd.randbytes(1024))
        wr(os.path.join(b, "_pcsx2_index"), 
            "{$ROOT: {timeCreated: 1690000000, timeModified: 1690000500}, "
            "icon.sys: {order: 1, timeCreated: 1690000010, timeModified: 1690000020}, "
            "GAME.DAT: {order: 2, timeCreated: 1690000030, timeModified: 1690000040}}")

        # C: 实机拷出来的普通文件夹，没有任何 _pcsx2_ 文件，icon.sys 非法
        c = os.path.join(self.card, "BISLPM-66168SAVE")
        os.makedirs(c)
        wr(os.path.join(c, "icon.sys"), rnd.randbytes(964))
        wr(os.path.join(c, "SAVE.BIN"), rnd.randbytes(33333))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def saves(self):
        return {s.host_name: s for s in list_saves(self.card)}


class TestYaml(unittest.TestCase):
    def _parse(self, text):
        p = os.path.join(tempfile.mkdtemp(), "i")
        wr(p, text)
        return parse_index(p)

    def test_quoted_keys_and_percent_root(self):
        r = self._parse("%ROOT:\n  timeCreated: 5\n  timeModified: 6\n"
                        "'my file.dat':\n  order: 2\n"
                        "\"a b\": {order: 1, timeCreated: 1}\n")
        self.assertEqual(r["%ROOT"]["timeModified"], 6)
        self.assertEqual(r["my file.dat"]["order"], 2)
        self.assertEqual(r["a b"]["timeCreated"], 1)

    def test_empty_and_missing(self):
        self.assertEqual(self._parse(""), {})
        self.assertEqual(parse_index("/nonexistent/_pcsx2_index"), {})


def make_ico(shapes, color=(255, 0, 0), texture=None, frames=(), anim_speed=1.0):
    """拼一个最小的 PS2 图标：一个三角形，shapes 是每个变形形状的 3 个顶点坐标。

    frames: [(shape_id, [(time, value), ...])]，用来做变形动画。"""
    tex_type = 0x04 if texture is not None else 0
    out = struct.pack("<IIIII", 0x010000, len(shapes), tex_type, 1, 3)
    uvs = ((0, 0), (4096, 0), (0, 4096))
    for v in range(3):
        for shape in shapes:
            out += struct.pack("<hhhH", *shape[v], 0)
        # 法线朝向相机（PS2 坐标里 Z 取反）
        out += struct.pack("<hhhHhhBBBB", 0, 0, -4096, 0, *uvs[v], *color, 0x80)
    frame_length = 10 if frames else 0
    out += struct.pack("<IIfII", 1, frame_length, anim_speed, 0, len(frames))
    for shape_id, keys in frames:
        out += struct.pack("<IIII", shape_id, len(keys) + 1, 0, 0)  # 格式里存的是 关键帧数 + 1
        for t, v in keys:
            out += struct.pack("<ff", t, v)
    if texture is not None:
        out += texture
    return out


def make_icon_sys_lit(icon_name=b"icon.ico", bg=(0, 0, 0)):
    """带背景色、环境光为 1 的 icon.sys。"""
    return iconsys._STRUCT.pack(
        b"PS2D", 0, 0, 0, 0x80,              # 0x0C: bg_alpha = 0x80（不透明）
        *([bg[0], bg[1], bg[2], 0] * 4), *([0.0] * 12),
        *([0.0] * 12), 1.0, 1.0, 1.0, 1.0,
        "テスト".encode("cp932"), icon_name, b"", b"", b"")


@unittest.skipUnless(importlib.util.find_spec("numpy"), "图标预览需要 numpy")
class TestIconRender(unittest.TestCase):
    # 一个盖住画面中心的大三角形（PS2 坐标：Y 向下，模型原点在脚下，整体高约 5）
    TRI = ((-4000, -4000, 0), (12000, -4000, 0), (-4000, -16000, 0))

    def model(self, **kw):
        from memcard_manager.iconrender import IconModel
        return IconModel(make_ico([self.TRI], **kw), make_icon_sys_lit(bg=(0, 255, 0)))   # 背景色按 0-255

    def test_vertex_color_and_background(self):
        img = self.model(color=(255, 0, 0)).render(64)
        self.assertEqual(img.shape, (64, 64, 3))
        self.assertEqual(tuple(img[32, 32]), (255, 0, 0))     # 三角形：顶点颜色 × 环境光
        self.assertEqual(tuple(img[63, 63]), (0, 255, 0))     # 角落：icon.sys 背景色

    def test_backface_culled(self):
        # 转 180° 看到的是背面，被剔除，只剩背景
        img = self.model().render(64, yaw=math.pi)
        self.assertEqual(tuple(img[32, 32]), (0, 255, 0))

    def test_texture(self):
        # 128x128 的 1-5-5-5 贴图，全蓝（B=31），乘上白色顶点颜色
        tex = struct.pack("<H", 31 << 10) * (128 * 128)
        img = self.model(color=(255, 255, 255), texture=tex).render(64)
        self.assertEqual(tuple(img[32, 32]), (0, 0, 255))

    def test_morph_animation(self):
        from memcard_manager.iconrender import IconModel
        moved = tuple((x + 20000, y, z) for x, y, z in self.TRI)   # 形状 1 移出画面中心
        ico = make_ico([self.TRI, moved],
                       frames=[(0, [(0.0, 1.0), (5.0, 0.0)]), (1, [(0.0, 0.0), (5.0, 1.0)])])
        m = IconModel(ico, make_icon_sys_lit())
        self.assertTrue(m.animated)
        self.assertEqual(tuple(m.render(64, seconds=0.0)[32, 32]), (255, 0, 0))
        # 每秒 60 帧 × anim_speed 1.0：第 5 帧（5/60 秒）完全变成形状 1，中心只剩背景
        self.assertEqual(tuple(m.render(64, seconds=5 / 60)[32, 32]), (0, 0, 0))
        # 动画循环：第 10 帧回到开头
        self.assertEqual(tuple(m.render(64, seconds=10 / 60)[32, 32]), (255, 0, 0))
        # anim_speed 0.5：同样的画面要多花一倍时间
        half = IconModel(make_ico([self.TRI, moved], anim_speed=0.5,
                                  frames=[(0, [(0.0, 1.0), (5.0, 0.0)]),
                                          (1, [(0.0, 0.0), (5.0, 1.0)])]),
                         make_icon_sys_lit())
        self.assertEqual(tuple(half.render(64, seconds=10 / 60)[32, 32]), (0, 0, 0))     # 第 5 帧
        self.assertEqual(tuple(half.render(64, seconds=20 / 60)[32, 32]), (255, 0, 0))   # 第 10 帧，回到开头

    def test_bad_icons(self):
        from memcard_manager.iconrender import IconError, IconModel
        for data in (None, b"", b"garbage" * 10):
            with self.assertRaises(IconError):
                IconModel(data)

    def test_icon_file_name(self):
        self.assertEqual(iconsys.icon_file_name(make_icon_sys_lit(b"face.ico")), b"face.ico")
        self.assertIsNone(iconsys.icon_file_name(b"\0" * 964))

    def test_read_icon_folder_and_image(self):
        tmp = tempfile.mkdtemp()
        try:
            card = os.path.join(tmp, "Folder.ps2")
            d = os.path.join(card, "BASLUS-11111ICON")
            os.makedirs(d)
            wr(os.path.join(d, "icon.sys"), make_icon_sys_lit(b"Face.ICO"))
            wr(os.path.join(d, "face.ico"), make_ico([self.TRI]))   # 大小写不同也要找到
            folder = open_card(card)
            s = folder.list_saves()[0]
            isys, ico = folder.read_icon(s)
            self.assertEqual(ico, make_ico([self.TRI]))

            img_path = os.path.join(tmp, "card.ps2")
            make_image(img_path)
            img = open_card(img_path)
            img.copy_from(folder, s)
            self.assertEqual(img.read_icon(img.list_saves()[0]), (isys, ico))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestIconSys(unittest.TestCase):
    def test_single_and_two_line(self):
        self.assertEqual(iconsys.description(make_icon_sys("ＩＣＯ")), "ICO")
        self.assertEqual(iconsys.description(make_icon_sys("ＧＴ４", "Ｏｎｌｉｎｅ")),
                         "GT4 Online")

    def test_cn_reserved_area_title(self):
        # 国行游戏：标题在 0x1C4（标志 + 换行位置 + GBK 文本），0xC0 处为空
        raw = "ＧＲＡＮ　ＴＵＲＩＳＭＯ　４Ｇａｍｅ　Ｄａｔａ".encode("gb18030")
        reserved = b"\x01\x00" + (28).to_bytes(2, "little") + raw
        data = iconsys._STRUCT.pack(
            b"PS2D", 0, 0, 0, 0, *([0] * 16), *([0.0] * 12), *([0.0] * 16),
            b"", b"icon0.ico", b"", b"", reserved)
        self.assertEqual(iconsys.parse_title(data), ("GRAN TURISMO 4", "Game Data"))
        self.assertEqual(iconsys.description(data), "GRAN TURISMO 4 Game Data")

    def test_invalid(self):
        self.assertEqual(iconsys.description(b"\0" * 964), "")
        self.assertEqual(iconsys.description(b"PS2D"), "")


class TestCard(CardTestCase):
    def test_listing_fields(self):
        s = self.saves()
        self.assertEqual(set(s), {"BASLUS-20209JEREMY", "BASCUS-97436GAMEDATA",
                                  "BISLPM-66168SAVE"})
        self.assertEqual(s["BASLUS-20209JEREMY"].description, "ICO")
        self.assertEqual(s["BASCUS-97436GAMEDATA"].description, "GT4 Online")
        self.assertEqual(s["BISLPM-66168SAVE"].description, "")
        # A 有 meta_directory，时间取自它: 2026-05-06 07:08:09
        self.assertEqual(s["BASLUS-20209JEREMY"].modified_str, "2026-05-06 07:08")
        # B 没有 meta，时间取自 $ROOT.timeModified
        self.assertEqual(s["BASCUS-97436GAMEDATA"].modified_str,
                         format_time(pack_time(1690000500)))

    def test_order_and_real_names(self):
        a = read_save(self.card, "BASLUS-20209JEREMY")
        self.assertEqual([f.name for f in a.files],
                         [b"icon.sys", b"ICON.ico", b"data:1|2.sav", b"empty.bin"])

    def test_card_size_matches_mymc_formula(self):
        s = self.saves()
        # 文件 1024+5120+2048+0 = 8192，目录项 6*512=3072 -> 11264
        self.assertEqual(s["BASLUS-20209JEREMY"].card_size, 11264)
        # 1024+1024 + 4*512=2048 -> 4096
        self.assertEqual(s["BASCUS-97436GAMEDATA"].card_size, 4096)
        # 1024+33792 + 2048 -> 36864
        self.assertEqual(s["BISLPM-66168SAVE"].card_size, 36864)


class TestPsu(CardTestCase):
    def test_structure_and_content(self):
        out = os.path.join(self.tmp, "out")
        path = export_save(self.saves()["BASLUS-20209JEREMY"], out)
        self.assertTrue(path.endswith("BASLUS-20209JEREMY.psu"))
        ents = parse_psu(path)
        self.assertEqual([e["name"] for e in ents],
                         [b"BASLUS-20209JEREMY", b".", b"..", b"icon.sys", b"ICON.ico",
                          b"data:1|2.sav", b"empty.bin"])
        self.assertEqual(ents[0]["size"], 6)           # 4 个文件 + . + ..
        self.assertEqual(ents[0]["mode"], 0x8427)
        by = {e["name"]: e for e in ents}
        self.assertEqual(by[b"icon.sys"]["body"], self.icon_a)
        self.assertEqual(by[b"ICON.ico"]["body"], self.ico_a)
        self.assertEqual(by[b"data:1|2.sav"]["body"], self.sav_a)
        self.assertEqual(by[b"empty.bin"]["size"], 0)

    def test_export_existing_file(self):
        out = os.path.join(self.tmp, "out")
        s = self.saves()["BASLUS-20209JEREMY"]
        p = export_save(s, out)
        wr(p, b"keep me")
        with self.assertRaises(FileExistsError):
            export_save(s, out, overwrite=False)
        with open(p, "rb") as f:
            self.assertEqual(f.read(), b"keep me")        # 没有被改写
        export_save(s, out)                                # 默认覆盖（界面问过之后才会这样调用）
        self.assertNotEqual(os.path.getsize(p), len(b"keep me"))

    def test_name_too_long(self):
        s = self.saves()["BISLPM-66168SAVE"]
        s.files[0].name = b"x" * 40
        with self.assertRaises(ValueError):
            export_save(s, os.path.join(self.tmp, "o"))


class TestImport(CardTestCase):
    def test_roundtrip(self):
        out = os.path.join(self.tmp, "out")
        paths = [export_save(s, out) for s in self.saves().values()]
        new_card = os.path.join(self.tmp, "New.ps2")
        os.makedirs(new_card)
        for p in paths:
            import_save(p, new_card)
        old, new = self.saves(), {s.host_name: s for s in list_saves(new_card)}
        self.assertEqual(set(old), set(new))
        for name, o in old.items():
            n = new[name]
            self.assertEqual([f.name for f in o.files], [f.name for f in n.files])
            self.assertEqual([(f.mode, f.attr, f.created, f.modified) for f in o.files],
                             [(f.mode, f.attr, f.created, f.modified) for f in n.files])
            for fo, fn in zip(o.files, n.files):
                with open(fo.host_path, "rb") as a, open(fn.host_path, "rb") as b:
                    self.assertEqual(a.read(), b.read())
            self.assertEqual((o.mode, o.created, o.modified), (n.mode, n.created, n.modified))
        # 非法字符被换成 _，真名保存在 meta 里
        self.assertTrue(os.path.isfile(os.path.join(new_card, "BASLUS-20209JEREMY", "data_1_2.sav")))
        self.assertEqual(new["BASLUS-20209JEREMY"].description, "ICO")

    def test_exists_and_overwrite(self):
        out = os.path.join(self.tmp, "out")
        p = export_save(self.saves()["BISLPM-66168SAVE"], out)
        with self.assertRaises(SaveExists):
            import_save(p, self.card)
        self.assertEqual(import_save(p, self.card, overwrite=True), "BISLPM-66168SAVE")

    def test_truncated(self):
        out = os.path.join(self.tmp, "out")
        p = export_save(self.saves()["BISLPM-66168SAVE"], out)
        with open(p, "r+b") as f:
            f.truncate(2000)
        with self.assertRaises(ValueError):
            import_save(p, os.path.join(self.tmp, "x"))

    def test_max_roundtrip(self):
        # MAX 不保存时间戳和 mode，只比较文件名、顺序和内容
        out = os.path.join(self.tmp, "out")
        new_card = os.path.join(self.tmp, "New.ps2")
        os.makedirs(new_card)
        for s in self.saves().values():
            p = export_save(s, out, "max")
            self.assertTrue(p.endswith(".max"))
            import_save(p, new_card)
        old, new = self.saves(), {s.host_name: s for s in list_saves(new_card)}
        self.assertEqual(set(old), set(new))
        for name, o in old.items():
            n = new[name]
            self.assertEqual([f.name for f in o.files], [f.name for f in n.files])
            for fo, fn in zip(o.files, n.files):
                with open(fo.host_path, "rb") as a, open(fn.host_path, "rb") as b:
                    self.assertEqual(a.read(), b.read())

    def test_max_japanese_title(self):
        # mymcplusplus 自己写 MAX 时日文标题会编码失败，这里要能正常导出
        b = os.path.join(self.card, "BISLPM-66168SAVE")
        wr(os.path.join(b, "icon.sys"), make_icon_sys("ドラゴン", "クエスト"))
        export_save(self.saves()["BISLPM-66168SAVE"], os.path.join(self.tmp, "o"), "max")

    def test_psv(self):
        created = struct.pack("<BBBBBBH", 0, 1, 2, 3, 4, 5, 2007)
        modified = struct.pack("<BBBBBBH", 0, 6, 7, 8, 9, 10, 2008)
        files = [(b"icon.sys", make_icon_sys("ＰＳＶ")), (b"DATA.BIN", self.rnd.randbytes(3000))]
        hdr = struct.pack("<4sI40s8xII", b"\0VSP", 0, b"\0" * 40, 0x2C, 2)
        hdr += struct.pack("<10I", *([0] * 9 + [len(files)]))
        hdr += struct.pack("<8s8sII32s", created, modified, len(files) + 2, 0x8427, b"BASLUS-12345PSV")
        off = len(hdr) + len(files) * (56 + 4)
        body = b""
        for name, data in files:
            hdr += struct.pack("<8s8sII32s", created, modified, len(data), 0x8497, name)
            hdr += struct.pack("<I", off + len(body))
            body += data
        p = os.path.join(self.tmp, "test.psv")
        wr(p, hdr + body)

        self.assertEqual(import_save(p, self.card), "BASLUS-12345PSV")
        s = read_save(self.card, "BASLUS-12345PSV")
        self.assertEqual([(f.name, f.created, f.modified) for f in s.files],
                         [(n, created, modified) for n, _ in files])
        with open(s.files[1].host_path, "rb") as f:
            self.assertEqual(f.read(), files[1][1])
        self.assertEqual(s.description, "PSV")

    def test_unknown_format(self):
        p = os.path.join(self.tmp, "junk.psu")
        wr(p, b"x" * 4000)
        with self.assertRaises(ValueError):
            import_save(p, self.card)

    def test_host_name(self):
        self.assertEqual(host_name(b'a\\b/c:d*e?f"g<h>i|j%k'), "a_b_c_d_e_f_g_h_i_j_k")
        self.assertEqual(host_name(b"name. "), "name__")


class TestCardOps(CardTestCase):
    def setUp(self):
        super().setUp()
        self.card_b = os.path.join(self.tmp, "B.ps2")
        os.makedirs(self.card_b)
        wr(os.path.join(self.card_b, "_pcsx2_superblock"), b"\0" * 512)

    def test_copy_keeps_metadata(self):
        cardops.copy_save(self.card, "BASLUS-20209JEREMY", self.card_b)
        a = read_save(self.card, "BASLUS-20209JEREMY")
        b = read_save(self.card_b, "BASLUS-20209JEREMY")
        self.assertEqual([(f.name, f.mode, f.created, f.modified) for f in a.files],
                         [(f.name, f.mode, f.created, f.modified) for f in b.files])
        self.assertEqual(cardops.digest(a), cardops.digest(b))

    def test_copy_exists_overwrite_and_same_card(self):
        cardops.copy_save(self.card, "BISLPM-66168SAVE", self.card_b)
        with self.assertRaises(SaveExists):
            cardops.copy_save(self.card, "BISLPM-66168SAVE", self.card_b)
        wr(os.path.join(self.card, "BISLPM-66168SAVE", "SAVE.BIN"), b"new")
        cardops.copy_save(self.card, "BISLPM-66168SAVE", self.card_b, overwrite=True, recycle=False)
        with open(os.path.join(self.card_b, "BISLPM-66168SAVE", "SAVE.BIN"), "rb") as f:
            self.assertEqual(f.read(), b"new")
        with self.assertRaises(ValueError):
            cardops.copy_save(self.card, "BISLPM-66168SAVE", self.card + os.sep)

    def test_delete(self):
        cardops.delete_save(self.card, "BISLPM-66168SAVE", recycle=False)
        self.assertNotIn("BISLPM-66168SAVE", self.saves())
        with self.assertRaises(FileNotFoundError):
            cardops.delete_save(self.card, "BISLPM-66168SAVE", recycle=False)
        for bad in ("", "..", "_pcsx2_superblock", "a" + os.sep + "b"):
            with self.assertRaises(ValueError):
                cardops.delete_save(self.card, bad, recycle=False)

    def test_compare(self):
        cardops.copy_save(self.card, "BASLUS-20209JEREMY", self.card_b)
        cardops.copy_save(self.card, "BISLPM-66168SAVE", self.card_b)
        wr(os.path.join(self.card_b, "BISLPM-66168SAVE", "SAVE.BIN"), b"changed")
        os.makedirs(os.path.join(self.card_b, "BASLUS-99999ONLYB"))
        a, b = FolderCard(self.card), FolderCard(self.card_b)
        st_a, st_b = cardops.compare(a.digests(a.list_saves()), b.digests(b.list_saves()))
        self.assertEqual(st_a, {b"BASLUS-20209JEREMY": cardops.SAME,
                                b"BISLPM-66168SAVE": cardops.DIFF,
                                b"BASCUS-97436GAMEDATA": cardops.ONLY})
        self.assertEqual(st_b, {b"BASLUS-20209JEREMY": cardops.SAME,
                                b"BISLPM-66168SAVE": cardops.DIFF,
                                b"BASLUS-99999ONLYB": cardops.ONLY})


    def test_compare_unreadable(self):
        # 读不了的存档（指纹为 None）单独标出来，不影响其他存档
        st_a, st_b = cardops.compare({b"X": "1", b"Y": None, b"Z": None, b"W": "2"},
                                     {b"X": "1", b"Y": "3", b"W": "9"})
        self.assertEqual(st_a, {b"X": cardops.SAME, b"Y": cardops.UNREADABLE,
                                b"Z": cardops.ONLY, b"W": cardops.DIFF})
        self.assertEqual(st_b, {b"X": cardops.SAME, b"Y": cardops.UNREADABLE,
                                b"W": cardops.DIFF})

    @unittest.skipUnless(sys.platform == "win32", "用 Windows 的独占打开模拟 PCSX2 锁文件")
    def test_digests_locked_file(self):
        import msvcrt
        path = os.path.join(self.card, "BISLPM-66168SAVE", "SAVE.BIN")
        fd = os.open(path, os.O_RDWR)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, os.path.getsize(path))
            card = FolderCard(self.card)
            d = card.digests(card.list_saves())
        finally:
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, os.path.getsize(path))
            os.close(fd)
        self.assertIsNone(d[b"BISLPM-66168SAVE"])
        self.assertIsNotNone(d[b"BASLUS-20209JEREMY"])

def make_image(path, ecc=True):
    """用 MyMC++ 格式化一张空的 8MB 记忆卡镜像。ecc=False 相当于 PS3 以外的无 ECC 镜像。"""
    with open(path, "w+b") as f:
        ps2mc.ps2mc(f, True, (ecc, ps2mc.PS2MC_STANDARD_PAGE_SIZE,
                              ps2mc.PS2MC_STANDARD_PAGES_PER_ERASE_BLOCK,
                              ps2mc.PS2MC_STANDARD_PAGES_PER_CARD)).close()


class TestImageCard(CardTestCase):
    def setUp(self):
        super().setUp()
        self.img_path = os.path.join(self.tmp, "card.ps2")
        make_image(self.img_path)
        self.img = open_card(self.img_path)
        self.folder = open_card(self.card)

    def mc_check(self, path):
        r = subprocess.run([sys.executable, "-m", "mymcplusplus", path, "check"], env=_MC_ENV,
                           capture_output=True, encoding="utf-8", errors="replace")
        self.assertIn("No errors found", r.stdout + r.stderr)

    def test_open_card_kind(self):
        self.assertIsInstance(self.img, ImageCard)
        self.assertIsInstance(self.folder, FolderCard)
        self.assertEqual(self.img.list_saves(), [])
        self.assertEqual(self.img.free // 1024, 8134)  # 空的标准 8MB 卡

    def test_folder_to_image_and_back(self):
        saves = {s.host_name: s for s in self.folder.list_saves()}
        for s in saves.values():
            self.img.copy_from(self.folder, s)
        self.assertTrue(os.path.exists(self.img_path + ".bak"))
        self.mc_check(self.img_path)

        img_saves = {s.host_name: s for s in self.img.list_saves()}
        # 文件名含非法字符的存档在镜像里是真名，Size 与文件夹卡算法一致
        self.assertEqual(set(img_saves), set(saves))
        for name, s in saves.items():
            self.assertEqual(img_saves[name].card_size, s.card_size, name)
        self.assertEqual(img_saves["BASCUS-97436GAMEDATA"].description, "GT4 Online")
        # 两种卡之间对比：内容全部相同
        st_f, st_i = cardops.compare(self.folder.digests(saves.values()),
                                     self.img.digests(img_saves.values()))
        self.assertEqual(set(st_f.values()) | set(st_i.values()), {cardops.SAME})

        # 镜像 -> 新的文件夹卡：名字、顺序、mode、时间戳、内容都保留
        new = os.path.join(self.tmp, "New.ps2")
        os.makedirs(new)
        new_card = open_card(new)
        for s in img_saves.values():
            new_card.copy_from(self.img, s)
        for name, s in saves.items():
            n = read_save(new, name)
            self.assertEqual([(f.name, f.mode, f.created, f.modified) for f in s.files],
                             [(f.name, f.mode, f.created, f.modified) for f in n.files], name)
            self.assertEqual(cardops.digest(s), cardops.digest(n))
            self.assertEqual((s.created, s.modified), (n.created, n.modified))

    def test_exists_overwrite_delete(self):
        self.img.list_saves()
        empty_free = self.img.free
        s = self.folder.list_saves()[0]
        self.img.copy_from(self.folder, s)
        with self.assertRaises(SaveExists):
            self.img.copy_from(self.folder, s)
        self.img.copy_from(self.folder, s, overwrite=True)
        self.assertEqual(len(self.img.list_saves()), 1)
        self.img.delete(self.img.list_saves()[0])
        self.assertEqual(self.img.list_saves(), [])
        self.assertLessEqual(empty_free - self.img.free, 1024)  # 根目录可能多占一个簇
        self.mc_check(self.img_path)

    def test_no_space(self):
        big = os.path.join(self.card, "BASLUS-77777BIG")
        os.makedirs(big)
        wr(os.path.join(big, "HUGE.BIN"), b"\0" * (8200 * 1024))
        s = [x for x in self.folder.list_saves() if x.host_name == "BASLUS-77777BIG"][0]
        with self.assertRaises(ValueError):
            self.img.copy_from(self.folder, s)
        self.assertEqual(self.img.list_saves(), [])
        self.mc_check(self.img_path)

    def test_no_ecc_image_and_export_import(self):
        # PS3 的 .vm2 / 某些工具做的镜像没有 ECC
        path = os.path.join(self.tmp, "noecc.vm2")
        make_image(path, ecc=False)
        self.assertEqual(os.path.getsize(path), 8 * 1024 * 1024)
        img = open_card(path)
        s = [x for x in self.folder.list_saves() if x.host_name == "BASLUS-20209JEREMY"][0]
        img.copy_from(self.folder, s)
        self.assertEqual(os.path.getsize(path), 8 * 1024 * 1024)
        self.mc_check(path)
        out = os.path.join(self.tmp, "out")
        p = img.export(img.list_saves()[0], out, "psu")
        root, files = read_save_file(p)
        self.assertEqual([f.name for f in files], [f.name for f in s.files])
        img.write(root, files, overwrite=True)
        self.assertEqual(cardops.digest(s), img.digests(img.list_saves())[b"BASLUS-20209JEREMY"])

    def test_not_an_image(self):
        p = os.path.join(self.tmp, "junk.ps2")
        wr(p, b"\0" * 1000)
        with self.assertRaises(ValueError):
            open_card(p).list_saves()


_MC_ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


class TestMymcCrossCheck(CardTestCase):
    """用 MyMC++ 把导出的 PSU 导入 .ps2 镜像再导出，交叉验证。"""

    def mc(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-m", "mymcplusplus", *args], cwd=cwd, env=_MC_ENV,
                              capture_output=True, encoding="utf-8", errors="replace",
                              check=True).stdout

    def test_import_check_and_sizes(self):
        out = os.path.join(self.tmp, "out")
        saves = self.saves()
        paths = [export_save(s, out) for s in saves.values()]
        img = os.path.join(self.tmp, "card.ps2")
        self.mc(img, "format")
        for p in paths:
            self.mc(img, "import", p)
        self.assertIn("No errors found", self.mc(img, "check"))

        # MyMC++ 的 dir 里 Size 与我们的 card_size 一致
        listing = self.mc(img, "dir")
        sizes = dict(re.findall(r"^(\S+)\s+.*\n\s*(\d+)KB", listing, re.M))
        for name, s in saves.items():
            self.assertEqual(int(sizes[name]), s.card_size // 1024, name)

        # 导回 PSU 后，文件名/顺序/内容/时间戳与我们导出的一致
        for name, s in saves.items():
            back = os.path.join(self.tmp, "back")
            os.makedirs(back, exist_ok=True)
            self.mc(img, "export", "-o", s.display_name + ".psu", s.display_name, cwd=back)
            mine = parse_psu(os.path.join(out, name + ".psu"))
            theirs = parse_psu(os.path.join(back, s.display_name + ".psu"))
            self.assertEqual(len(mine), len(theirs))
            for m, t in zip(mine, theirs):
                self.assertEqual(m["name"], t["name"])
                self.assertEqual(m["body"], t["body"])
                if m["name"] not in (b".", b".."):
                    self.assertEqual(m["created"], t["created"])
                    self.assertEqual(m["modified"], t["modified"])


if __name__ == "__main__":
    unittest.main()
