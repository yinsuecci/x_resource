"""Viral news desk — local server for posting-ready Chinese digests."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from fetcher import fetch_all
from images import fetch_images
from summarizer import summarize_many
import httpx
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / "cache.json"
DATA.mkdir(exist_ok=True)

app = FastAPI(title="流量新闻台")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "items": [],
    "errors": [],
    "updated_at": None,
    "refreshing": False,
    "message": "",
}


def _load_cache() -> None:
    if not CACHE.exists():
        return
    try:
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
        _state["items"] = raw.get("items", [])
        _state["errors"] = raw.get("errors", [])
        _state["updated_at"] = raw.get("updated_at")
    except Exception:
        pass


def _save_cache() -> None:
    payload = {
        "items": _state["items"],
        "errors": _state["errors"],
        "updated_at": _state["updated_at"],
    }
    CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_pipeline(force: bool = False) -> dict[str, Any]:
    with _lock:
        if _state["refreshing"]:
            return {"ok": False, "message": "正在刷新，请稍候…", "refreshing": True}
        # 15 分钟内有缓存且非强制 → 直接返回
        if not force and _state["items"] and _state["updated_at"]:
            try:
                ts = datetime.fromisoformat(_state["updated_at"])
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                if age < 15 * 60:
                    return {
                        "ok": True,
                        "cached": True,
                        "items": _state["items"],
                        "errors": _state["errors"],
                        "updated_at": _state["updated_at"],
                        "message": "使用近期缓存（15 分钟内）",
                    }
            except Exception:
                pass
        _state["refreshing"] = True
        _state["message"] = "抓取 RSS 并筛选流量话题…"

    try:
        clean, errors = fetch_all()
        with _lock:
            _state["message"] = f"已筛出 {len(clean)} 条，正在生成中文摘要…"
        summarized = summarize_many(clean, limit=22)
        now = datetime.now(timezone.utc).isoformat()
        with _lock:
            _state["items"] = summarized
            _state["errors"] = errors
            _state["updated_at"] = now
            _state["message"] = "完成"
            _save_cache()
        return {
            "ok": True,
            "cached": False,
            "items": summarized,
            "errors": errors,
            "updated_at": now,
            "message": "刷新完成",
        }
    except Exception as exc:
        with _lock:
            _state["message"] = f"失败：{exc}"
        return {"ok": False, "message": str(exc), "items": _state["items"], "errors": _state["errors"]}
    finally:
        with _lock:
            _state["refreshing"] = False


_load_cache()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
def status() -> JSONResponse:
    return JSONResponse(
        {
            "refreshing": _state["refreshing"],
            "updated_at": _state["updated_at"],
            "count": len(_state["items"]),
            "message": _state["message"],
            "has_cache": bool(_state["items"]),
        }
    )


@app.get("/api/feed")
def feed() -> JSONResponse:
    return JSONResponse(
        {
            "items": _state["items"],
            "errors": _state["errors"],
            "updated_at": _state["updated_at"],
            "refreshing": _state["refreshing"],
            "message": _state["message"],
        }
    )


@app.post("/api/refresh")
def refresh(force: bool = True) -> JSONResponse:
    result = refresh_pipeline(force=force)
    return JSONResponse(result)


@app.get("/api/images")
def api_images(category: str = Query("全部", description="全部|二次元|风景")) -> JSONResponse:
    if category not in {"全部", "二次元", "风景"}:
        category = "全部"
    result = fetch_images(category=category)
    return JSONResponse(result)


@app.get("/api/img-proxy")
def img_proxy(url: str = Query(..., min_length=8)) -> Response:
    """仅代理 Pixiv CDN 缩略图（需 Referer），供页面预览。"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host.endswith("pximg.net"):
        raise HTTPException(status_code=400, detail="host not allowed")
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.pixiv.net/",
                },
            )
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    ctype = resp.headers.get("content-type", "image/jpeg")
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=502, detail="not an image")
    return Response(content=resp.content, media_type=ctype, headers={"Cache-Control": "public, max-age=3600"})


def warmup() -> None:
    time.sleep(0.8)
    if not _state["items"]:
        refresh_pipeline(force=True)


threading.Thread(target=warmup, daemon=True).start()
