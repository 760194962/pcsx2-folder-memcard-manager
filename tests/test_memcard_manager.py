import importlib.util
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

from memcard_manager import iconsys  # noqa: E402
from memcard_manager.foldercard import list_saves, read_save  # noqa: E402
from memcard_manager.psu import (ALIGN, ENTRY_SIZE, export_save,  # noqa: E402
                                 format_time, pack_time)
from memcard_manager.yamlmini import parse_index  # noqa: E402


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


class TestIconSys(unittest.TestCase):
    def test_single_and_two_line(self):
        self.assertEqual(iconsys.description(make_icon_sys("ＩＣＯ")), "ICO")
        self.assertEqual(iconsys.description(make_icon_sys("ＧＴ４", "Ｏｎｌｉｎｅ")),
                         "GT4 Online")

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

    def test_name_too_long(self):
        s = self.saves()["BISLPM-66168SAVE"]
        s.files[0].name = b"x" * 40
        with self.assertRaises(ValueError):
            export_save(s, os.path.join(self.tmp, "o"))


@unittest.skipUnless(importlib.util.find_spec("mymcplus"),
                     "未安装 mymcplus，跳过交叉验证（pip install mymcplus）")
class TestMymcplusCrossCheck(CardTestCase):
    def mc(self, *args):
        return subprocess.run([sys.executable, "-m", "mymcplus", *args],
                              capture_output=True, text=True, check=True).stdout

    def test_import_check_and_sizes(self):
        out = os.path.join(self.tmp, "out")
        saves = self.saves()
        paths = [export_save(s, out) for s in saves.values()]
        img = os.path.join(self.tmp, "card.ps2")
        self.mc(img, "format")
        for p in paths:
            self.mc(img, "import", p)
        self.assertIn("No errors found", self.mc(img, "check"))

        # mymcplus 的 dir 里 Size 与我们的 card_size 一致
        listing = self.mc(img, "dir")
        sizes = dict(re.findall(r"^(\S+)\s+.*\n\s*(\d+)KB", listing, re.M))
        for name, s in saves.items():
            self.assertEqual(int(sizes[name]), s.card_size // 1024, name)

        # 导回 PSU 后，文件名/顺序/内容/时间戳与我们导出的一致
        for name, s in saves.items():
            back = os.path.join(self.tmp, "back")
            os.makedirs(back, exist_ok=True)
            subprocess.run([sys.executable, "-m", "mymcplus", img, "export", s.display_name],
                           cwd=back, check=True, capture_output=True)
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
