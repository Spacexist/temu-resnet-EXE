# -*- coding: utf-8 -*-
"""把当天多份类目 CSV 合成一份。

用法：
  python merge_csv.py a.csv b.csv c.csv
  python merge_csv.py --dir D:\\today --n 3 --out merged.csv
  无参数会退出，避免误吃 Downloads 里最新文件。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = Path.home() / "Downloads"
DATA_STORE = Path(os.environ.get("KITCHEN_DATA_STORE", ROOT / "data_store")).expanduser().resolve()
INBOX = DATA_STORE / "inbox"
RAW = DATA_STORE / "raw"
TABLE_SUFFIXES = {".csv", ".xlsx", ".xls"}
CAT_COL = "前台分类（中文）"


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """双表头压成单行列名。"""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [
            str(b).strip() if not str(b).startswith("Unnamed") else str(a).strip()
            for a, b in df.columns
        ]
    return df


def read_table(path: Path) -> pd.DataFrame:
    """Temu 导出经常是 xlsx 外壳的 csv。"""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        try:
            df = pd.read_excel(path, sheet_name="sheet", header=[0, 1])
            return flatten_columns(df)
        except Exception:
            return pd.read_csv(path, encoding="utf-8-sig")
    df = pd.read_excel(path, sheet_name="sheet", header=[0, 1])
    return flatten_columns(df)


def cat_summary(df: pd.DataFrame) -> str:
    """一级类目前几名，方便核对是不是三个不同类。"""
    col = "前台分类（中文）" if "前台分类（中文）" in df.columns else None
    if col is None:
        return ""
    top = (
        df[col]
        .astype(str)
        .str.split("/", n=1)
        .str[0]
        .value_counts()
        .head(5)
    )
    parts = []
    for k, v in top.items():
        if v <= 0:
            continue
        name = str(k).strip()
        if not name or name.lower() == "nan":
            continue
        parts.append(f"{name}={v}")
    return "；".join(parts)


def _count_csv_data_rows(path: Path) -> int:
    """按行数估计 CSV 数据行（不含表头），避免为行数全表读入内存。"""
    with path.open("rb") as f:
        n = sum(1 for _ in f)
    return max(0, n - 1)


def _scan_rows_and_cats(path: Path) -> tuple[int, str]:
    """文件列表用：尽量只读类目列，行数用计数或 len。"""
    path = path.expanduser().resolve()
    if path.suffix.lower() == ".csv":
        try:
            df = pd.read_excel(path, sheet_name="sheet", header=[0, 1])
            df = flatten_columns(df)
            return len(df), cat_summary(df) or "未识别类目"
        except Exception:
            header = pd.read_csv(path, encoding="utf-8-sig", nrows=0)
            if CAT_COL in header.columns:
                cat_df = pd.read_csv(path, encoding="utf-8-sig", usecols=[CAT_COL])
                return len(cat_df), cat_summary(cat_df) or "未识别类目"
            return _count_csv_data_rows(path), "未识别类目"
    df = read_table(path)
    return len(df), cat_summary(df) or "未识别类目"


def scan_table_meta(path: Path, entries: dict[str, dict]) -> dict:
    """带 mtime/size 缓存的列表元数据；entries 会被就地更新。"""
    path = path.expanduser().resolve()
    key = str(path)
    st = path.stat()
    mtime_ns, size = st.st_mtime_ns, st.st_size
    prev = entries.get(key)
    if prev and prev.get("mtime_ns") == mtime_ns and prev.get("size") == size:
        return prev
    meta: dict = {"mtime_ns": mtime_ns, "size": size}
    try:
        rows, cats = _scan_rows_and_cats(path)
        meta["rows"] = int(rows)
        meta["cats"] = cats
        meta["error"] = ""
    except Exception as exc:
        meta["rows"] = None
        meta["cats"] = ""
        meta["error"] = type(exc).__name__
    entries[key] = meta
    return meta


def default_inputs(n: int = 3) -> list[Path]:
    """Downloads 里按修改时间取最新 n 个表格。"""
    files = [
        p
        for p in DOWNLOADS.iterdir()
        if p.is_file() and p.suffix.lower() in TABLE_SUFFIXES
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if len(files) < n:
        raise SystemExit(f"Downloads 里表格不足 {n} 个，只找到 {len(files)}")
    return files[:n]


def merge_files(paths: list[Path], dest: Path | None = None) -> Path:
    """合并、按商品ID去重（销量高的留下），写出 UTF-8-SIG CSV。"""
    if not paths:
        raise SystemExit("没有输入文件")
    frames = []
    for src in paths:
        df = read_table(src)
        df["_pack"] = src.stem
        frames.append(df)
        print(f"[merge] {src.name}  行={len(df)}  {cat_summary(df)}")
    out = pd.concat(frames, ignore_index=True)
    n0 = len(out)
    if "商品ID" in out.columns:
        out["商品ID"] = out["商品ID"].astype(str)
        if "总销量" in out.columns:
            out["总销量"] = pd.to_numeric(out["总销量"], errors="coerce").fillna(0)
            out = out.sort_values(["商品ID", "总销量"], ascending=[True, False])
        before = len(out)
        out = out.drop_duplicates("商品ID", keep="first")
        print(f"[merge] 商品ID 去重 {before} → {len(out)}")
    if dest is None:
        RAW.mkdir(parents=True, exist_ok=True)
        dest = RAW / f"{datetime.now().strftime('%Y%m%d')}_merged.csv"
    dest = dest.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False, encoding="utf-8-sig")
    INBOX.mkdir(parents=True, exist_ok=True)
    inbox_copy = INBOX / dest.name
    if inbox_copy.resolve() != dest:
        import shutil

        shutil.copy2(dest, inbox_copy)
    print(f"[merge] 合计 {n0} → {len(out)}  写出 {dest}")
    return dest


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="合并多份 Temu 类目 CSV")
    ap.add_argument("files", nargs="*", help="要合并的 csv/xlsx（建议直接点名三个文件）")
    ap.add_argument("--dir", default="", help="从这个目录取最新 N 个表格")
    ap.add_argument("--n", type=int, default=3, help="配合 --dir 使用，默认 3")
    ap.add_argument("--out", default="", help="输出路径，默认 data/raw/YYYYMMDD_merged.csv")
    args = ap.parse_args()
    if args.files:
        paths = [Path(p) for p in args.files]
    elif args.dir:
        folder = Path(args.dir)
        files = [
            p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in TABLE_SUFFIXES
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        paths = files[: args.n]
        if len(paths) < args.n:
            raise SystemExit(f"{folder} 里表格不足 {args.n} 个")
    else:
        raise SystemExit("请写上三个 csv 路径，或加 --dir 指向文件夹")
    dest = Path(args.out) if args.out else None
    merge_files(paths, dest)


if __name__ == "__main__":
    main()
