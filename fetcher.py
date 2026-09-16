"""Fetch RSS + Chinese hotboards + optional X viral posts."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from cn_hot import fetch_hotboards
from scorer import FEEDS, score_item
from x_fetch import fetch_x_viral

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "ViralNewsDesk/1.0"
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(entry: dict[str, Any]) -> str | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    if entry.get("published_parsed"):
        try:
            t = entry.published_parsed
            dt = datetime(*t[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return None
    return None


def _item_id(link: str, title: str) -> str:
    return hashlib.sha1(f"{link}|{title}".encode("utf-8")).hexdigest()[:16]


def _is_zh(text: str) -> bool:
    return len(CJK_RE.findall(text or "")) >= 4


def _fetch_rss(client: httpx.Client) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()

    for feed in FEEDS:
        try:
            resp = client.get(feed["url"])
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as exc:
            errors.append(
                {
                    "_error": True,
                    "source_id": feed["id"],
                    "source": feed["name"],
                    "error": str(exc),
                }
            )
            continue

        limit = 12 if feed["id"] == "huxiu" else 25
        for entry in parsed.entries[:limit]:
            title = _strip_html(entry.get("title", ""))
            link = entry.get("link") or entry.get("id") or ""
            if not title or not link:
                continue
            summary = _strip_html(
                entry.get("summary")
                or entry.get("description")
                or (entry.get("content", [{}])[0].get("value") if entry.get("content") else "")
                or ""
            )
            if len(summary) > 600:
                summary = summary[:600] + "…"

            iid = _item_id(link, title)
            if iid in seen:
                continue
            seen.add(iid)

            scored = score_item(title, summary, feed["id"])
            if scored.drop or scored.score < 14:
                continue

            items.append(
                {
                    "id": iid,
                    "source_id": feed["id"],
                    "source": feed["name"],
                    "title": title,
                    "summary_en": summary,
                    "link": link,
                    "published": _parse_date(entry),
                    "score": scored.score,
                    "tags": scored.tags,
                    "lang": "zh" if _is_zh(title) else "en",
                }
            )
    return items, errors


def fetch_all(timeout: float = 18.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as client:
        rss_items, rss_errors = _fetch_rss(client)
        items.extend(rss_items)
        errors.extend(rss_errors)

    cn_items, cn_errors = fetch_hotboards(timeout=timeout)
    items.extend(cn_items)
    errors.extend(cn_errors)

    x_items, x_errors = fetch_x_viral(timeout=timeout)
    items.extend(x_items)
    errors.extend(x_errors)

    # 去重（标题近似）
    deduped: list[dict[str, Any]] = []
    for it in items:
        key = re.sub(r"\s+", "", (it.get("title") or "")[:40])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    deduped.sort(key=lambda x: (x.get("score", 0), x.get("published") or ""), reverse=True)
    return deduped, errors
