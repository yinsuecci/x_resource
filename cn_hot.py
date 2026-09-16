"""Chinese hotboards + conflict-oriented scoring helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "ViralNewsDesk/1.0"
)

# 国内热榜（公开聚合 API）
HOTBOARDS: list[dict[str, str]] = [
    {"id": "cn-weibo", "name": "微博热搜", "type": "weibo", "tag": "中国热点"},
    {"id": "cn-zhihu", "name": "知乎热榜", "type": "zhihu", "tag": "中国热点"},
    {"id": "cn-baidu", "name": "百度热搜", "type": "baidu", "tag": "中国热点"},
    {"id": "cn-toutiao", "name": "今日头条热榜", "type": "toutiao", "tag": "中国热点"},
    {"id": "cn-36kr", "name": "36氪热榜", "type": "36kr", "tag": "中国热点"},
    {"id": "cn-ithome", "name": "IT之家热榜", "type": "ithome", "tag": "科技公司"},
    {"id": "cn-thepaper", "name": "澎湃热榜", "type": "thepaper", "tag": "中国热点"},
]

# 娱乐向、难站队 → 丢
CN_DROP = [
    r"恋情", r"官宣结婚", r"官宣分手", r"综艺", r"追剧", r"剧透", r"美妆", r"穿搭",
    r"减肥餐", r"食谱", r"萌宠", r"明星同款", r"演唱会歌单", r"舞蹈挑战",
    r"擦丝器", r"懒人不开火", r"今日穿什么",
]

# 中文流量钩子
CN_BOOST = [
    r"裁员", r"垄断", r"反垄断", r"暴跌", r"暴涨", r"崩盘", r"跑路", r"造假", r"丑闻", r"塌房",
    r"封杀", r"抵制", r"制裁", r"关税", r"降息", r"加息", r"美联储", r"特朗普", r"川普",
    r"大模型", r"人工智能", r"\bAI\b", r"DeepSeek", r"ChatGPT", r"OpenAI", r"Claude", r"Gemini",
    r"开源", r"闭源", r"英伟达", r"黄仁勋", r"马斯克", r"奥特曼", r"字节", r"腾讯", r"阿里",
    r"华为", r"小米", r"苹果", r"iPhone", r"芯片", r"出口管制",
    r"比特币", r"加密货币", r"虚拟币", r"稳定币", r"币安", r"交易所",
    r"房价", r"楼市", r"股市", r"A股", r"港股", r"纳斯达克", r"金价", r"通胀",
    r"高考", r"考研", r"学历", r"第一学历", r"清北", r"清华", r"北大", r"哈佛", r"斯坦福",
    r"公务员", r"编制", r"失业", r"应届生", r"实习", r"35岁",
    r"数据泄露", r"隐私", r"监控", r"审查", r"言论", r"女权", r"性别",
    r"战争", r"冲突", r"台海", r"南海", r"中美", r"俄乌", r"以巴",
    r"疫苗", r"癌症", r"长寿", r"基因编辑", r"学术造假", r"论文",
    r"图灵班", r"名校", r"面试", r"拒录", r"歧视",
]

CN_TAG_RULES: list[tuple[str, list[str]]] = [
    ("政治对立", [r"特朗普", r"川普", r"制裁", r"关税", r"战争", r"台海", r"中美", r"冲突"]),
    ("AI模型", [r"大模型", r"人工智能", r"DeepSeek", r"ChatGPT", r"OpenAI", r"Claude", r"Gemini", r"\bAI\b"]),
    ("科技公司", [r"苹果", r"华为", r"小米", r"字节", r"腾讯", r"阿里", r"英伟达", r"裁员", r"芯片"]),
    ("高校", [r"清华", r"北大", r"哈佛", r"斯坦福", r"学历", r"高考", r"考研", r"名校", r"图灵班"]),
    ("股市", [r"股市", r"A股", r"港股", r"暴跌", r"暴涨", r"金价", r"降息", r"加息", r"美联储"]),
    ("加密货币", [r"比特币", r"加密", r"虚拟币", r"稳定币", r"币安"]),
    ("中国热点", [r".*"]),  # 热榜默认带中国热点，下面单独处理
]


def _count(patterns: list[str], text: str) -> int:
    n = 0
    for p in patterns:
        if re.search(p, text, re.I):
            n += 1
    return n


def score_cn_hot(title: str, summary: str, rank: int) -> tuple[int, list[str], bool]:
    blob = f"{title}\n{summary}"
    if _count(CN_DROP, blob):
        return 0, [], True

    boost = _count(CN_BOOST, blob)
    # 热榜本身有流量：名次越前分越高
    score = max(0, 40 - rank) + boost * 10
    tags = ["中国热点"]
    for tag, pats in CN_TAG_RULES:
        if tag == "中国热点":
            continue
        if _count(pats, blob):
            tags.append(tag)

    # 纯娱乐/无钩子且排名靠后 → 丢；前 8 名即使弱钩子也留一点（热搜本身可发）
    drop = False
    if boost == 0 and rank > 8:
        drop = True
    if boost == 0 and rank <= 8:
        score = max(score, 18)
        if "大众话题" not in tags:
            tags.append("大众话题")

    return score, tags, drop


def fetch_hotboards(timeout: float = 15.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as client:
        for board in HOTBOARDS:
            url = f"https://uapis.cn/api/v1/misc/hotboard?type={board['type']}"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("list") or []
            except Exception as exc:
                errors.append(
                    {"_error": True, "source_id": board["id"], "source": board["name"], "error": str(exc)}
                )
                continue

            for row in rows[:40]:
                title = (row.get("title") or "").strip()
                link = (row.get("url") or row.get("mobil_url") or "").strip()
                if not title:
                    continue
                if not link:
                    link = f"https://www.baidu.com/s?wd={title}"
                rank = int(row.get("index") or row.get("rank") or 99)
                hot = row.get("hot") or row.get("hotValue") or ""
                summary = f"热度：{hot}" if hot else f"{board['name']} 第 {rank} 名"
                score, tags, drop = score_cn_hot(title, summary, rank)
                if drop or score < 14:
                    continue
                iid = hashlib.sha1(f"{board['id']}|{title}".encode("utf-8")).hexdigest()[:16]
                items.append(
                    {
                        "id": iid,
                        "source_id": board["id"],
                        "source": board["name"],
                        "title": title,
                        "summary_en": summary,
                        "link": link,
                        "published": data.get("update_time"),
                        "score": score,
                        "tags": tags,
                        "lang": "zh",
                    }
                )
    return items, errors
