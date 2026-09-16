"""Background-friendly images from Pixiv ranking, Wallhaven, Safebooru (safe only)."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

PROXY_HOSTS = {"i.pximg.net", "s.pximg.net"}


def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _proxy_url(raw: str) -> str:
    if not raw:
        return ""
    if "pximg.net" in raw:
        return f"/api/img-proxy?url={quote(raw, safe='')}"
    return raw


def _is_wallpaperish(w: int | None, h: int | None) -> bool:
    if not w or not h:
        return True
    # 偏横图 / 接近桌面比例，更适合背景
    return w >= h * 0.85 and w >= 1200


def fetch_pixiv_ranking(client: httpx.Client, mode: str = "daily") -> list[dict[str, Any]]:
    """Pixiv 公开日榜 JSON（无需登录）。缩略图经本地代理带 Referer。"""
    url = f"https://www.pixiv.net/ranking.php?mode={mode}&content=illust&format=json"
    resp = client.get(url, headers={"User-Agent": UA, "Referer": "https://www.pixiv.net/"})
    resp.raise_for_status()
    data = resp.json()
    out: list[dict[str, Any]] = []
    for row in (data.get("contents") or [])[:24]:
        illust_id = str(row.get("illust_id") or "")
        title = row.get("title") or "Pixiv 作品"
        user = row.get("user_name") or ""
        thumb = row.get("url") or ""
        tags = row.get("tags") or []
        # 粗滤 NSFW 标签
        tag_blob = " ".join(tags).lower()
        if any(x in tag_blob for x in ("r-18", "r18", "nsfw", "裸", "性感")):
            continue
        page = f"https://www.pixiv.net/artworks/{illust_id}"
        out.append(
            {
                "id": _id("pixiv", illust_id),
                "source": "Pixiv 日榜",
                "category": "二次元",
                "title": title,
                "author": user,
                "page_url": page,
                "thumb_url": _proxy_url(thumb),
                "image_url": _proxy_url(thumb),
                "tags": tags[:8] if isinstance(tags, list) else [],
                "width": row.get("width"),
                "height": row.get("height"),
            }
        )
    return out


def fetch_wallhaven(
    client: httpx.Client,
    query: str,
    category: str,
    categories_flag: str,
) -> list[dict[str, Any]]:
    """Wallhaven：categories 100=general 010=anime 001=people；purity 100=sfw."""
    params = {
        "q": query,
        "categories": categories_flag,
        "purity": "100",
        "atleast": "1920x1080",
        "sorting": "favorites",
        "order": "desc",
        "page": "1",
    }
    resp = client.get("https://wallhaven.cc/api/v1/search", params=params, headers={"User-Agent": UA})
    resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for row in (resp.json().get("data") or [])[:18]:
        w = int((row.get("dimension_x") or 0))
        h = int((row.get("dimension_y") or 0))
        if not _is_wallpaperish(w, h):
            continue
        thumbs = row.get("thumbs") or {}
        out.append(
            {
                "id": _id("wh", row.get("id", "")),
                "source": "Wallhaven",
                "category": category,
                "title": f"{query} · {row.get('id')}",
                "author": "",
                "page_url": row.get("url") or "",
                "thumb_url": thumbs.get("large") or thumbs.get("original") or row.get("path"),
                "image_url": row.get("path") or thumbs.get("original"),
                "tags": [t.get("name") for t in (row.get("tags") or [])[:8] if isinstance(t, dict)],
                "width": w,
                "height": h,
            }
        )
    return out


def fetch_safebooru(client: httpx.Client, tags: str, category: str) -> list[dict[str, Any]]:
    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": "1",
        "limit": "24",
        "tags": tags,
    }
    resp = client.get("https://safebooru.org/index.php", params=params, headers={"User-Agent": UA})
    resp.raise_for_status()
    text = resp.text.strip()
    if not text.startswith("["):
        return []
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        w = int(row.get("width") or 0)
        h = int(row.get("height") or 0)
        if w and h and w < 1280:
            continue
        file_url = row.get("file_url") or ""
        sample = row.get("sample_url") or file_url
        preview = row.get("preview_url") or sample
        post_id = str(row.get("id") or "")
        tag_str = row.get("tags") or ""
        tag_list = [t for t in tag_str.split() if t][:8]
        out.append(
            {
                "id": _id("sb", post_id),
                "source": "Safebooru",
                "category": category,
                "title": tag_list[0] if tag_list else f"#{post_id}",
                "author": row.get("owner") or "",
                "page_url": f"https://safebooru.org/index.php?page=post&s=view&id={post_id}",
                "thumb_url": preview,
                "image_url": sample or file_url,
                "tags": tag_list,
                "width": w or None,
                "height": h or None,
            }
        )
    return out


def fetch_images(category: str = "全部", timeout: float = 20.0) -> dict[str, Any]:
    """category: 全部 | 二次元 | 风景"""
    cat = (category or "全部").strip()
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        jobs: list[tuple[str, Any]] = []
        if cat in {"全部", "二次元"}:
            jobs.append(("pixiv", lambda: fetch_pixiv_ranking(client)))
            jobs.append(("wallhaven-anime", lambda: fetch_wallhaven(client, "anime", "二次元", "010")))
            jobs.append(
                (
                    "safebooru-anime",
                    lambda: fetch_safebooru(
                        client,
                        "scenery rating:general widescreen",
                        "二次元",
                    ),
                )
            )
        if cat in {"全部", "风景"}:
            jobs.append(
                ("wallhaven-land", lambda: fetch_wallhaven(client, "landscape", "风景", "100"))
            )
            jobs.append(
                ("wallhaven-nature", lambda: fetch_wallhaven(client, "nature mountains", "风景", "100"))
            )
            jobs.append(
                (
                    "safebooru-scenery",
                    lambda: fetch_safebooru(client, "scenery rating:general widescreen", "风景"),
                )
            )

        for name, fn in jobs:
            try:
                chunk = fn()
                if cat != "全部":
                    chunk = [x for x in chunk if x.get("category") == cat]
                images.extend(chunk)
            except Exception as exc:
                errors.append({"source": name, "error": str(exc)})

    # 去重
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for im in images:
        key = im.get("page_url") or im.get("id")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(im)

    return {"items": deduped, "errors": errors, "category": cat, "count": len(deduped)}
