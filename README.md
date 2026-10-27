# PCSX2 Memcard Manager

Unofficial tool to browse **PCSX2 Folder memory cards** and **memory card images** (PCSX2 `.ps2`, PS3 `.vm2`, …), copy saves between them, and import/export saves (`.psu`, `.max`, …).

非官方工具：直接浏览 PCSX2 **文件夹卡**（Folder 记忆卡）和**记忆卡镜像**（PCSX2 的 `.ps2`、PS3 的 `.vm2` 等），在卡之间复制存档，导入/导出 `.psu`、`.max` 等存档文件。

Save file formats and card images are handled by [MyMC++](https://github.com/Adubbz/mymcplusplus) (`mymcplusplus`, the mymc version recommended by the PCSX2 docs); this tool adds the Folder card side and the dual-slot UI.
存档文件格式和镜像卡读写交给 MyMC++，本工具负责文件夹卡和双插槽界面。

## Card types / 支持的卡

| Type | Notes |
|---|---|
| PCSX2 Folder card (a directory) | Reads/writes PCSX2's `_pcsx2_*` metadata like PCSX2 does |
| Card image `.ps2` `.vm2` `.mcd` `.mc2` `.bin` | 8 MB standard PS2 card, with or without ECC. PS3 internal `.vm2` files (`dev_hdd0/savedata/vmc`) are unencrypted and work as-is; encrypted `.vme` / exported cards do not |

Before the first change to an image in a session, the whole image is backed up to `<file>.bak`.
镜像卡在本次打开后第一次修改前，会整张备份为 `<文件名>.bak`。

## Features / 功能

- List saves with **Directory / Size / Modified / Description**, the same columns as mymc
  - Description is read from `icon.sys` (Shift-JIS title; Chinese-region games that store a GBK title in the reserved area are supported too)
  - Size is the space used on a memory card (1 KB clusters), matching mymc
- **Export** one, several or all saves as `.psu` or `.max`
- **Import** `.psu` `.max` `.cbs` `.sps` `.xps` `.psv` (PS2 saves only) into a Folder card; the format is detected from the file content
  - Writes the same `_pcsx2_index` / `_pcsx2_meta` files PCSX2 does, so names, order and timestamps survive a PSU round trip
  - `.max` has no timestamps or mode flags; imports use the current time and default modes
- Reads PCSX2 metadata the same way PCSX2 does:
  - `_pcsx2_index`: file order and timestamps
  - `_pcsx2_meta/`: original file names (PCSX2 replaces `\ % : | " < >` and trailing dots/spaces with `_` on disk), mode and attribute flags
  - `_pcsx2_meta_directory`: the save directory's own entry
- Plain save folders without any `_pcsx2_*` files (e.g. copied off a real PS2 with uLaunchELF) also work; file timestamps are used instead

## Usage / 用法

Requires Python 3.8+, MyMC++ and numpy (numpy is only needed for the icon preview):

```
pip install mymcplusplus numpy
```

**GUI / 图形界面** — on Windows double-click `Run.bat` (finds Python, installs `mymcplusplus` and `numpy` if missing, then opens the GUI). Or double-click `run_gui.pyw`, or:

```
python -m memcard_manager
```

Two slots side by side, like Dolphin's memory card manager. In each slot click **Folder card…** and pick a Folder card directory (e.g. `.../PCSX2/memcards/Folder.ps2`, the one containing `_pcsx2_superblock`), or **Card image…** and pick a `.ps2` / `.vm2` file. The last opened cards are reopened on start.
左右两个插槽，仿 Dolphin 的存储卡管理器；每个插槽可以打开文件夹卡或镜像卡，启动时自动打开上次用过的卡。

- **Language / 语言**: English or Chinese, picked from the system language (Chinese if either the Windows display language or the region format is Chinese). Change it in the 语言 / Language menu; it applies after a restart
  界面有中文和英文，默认跟随系统；可以在“语言 / Language”菜单里切换，重启后生效
- **Compare / 对比**: with both slots open, each save is marked Same / Different / Only here, compared by file names, order and content (works across card types, e.g. Folder card vs `.vm2`)
- **Copy / 复制**: Copy to B → / ← Copy to A copies the selected saves as-is, including PCSX2 metadata
- **Import / Export / Delete / Open folder** per slot (buttons under each list, or right-click)
- On Folder cards, delete moves saves to the Recycle Bin on Windows; overwriting on copy does the same with the old save. On images, see the `.bak` backup above
- Copying into an image checks free space first, so a save that doesn't fit is rejected without touching the image
- Click a column header to sort, again to reverse
- **Icon preview / 图标预览**: select a save to see its animated 3D icon under the list, with the save's own background colours and lighting from `icon.sys`; it slowly spins, drag it to turn it. Rendered on the CPU with numpy. Animation speed (60 frames/s × the icon's `anim_speed`), spin (30°/s), colours and background were calibrated against recordings of the real PS2 BIOS browser; MyMC++ plays icons at a fixed 8 frames/s and the original mymc ignores `anim_speed`
- Before writing to a card, the tool checks whether PCSX2 is running and asks first

**Command line / 命令行**

```
# list saves
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2"

# export everything as PSU
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2" -o out --all

# export specific saves as MAX
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2" -o out -f max -s BASLUS-20500RDR -s BASLUS-20873SH4

# import saves into the card (close PCSX2 first); --force overwrites existing saves
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2" -i a.psu -i b.max -i c.psv

# the card can also be an image: list / export / import work the same
python -m memcard_manager "D:\PS3\vmc\PS2 Internal Memory Card 1.VM2" -o out --all
```

Or install it: `pip install .` then use `pcsx2-memcard` / `pcsx2-memcard-gui`.

`.max` compression/decompression is pure Python (MyMC++'s LZARI), roughly 10 s per MB.

## Tests / 测试

```
python -m unittest discover -s tests -v
```

Tests build a synthetic Folder card, round-trip saves through PSU / MAX / PSV, and cross-check with MyMC++: the exported PSUs are imported into a `.ps2` image, `check`ed, the Size column compared, and exported back to verify names, order, content and timestamps.

## Not yet / 暂未支持

- Long names: PS2 names are limited to 31 bytes; longer ones fail to export with an error
- PS1 saves in `.psv`

## Format notes / 格式说明

Folder card layout was checked against PCSX2's `pcsx2/SIO/Memcard/MemoryCardFolder.cpp`.

## License

GPL-3.0-or-later, because it builds on MyMC++ (GPL-3). See [LICENSE](LICENSE).

## Disclaimer

Not affiliated with the PCSX2 project. Back up your memory card folder before use; importing writes into the card folder (and `--force` / the overwrite prompt replaces a save), so close PCSX2 first.
