"""Chinese summaries for posting — LLM if configured, else MyMemory / Google translate."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx
from deep_translator import GoogleTranslator, MyMemoryTranslator
from dotenv import load_dotenv

load_dotenv()


def _translate(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    chunk = text[:4500]
    # 国内更稳：先 MyMemory，再 Google
    errors: list[str] = []
    try:
        out = MyMemoryTranslator(source="en-US", target="zh-CN").translate(chunk)
        if out and out.strip() and out.strip() != chunk:
            return out.strip()
    except Exception as exc:
        errors.append(f"mymemory:{exc}")

    for _ in range(2):
        try:
            out = GoogleTranslator(source="auto", target="zh-CN").translate(chunk)
            if out and out.strip():
                return out.strip()
        except Exception as exc:
            errors.append(f"google:{exc}")
            time.sleep(1.2)

    return text


def _has_llm() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _llm_base() -> tuple[str, str, str]:
    if os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        key = os.getenv("DEEPSEEK_API_KEY", "")
        base = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        model = os.getenv("OPENAI_MODEL", "deepseek-chat")
        return key, base, model
    key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return key, base, model


def _llm_summarize(item: dict[str, Any]) -> dict[str, str] | None:
    key, base, model = _llm_base()
    if not key:
        return None
    prompt = f"""你是中文自媒体选题助手。根据下面英文新闻，写适合发社交媒体的中文素材。
要求：
1. 只保留大众关心、容易站队/吵架的点；不要学术腔。
2. title_zh：一句有冲击力的中文标题（可略带情绪，但不要造谣）。
3. summary_zh：80–120字中文摘要，说清「发生了什么 + 为什么有人会吵」。
4. hook：一句可直接当发帖开头的钩子（中文）。
5. 不要编造原文没有的事实。

来源：{item.get('source')}
英文标题：{item.get('title')}
英文摘要：{item.get('summary_en')}
链接：{item.get('link')}

只输出 JSON：{{"title_zh":"...","summary_zh":"...","hook":"..."}}"""

    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.4,
                    "messages": [
                        {"role": "system", "content": "你只输出合法 JSON，不要 Markdown。"},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            data = json.loads(content)
            return {
                "title_zh": str(data.get("title_zh", "")).strip(),
                "summary_zh": str(data.get("summary_zh", "")).strip(),
                "hook": str(data.get("hook", "")).strip(),
            }
    except Exception:
        return None


def _looks_zh(text: str) -> bool:
    return len(re.findall(r"[\u4e00-\u9fff]", text or "")) >= 4


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    llm = _llm_summarize(item) if _has_llm() else None
    if llm and llm.get("summary_zh"):
        return {**item, **llm, "summary_mode": "llm"}

    title = item.get("title", "") or ""
    body = item.get("summary_en") or ""
    tags = "、".join(item.get("tags") or [])

    # 已是中文（国内热榜 / 中文媒体 / 中文推文）：不再机翻
    if item.get("lang") == "zh" or _looks_zh(title):
        summary_zh = body if _looks_zh(body) else (body or "热榜话题，可直接结合原文链接发文。")
        if len(summary_zh) > 180:
            summary_zh = summary_zh[:180] + "…"
        hook = f"【{tags or '中国热点'}】{title}"
        return {
            **item,
            "title_zh": title,
            "summary_zh": summary_zh,
            "hook": hook,
            "summary_mode": "zh-native",
        }

    title_zh = _translate(title)
    parts = re.split(r"(?<=[.!?])\s+", body or title)
    lead = " ".join(parts[:2]) if parts else title
    time.sleep(0.35)
    summary_zh = _translate(lead)
    hook = f"【{tags or '热点'}】{title_zh}"
    return {
        **item,
        "title_zh": title_zh,
        "summary_zh": summary_zh,
        "hook": hook,
        "summary_mode": "translate",
    }


def summarize_many(items: list[dict[str, Any]], limit: int = 22) -> list[dict[str, Any]]:
    # 尽量中英 / 多标签混排，避免刷屏同一来源
    picked: list[dict[str, Any]] = []
    by_source: dict[str, int] = {}
    for item in items:
        sid = item.get("source_id") or ""
        if by_source.get(sid, 0) >= 4:
            continue
        picked.append(item)
        by_source[sid] = by_source.get(sid, 0) + 1
        if len(picked) >= limit:
            break

    out: list[dict[str, Any]] = []
    for item in picked:
        try:
            out.append(summarize_item(item))
        except Exception as exc:
            out.append(
                {
                    **item,
                    "title_zh": item.get("title", ""),
                    "summary_zh": f"（摘要失败：{exc}）",
                    "hook": item.get("title", ""),
                    "summary_mode": "error",
                }
            )
    return out
