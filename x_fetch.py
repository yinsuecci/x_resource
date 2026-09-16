"""Fetch high-engagement X posts via official API when configured."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

UA = "ViralNewsDesk/1.0"

# 冲突向 / 大众关心关键词检索；需 X API Bearer Token（Recent Search）
DEFAULT_QUERY = (
    '(OpenAI OR Anthropic OR DeepSeek OR ChatGPT OR Claude OR Gemini OR Grok OR Nvidia '
    'OR Bitcoin OR crypto OR Trump OR "stock market" OR layoff OR antitrust OR Harvard '
    'OR "gene editing" OR China OR Taiwan) '
    'min_faves:800 -is:retweet -is:reply'
)


def _bearer() -> str:
    return (
        os.getenv("X_BEARER_TOKEN")
        or os.getenv("TWITTER_BEARER_TOKEN")
        or ""
    ).strip()


def fetch_x_viral(timeout: float = 20.0, max_results: int = 20) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    token = _bearer()
    if not token:
        return [], [
            {
                "_error": True,
                "source_id": "x-viral",
                "source": "X 火爆帖",
                "error": "未配置 X_BEARER_TOKEN；已跳过。在 .env 填入后可拉取高赞帖。",
            }
        ]

    query = os.getenv("X_SEARCH_QUERY", DEFAULT_QUERY).strip() or DEFAULT_QUERY
    params = {
        "query": query,
        "max_results": str(min(max(10, max_results), 100)),
        "tweet.fields": "created_at,public_metrics,lang,entities",
        "expansions": "author_id",
        "user.fields": "username,name",
        "sort_order": "relevancy",
    }
    headers = {"Authorization": f"Bearer {token}", "User-Agent": UA}

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get("https://api.x.com/2/tweets/search/recent", params=params)
            if resp.status_code == 404:
                resp = client.get("https://api.twitter.com/2/tweets/search/recent", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        return [], [
            {
                "_error": True,
                "source_id": "x-viral",
                "source": "X 火爆帖",
                "error": str(exc),
            }
        ]

    users = {u["id"]: u for u in (payload.get("includes") or {}).get("users") or []}
    items: list[dict[str, Any]] = []
    for tw in payload.get("data") or []:
        text = (tw.get("text") or "").strip()
        if not text:
            continue
        tid = tw.get("id")
        metrics = tw.get("public_metrics") or {}
        likes = int(metrics.get("like_count") or 0)
        rts = int(metrics.get("retweet_count") or 0)
        quotes = int(metrics.get("quote_count") or 0)
        replies = int(metrics.get("reply_count") or 0)
        eng = likes + rts * 2 + quotes * 2 + replies
        author = users.get(tw.get("author_id") or "", {})
        username = author.get("username") or "unknown"
        link = f"https://x.com/{username}/status/{tid}"
        title = text.split("\n")[0][:120]
        summary = (
            f"@{username} · 赞 {likes} · 转发 {rts} · 引用 {quotes} · 回复 {replies}\n{text[:400]}"
        )
        # 互动越高分越高
        score = 20 + min(eng // 50, 80)
        lang = "zh" if tw.get("lang") == "zh" else "en"
        tags = ["X热帖"]
        low = text.lower()
        if any(k in low for k in ("openai", "anthropic", "deepseek", "chatgpt", "claude", "gemini", "ai")):
            tags.append("AI模型")
        if any(k in low for k in ("trump", "election", "war", "china", "taiwan")):
            tags.append("政治对立")
        if any(k in low for k in ("bitcoin", "crypto", "ethereum")):
            tags.append("加密货币")
        if any(k in low for k in ("stock", "nasdaq", "fed", "inflation")):
            tags.append("股市")

        iid = hashlib.sha1(f"x|{tid}".encode("utf-8")).hexdigest()[:16]
        items.append(
            {
                "id": iid,
                "source_id": "x-viral",
                "source": f"X · @{username}",
                "title": title,
                "summary_en": summary,
                "link": link,
                "published": tw.get("created_at"),
                "score": score,
                "tags": tags,
                "lang": lang,
                "engagement": eng,
            }
        )

    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items, []
