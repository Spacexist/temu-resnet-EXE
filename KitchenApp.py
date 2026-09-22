# -*- coding: utf-8 -*-
"""模型训练便携版 UI：普通用户只通过这个入口跑日更。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import END, StringVar, Tk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

ROOT = Path(__file__).resolve().parent
PIPE = ROOT / "pipeline"
CONFIG = ROOT / "portable_config.json"
TABLE_SUFFIXES = {".csv", ".xlsx", ".xls"}
MODEL_FILES = ("lgbm_full.txt", "feature_names.json", "cat_l2_te.json", "y_cap.json", "meta.json")
RESET_DIRS = ("artifacts", "npz", "lgb")
_LOG_PROGRESS_DOWNLOAD = re.compile(r"\[download\]\s+\S+\s+(\d+)/(\d+)")
_LOG_PROGRESS_IMG = re.compile(r"\[embed\]\s+img\s+(\d+)/(\d+)")


def default_config() -> dict:
    """返回首次启动配置，所有用户数据默认写入便携包内。"""
    return {
        "data_store": "data_store",
        "last_input_dir": "",
        "last_share_html": "",
        "last_filtered_html": "",
    }


def load_config() -> dict:
    """读取便携配置；缺失或损坏时用默认值兜底。"""
    if not CONFIG.is_file():
        return default_config()
    try:
        merged = default_config()
        merged.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        return merged
    except json.JSONDecodeError:
        return default_config()


def save_config(cfg: dict) -> None:
    """保存便携配置，供下次启动复用。"""
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_data_store(raw: str) -> Path:
    """把配置里的数据目录解析成绝对路径，支持相对便携包路径。"""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def runtime_python() -> str:
    """优先使用随包 runtime，缺失时回退到当前 Python。"""
    for rel in (
        ROOT / "runtime" / "base-python" / "python.exe",
        ROOT / "runtime" / "base-python" / "Scripts" / "python.exe",
    ):
        if rel.is_file():
            return str(rel)
    return sys.executable


def ensure_dirs(data_store: Path) -> None:
    """创建用户数据目录结构。"""
    for name in (
        "raw",
        "cleaned",
        "published",
        "image_cache",
        "logs",
        "output",
        "artifacts",
        "npz",
        "lgb",
        "inbox",
        "data_cache",
    ):
        (data_store / name).mkdir(parents=True, exist_ok=True)


def day_stamp() -> str:
    """生成日志和诊断包使用的时间戳。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def fmt_mtime(path: Path) -> str:
    """把文件修改时间格式化成用户可读的分钟级时间。"""
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


