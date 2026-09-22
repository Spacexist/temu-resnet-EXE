# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np


def norm_id(pid: str) -> str:
    s = str(pid).strip()
    if s.endswith(".0"):
        return s[:-2]
    return s


def merge_vectors_npz(path: Path, ids: list[str], X: np.ndarray) -> None:
    """把本批向量合并进 img.npz / txt.npz，供预测后的增量训练复用。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, np.ndarray] = {}
    if path.is_file():
        with np.load(path, allow_pickle=True) as z:
            for i, v in zip(z["ids"], z["X"]):
                existing[norm_id(str(i))] = np.asarray(v, dtype=np.float32)
    for pid, vec in zip(ids, X):
        existing[norm_id(str(pid))] = np.asarray(vec, dtype=np.float32)
    all_ids = list(existing.keys())
    stacked = np.stack([existing[i] for i in all_ids]).astype(np.float32)
    tmp = path.parent / f".{path.stem}.{int(time.time() * 1000)}.npz"
    np.savez_compressed(tmp, ids=np.array(all_ids, dtype=object), X=stacked)
    os.replace(tmp, path)


def load_pair(
    art_dir: Path, npz_dir: Path | None = None
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]] | None:
    base = npz_dir if npz_dir is not None else art_dir
    img_p = base / "img.npz"
    txt_p = base / "txt.npz"
    if not img_p.is_file() or not txt_p.is_file():
        return None
    z_img = np.load(img_p, allow_pickle=True)
    z_txt = np.load(txt_p, allow_pickle=True)
    img_map = {norm_id(i): v for i, v in zip(z_img["ids"], z_img["X"])}
    txt_map = {norm_id(i): v for i, v in zip(z_txt["ids"], z_txt["X"])}
    return img_map, txt_map


def fill_from_cache(
    ids: list[str],
    img_map: dict[str, np.ndarray],
    txt_map: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(ids)
    X_img = np.zeros((n, 512), dtype=np.float32)
    X_txt = np.zeros((n, 512), dtype=np.float32)
    miss = np.ones(n, dtype=bool)
    for i, pid in enumerate(ids):
        pid = norm_id(pid)
        if pid in img_map and pid in txt_map:
            X_img[i] = img_map[pid]
            X_txt[i] = txt_map[pid]
            miss[i] = False
    return X_img, X_txt, miss
