"""简易图形界面（tkinter，Windows 版 Python 自带）。"""

from .foldercard import list_saves, looks_like_folder_card
from .psu import export_save


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("PCSX2 Folder 记忆卡管理器")
    root.geometry("900x520")

    card_var = tk.StringVar()
    out_var = tk.StringVar()
    saves_cache = []

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Folder 卡文件夹:").grid(row=0, column=0, sticky="w")
    ttk.Entry(top, textvariable=card_var).grid(row=0, column=1, sticky="ew", padx=6)
    top.columnconfigure(1, weight=1)

    cols = ("name", "size", "modified", "desc")
    tree = ttk.Treeview(root, columns=cols, show="headings", selectmode="extended")
    for key, text, width, anchor in (
            ("name", "Directory", 230, "w"),
            ("size", "Size", 70, "e"),
            ("modified", "Modified", 130, "w"),
            ("desc", "Description", 420, "w")):
        tree.heading(key, text=text)
        tree.column(key, width=width, anchor=anchor)
    tree.pack(fill="both", expand=True, padx=8, pady=4)

    def load(path=None):
        path = (path or card_var.get()).strip()
        if not path:
            return
        try:
            saves = list_saves(path)
        except Exception as e:  # noqa
            messagebox.showerror("读取失败", str(e))
            return
        saves_cache[:] = saves
        tree.delete(*tree.get_children())
        for i, s in enumerate(saves):
            tree.insert("", "end", iid=str(i),
                        values=(s.display_name, "%dK" % (s.card_size // 1024),
                                s.modified_str, s.description))
        if not looks_like_folder_card(path):
            messagebox.showwarning(
                "提示", "这个文件夹里没有 _pcsx2_superblock，可能不是 Folder 卡本身。\n"
                        "应选择类似 memcards/Folder.ps2 这样的文件夹。")

    def pick_card():
        p = filedialog.askdirectory(title="选择 Folder 记忆卡文件夹（例如 Folder.ps2）")
        if p:
            card_var.set(p)
            load(p)

    def pick_out():
        p = filedialog.askdirectory(title="选择 PSU 输出文件夹")
        if p:
            out_var.set(p)

    def do_export(selected_only):
        if not saves_cache:
            messagebox.showinfo("提示", "请先选择 Folder 卡文件夹。")
            return
        if not out_var.get().strip():
            pick_out()
            if not out_var.get().strip():
                return
        if selected_only:
            chosen = [saves_cache[int(i)] for i in tree.selection()]
            if not chosen:
                messagebox.showinfo("提示", "请先在列表中选择存档。")
                return
        else:
            chosen = list(saves_cache)
        ok, errs = [], []
        for s in chosen:
            try:
                ok.append(export_save(s, out_var.get().strip()))
            except Exception as e:  # noqa
                errs.append("%s: %s" % (s.display_name, e))
        msg = "已导出 %d 个 PSU 到:\n%s" % (len(ok), out_var.get().strip())
        if errs:
            msg += "\n\n失败:\n" + "\n".join(errs)
        messagebox.showinfo("完成", msg)

    ttk.Button(top, text="浏览…", command=pick_card).grid(row=0, column=2)
    ttk.Button(top, text="读取", command=load).grid(row=0, column=3, padx=(6, 0))

    bottom = ttk.Frame(root, padding=8)
    bottom.pack(fill="x")
    ttk.Label(bottom, text="输出文件夹:").grid(row=0, column=0, sticky="w")
    ttk.Entry(bottom, textvariable=out_var).grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Button(bottom, text="浏览…", command=pick_out).grid(row=0, column=2)
    bottom.columnconfigure(1, weight=1)
    btns = ttk.Frame(root, padding=(8, 0, 8, 8))
    btns.pack(fill="x")
    ttk.Button(btns, text="导出所选", command=lambda: do_export(True)).pack(side="right")
    ttk.Button(btns, text="导出全部", command=lambda: do_export(False)).pack(side="right", padx=6)

    root.mainloop()
    return 0
