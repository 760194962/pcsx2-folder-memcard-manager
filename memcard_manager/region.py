"""根据存档目录名判断游戏的区域版本。

PS2 存档目录名的格式是 "B" + 主机区域字母 + 游戏编号 + 自定义部分，例如
BASLUS-20209JEREMY、BISLPM-66168SAVE、BCSCCS-60002GAMEDATA。

* 第 2 个字母是存档所属的主机区域：A 美、E 欧、I 日（亚洲版也是 I）、C 中国、K 韩
* 游戏编号前缀（SLUS / SLPM / SCAJ …）的后两个字母更细，能区分出亚洲版、韩版、国行（China），
  所以优先看编号，认不出来再退回区域字母
"""

import re

_NAME = re.compile(r"^B([A-Z])([A-Z]{4})-?(\d{3})\.?(\d{2})")
_SYSTEM = re.compile(r"^B([A-Z])DATA-SYSTEM$")

# 编号前缀的后两个字母 -> 版本
_BY_SERIAL = {
    "US": "USA", "UD": "USA",            # SLUS / SCUS，UD 为体验版
    "ES": "Europe", "ED": "Europe",      # SLES / SCES，ED 为体验版
    "PS": "Japan", "PM": "Japan", "PN": "Japan", "PB": "Japan",  # SLPS / SLPM / SCPS / SCPN
    "AJ": "Asia",                        # SCAJ / SLAJ，港台及东南亚
    "KA": "Korea",                       # SCKA / SLKA
    "CS": "China",                       # SCCS，中国大陆（国行）
}

# 主机区域字母 -> 版本
_BY_LETTER = {"A": "USA", "E": "Europe", "I": "Japan", "C": "China", "K": "Korea"}


def serial(dirname):
    """存档目录名里的游戏编号，如 "SLUS-20209"；认不出时返回 ""。"""
    m = _NAME.match(dirname)
    if not m:
        return ""
    return "%s-%s%s" % (m.group(2), m.group(3), m.group(4))


def region(dirname):
    """存档目录名 -> "Japan" / "USA" / "Europe" / "Asia" / "Korea" / "China"（Redump 的写法）；
    认不出时返回 ""。"""
    m = _SYSTEM.match(dirname)
    if m:
        return _BY_LETTER.get(m.group(1), "")   # 主机的系统数据，按主机区域
    m = _NAME.match(dirname)
    if m:
        r = _BY_SERIAL.get(m.group(2)[2:])
        if r:
            return r
    if len(dirname) >= 2 and dirname[0] == "B":
        return _BY_LETTER.get(dirname[1], "")
    return ""
