"""图形界面（tkinter，Windows 版 Python 自带）。

仿 Dolphin 的存储卡管理器：左右两个插槽各打开一张卡（PCSX2 Folder 卡，或 .ps2 / .vm2
等镜像卡），可以互相复制，两张卡都打开时自动对比（相同 / 不同 / 仅此卡）。
"""

import json
import os
import subprocess
import sys

from . import cardops
from .cards import IMAGE_EXTS, open_card
from .foldercard import looks_like_folder_card
from .importer import SaveExists
from .ps2dirent import unpack_time
from .saveformats import EXPORT_FORMATS, IMPORT_EXTS, read_save_file

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".pcsx2_memcard_manager.json")

COLS = ("name", "size", "modified", "desc", "cmp")
TITLES = {"name": "Directory", "size": "Size", "modified": "Modified",
          "desc": "Description", "cmp": "对比"}
WIDTHS = {"name": 175, "size": 55, "modified": 115, "desc": 230, "cmp": 55}
CMP_TEXT = {cardops.SAME: "相同", cardops.DIFF: "不同", cardops.ONLY: "仅此卡"}
CMP_ORDER = {cardops.ONLY: 0, cardops.DIFF: 1, cardops.SAME: 2}


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def open_in_explorer(path, select=False):
    if sys.platform == "win32":
        if select:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("PCSX2 Folder 记忆卡管理器")
    # 按屏幕大小决定初始尺寸，小屏幕上不要超出
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(1420, sw - 60), min(720, sh - 120)
    root.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, max((sh - h) // 2 - 30, 0)))
    root.minsize(900, 400)
    cfg = load_config()

    def busy(on):
        # MAX 的压缩/解压是纯 Python，大存档要十几秒，期间显示等待光标
        root.config(cursor="watch" if on else "")
        root.update()

    def confirm_pcsx2_closed():
        """写卡前检查 PCSX2；在运行时让用户确认。返回 False 表示取消。"""
        if not cardops.pcsx2_running():
            return True
        return messagebox.askyesno(
            "PCSX2 正在运行",
            "检测到 PCSX2 正在运行。\n\n"
            "PCSX2 运行时会占用 Folder 卡并在退出或换卡时回写，"
            "这时修改卡里的存档可能被覆盖、复制不完整，甚至损坏存档。\n\n"
            "建议先关闭 PCSX2 再操作。仍要继续吗？",
            icon="warning", default="no")

    def report(title, ok_msg, errs):
        msg = ok_msg
        if errs:
            msg += "\n\n失败:\n" + "\n".join(errs)
        (messagebox.showwarning if errs else messagebox.showinfo)(title, msg)

    class CardPane:
        def __init__(self, parent, slot):
            self.slot = slot
            self.other = None
            self.cardobj = None  # cards.FolderCard / cards.ImageCard
            self.saves = []     # iid = 下标
            self.rows = []      # 每行显示的值（不含对比列）
            self.status = {}    # 目录名 -> SAME / DIFF / ONLY
            self.sort_col, self.sort_rev = None, False
            self.path_var = tk.StringVar()

            self.frame = ttk.LabelFrame(parent, text="插槽 " + slot, padding=6)
            top = ttk.Frame(self.frame)
            top.pack(fill="x")
            ttk.Entry(top, textvariable=self.path_var).pack(side="left", fill="x", expand=True)
            ttk.Button(top, text="文件夹卡…", command=self.pick_folder).pack(side="left", padx=(6, 0))
            ttk.Button(top, text="镜像卡…", command=self.pick_image).pack(side="left", padx=(6, 0))
            ttk.Button(top, text="刷新", command=lambda: self.load()).pack(side="left", padx=(6, 0))

            box = ttk.Frame(self.frame)
            box.pack(fill="both", expand=True, pady=6)
            self.tree = ttk.Treeview(box, columns=COLS, show="headings", selectmode="extended")
            sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="left", fill="y")
            for c in COLS:
                self.tree.heading(c, text=TITLES[c], command=lambda c=c: self.sort_by(c))
                self.tree.column(c, width=WIDTHS[c], anchor="e" if c == "size" else "w",
                                 stretch=c == "desc")
            self.tree.tag_configure(cardops.ONLY, background="#e3f4e6")
            self.tree.tag_configure(cardops.DIFF, background="#fff1d6")
            self.tree.bind("<<TreeviewSelect>>", lambda e: update_buttons())
            self.tree.bind("<Double-1>", lambda e: self.open_folder())
            self.tree.bind("<Button-3>", self.context_menu)

            self.info = ttk.Label(self.frame, text="未打开")
            self.info.pack(fill="x")
            bar = ttk.Frame(self.frame)
            bar.pack(fill="x", pady=(6, 0))
            self.btn_import = ttk.Button(bar, text="导入…", command=self.do_import)
            self.btn_export = ttk.Button(bar, text="导出…", command=self.do_export)
            self.btn_delete = ttk.Button(bar, text="删除", command=self.do_delete)
            self.btn_folder = ttk.Button(bar, text="打开文件夹", command=self.open_folder)
            for b in (self.btn_import, self.btn_export, self.btn_delete, self.btn_folder):
                b.pack(side="left", padx=(0, 6))

        # ---- 读取与显示 ----
        @property
        def card(self):
            return self.path_var.get().strip()

        @property
        def loaded(self):
            return self.cardobj is not None

        def _initialdir(self):
            c = self.card
            return (c if os.path.isdir(c) else os.path.dirname(c)) or None

        def pick_folder(self):
            p = filedialog.askdirectory(title="选择插槽 %s 的 Folder 记忆卡（例如 Folder.ps2）" % self.slot,
                                        initialdir=self._initialdir())
            if p:
                self.path_var.set(os.path.normpath(p))
                self.load(warn=True)

        def pick_image(self):
            p = filedialog.askopenfilename(
                title="选择插槽 %s 的记忆卡镜像" % self.slot, initialdir=self._initialdir(),
                filetypes=[("PS2 记忆卡镜像", " ".join(IMAGE_EXTS)), ("所有文件", "*.*")])
            if p:
                self.path_var.set(os.path.normpath(p))
                self.load(warn=True)

        def load(self, warn=False, compare=True):
            path = self.card
            self.cardobj, self.saves, self.rows = None, [], []
            self.tree.delete(*self.tree.get_children())
            self.frame.config(text="插槽 " + self.slot)
            if not path:
                self.info.config(text="未打开")
                update_buttons()
                return
            try:
                card = open_card(path)
                self.saves = card.list_saves()
                self.cardobj = card
            except Exception as e:  # noqa
                self.info.config(text="读取失败: %s" % e)
                if warn:
                    messagebox.showerror("读取失败", str(e))
                if compare:
                    refresh_compare()
                update_buttons()
                return
            self.frame.config(text="插槽 %s — %s" % (self.slot, card.kind_label))
            cfg["card_" + self.slot.lower()] = path
            save_config(cfg)
            self.rows = [(s.display_name, "%dK" % (s.card_size // 1024), s.modified_str,
                          s.description) for s in self.saves]
            for i, row in enumerate(self.rows):
                self.tree.insert("", "end", iid=str(i), values=row + ("",))
            used = sum(s.card_size for s in self.saves) // 1024
            text = "%d 个存档，已用 %dK" % (len(self.saves), used)
            if card.free is not None:
                text += "，剩余 %dK" % (card.free // 1024)
            self.info.config(text=text)
            self.apply_sort()
            if warn and card.kind == "folder" and not looks_like_folder_card(path):
                messagebox.showwarning(
                    "提示", "这个文件夹里没有 _pcsx2_superblock，可能不是 Folder 卡本身。\n"
                            "应选择类似 memcards/Folder.ps2 这样的文件夹。")
            if compare:
                refresh_compare()
            update_buttons()

        def set_status(self, status):
            self.status = status
            for i, s in enumerate(self.saves):
                st = status.get(s.name)
                self.tree.set(str(i), "cmp", CMP_TEXT.get(st, ""))
                self.tree.item(str(i), tags=(st,) if st in (cardops.ONLY, cardops.DIFF) else ())
            if self.sort_col == "cmp":
                self.apply_sort()

        # ---- 排序 ----
        def sort_key(self, col):
            if col == "name":
                return lambda i: self.saves[i].display_name.lower()
            if col == "size":
                return lambda i: self.saves[i].card_size
            if col == "modified":
                return lambda i: unpack_time(self.saves[i].modified)
            if col == "desc":
                return lambda i: self.rows[i][3].lower()
            return lambda i: CMP_ORDER.get(self.status.get(self.saves[i].name), 3)

        def apply_sort(self):
            for c in COLS:
                arrow = (" ▼" if self.sort_rev else " ▲") if c == self.sort_col else ""
                self.tree.heading(c, text=TITLES[c] + arrow)
            if self.sort_col is None:
                return
            order = sorted(range(len(self.saves)), key=self.sort_key(self.sort_col),
                           reverse=self.sort_rev)
            for pos, i in enumerate(order):
                self.tree.move(str(i), "", pos)

        def sort_by(self, col):
            if self.sort_col == col:
                self.sort_rev = not self.sort_rev
            else:
                self.sort_col, self.sort_rev = col, False
            self.apply_sort()

        # ---- 操作 ----
        def selected(self):
            return [self.saves[int(i)] for i in self.tree.selection()]

        def select_names(self, names):
            iids = [str(i) for i, s in enumerate(self.saves) if s.host_name in names]
            self.tree.selection_set(iids)
            if iids:
                self.tree.see(iids[0])

        def open_folder(self):
            if not self.loaded:
                return
            if self.cardobj.kind == "image":
                open_in_explorer(self.cardobj.path, select=True)
                return
            sel = self.selected()
            path = self.cardobj.folder_of(sel[0] if sel else None)
            if path and os.path.isdir(path):
                open_in_explorer(path)

        def do_export(self):
            chosen = self.selected()
            if not chosen:
                messagebox.showinfo("提示", "请先在插槽 %s 的列表中选择存档。" % self.slot)
                return
            out = filedialog.askdirectory(title="选择导出文件夹（格式: %s）" % fmt_var.get().upper(),
                                          initialdir=cfg.get("out_dir") or None)
            if not out:
                return
            cfg["out_dir"] = out
            save_config(cfg)
            fmt = fmt_var.get()
            ok, errs = [], []
            busy(True)
            try:
                for s in chosen:
                    try:
                        ok.append(self.cardobj.export(s, out, fmt))
                    except Exception as e:  # noqa
                        errs.append("%s: %s" % (s.display_name, e))
            finally:
                busy(False)
            report("导出完成", "已导出 %d 个 %s 到:\n%s" % (len(ok), fmt.upper(), out), errs)

        def do_import(self):
            if not self.loaded:
                messagebox.showinfo("提示", "请先打开插槽 %s 的记忆卡。" % self.slot)
                return
            paths = filedialog.askopenfilenames(
                title="选择要导入到插槽 %s 的存档" % self.slot,
                initialdir=cfg.get("import_dir") or None,
                filetypes=[("PS2 存档", " ".join(IMPORT_EXTS)), ("所有文件", "*.*")])
            if not paths or not confirm_pcsx2_closed():
                return
            cfg["import_dir"] = os.path.dirname(paths[0])
            ok, errs = [], []
            busy(True)
            try:
                for p in paths:
                    try:
                        root_ent, files = read_save_file(p)
                        try:
                            ok.append(self.cardobj.write(root_ent, files))
                        except SaveExists as e:
                            busy(False)
                            if messagebox.askyesno("存档已存在", "插槽 %s 里已有存档 %s，要覆盖吗？"
                                                   % (self.slot, e)):
                                busy(True)
                                ok.append(self.cardobj.write(root_ent, files, overwrite=True))
                    except Exception as e:  # noqa
                        errs.append("%s: %s" % (os.path.basename(p), e))
            finally:
                busy(False)
            self.load()
            self.select_names(set(ok))
            report("导入完成", "已导入 %d 个存档到插槽 %s。" % (len(ok), self.slot), errs)

        def do_delete(self):
            chosen = self.selected()
            if not chosen:
                return
            names = [s.display_name for s in chosen]
            listing = "\n".join(names[:12]) + ("\n…（共 %d 个）" % len(names) if len(names) > 12 else "")
            if self.cardobj.kind == "image":
                where = "删除（首次修改前会把整张卡备份为 .bak）"
            else:
                where = "移到回收站" if cardops.can_recycle() else "永久删除（无法恢复）"
            if not messagebox.askyesno("删除存档", "要从插槽 %s %s以下存档吗？\n\n%s"
                                       % (self.slot, where, listing), icon="warning"):
                return
            if not confirm_pcsx2_closed():
                return
            errs = []
            busy(True)
            try:
                for s in chosen:
                    try:
                        self.cardobj.delete(s)
                    except Exception as e:  # noqa
                        errs.append("%s: %s" % (s.display_name, e))
            finally:
                busy(False)
            self.load()
            if errs:
                report("删除", "部分存档删除失败。", errs)

        def copy_to_other(self):
            dst = self.other
            chosen = self.selected()
            if not chosen or not dst.loaded or not confirm_pcsx2_closed():
                return
            ok, errs = [], []
            busy(True)
            try:
                for s in chosen:
                    try:
                        try:
                            ok.append(dst.cardobj.copy_from(self.cardobj, s))
                        except SaveExists:
                            busy(False)
                            if dst.cardobj.kind == "image":
                                old = "被替换（整张卡已备份为 .bak）"
                            else:
                                old = "移到回收站" if cardops.can_recycle() else "被删除"
                            if messagebox.askyesno(
                                    "存档已存在", "插槽 %s 里已有存档 %s，要覆盖吗？\n（旧存档会%s）"
                                    % (dst.slot, s.display_name, old)):
                                busy(True)
                                ok.append(dst.cardobj.copy_from(self.cardobj, s, overwrite=True))
                    except Exception as e:  # noqa
                        errs.append("%s: %s" % (s.display_name, e))
            finally:
                busy(False)
            dst.load()
            dst.select_names(set(ok))
            if errs:
                report("复制", "已复制 %d 个存档到插槽 %s。" % (len(ok), dst.slot), errs)

        def context_menu(self, event):
            iid = self.tree.identify_row(event.y)
            if iid and iid not in self.tree.selection():
                self.tree.selection_set(iid)
            has = bool(self.tree.selection())
            m = tk.Menu(self.tree, tearoff=False)
            st = "normal" if has else "disabled"
            m.add_command(label="打开存档文件夹" if self.cardobj and self.cardobj.kind == "folder"
                          else "在资源管理器中显示镜像", command=self.open_folder,
                          state=st if self.loaded else "disabled")
            m.add_command(label="复制到插槽 %s" % self.other.slot, command=self.copy_to_other,
                          state=st if self.other.loaded else "disabled")
            m.add_command(label="导出…", command=self.do_export, state=st)
            m.add_separator()
            m.add_command(label="删除", command=self.do_delete, state=st)
            m.tk_popup(event.x_root, event.y_root)

    # ---- 布局：插槽 A | 中间按钮 | 插槽 B ----
    body = ttk.Frame(root, padding=8)
    body.pack(fill="both", expand=True)
    pane_a = CardPane(body, "A")
    pane_b = CardPane(body, "B")
    pane_a.other, pane_b.other = pane_b, pane_a
    pane_a.frame.grid(row=0, column=0, sticky="nsew")
    pane_b.frame.grid(row=0, column=2, sticky="nsew")
    body.columnconfigure(0, weight=1)
    body.columnconfigure(2, weight=1)
    body.rowconfigure(0, weight=1)

    mid = ttk.Frame(body, padding=(8, 0))
    mid.grid(row=0, column=1)
    btn_a2b = ttk.Button(mid, text="复制到 B →", width=14, command=pane_a.copy_to_other)
    btn_b2a = ttk.Button(mid, text="← 复制到 A", width=14, command=pane_b.copy_to_other)
    btn_a2b.pack(pady=4)
    btn_b2a.pack(pady=4)
    ttk.Separator(mid).pack(fill="x", pady=12)
    ttk.Label(mid, text="导出格式").pack()
    fmt_var = tk.StringVar(value=cfg.get("fmt") if cfg.get("fmt") in EXPORT_FORMATS else "psu")
    fmt_box = ttk.Combobox(mid, textvariable=fmt_var, values=list(EXPORT_FORMATS),
                           state="readonly", width=6)
    fmt_box.pack(pady=4)

    def on_fmt(_e=None):
        cfg["fmt"] = fmt_var.get()
        save_config(cfg)
    fmt_box.bind("<<ComboboxSelected>>", on_fmt)

    legend = ttk.Frame(mid)
    legend.pack(pady=(16, 0))
    for st, color in ((cardops.ONLY, "#e3f4e6"), (cardops.DIFF, "#fff1d6")):
        tk.Label(legend, text=CMP_TEXT[st], bg=color, width=8).pack(pady=2)

    def refresh_compare():
        if pane_a.loaded and pane_b.loaded:
            try:
                st_a, st_b = cardops.compare(pane_a.cardobj.digests(pane_a.saves),
                                             pane_b.cardobj.digests(pane_b.saves))
            except Exception:  # noqa
                st_a, st_b = {}, {}
        else:
            st_a = st_b = {}
        pane_a.set_status(st_a)
        pane_b.set_status(st_b)

    def update_buttons():
        for p in (pane_a, pane_b):
            has = bool(p.tree.selection())
            p.btn_import.state(["!disabled"] if p.loaded else ["disabled"])
            for b in (p.btn_export, p.btn_delete):
                b.state(["!disabled"] if has else ["disabled"])
            p.btn_folder.state(["!disabled"] if p.loaded else ["disabled"])
        btn_a2b.state(["!disabled"] if pane_a.tree.selection() and pane_b.loaded else ["disabled"])
        btn_b2a.state(["!disabled"] if pane_b.tree.selection() and pane_a.loaded else ["disabled"])

    # 启动时自动打开上次用过的卡
    for p in (pane_a, pane_b):
        last = cfg.get("card_" + p.slot.lower())
        if last and os.path.exists(last):
            p.path_var.set(last)
            p.load(compare=False)
    refresh_compare()
    update_buttons()

    root.mainloop()
    return 0
