"""RSS sources and viral / conflict scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass

# 只收新闻/评论向源；避开纯论文 feed
FEEDS: list[dict[str, str]] = [
    {"id": "nature-latest", "name": "Nature 最新新闻", "url": "https://www.nature.com/latest-news.rss"},
    {"id": "nature-news", "name": "Nature 新闻", "url": "https://www.nature.com/nature/articles?type=news&format=rss"},
    {"id": "nature-nv", "name": "Nature 评论", "url": "https://www.nature.com/nature/articles?type=news-and-views&format=rss"},
    {"id": "econ-world", "name": "经济学人·世界", "url": "https://www.economist.com/the-world-this-week/rss.xml"},
    {"id": "econ-us", "name": "经济学人·美国", "url": "https://www.economist.com/united-states/rss.xml"},
    {"id": "econ-china", "name": "经济学人·中国", "url": "https://www.economist.com/china/rss.xml"},
    {"id": "econ-biz", "name": "经济学人·商业", "url": "https://www.economist.com/business/rss.xml"},
    {"id": "econ-fin", "name": "经济学人·财经", "url": "https://www.economist.com/finance-and-economics/rss.xml"},
    {"id": "econ-sci", "name": "经济学人·科技", "url": "https://www.economist.com/science-and-technology/rss.xml"},
    {"id": "bbc-world", "name": "BBC 世界", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"id": "bbc-tech", "name": "BBC 科技", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    {"id": "bbc-zh", "name": "BBC 中文", "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"},
    {"id": "ft-zh", "name": "FT 中文网", "url": "https://www.ftchinese.com/rss/news"},
    {"id": "thepaper", "name": "澎湃新闻", "url": "https://feedx.net/rss/thepaper.xml"},
    {"id": "weibo-rss", "name": "微博热搜RSS", "url": "https://decemberpei.cyou/rssbox/weibo-realtimehot.xml"},
    {"id": "thepaper-hot-rss", "name": "澎湃热榜RSS", "url": "https://decemberpei.cyou/rssbox/thepaper.xml"},
    {"id": "kr36", "name": "36氪", "url": "https://36kr.com/feed"},
    {"id": "huxiu", "name": "虎嗅", "url": "https://rss.huxiu.com/"},
    {"id": "solidot", "name": "Solidot", "url": "https://www.solidot.org/index.rss"},
    {"id": "techcrunch-ai", "name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"id": "theverge", "name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
    {"id": "decrypt", "name": "Decrypt 加密", "url": "https://decrypt.co/feed"},
    {"id": "mit-tech", "name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
]

# 能站队、能吵架、大众关心
BOOST = [
    r"\btrump\b", r"\belection\b", r"\bwar\b", r"\bukraine\b", r"\bgaza\b", r"\bisrael\b",
    r"\bchina\b", r"\btaiwan\b", r"\bimmi\w*", r"\bborder\b", r"\bsanction\b",
    r"\blayoff\b", r"\bfired\b", r"\bunemployment\b", r"\bwage\b", r"\bstrike\b",
    r"\bmonopol\w*", r"\bantitrust\b", r"\blawsuit\b", r"\bsue[ds]?\b", r"\bscandal\b",
    r"\bcensor\w*", r"\bbias\b", r"\bbanned\b", r"\bban\b", r"\bregulat\w*",
    r"\bopenai\b", r"\banthropic\b", r"\bgemini\b", r"\bchatgpt\b", r"\bclaude\b",
    r"\bgrok\b", r"\bdeepseek\b", r"\billama\b", r"\bai model\b", r"\bartificial intelligence\b",
    r"\bagi\b", r"\bsuperintelligence\b", r"\bjob[s]?\b.*(ai|robot)", r"\bai\b.*(job|work|replace)",
    r"\bcrypto\b", r"\bbitcoin\b", r"\bethereum\b", r"\bstablecoin\b", r"\bsec\b",
    r"\bcrash\b", r"\bplung\w*", r"\brally\b", r"\bbubble\b", r"\bfraud\b", r"\bponzi\b",
    r"\bharvard\b", r"\bstanford\b", r"\bmit\b", r"\buniversity\b", r"\bdei\b",
    r"\btuition\b", r"\badmission\b", r"\bclimate\b", r"\bcarbon\b", r"\bpandemic\b",
    r"\bvaccine\b", r"\bgene edit\w*", r"\bcrispr\b", r"\blongevity\b", r"\bobesity\b",
    r"\bcancer\w*", r"\bfertility\b", r"\bibuprofen\b", r"\bmicroplastic\b",
    r"\belon\b", r"\bmusk\b", r"\baltman\b", r"\bzuckerberg\b", r"\bbessent\b",
    r"\btariff\b", r"\binflation\b", r"\bfed\b", r"\brecession\b", r"\bstock market\b",
    r"\bprivacy\b", r"\bsurveillance\b", r"\bdeepfake\b", r"\bcopyright\b",
]

# 太学术 / 高深 → 直接降权或剔除
PENALTY = [
    r"\bmethodology\b", r"\bmeta-analysis\b", r"\bcrystallograph\w*", r"\bproteomic\w*",
    r"\bin vitro\b", r"\bin vivo\b", r"\btranscriptom\w*", r"\bepigenomic\w*",
    r"\bassay\b", r"\bpolymerase\b", r"\bnanoscale\b", r"\bspectroscop\w*",
    r"\btheorem\b", r"\blemma\b", r"\bcovariate\b", r"\bpreprint\b",
    r"\bsupplementary information\b", r"\bretraction watch\b",
    r"\bconference abstract\b", r"\bpeer review\b",
]

TAG_RULES: list[tuple[str, list[str]]] = [
    ("政治对立", [r"\belection\b", r"\btrump\b", r"\bwar\b", r"\bimmi\w*", r"\bsanction\b", r"\btariff\b", r"特朗普", r"制裁", r"关税"]),
    ("AI模型", [r"\bopenai\b", r"\banthropic\b", r"\bgemini\b", r"\bchatgpt\b", r"\bclaude\b", r"\bdeepseek\b", r"\bai model\b", r"\bagi\b", r"\bartificial intelligence\b", r"大模型"]),
    ("科技公司", [r"\bgoogle\b", r"\bapple\b", r"\bmeta\b", r"\bamazon\b", r"\bmicrosoft\b", r"\bnvidia\b", r"\blayoff\b", r"\bantitrust\b", r"裁员", r"华为", r"字节"]),
    ("科研争议", [r"\bnature\b", r"\bclimate\b", r"\bcrispr\b", r"\bvaccine\b", r"\blongevity\b", r"\bmicroplastic\b", r"学术造假"]),
    ("高校", [r"\buniversity\b", r"\bharvard\b", r"\bstanford\b", r"\bdei\b", r"\badmission\b", r"\btuition\b", r"清华", r"北大", r"学历"]),
    ("股市", [r"\bstock\b", r"\bwall street\b", r"\binflation\b", r"\bfed\b", r"\brecession\b", r"\bcrash\b", r"A股", r"暴跌", r"金价"]),
    ("加密货币", [r"\bcrypto\b", r"\bbitcoin\b", r"\bethereum\b", r"\bstablecoin\b", r"\bsec\b.*crypto", r"比特币", r"虚拟币"]),
    ("中国热点", [r"中国", r"北京", r"上海", r"微信", r"微博", r"抖音", r"字节", r"华为", r"A股", r"清北"]),
]


@dataclass
class ScoredItem:
    score: int
    tags: list[str]
    drop: bool


def _count(patterns: list[str], text: str) -> int:
    n = 0
    for p in patterns:
        if re.search(p, text, re.I):
            n += 1
    return n


def score_item(title: str, summary: str, source_id: str) -> ScoredItem:
    blob = f"{title}\n{summary}"
    boost = _count(BOOST, blob)
    penalty = _count(PENALTY, blob)

    # Nature 研究通讯若无有学术词、没有大众钩子 → 丢掉
    drop = False
    if penalty >= 2 and boost == 0:
        drop = True
    if source_id.startswith("nature") and boost == 0 and penalty >= 1:
        drop = True
    # 标题像论文题目（冒号+极长、满是专有名词）且无 boost
    if boost == 0 and len(title) > 120 and ":" in title:
        drop = True

    score = boost * 12 - penalty * 8
    # 来源加权：大众媒体略高，方便发文
    if source_id.startswith("econ") or source_id.startswith("bbc"):
        score += 3
    if source_id.startswith("nature") and boost > 0:
        score += 5  # Nature 牌子本身有流量
    if source_id in {"techcrunch-ai", "decrypt", "theverge", "mit-tech"}:
        score += 2
    if source_id in {"bbc-zh", "ft-zh", "thepaper", "weibo-rss", "kr36", "huxiu", "solidot", "thepaper-hot-rss"}:
        score += 4
        # 中文源：用中文钩子再加一次分
        from cn_hot import CN_BOOST, _count as cn_count

        cn_boost = cn_count(CN_BOOST, blob)
        score += cn_boost * 8
        if cn_boost and boost == 0:
            drop = False
            boost = cn_boost

    tags: list[str] = []
    for tag, pats in TAG_RULES:
        if _count(pats, blob):
            tags.append(tag)
    if source_id in {"bbc-zh", "ft-zh", "thepaper", "weibo-rss", "kr36", "huxiu", "thepaper-hot-rss"}:
        if "中国热点" not in tags:
            tags.append("中国热点")
    if not tags and boost > 0:
        tags.append("大众话题")

    # 至少要命中一个流量钩子
    if boost == 0:
        drop = True

    return ScoredItem(score=score, tags=tags, drop=drop)
