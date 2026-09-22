# -*- coding: utf-8 -*-
"""Temu JP 区域一致的站点入口与 HTTP 头（选品下载/脚本用）。"""

# 日本站英文界面（region=100, currency=JPY）
TEMU_HOME = "https://www.temu.com/jp-en/"

TEMU_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 与浏览器 JP 站一致：英文 + 日本优先，避免 zh-CN + Asia/Shanghai 与站点错位
TEMU_ACCEPT_LANGUAGE = "en-JP,en;q=0.9,ja;q=0.8"


def temu_aiohttp_headers(*, image: bool = True) -> dict[str, str]:
    """主图 CDN 会看 Referer / Accept / Sec-Fetch，头太少像脚本。"""
    headers: dict[str, str] = {
        "User-Agent": TEMU_USER_AGENT,
        "Referer": TEMU_HOME,
        "Accept-Language": TEMU_ACCEPT_LANGUAGE,
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }
    if image:
        headers.update(
            {
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Sec-Fetch-Dest": "image",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "cross-site",
            }
        )
    else:
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        )
    return headers
