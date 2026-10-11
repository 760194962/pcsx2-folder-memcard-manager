# PCSX2 Folder Memcard Manager

Unofficial tool to browse **PCSX2 Folder memory cards** and export saves as **.psu** (EMS format) — no need to convert the whole card to a `.ps2` image first.

非官方工具：直接浏览 PCSX2 **Folder 记忆卡**里的存档，并导出为 **.psu**，不用先把整张卡转换成 `.ps2` 镜像。

Pure Python standard library, no dependencies. 只用 Python 标准库，无需安装依赖。

## Features / 功能

- List saves with **Directory / Size / Modified / Description**, the same columns as mymc
  - Description is read from `icon.sys` (Shift-JIS title)
  - Size is the space used on a memory card (1 KB clusters), matching mymc
- Export one, several or all saves as `.psu`, loadable by mymc / mymc+ / uLaunchELF
- Reads PCSX2 metadata the same way PCSX2 does:
  - `_pcsx2_index`: file order and timestamps
  - `_pcsx2_meta/`: original file names (PCSX2 replaces `\ % : | " < >` and trailing dots/spaces with `_` on disk), mode and attribute flags
  - `_pcsx2_meta_directory`: the save directory's own entry
- Plain save folders without any `_pcsx2_*` files (e.g. copied off a real PS2 with uLaunchELF) also work; file timestamps are used instead

## Usage / 用法

Requires Python 3.8+.

**GUI / 图形界面** — double-click `run_gui.pyw`, or:

```
python -m memcard_manager
```

Pick the Folder card directory itself (e.g. `.../PCSX2/memcards/Folder.ps2`, the one containing `_pcsx2_superblock`), select saves, choose an output folder, then click **导出所选** (export selected) or **导出全部** (export all).

**Command line / 命令行**

```
# list saves
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2"

# export everything
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2" -o out --all

# export specific saves
python -m memcard_manager "D:\PS2\PCSX2\memcards\Folder.ps2" -o out -s BASLUS-20500RDR -s BASLUS-20873SH4
```

Or install it: `pip install .` then use `pcsx2-memcard` / `pcsx2-memcard-gui`.

## Tests / 测试

```
python -m unittest discover -s tests -v
```

Tests build a synthetic Folder card. If [mymcplus](https://pypi.org/project/mymcplus/) is installed, they also import the exported PSUs into a `.ps2` image, run `check`, compare the Size column, and export them back to verify names, order, content and timestamps.

## Not yet / 暂未支持

- Icon preview (`.ico` files are 3D models)
- Importing `.psu` into a Folder card
- Long names: PS2 names are limited to 31 bytes; longer ones fail to export with an error

## Format notes / 格式说明

Folder card layout was checked against PCSX2's `pcsx2/SIO/Memcard/MemoryCardFolder.cpp`. A PSU file is a sequence of 512-byte PS2 directory entries (the directory, `.`, `..`, then one per file), each file entry followed by its data padded to 1024 bytes.

## Disclaimer

Not affiliated with the PCSX2 project. Back up your memory card folder before use; this tool only reads it.