class KitchenApp:
    """模型训练便携版主窗口。"""

    def __init__(self) -> None:
        self.cfg = load_config()
        self.data_store = resolve_data_store(self.cfg["data_store"])
        ensure_dirs(self.data_store)
        self.files: list[Path] = []
        self.busy = False

        self.root = Tk()
        self.root.title("模型训练")
        self.root.geometry("1320x820")
        self.root.minsize(1100, 720)

        self.status_var = StringVar(value="正在自检...")
        self.folder_var = StringVar(value=self.cfg.get("last_input_dir") or "未选择")
        self.state_var = StringVar(value="状态：未导入")
        self.model_var = StringVar(value="模型：检查中")
        self.phase_var = StringVar(value="")
        self.progress_pct_var = StringVar(value="")

        self._setup_style()
        self._build_ui()
        self._self_check()

    def _setup_style(self) -> None:
        """配置窗口主题、字体和常用控件样式。"""
        self._bg = "#F5F4F1"
        self._surface = "#FFFFFF"
        self._ink = "#1C1917"
        self._muted = "#6B6560"
        self._border = "#E8E6E1"
        self._accent = "#E85D04"
        self._accent_hover = "#C44F03"
        self.root.configure(bg=self._bg)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background=self._bg)
        style.configure("TFrame", background=self._bg)
        style.configure("Card.TFrame", background=self._surface)
        style.configure("CardTitle.TLabel", background=self._surface, foreground=self._ink, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("CardHint.TLabel", background=self._surface, foreground=self._muted, font=("Microsoft YaHei UI", 9))
        style.configure("Path.TLabel", background=self._surface, foreground=self._muted, font=("Segoe UI", 9))
        style.configure("Model.TLabel", background="#FFF4E6", foreground="#9A3412", padding=(12, 8), font=("Microsoft YaHei UI", 9))
        style.configure("Status.TLabel", background="#FFFFFF", foreground="#44403C", padding=(12, 8), font=("Microsoft YaHei UI", 9))
        style.configure("State.TLabel", background=self._bg, foreground=self._muted, font=("Microsoft YaHei UI", 9))
        style.configure("TButton", padding=(14, 8), font=("Microsoft YaHei UI", 10))
        style.configure(
            "Primary.TButton",
            font=("Microsoft YaHei UI", 10, "bold"),
            padding=(18, 10),
            background=self._accent,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", self._accent_hover), ("pressed", "#A34402")],
            foreground=[("disabled", "#F5F5F4")],
        )
        style.configure(
            "Ghost.TButton",
            padding=(12, 8),
            background=self._surface,
            foreground=self._ink,
            borderwidth=1,
            relief="solid",
        )
        style.map("Ghost.TButton", background=[("active", "#FAFAF9")])
        style.configure(
            "Treeview",
            background=self._surface,
            fieldbackground=self._surface,
            foreground=self._ink,
            rowheight=30,
            borderwidth=0,
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#F0EEEA",
            foreground="#44403C",
            font=("Microsoft YaHei UI", 9, "bold"),
            relief="flat",
            padding=(8, 6),
        )
        style.map("Treeview", background=[("selected", "#FFF4E6")], foreground=[("selected", "#9A3412")])
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#E8E6E1",
            background=self._accent,
            bordercolor="#E8E6E1",
            lightcolor=self._accent,
            darkcolor=self._accent,
            thickness=6,
        )

    def _card(self, parent, title: str, hint: str = "") -> ttk.Frame:
        """带细边框的白色卡片容器。"""
        wrap = tk.Frame(parent, bg=self._border, padx=1, pady=1)
        wrap.pack(fill="x", pady=(0, 12))
        inner = ttk.Frame(wrap, style="Card.TFrame", padding=(16, 14))
        inner.pack(fill="both", expand=True)
        head = ttk.Frame(inner, style="Card.TFrame")
        head.pack(fill="x", pady=(0, 10))
        ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side="left")
        if hint:
            ttk.Label(inner, text=hint, style="CardHint.TLabel").pack(anchor="w", pady=(0, 8))
        return inner

    def _build_ui(self) -> None:
        """搭建主流程界面。"""
        header = tk.Frame(self.root, bg="#1C1917", height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        head_inner = tk.Frame(header, bg="#1C1917")
        head_inner.pack(fill="both", expand=True, padx=22, pady=14)
        tk.Label(
            head_inner,
            text="模型训练",
            bg="#1C1917",
            fg="#FAFAF9",
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            head_inner,
            text="导入数据 → 训练预测 → 浏览器筛选 → 留货给明天模型",
            bg="#1C1917",
            fg="#A8A29E",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(4, 0))
        model_chip = tk.Frame(head_inner, bg="#292524", padx=12, pady=6)
        model_chip.place(relx=1.0, rely=0.5, anchor="e")
        tk.Label(
            model_chip,
            textvariable=self.model_var,
            bg="#292524",
            fg="#FDBA74",
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        ttk.Button(model_chip, text="清空缓存", command=self.clear_incremental_model, style="Ghost.TButton").pack(
            side="left", padx=(10, 0)
        )

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self._border, sashrelief=tk.FLAT, sashwidth=5)
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(20, 16, 12, 16))
        right = ttk.Frame(paned, padding=(4, 16, 18, 16))
        paned.add(left, minsize=560)
        paned.add(right, minsize=380)
        try:
            paned.paneconfigure(left, stretch="always")
            paned.paneconfigure(right, stretch="always")
        except tk.TclError:
            pass

        step1 = self._card(left, "① 今日数据文件夹", "选择 Downloads 或放有 Temu 导出表的目录。")
        row1 = ttk.Frame(step1, style="Card.TFrame")
        row1.pack(fill="x")
        ttk.Button(row1, text="选择文件夹", command=self.choose_folder, style="Primary.TButton").pack(side="left")
        ttk.Button(row1, text="刷新列表", command=self.scan_folder, style="Ghost.TButton").pack(side="left", padx=(8, 0))
        ttk.Label(row1, textvariable=self.folder_var, style="Path.TLabel", anchor="w").pack(
            side="left", fill="x", expand=True, padx=(14, 0)
        )

        step2 = self._card(
            left,
            "② 选择要导入的文件",
            "Ctrl / Shift 多选；按修改时间倒序，方便认最新表。",
        )
        cols = ("mtime", "name", "rows", "size", "cats")
        tree_wrap = tk.Frame(step2, bg=self._border, padx=1, pady=1)
        tree_wrap.pack(fill="x")
        self.file_tree = ttk.Treeview(
            tree_wrap,
            columns=cols,
            show="headings",
            selectmode="extended",
            height=9,
        )
        self.file_tree.heading("mtime", text="修改时间")
        self.file_tree.heading("name", text="文件名")
        self.file_tree.heading("rows", text="行数")
        self.file_tree.heading("size", text="大小")
        self.file_tree.heading("cats", text="类目摘要")
        self.file_tree.column("mtime", width=128, minwidth=100, stretch=False)
        self.file_tree.column("name", width=200, minwidth=120, stretch=False)
        self.file_tree.column("rows", width=64, minwidth=50, stretch=False, anchor="e")
        self.file_tree.column("size", width=72, minwidth=56, stretch=False, anchor="e")
        self.file_tree.column("cats", width=420, minwidth=200, stretch=True)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vsb.set)
        self.file_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        step3 = self._card(left, "③ 执行")
        btns = ttk.Frame(step3, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="生成今日筛选 HTML", command=self.run_today, style="Primary.TButton").pack(side="left")
        ttk.Button(btns, text="打开最新 HTML", command=self.open_latest_html, style="Ghost.TButton").pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(btns, text="数据分析", command=self.run_analysis, style="Ghost.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="生成诊断包", command=self.make_diagnostics, style="Ghost.TButton").pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(btns, text="迁移数据目录", command=self.migrate_data_store, style="Ghost.TButton").pack(side="right")

        ttk.Label(left, textvariable=self.state_var, style="State.TLabel", anchor="w").pack(
            fill="x", pady=(4, 0)
        )

        log_outer = tk.Frame(right, bg=self._border, padx=1, pady=1)
        log_outer.pack(fill="both", expand=True)
        log_card = ttk.Frame(log_outer, style="Card.TFrame", padding=(14, 12))
        log_card.pack(fill="both", expand=True)
        ttk.Label(log_card, text="运行日志", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(log_card, textvariable=self.status_var, style="CardHint.TLabel").pack(anchor="w", pady=(2, 10))

        phase_row = ttk.Frame(log_card, style="Card.TFrame")
        phase_row.pack(fill="x", pady=(0, 6))
        ttk.Label(phase_row, textvariable=self.phase_var, style="CardTitle.TLabel").pack(side="left")
        ttk.Label(phase_row, textvariable=self.progress_pct_var, style="CardHint.TLabel").pack(side="right")

        self.progress = ttk.Progressbar(log_card, mode="determinate", maximum=100, value=0)
        self.progress.pack(fill="x", pady=(0, 10))

        self.log = ScrolledText(
            log_card,
            borderwidth=0,
            highlightthickness=0,
            font=("Cascadia Mono", 9),
            bg="#18181B",
            fg="#D4D4D8",
            insertbackground="#FDBA74",
            selectbackground="#3F3F46",
            selectforeground="#FAFAF9",
            padx=10,
            pady=8,
            wrap=tk.WORD,
        )
        self.log.pack(fill="both", expand=True)

    def model_status_text(self) -> str:
        """返回当前增量模型或内置模型的更新时间文案。"""
        incremental = self.data_store / "lgb" / "lgbm_full.txt"
        bundled = ROOT / "screener" / "model" / "lgbm_full.txt"
        if incremental.is_file():
            return f"增量模型：{fmt_mtime(incremental)}"
        if bundled.is_file():
            return f"内置模型：{fmt_mtime(bundled)}"
        return "模型：未找到"

    def refresh_model_status(self) -> None:
        """刷新右上角模型状态显示。"""
        self.model_var.set(self.model_status_text())

    def format_log_line(self, msg: str) -> str:
        """给阶段日志前加文本框提示，普通文本保持原样。"""
        out: list[str] = []
        for line in msg.splitlines(keepends=True):
            raw = line.lstrip()
            if raw.startswith("[") and not raw.startswith("[ ] "):
                prefix_len = len(line) - len(raw)
                line = line[:prefix_len] + "[ ] " + raw
            out.append(line)
        return "".join(out)

    def _write(self, msg: str) -> None:
        """向 UI 日志区写入一行文本。"""
        self.log.insert(END, self.format_log_line(msg))
        self.log.see(END)

    def _schedule_phase(self, phase: str) -> None:
        def apply() -> None:
            self.phase_var.set(phase)
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)

        self.root.after(0, apply)

    def _schedule_progress(self, value: int, maximum: int, phase: str) -> None:
        def apply() -> None:
            mx = max(int(maximum), 1)
            val = min(int(value), mx)
            pct = int(100 * val / mx)
            self.phase_var.set(phase)
            self.progress_pct_var.set(f"{pct}%  ({val}/{mx})")
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=mx, value=val)

        self.root.after(0, apply)

    def _progress_reset(self) -> None:
        self.phase_var.set("正在启动…")
        self.progress_pct_var.set("")
        self.progress.stop()
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

    def _progress_idle(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.phase_var.set("")
        self.progress_pct_var.set("")

    def _update_progress_from_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        if "[prep]" in stripped:
            self._schedule_phase("准备数据…")
            return
        if "[download]" in stripped:
            m = _LOG_PROGRESS_DOWNLOAD.search(stripped)
            if m:
                self._schedule_progress(int(m.group(1)), int(m.group(2)), "下载主图")
            else:
                self._schedule_phase("下载主图")
            return
        if "下载未缓存主图" in stripped:
            self._schedule_phase("图像向量 (ResNet18)…")
            return
        if "[embed]" in stripped:
            m = _LOG_PROGRESS_IMG.search(stripped)
            if m:
                self._schedule_progress(int(m.group(1)), int(m.group(2)), "图像向量 (ResNet18)")
                return
            if "BGE" in stripped:
                self._schedule_phase("文本向量 (BGE)…")
                return
            if "新增 ResNet" in stripped:
                self._schedule_phase("图像向量 (ResNet18)…")
                return
            self._schedule_phase("生成向量…")
            return
        if "Batches:" in stripped or ("|" in stripped and "/" in stripped):
            pairs = re.findall(r"(\d+)/(\d+)", stripped)
            if pairs:
                done, total = int(pairs[-1][0]), int(pairs[-1][1])
                if total > 1:
                    self._schedule_progress(done, total, "文本向量 (BGE)")
            return
        if "[train]" in stripped:
            self._schedule_phase("训练 LightGBM…")
            return
        if "[html]" in stripped.lower() or "生成" in stripped and "html" in stripped.lower():
            self._schedule_phase("生成 HTML…")

    def _self_check(self) -> None:
        """检查模型、数据目录和 Python 运行时是否可用。"""
        ensure_dirs(self.data_store)
        missing = [name for name in MODEL_FILES if not (ROOT / "screener" / "model" / name).is_file()]
        py = runtime_python()
        if not Path(py).is_file():
            self.status_var.set("自检失败：找不到 Python 运行时")
            return
        if missing:
            self.status_var.set(f"自检通过：模型缓存为空，下次生成会从0训练；数据目录 {self.data_store}")
        else:
            self.status_var.set(f"自检通过：数据目录 {self.data_store}")
        self.refresh_model_status()
        last_dir = self.cfg.get("last_input_dir")
        if last_dir and Path(last_dir).is_dir():
            self.scan_folder()

    def choose_folder(self) -> None:
        """选择包含今日表格的文件夹。"""
        initial = self.cfg.get("last_input_dir") or str(Path.home() / "Downloads")
        chosen = filedialog.askdirectory(title="选择今日数据文件夹", initialdir=initial)
        if not chosen:
            return
        self.cfg["last_input_dir"] = chosen
        save_config(self.cfg)
        self.folder_var.set(chosen)
        self.scan_folder()

    def _scan_cache_path(self) -> Path:
        return self.data_store / "scan_index_cache.json"

    def _load_scan_cache(self) -> dict:
        path = self._scan_cache_path()
        if not path.is_file():
            return {"entries": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"entries": {}}
        if not isinstance(data.get("entries"), dict):
            data["entries"] = {}
        return data

    def _save_scan_cache(self, cache: dict) -> None:
        self._scan_cache_path().write_text(
            json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def scan_folder(self) -> None:
        """扫描候选表格并显示行数、大小和类目摘要。"""
        folder_raw = self.cfg.get("last_input_dir", "")
        folder = Path(folder_raw) if folder_raw else None
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        self.files = []
        if not folder or not folder.is_dir():
            self._write("请先选择数据文件夹。\n")
            return
        sys.path.insert(0, str(PIPE))
        from merge_csv import scan_table_meta  # noqa: WPS433

        cache = self._load_scan_cache()
        entries = cache["entries"]
        seen_keys: set[str] = set()

        for path in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file() or path.suffix.lower() not in TABLE_SUFFIXES:
                continue
            seen_keys.add(str(path.resolve()))
            meta = scan_table_meta(path, entries)
            size_kb = path.stat().st_size // 1024
            if meta.get("error"):
                values = (fmt_mtime(path), path.name, "—", "—", f"读取失败：{meta['error']}")
            else:
                values = (
                    fmt_mtime(path),
                    path.name,
                    str(meta.get("rows", "—")),
                    f"{size_kb} KB",
                    meta.get("cats") or "未识别类目",
                )
            iid = str(len(self.files))
            self.files.append(path)
            self.file_tree.insert("", END, iid=iid, values=values)

        stale = [k for k in entries if k not in seen_keys]
        for k in stale:
            del entries[k]
        self._save_scan_cache(cache)

        self.folder_var.set(str(folder))
        self.state_var.set(f"状态：发现 {len(self.files)} 个候选文件，请选中本次要导入的文件")

    def selected_files(self) -> list[Path]:
        """返回用户在列表中选中的表格路径。"""
        out: list[Path] = []
        for iid in self.file_tree.selection():
            try:
                out.append(self.files[int(iid)])
            except (ValueError, IndexError):
                continue
        return out

    def clear_incremental_model(self) -> None:
        """清空模型和训练缓存，让下一次生成时用当前数据从0训练。"""
        if self.busy:
            messagebox.showinfo("正在运行", "当前任务还没结束，请稍等。")
            return
        ok = messagebox.askyesno(
            "确认清空",
            "会删除当前模型权重和训练中间缓存。\n不会删除原始 CSV、输出 HTML、图片缓存和日志。\n\n继续吗？",
        )
        if not ok:
            return
        for name in RESET_DIRS:
            folder = self.data_store / name
            if folder.is_dir():
                shutil.rmtree(folder)
            folder.mkdir(parents=True, exist_ok=True)
        for name in MODEL_FILES:
            (ROOT / "screener" / "model" / name).unlink(missing_ok=True)
        self.refresh_model_status()
        self.state_var.set("状态：已清空模型缓存；下次生成会用当前数据从0训练")
        self._write("[train] 已清空模型缓存，下次生成会用当前数据从0训练。\n")

    def run_bg(self, job) -> None:
        """在后台线程执行耗时任务，避免 UI 卡死。"""
        if self.busy:
            messagebox.showinfo("正在运行", "当前任务还没结束，请稍等。")
            return
        self.busy = True
        self.root.after(0, self._progress_reset)

        def wrap() -> None:
            try:
                job()
            except Exception:
                err = traceback.format_exc()
                self.root.after(0, lambda: self._write("失败：\n" + err + "\n"))
                self.root.after(0, lambda: self.status_var.set("任务失败，请点“生成诊断包”发给维护人员"))
            finally:
                self.busy = False
                self.root.after(0, self._progress_idle)

        threading.Thread(target=wrap, daemon=True).start()

    def child_env(self) -> dict[str, str]:
        """构造子进程环境，强制 pipeline 使用当前数据目录。"""
        env = os.environ.copy()
        env["KITCHEN_DATA_STORE"] = str(self.data_store)
        env["HF_HOME"] = str(ROOT / "runtime" / "hf-cache")
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def run_cmd(self, args: list[str]) -> int:
        """运行子命令并把输出实时写入 UI 和日志文件。"""
        logs_dir = self.data_store / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"run_{day_stamp()}.log"
        cmd = [runtime_python(), *args]
        self.root.after(0, lambda: self._write("$ " + " ".join(cmd) + "\n"))
        with log_path.open("w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                env=self.child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log_file.write(line)
                self._update_progress_from_line(line)
                self.root.after(0, lambda msg=line: self._write(msg))
            return proc.wait()

    def run_today(self) -> None:
        """执行今日导入、自动增量训练、预测和 HTML 生成。"""
        paths = self.selected_files()
        if not paths:
            messagebox.showwarning("未选择文件", "请先在列表中选中本次要导入的 CSV/XLSX。")
            return

        def job() -> None:
            self.root.after(0, lambda: self.state_var.set("状态：正在生成 HTML，并训练明天模型"))
            args = [str(PIPE / "daily.py"), "--today", *[str(p) for p in paths]]
            code = self.run_cmd(args)
            if code != 0:
                raise RuntimeError(f"daily.py exit={code}")
            self.root.after(0, self.refresh_model_status)
            latest = self.latest_share_html()
            if latest:
                self.cfg["last_share_html"] = str(latest)
                save_config(self.cfg)
                self.root.after(0, lambda: self.state_var.set(f"状态：重点 HTML 已生成 {latest.name}"))
                self.root.after(0, lambda: webbrowser.open(latest.as_uri()))

        self.run_bg(job)

    def run_analysis(self) -> None:
        """执行基础数据分析并打开最新分析 HTML。"""
        def job() -> None:
            self.root.after(0, lambda: self.state_var.set("状态：正在生成基础数据分析"))
            args = [str(PIPE / "daily.py"), "--analysis-only"]
            code = self.run_cmd(args)
            if code != 0:
                raise RuntimeError(f"daily.py analysis exit={code}")
            latest = self.latest_analysis_html()
            if latest:
                self.root.after(0, lambda: self.state_var.set(f"状态：数据分析已生成 {latest.name}"))
                self.root.after(0, lambda: webbrowser.open(latest.as_uri()))

        self.run_bg(job)

    def latest_analysis_html(self) -> Path | None:
        """返回 data_store/output 中最新的数据分析 HTML。"""
        out = self.data_store / "output"
        htmls = sorted(out.glob("*_分析.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        return htmls[0] if htmls else None

    def latest_share_html(self) -> Path | None:
        """返回 data_store/output 中最新的筛选 HTML，兼容旧分享命名。"""
        out = self.data_store / "output"
        htmls = [
            p
            for p in out.glob("*.html")
            if not p.name.endswith("_screener.html") and p.name not in {"分析.html", "上传.html"}
        ]
        htmls = sorted(htmls, key=lambda p: p.stat().st_mtime, reverse=True)
        return htmls[0] if htmls else None

    def open_latest_html(self) -> None:
        """打开最新生成的筛选 HTML。"""
        latest = self.latest_share_html()
        if not latest:
            messagebox.showinfo("没有 HTML", "请先生成今日筛选 HTML。")
            return
        webbrowser.open(latest.as_uri())

    def migrate_data_store(self) -> None:
        """把数据目录复制到新位置并切换配置。"""
        chosen = filedialog.askdirectory(title="选择新的数据目录")
        if not chosen:
            return
        new_dir = Path(chosen).expanduser().resolve()
        if new_dir == self.data_store:
            return
        if not messagebox.askyesno("确认迁移", f"会把现有数据复制到：\n{new_dir}\n\n继续吗？"):
            return
        ensure_dirs(new_dir)
        for item in self.data_store.iterdir():
            target = new_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, target)
        self.data_store = new_dir
        self.cfg["data_store"] = str(new_dir)
        save_config(self.cfg)
        self.status_var.set(f"数据目录已迁移：{new_dir}")
        self.refresh_model_status()

    def make_diagnostics(self) -> None:
        """生成用于排查的诊断包，不包含完整原始 CSV 和模型权重。"""
        diag = self.data_store / "logs" / f"diagnostics_{day_stamp()}.zip"
        model_status = {name: (ROOT / "screener" / "model" / name).is_file() for name in MODEL_FILES}
        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "root": str(ROOT),
            "data_store": str(self.data_store),
            "runtime_python": runtime_python(),
            "model_status": model_status,
            "files": [str(p) for p in self.files],
        }
        with zipfile.ZipFile(diag, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            if CONFIG.is_file():
                zf.write(CONFIG, "portable_config.json")
            logs = sorted((self.data_store / "logs").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            for log_path in logs[:5]:
                zf.write(log_path, f"logs/{log_path.name}")
            self._add_input_samples(zf)
        self._write(f"诊断包：{diag}\n")
        messagebox.showinfo("诊断包已生成", str(diag))

    def _add_input_samples(self, zf: zipfile.ZipFile) -> None:
        """把候选输入文件的前几行样本写入诊断包。"""
        if not self.files:
            return
        sys.path.insert(0, str(PIPE))
        from merge_csv import read_table  # noqa: WPS433

        for path in self.files[:8]:
            try:
                sample = read_table(path).head(5).to_csv(index=False)
                zf.writestr(f"samples/{path.stem}_head.csv", sample)
            except Exception as exc:
                zf.writestr(f"samples/{path.stem}_error.txt", repr(exc))

    def run(self) -> None:
        """启动 Tk 主循环。"""
        self.root.mainloop()


def main() -> None:
    """程序入口。"""
    KitchenApp().run()


if __name__ == "__main__":
    main()
