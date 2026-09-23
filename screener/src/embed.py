# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import hashlib
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message="Palette images with Transparency expressed in bytes",
    category=UserWarning,
)

import aiohttp
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from sentence_transformers import SentenceTransformer
from torchvision import models

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BGE_CACHES = (
    PROJECT_ROOT / "env" / "hf-cache" / "models--BAAI--bge-small-zh-v1.5",
    PROJECT_ROOT / "env" / "hf-cache" / "hub" / "models--BAAI--bge-small-zh-v1.5",
    PROJECT_ROOT / "runtime" / "hf-cache" / "models--BAAI--bge-small-zh-v1.5",
    PROJECT_ROOT / "runtime" / "hf-cache" / "hub" / "models--BAAI--bge-small-zh-v1.5",
)


def local_bge_model(model_name: str) -> str:
    """优先把 BGE 模型名解析到便携包里的本地快照目录。"""
    if model_name != "BAAI/bge-small-zh-v1.5":
        return model_name
    for cache in BGE_CACHES:
        snapshots = cache / "snapshots"
        if snapshots.is_dir():
            dirs = [p for p in snapshots.iterdir() if p.is_dir()]
            if dirs:
                return str(max(dirs, key=lambda p: p.stat().st_mtime))
    return model_name


def url_to_path(url: str, cache_dirs: list[Path]) -> Path:
    h = hashlib.md5(url.encode("utf-8")).hexdigest()
    ext = ".jpg"
    low = url.lower()
    if ".png" in low:
        ext = ".png"
    elif ".webp" in low:
        ext = ".webp"
    elif ".jpeg" in low:
        ext = ".jpeg"
    for d in cache_dirs:
        p = d / f"{h}{ext}"
        if p.exists() and p.stat().st_size > 1024:
            return p
    return cache_dirs[-1] / f"{h}{ext}"


def image_ok(url: str, cache_dirs: list[Path]) -> bool:
    if not url:
        return False
    p = url_to_path(url, cache_dirs)
    return p.exists() and p.stat().st_size > 1024


async def _download_one(session, url: str, dest: Path, sem: asyncio.Semaphore):
    if dest.exists() and dest.stat().st_size > 1024:
        return url, True
    async with sem:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return url, False
                data = await resp.read()
                if len(data) < 1024:
                    return url, False
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(data)
                tmp.replace(dest)
                return url, True
        except Exception:
            return url, False


async def _download_round(session, urls: list[str], cache_dirs: list[Path], sem: asyncio.Semaphore, label: str):
    """执行一轮图片下载，并向日志实时输出完成进度。"""
    tasks = [_download_one(session, u, url_to_path(u, cache_dirs), sem) for u in urls if u]
    total = len(tasks)
    results: dict[str, bool] = {}
    if not tasks:
        return results
    done = 0
    next_report = 0
    for task in asyncio.as_completed(tasks):
        url, ok = await task
        results[url] = ok
        done += 1
        if done == total or done >= next_report:
            good = sum(1 for v in results.values() if v)
            bad = done - good
            print(f"[download] {label} {done}/{total} 成功={good} 失败={bad}", flush=True)
            next_report = min(total, done + max(20, total // 20))
    return results


async def download_urls(urls: list[str], cache_dirs: list[Path], concurrency: int):
    """下载当前预测文件缺失的主图，供没有图片向量缓存的 SKU 生成 embedding。"""
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    try:
        from temu_region import temu_aiohttp_headers
    except ModuleNotFoundError:
        sys.path.insert(0, str(_root / "pipeline"))
        from temu_region import temu_aiohttp_headers

    headers = temu_aiohttp_headers()
    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        ok_map = await _download_round(session, urls, cache_dirs, sem, "首轮")
        for round_no in range(1, 4):
            failed = [u for u, ok in ok_map.items() if not ok]
            if not failed:
                break
            print(f"[download] retry {round_no} 只重试失败 {len(failed)} 张", flush=True)
            retry_map = await _download_round(session, failed, cache_dirs, sem, f"retry{round_no}")
            ok_map.update(retry_map)
    return ok_map


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def build_resnet():
    weights = models.ResNet18_Weights.IMAGENET1K_V1
    model = models.resnet18(weights=weights)
    model.fc = nn.Identity()
    model.eval()
    return model, weights.transforms()


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n = np.maximum(n, 1e-12)
    return (x / n).astype(np.float32)


@torch.no_grad()
def embed_images(paths: list[Path | None], batch: int = 32) -> tuple[np.ndarray, np.ndarray]:
    n = len(paths)
    out = np.zeros((n, 512), dtype=np.float32)
    missing = np.ones(n, dtype=bool)
    dev = device()
    print(f"[embed] 加载 ResNet18 device={dev}", flush=True)
    model, tfm = build_resnet()
    model = model.to(dev)
    print(f"[embed] 图像向量开始 共 {n} 行（CPU 版较慢，日志会按批次更新）", flush=True)
    batch_idx: list[int] = []
    batch_tensors: list = []
    next_report = 0

    def flush() -> None:
        nonlocal batch_idx, batch_tensors
        if not batch_tensors:
            return
        x = torch.stack(batch_tensors).to(dev)
        feat = l2_normalize(model(x).cpu().numpy())
        for j, i in enumerate(batch_idx):
            out[i] = feat[j]
            missing[i] = False
        batch_idx = []
        batch_tensors = []

    for i, p in enumerate(paths):
        if not p or not p.exists():
            if i >= next_report:
                print(f"[embed] img {i + 1}/{n}", flush=True)
                next_report = min(n, i + 1 + max(32, n // 40))
            continue
        try:
            im = Image.open(p).convert("RGB")
            batch_tensors.append(tfm(im))
            batch_idx.append(i)
            if len(batch_tensors) >= batch:
                flush()
        except Exception:
            pass
        if i >= next_report:
            print(f"[embed] img {i + 1}/{n}", flush=True)
            next_report = min(n, i + 1 + max(32, n // 40))
    flush()
    print(f"[embed] img {n}/{n}", flush=True)
    return out, missing


def embed_texts(texts: list[str], model_name: str, batch: int = 32) -> np.ndarray:
    model = SentenceTransformer(local_bge_model(model_name))
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(dev)
    return model.encode(
        texts,
        batch_size=batch,
        show_progress_bar=len(texts) > 200,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)
