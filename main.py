"""
AstrBot 推特 RSS 智能订阅、分群独立标签过滤与每日24h新闻简报插件 (astrbot_plugin_twitter_rss)
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import email.utils
import hashlib
import html
import json
import mimetypes
import pathlib
import random
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

# 直接内嵌最新 HTML 模板，确保在 AstrBot 热重载 main.py 时不会因 sys.modules 缓存旧的 templates.py 而导致样式不更新
TWEET_CARD_TMPL = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<style>\n  * {\n    box-sizing: border-box;\n    margin: 0;\n    padding: 0;\n  }\n  html {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #fefefe;\n  }\n  body {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #ffffff;\n    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;\n    color: #0f172a;\n  }\n  .card {\n    width: 100%;\n    background: #ffffff;\n    padding: 28px 32px;\n  }\n  .header {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    margin-bottom: 16px;\n  }\n  .author-box {\n    display: flex;\n    align-items: center;\n    gap: 14px;\n  }\n  .avatar {\n    width: 52px;\n    height: 52px;\n    border-radius: 50%;\n    background: #1d9bf0;\n    color: #ffffff;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    font-size: 22px;\n    font-weight: 700;\n    overflow: hidden;\n    flex-shrink: 0;\n    border: 1px solid #e2e8f0;\n  }\n  .avatar img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n  }\n  .author-meta {\n    display: flex;\n    flex-direction: column;\n    gap: 3px;\n  }\n  .author-name-row {\n    display: flex;\n    align-items: center;\n    gap: 6px;\n  }\n  .author-name {\n    font-size: 19px;\n    font-weight: 800;\n    color: #0f172a;\n  }\n  .verified-badge {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    width: 18px;\n    height: 18px;\n    border-radius: 50%;\n    background: #1d9bf0;\n    color: #ffffff;\n    font-size: 11px;\n    font-weight: 900;\n  }\n  .author-sub {\n    font-size: 14px;\n    color: #64748b;\n    font-weight: 500;\n  }\n  .brand-logo {\n    width: 34px;\n    height: 34px;\n    border-radius: 9px;\n    background: #0f172a;\n    color: #ffffff;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    font-size: 19px;\n    font-weight: 900;\n  }\n  .tweet-section {\n    margin-bottom: 12px;\n  }\n  .tweet-body {\n    font-size: 18px;\n    line-height: 1.65;\n    color: #0f172a;\n    white-space: pre-wrap;\n    word-break: break-word;\n  }\n  .tweet-tags {\n    margin-top: 4px;\n    font-size: 17px;\n    line-height: 1.6;\n    color: #1d9bf0;\n    font-weight: 500;\n    word-break: break-word;\n  }\n  .trans-section {\n    margin-top: 8px;\n    margin-bottom: 14px;\n    padding-top: 10px;\n    border-top: 1px solid #f1f5f9;\n  }\n  .trans-body {\n    font-size: 16.5px;\n    line-height: 1.65;\n    color: #334155;\n    white-space: pre-wrap;\n    word-break: break-word;\n  }\n  .trans-tags {\n    margin-top: 4px;\n    font-size: 16.5px;\n    line-height: 1.6;\n    color: #1d9bf0;\n    font-weight: 500;\n    word-break: break-word;\n  }\n  .media-grid {\n    display: grid;\n    gap: 10px;\n    margin-top: 12px;\n    border-radius: 16px;\n    overflow: hidden;\n  }\n  .media-grid.count-1 {\n    grid-template-columns: 1fr;\n  }\n  .media-grid.count-2, .media-grid.count-3, .media-grid.count-4 {\n    grid-template-columns: 1fr 1fr;\n  }\n  .media-item {\n    width: 100%;\n    overflow: hidden;\n    background: #f8fafc;\n    border-radius: 14px;\n    border: 1px solid #e2e8f0;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n  }\n  .media-grid.count-1 .media-item img {\n    width: 100%;\n    height: auto;\n    display: block;\n  }\n  .media-grid.count-2 .media-item img,\n  .media-grid.count-3 .media-item img,\n  .media-grid.count-4 .media-item img {\n    width: 100%;\n    height: 320px;\n    object-fit: cover;\n    display: block;\n  }\n</style>\n</head>\n<body>\n  <div class="card" id="tweet-card">\n    <div class="header">\n      <div class="author-box">\n        <div class="avatar">\n          {% if avatar_src %}\n          <img src="{{ avatar_src }}" onerror="this.style.display=\'none\';this.parentNode.innerText=\'{{ author_initial }}\';" />\n          {% else %}\n          {{ author_initial }}\n          {% endif %}\n        </div>\n        <div class="author-meta">\n          <div class="author-name-row">\n            <span class="author-name">{{ author_name }}</span>\n            <span class="verified-badge">✓</span>\n          </div>\n          <span class="author-sub">@{{ username }}{% if pub_date %} · {{ pub_date }}{% endif %}</span>\n        </div>\n      </div>\n      <div class="brand-logo">𝕏</div>\n    </div>\n\n    {% if orig_body or orig_tags %}\n    <div class="tweet-section">\n      {% if orig_body %}\n      <div class="tweet-body">{{ orig_body }}</div>\n      {% endif %}\n      {% if orig_tags %}\n      <div class="tweet-tags">{{ orig_tags|join(\' \') }}</div>\n      {% endif %}\n    </div>\n    {% endif %}\n\n    {% if translated_body or translated_tags %}\n    <div class="trans-section">\n      {% if orig_body and translated_body %}\n      <div class="trans-body">{{ translated_body }}</div>\n      {% endif %}\n      {% if translated_tags %}\n      <div class="trans-tags">{{ translated_tags|join(\' \') }}</div>\n      {% endif %}\n    </div>\n    {% endif %}\n\n    {% if display_images %}\n    <div class="media-grid count-{{ display_images|length if display_images|length <= 4 else 4 }}">\n      {% for img_src in display_images[:4] %}\n      <div class="media-item">\n        <img src="{{ img_src }}" onerror="this.parentNode.style.display=\'none\';" />\n      </div>\n      {% endfor %}\n    </div>\n    {% endif %}\n  </div>\n</body>\n</html>\n'

DAILY_DIGEST_TMPL = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<style>\n  * {\n    box-sizing: border-box;\n    margin: 0;\n    padding: 0;\n  }\n  html {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #fefefe;\n  }\n  body {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #ffffff;\n    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;\n    color: #181e29;\n    -webkit-font-smoothing: antialiased;\n  }\n  .digest-page {\n    width: 100%;\n    background: linear-gradient(\n      160deg,\n      rgba(var(--theme-rgb, 245, 242, 255), 0.65) 0%,\n      #ffffff 42%,\n      rgba(var(--theme-soft-rgb, 239, 247, 255), 0.55) 100%\n    );\n    padding: 34px 36px 38px 36px;\n    position: relative;\n    overflow: hidden;\n  }\n  .page-deco-circle {\n    position: absolute;\n    top: -90px;\n    right: -70px;\n    width: 260px;\n    height: 260px;\n    border-radius: 50%;\n    background: radial-gradient(\n      circle,\n      rgba(var(--theme-accent-rgb, 124, 58, 237), 0.10) 0%,\n      rgba(var(--theme-accent-rgb, 124, 58, 237), 0) 70%\n    );\n    pointer-events: none;\n    z-index: 0;\n  }\n  .digest-header {\n    position: relative;\n    z-index: 2;\n    display: flex;\n    align-items: flex-end;\n    justify-content: space-between;\n    gap: 20px;\n  }\n  .header-left {\n    display: flex;\n    align-items: center;\n    gap: 16px;\n  }\n  .header-accent-bar {\n    width: 8px;\n    height: 46px;\n    border-radius: 99px;\n    background: var(--theme-accent, #7c3aed);\n    box-shadow: 0 4px 14px rgba(var(--theme-accent-rgb, 124, 58, 237), 0.30);\n    flex-shrink: 0;\n  }\n  .header-title-wrap {\n    display: flex;\n    flex-direction: column;\n    gap: 4px;\n  }\n  .header-title {\n    font-size: 32px;\n    font-weight: 900;\n    color: #141923;\n    letter-spacing: 1.5px;\n    line-height: 1.1;\n  }\n  .header-sub {\n    font-size: 11px;\n    font-weight: 800;\n    letter-spacing: 2.4px;\n    text-transform: uppercase;\n    color: var(--theme-accent, #7c3aed);\n    opacity: 0.88;\n  }\n  .header-right {\n    display: flex;\n    flex-direction: column;\n    align-items: flex-end;\n    gap: 7px;\n  }\n  .date-badge {\n    background: rgba(var(--theme-rgb, 245, 242, 255), 0.95);\n    color: var(--theme-accent, #7c3aed);\n    border: 1px solid var(--theme-border, #ddd6fe);\n    padding: 5px 14px;\n    border-radius: 99px;\n    font-size: 12.5px;\n    font-weight: 800;\n    letter-spacing: 0.8px;\n  }\n  .stats-row {\n    display: flex;\n    align-items: center;\n    gap: 8px;\n    font-size: 12px;\n    font-weight: 600;\n    color: #64748b;\n  }\n  .stats-row strong {\n    color: #1e293b;\n    font-weight: 800;\n  }\n  .stats-dot {\n    width: 4px;\n    height: 4px;\n    border-radius: 50%;\n    background: var(--theme-accent, #7c3aed);\n    opacity: 0.45;\n  }\n  .header-divider {\n    position: relative;\n    z-index: 2;\n    height: 2px;\n    margin: 20px 0 24px 0;\n    border-radius: 99px;\n    background: linear-gradient(\n      90deg,\n      var(--theme-accent, #7c3aed) 0%,\n      var(--theme-border, #ddd6fe) 38%,\n      rgba(226, 232, 240, 0.35) 100%\n    );\n  }\n  .digest-list {\n    position: relative;\n    z-index: 2;\n    display: flex;\n    flex-direction: column;\n    gap: 18px;\n  }\n  .news-card {\n    position: relative;\n    width: 100%;\n    border-radius: 22px;\n    overflow: hidden;\n    background: linear-gradient(\n      135deg,\n      rgb(var(--card-rgb)) 0%,\n      rgb(var(--card-soft-rgb)) 100%\n    );\n    border: 1.5px solid var(--card-border);\n    box-shadow:\n      0 10px 26px -10px rgba(var(--accent-rgb), 0.14),\n      inset 0 1px 0 rgba(255, 255, 255, 0.88);\n    display: flex;\n    align-items: stretch;\n  }\n  .news-card.has-image {\n    min-height: 178px;\n  }\n  .news-card.no-image {\n    min-height: 136px;\n  }\n  .card-accent-strip {\n    width: 6px;\n    background: var(--accent);\n    flex-shrink: 0;\n    z-index: 3;\n  }\n  .card-body {\n    position: relative;\n    z-index: 3;\n    display: flex;\n    flex-direction: column;\n    justify-content: center;\n  }\n  .news-card.has-image .card-body {\n    width: 64%;\n    padding: 22px 18px 22px 22px;\n  }\n  .news-card.no-image .card-body {\n    width: 100%;\n    padding: 22px 28px 22px 22px;\n  }\n  .card-meta {\n    display: flex;\n    align-items: center;\n    flex-wrap: wrap;\n    gap: 8px;\n    margin-bottom: 9px;\n  }\n  .card-num {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    height: 22px;\n    padding: 0 9px;\n    border-radius: 99px;\n    background: var(--accent);\n    color: #ffffff;\n    font-size: 11.5px;\n    font-weight: 800;\n    letter-spacing: 0.6px;\n    box-shadow: 0 2px 6px rgba(var(--accent-rgb), 0.25);\n  }\n  .card-cat {\n    display: inline-flex;\n    align-items: center;\n    height: 22px;\n    padding: 0 10px;\n    border-radius: 99px;\n    background: var(--tag-bg);\n    color: var(--accent);\n    border: 1px solid rgba(var(--accent-rgb), 0.22);\n    font-size: 11.5px;\n    font-weight: 700;\n    letter-spacing: 0.3px;\n  }\n  .card-author {\n    font-size: 12.5px;\n    font-weight: 700;\n    color: #334155;\n  }\n  .card-time {\n    font-size: 11.5px;\n    font-weight: 500;\n    color: #64748b;\n  }\n  .card-title {\n    font-size: 19px;\n    font-weight: 850;\n    color: #141923;\n    line-height: 1.38;\n    margin-bottom: 7px;\n    letter-spacing: 0.2px;\n    text-shadow: 0 1px 10px rgba(var(--card-rgb), 0.95);\n  }\n  .card-summary {\n    font-size: 14.5px;\n    font-weight: 500;\n    color: #334155;\n    line-height: 1.66;\n    word-break: break-word;\n    text-shadow: 0 1px 8px rgba(var(--card-rgb), 0.95);\n  }\n  .card-artwork {\n    position: absolute;\n    top: 0;\n    right: 0;\n    bottom: 0;\n    width: 58%;\n    z-index: 1;\n    overflow: hidden;\n  }\n  .card-artwork img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    object-position: center 20%;\n    display: block;\n  }\n  .card-artwork-fade {\n    position: absolute;\n    inset: 0;\n    z-index: 2;\n    background:\n      linear-gradient(\n        90deg,\n        rgba(var(--card-rgb), 1) 0%,\n        rgba(var(--card-rgb), 0.99) 14%,\n        rgba(var(--card-rgb), 0.92) 28%,\n        rgba(var(--card-rgb), 0.68) 46%,\n        rgba(var(--card-rgb), 0.26) 68%,\n        rgba(var(--card-rgb), 0.04) 86%,\n        rgba(var(--card-rgb), 0) 100%\n      ),\n      linear-gradient(\n        180deg,\n        rgba(var(--card-rgb), 0.14) 0%,\n        rgba(var(--card-rgb), 0) 22%,\n        rgba(var(--card-rgb), 0) 78%,\n        rgba(var(--card-rgb), 0.18) 100%\n      );\n  }\n  .card-watermark-num {\n    position: absolute;\n    right: 22px;\n    bottom: -10px;\n    font-size: 76px;\n    font-weight: 900;\n    line-height: 1;\n    letter-spacing: -2px;\n    color: rgba(var(--accent-rgb), 0.07);\n    pointer-events: none;\n    z-index: 1;\n    user-select: none;\n  }\n</style>\n</head>\n<body>\n  <div\n    class="digest-page"\n    style="\n      --theme-rgb: {{ theme.card_rgb }};\n      --theme-soft-rgb: {{ theme.card_soft_rgb }};\n      --theme-border: {{ theme.card_border }};\n      --theme-accent: {{ theme.accent }};\n      --theme-accent-rgb: {{ theme.accent_rgb }};\n    "\n  >\n    <div class="page-deco-circle"></div>\n\n    <div class="digest-header">\n      <div class="header-left">\n        <div class="header-accent-bar"></div>\n        <div class="header-title-wrap">\n          <div class="header-title">今日要闻</div>\n          <div class="header-sub">DAILY CURATED BRIEFING</div>\n        </div>\n      </div>\n\n      <div class="header-right">\n        <div class="date-badge">{{ date_str }}</div>\n        <div class="stats-row">\n          <span>24H 收录 <strong>{{ total_count }}</strong></span>\n          <span class="stats-dot"></span>\n          <span>精选 <strong>{{ items|length }}</strong></span>\n          <span class="stats-dot"></span>\n          <span>订阅 <strong>{{ account_count }}</strong></span>\n        </div>\n      </div>\n    </div>\n\n    <div class="header-divider"></div>\n\n    <div class="digest-list">\n      {% for item in items %}\n      <div\n        class="news-card {% if item.thumb_src %}has-image{% else %}no-image{% endif %}"\n        style="\n          --card-rgb: {{ item.palette.card_rgb }};\n          --card-soft-rgb: {{ item.palette.card_soft_rgb }};\n          --card-border: {{ item.palette.card_border }};\n          --accent: {{ item.palette.accent }};\n          --accent-rgb: {{ item.palette.accent_rgb }};\n          --tag-bg: {{ item.palette.tag_bg }};\n        "\n      >\n        <div class="card-accent-strip"></div>\n\n        <div class="card-body">\n          <div class="card-meta">\n            <span class="card-num">{{ "%02d"|format(loop.index) }}</span>\n            <span class="card-cat">{{ item.category or "资讯速递" }}</span>\n            <span class="card-author">@{{ item.username }}{% if item.author_name and item.author_name != item.username %} · {{ item.author_name }}{% endif %}</span>\n            {% if item.pub_date %}\n            <span class="card-time">{{ item.pub_date }}</span>\n            {% endif %}\n          </div>\n          <div class="card-title">{{ item.title }}</div>\n          <div class="card-summary">{{ item.summary }}</div>\n        </div>\n\n        {% if item.thumb_src %}\n        <div class="card-artwork">\n          <img src="{{ item.thumb_src }}" onerror="this.parentNode.style.display=\'none\';" />\n          <div class="card-artwork-fade"></div>\n        </div>\n        {% else %}\n        <div class="card-watermark-num">{{ "%02d"|format(loop.index) }}</div>\n        {% endif %}\n      </div>\n      {% endfor %}\n    </div>\n  </div>\n</body>\n</html>\n'


# 内置多源回退路由列表
FALLBACK_SOURCE_TEMPLATES = [
    "https://fxtwitter.com/{username}/feed.xml",
    "https://fixupx.com/{username}/feed.xml",
    "https://api.fxtwitter.com/2/profile/{username}/statuses",
    "https://rsshub.rssforever.com/twitter/user/{username}",
    "https://rsshub.pseudoyu.com/twitter/user/{username}",
    "https://hub.slarker.me/twitter/user/{username}",
    "https://nitter.poast.org/{username}/rss",
]


MACARON_PALETTES: list[dict[str, str]] = [
    {
        "name": "sakura_blush",
        "card_rgb": "255, 241, 246",
        "card_soft_rgb": "254, 226, 236",
        "card_border": "#F9C6DC",
        "accent": "#D6336C",
        "accent_rgb": "214, 51, 108",
        "tag_bg": "rgba(214, 51, 108, 0.10)",
    },
    {
        "name": "mint_seafoam",
        "card_rgb": "237, 251, 246",
        "card_soft_rgb": "214, 245, 234",
        "card_border": "#A7F3D0",
        "accent": "#0D9488",
        "accent_rgb": "13, 148, 136",
        "tag_bg": "rgba(13, 148, 136, 0.10)",
    },
    {
        "name": "apricot_cream",
        "card_rgb": "255, 246, 236",
        "card_soft_rgb": "254, 230, 206",
        "card_border": "#FED7AA",
        "accent": "#DD5B19",
        "accent_rgb": "221, 91, 25",
        "tag_bg": "rgba(221, 91, 25, 0.10)",
    },
    {
        "name": "taro_lavender",
        "card_rgb": "245, 242, 255",
        "card_soft_rgb": "232, 224, 255",
        "card_border": "#DDD6FE",
        "accent": "#7048E8",
        "accent_rgb": "112, 72, 232",
        "tag_bg": "rgba(112, 72, 232, 0.10)",
    },
    {
        "name": "soda_sky",
        "card_rgb": "239, 247, 255",
        "card_soft_rgb": "218, 236, 255",
        "card_border": "#BAE6FD",
        "accent": "#0284C7",
        "accent_rgb": "2, 132, 199",
        "tag_bg": "rgba(2, 132, 199, 0.10)",
    },
    {
        "name": "lemon_butter",
        "card_rgb": "254, 250, 232",
        "card_soft_rgb": "253, 239, 194",
        "card_border": "#FDE68A",
        "accent": "#C27803",
        "accent_rgb": "194, 120, 3",
        "tag_bg": "rgba(194, 120, 3, 0.11)",
    },
    {
        "name": "matcha_pistachio",
        "card_rgb": "241, 250, 240",
        "card_soft_rgb": "220, 243, 218",
        "card_border": "#BBF7D0",
        "accent": "#15803D",
        "accent_rgb": "21, 128, 61",
        "tag_bg": "rgba(21, 128, 61, 0.10)",
    },
    {
        "name": "berry_coral",
        "card_rgb": "255, 241, 242",
        "card_soft_rgb": "254, 222, 226",
        "card_border": "#FECDD3",
        "accent": "#E11D48",
        "accent_rgb": "225, 29, 72",
        "tag_bg": "rgba(225, 29, 72, 0.10)",
    },
]

_EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "\uFE0F"
    "]+",
    flags=re.UNICODE,
)

_FORBIDDEN_META_KEYWORDS = (
    "无法判断",
    "暂无法",
    "未进一步说明",
    "未进一步透露",
    "未透露",
    "尚未透露",
    "未提及",
    "尚未提及",
    "未包含可核验",
    "所提供素材未",
    "素材未包含",
    "尚不清楚",
    "暂不清楚",
    "未提供更多",
    "未给出更多",
    "未说明具体",
    "无法核实",
    "无法确认",
)


def _clean_digest_text(text: str, is_summary: bool = False) -> str:
    """移除 Emoji 及任何类似‘无法判断xxx’、‘未进一步说明xxx’的冗余废话分句"""
    if not text:
        return ""
    cleaned = _EMOJI_RE.sub("", str(text)).strip()
    if not is_summary:
        return cleaned

    sentences = re.split(r"([。；;！!])", cleaned)
    kept_parts: list[str] = []
    idx = 0
    while idx < len(sentences):
        seg = sentences[idx]
        punct = sentences[idx + 1] if idx + 1 < len(sentences) else ""
        idx += 2
        if not seg.strip():
            continue
        sub_clauses = re.split(r"([，,；;])", seg)
        filtered_clauses: list[str] = []
        c_idx = 0
        while c_idx < len(sub_clauses):
            c_seg = sub_clauses[c_idx]
            c_punct = sub_clauses[c_idx + 1] if c_idx + 1 < len(sub_clauses) else ""
            c_idx += 2
            if any(kw in c_seg for kw in _FORBIDDEN_META_KEYWORDS):
                break
            filtered_clauses.append(c_seg + c_punct)

        rebuilt = "".join(filtered_clauses).rstrip("，,；; ")
        if rebuilt and not any(kw in rebuilt for kw in _FORBIDDEN_META_KEYWORDS):
            kept_parts.append(rebuilt + (punct or "。"))

    result = "".join(kept_parts).strip().rstrip("；;，,") + ("。" if kept_parts else "")
    result = result.replace("。。", "。")
    return result or cleaned


@register(
    "astrbot_plugin_twitter_rss",
    "AstrBotUser",
    "按照推特 RSS 订阅获取推文，支持按群聊独立配置订阅账号与视觉标签过滤（必须包含+任意匹配+排除标签）、无黑边推文卡片渲染（含正文与蓝色标签翻译）+原图单独发送，以及每日24小时精选新闻长图推送",
    "v1.4.0",
    "https://github.com/AstrBotDevs/astrbot_plugin_twitter_rss",
)

class TwitterRssPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config: AstrBotConfig | dict[str, Any] = config if config is not None else {}

        # 自动检测并迁移旧版失效的 rsshub.app 官方默认地址
        curr_base = str(self.config.get("rss_base_url", "") or "").strip()
        if "rsshub.app/twitter/" in curr_base:
            self.config["rss_base_url"] = "https://fxtwitter.com/{username}/feed.xml"
            self._save_plugin_config()

        # 使用框架规范的 StarTools.get_data_dir 获取持久化数据目录
        try:
            data_dir = StarTools.get_data_dir("astrbot_plugin_twitter_rss")
        except TypeError:
            data_dir = StarTools.get_data_dir()
        self.data_dir = pathlib.Path(str(data_dir))
        self.image_cache_dir = self.data_dir / "image_cache"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.data_dir / "state.json"
        self.history_file = self.data_dir / "tweets_24h.json"

        self.state: dict[str, Any] = self._load_json_sync(
            self.state_file,
            default={
                "seen_ids": {},  # {f"{umo}::{account}": [tweet_id, ...]}
                "initialized_keys": [],  # [f"{umo}::{account}", ...]
                "last_digest_date": "",
                "group_umo_map": {},  # {group_id: unified_msg_origin}
            },
        )
        self.history_tweets: list[dict[str, Any]] = self._load_json_sync(
            self.history_file, default=[]
        )

        # 自动将旧版全局配置平滑迁移到按群聊分类的 group_subscriptions 中
        self._migrate_legacy_config()

        self.http_client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task | None = None
        self._digest_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._started = False

    def _migrate_legacy_config(self):
        """如果旧配置中有全局 twitter_accounts 或 push_targets，且 group_subscriptions 为空，则自动迁移"""
        groups = self.config.get("group_subscriptions")
        if isinstance(groups, list) and len(groups) > 0:
            return

        old_targets = [
            str(x).strip()
            for x in (self.config.get("push_targets", []) or [])
            if str(x).strip()
        ]
        old_accounts = [
            str(x).strip().lstrip("@")
            for x in (self.config.get("twitter_accounts", []) or [])
            if str(x).strip()
        ]
        if not old_targets and not old_accounts:
            return

        old_must = [
            str(x).strip()
            for x in (self.config.get("must_include_image_tags", []) or [])
            if str(x).strip()
        ]
        old_any = [
            str(x).strip()
            for x in (
                self.config.get("any_include_image_tags")
                or self.config.get("include_image_tags")
                or ["插画", "二次元"]
            )
            if str(x).strip()
        ]
        old_exc = [
            str(x).strip()
            for x in (
                self.config.get("exclude_image_tags")
                or ["NSFW", "血腥暴力", "广告二维码"]
            )
            if str(x).strip()
        ]

        migrated: list[dict[str, Any]] = []
        target_list = old_targets if old_targets else [""]
        for idx, umo in enumerate(target_list, start=1):
            gname = umo.split(":")[-1] if umo else f"默认订阅群 {idx}"
            migrated.append(
                {
                    "__template_key": "group_rule",
                    "group_name": f"群聊 {gname}",
                    "target_umo": umo,
                    "twitter_accounts": list(old_accounts),
                    "enable_vision_tag_filter": bool(
                        self.config.get("enable_vision_tag_filter", True)
                    ),
                    "must_include_image_tags": list(old_must),
                    "any_include_image_tags": list(old_any),
                    "exclude_image_tags": list(old_exc),
                    "enable_text_ai_filter": bool(
                        self.config.get("enable_text_ai_filter", True)
                    ),
                    "text_filter_prompt": str(
                        self.config.get(
                            "text_filter_prompt",
                            "请判断这条推文是否值得推送：重要动态、有趣创作、高质量作品分享值得推送；纯广告、无意义水帖不值得推送。",
                        )
                    ),
                    "enable_daily_digest": True,
                }
            )
        self.config["group_subscriptions"] = migrated
        self._save_plugin_config()
        logger.info(f"[TwitterRSS] 已将旧版配置平滑迁移为 {len(migrated)} 个分群独立配置。")

    # =========================================================================
    # 生命周期管理
    # =========================================================================

    async def initialize(self):
        await self._ensure_started()

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        await self._ensure_started()

    async def _ensure_started(self):
        if self._started:
            return
        self._started = True
        await self._init_http_client()
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._digest_task = asyncio.create_task(self._digest_loop())
        logger.info(
            f"[TwitterRSS] 插件已启动，当前已配置分群规则数: {len(self._get_group_rules())}"
        )

    async def _init_http_client(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
        proxy = str(self.config.get("http_proxy", "") or "").strip() or None
        headers = {
            "User-Agent": (
                "AstrBot-TwitterRSS/1.3 (RSS Feed Reader; TelegramBot; "
                "+https://github.com/AstrBotDevs/AstrBot)"
            ),
            "Accept": (
                "application/rss+xml, application/atom+xml, application/xml, "
                "text/xml, application/json, */*;q=0.8"
            ),
        }
        self.http_client = httpx.AsyncClient(
            headers=headers,
            proxy=proxy,
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
        )

    async def terminate(self):
        self._started = False
        for task in (self._poll_task, self._digest_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
        logger.info("[TwitterRSS] 插件后台任务与 HTTP 客户端已安全关闭。")

    # =========================================================================
    # 分群配置与持久化辅助方法
    # =========================================================================

    @staticmethod
    def _load_json_sync(path: pathlib.Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[TwitterRSS] 读取 JSON 文件 {path} 失败: {e}")
            return default

    async def _save_state(self):
        def _write():
            self.state_file.write_text(
                json.dumps(self.state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        await asyncio.to_thread(_write)

    async def _save_history(self):
        cutoff = time.time() - 48 * 3600
        self.history_tweets = [
            t for t in self.history_tweets if t.get("timestamp", 0) >= cutoff
        ]

        def _write():
            self.history_file.write_text(
                json.dumps(self.history_tweets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        await asyncio.to_thread(_write)

    def _save_plugin_config(self):
        if hasattr(self.config, "save_config"):
            try:
                self.config.save_config()
            except Exception as e:
                logger.warning(f"[TwitterRSS] 保存插件配置失败: {e}")

    def _get_group_rules(self) -> list[dict[str, Any]]:
        raw = self.config.get("group_subscriptions", [])
        if not isinstance(raw, list):
            return []
        return [r for r in raw if isinstance(r, dict)]

    def _resolve_target_umo(self, target_umo: str) -> str:
        """将纯数字群号自动解析为完整 unified_msg_origin"""
        t = str(target_umo or "").strip()
        if not t:
            return ""
        if ":" in t:
            return t
        umo_map: dict[str, str] = self.state.get("group_umo_map", {})
        if t in umo_map:
            return umo_map[t]
        return f"aiocqhttp:GroupMessage:{t}"

    def _record_event_umo(self, event: AstrMessageEvent):
        umo = str(event.unified_msg_origin or "").strip()
        gid = ""
        if hasattr(event, "get_group_id"):
            try:
                gid = str(event.get_group_id() or "").strip()
            except Exception:
                gid = ""
        if gid and umo:
            umo_map = self.state.setdefault("group_umo_map", {})
            if umo_map.get(gid) != umo:
                umo_map[gid] = umo

    def _find_or_create_group_rule(
        self, event: AstrMessageEvent, create_if_missing: bool = True
    ) -> dict[str, Any] | None:
        """查找或自动创建当前群聊/会话对应的独立订阅与标签过滤配置"""
        self._record_event_umo(event)
        umo = str(event.unified_msg_origin or "").strip()
        gid = ""
        if hasattr(event, "get_group_id"):
            try:
                gid = str(event.get_group_id() or "").strip()
            except Exception:
                gid = ""

        rules = self._get_group_rules()
        for r in rules:
            cfg_target = str(r.get("target_umo", "") or "").strip()
            if cfg_target == umo or (gid and cfg_target == gid):
                if cfg_target != umo and umo:
                    r["target_umo"] = umo
                    self._save_plugin_config()
                return r

        # 如果有一条未绑定 target_umo 的模板配置，自动将其绑定到当前会话
        for r in rules:
            if not str(r.get("target_umo", "") or "").strip():
                r["target_umo"] = umo
                if not r.get("group_name") or r.get("group_name") == "未命名群聊":
                    r["group_name"] = f"群聊 {gid}" if gid else f"会话 {umo.split(':')[-1]}"
                self._save_plugin_config()
                return r

        if not create_if_missing:
            return None

        new_rule: dict[str, Any] = {
            "__template_key": "group_rule",
            "group_name": f"群聊 {gid}" if gid else f"会话 {umo.split(':')[-1]}",
            "target_umo": umo,
            "twitter_accounts": [],
            "enable_vision_tag_filter": True,
            "must_include_image_tags": ["二次元"],
            "any_include_image_tags": ["插画", "美少女", "萝莉", "立绘", "动漫角色"],
            "exclude_image_tags": ["NSFW", "血腥暴力", "广告二维码", "纯文字聊天截图"],
            "enable_text_ai_filter": True,
            "text_filter_prompt": (
                "请判断这条推文是否值得推送：重要动态、有趣创作、高质量作品分享值得推送；"
                "纯广告、无意义水帖不值得推送。"
            ),
            "enable_daily_digest": True,
        }
        rules.append(new_rule)
        self.config["group_subscriptions"] = rules
        self._save_plugin_config()
        return new_rule

    @staticmethod
    def _clean_str_list(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(x).strip() for x in raw if str(x).strip()]

    @classmethod
    def _get_rule_accounts(cls, rule: dict[str, Any]) -> list[str]:
        return [x.lstrip("@") for x in cls._clean_str_list(rule.get("twitter_accounts", []))]

    # =========================================================================
    # 后台定时任务循环
    # =========================================================================

    async def _poll_loop(self):
        await asyncio.sleep(8)
        while self._started:
            try:
                await self.check_all_accounts(manual=False)
                await self._cleanup_image_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TwitterRSS] 定时轮询推文异常: {e}")

            interval_min = max(2, int(self.config.get("poll_interval_minutes", 15) or 15))
            await asyncio.sleep(interval_min * 60)

    async def _digest_loop(self):
        await asyncio.sleep(15)
        while self._started:
            try:
                if self.config.get("enable_daily_digest", True):
                    target_time = str(self.config.get("daily_digest_time", "08:30") or "08:30").strip()
                    now = datetime.datetime.now()
                    now_hm = now.strftime("%H:%M")
                    today_str = now.strftime("%Y-%m-%d")

                    if (
                        now_hm == target_time
                        and self.state.get("last_digest_date") != today_str
                    ):
                        self.state["last_digest_date"] = today_str
                        await self._save_state()
                        logger.info(f"[TwitterRSS] 到达每日新闻精选推送时间 ({target_time})，开始按群生成24小时新闻简报...")
                        await self.run_daily_digest()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TwitterRSS] 每日24小时新闻定时任务异常: {e}")

            await asyncio.sleep(30)

    async def _cleanup_image_cache(self):
        def _clean():
            cutoff = time.time() - 36 * 3600
            for f in self.image_cache_dir.glob("*"):
                try:
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass

        await asyncio.to_thread(_clean)

    # =========================================================================
    # 多源 RSS / JSON API 获取与解析
    # =========================================================================

    @staticmethod
    def _format_template_url(template: str, username: str) -> str:
        if "{username}" in template:
            return template.replace("{username}", username)
        return f"{template.rstrip('/')}/{username}"

    def _build_rss_url(self, account_or_url: str) -> str:
        if account_or_url.startswith(("http://", "https://")):
            return account_or_url
        base = str(
            self.config.get("rss_base_url", "https://fxtwitter.com/{username}/feed.xml")
            or "https://fxtwitter.com/{username}/feed.xml"
        ).strip()
        if "rsshub.app/twitter/" in base:
            base = "https://fxtwitter.com/{username}/feed.xml"
        return self._format_template_url(base, account_or_url)

    def _get_candidate_urls(self, account_or_url: str) -> list[str]:
        if account_or_url.startswith(("http://", "https://")):
            m = re.search(r"twitter/user/([A-Za-z0-9_]+)", account_or_url)
            if m and "rsshub.app" in account_or_url:
                uname = m.group(1)
                return [self._format_template_url(t, uname) for t in FALLBACK_SOURCE_TEMPLATES]
            return [account_or_url]

        username = account_or_url.strip().lstrip("@")
        primary = self._build_rss_url(username)
        candidates = [primary]

        if self.config.get("enable_multi_source_fallback", True):
            for tmpl in FALLBACK_SOURCE_TEMPLATES:
                u = self._format_template_url(tmpl, username)
                if u not in candidates:
                    candidates.append(u)
        return candidates

    async def _fetch_account_tweets(self, account: str) -> list[dict[str, Any]]:
        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        candidate_urls = self._get_candidate_urls(account)
        errors: list[str] = []

        for url in candidate_urls:
            try:
                resp = await self.http_client.get(url)
                final_url = str(resp.url)
                if "google.com/404" in final_url or "x.com/i/flow/login" in final_url:
                    errors.append(f"{url} -> 重定向至无效页面 ({final_url})")
                    continue

                resp.raise_for_status()
                body_text = resp.text.strip()
                if not body_text:
                    errors.append(f"{url} -> 返回内容为空")
                    continue

                content_type = resp.headers.get("content-type", "").lower()
                if (
                    "json" in content_type
                    or body_text.startswith("{")
                    or body_text.startswith("[")
                ):
                    tweets = await asyncio.to_thread(
                        self._parse_fxtwitter_json, body_text, account
                    )
                else:
                    tweets = await asyncio.to_thread(
                        self._parse_rss_xml, body_text, account
                    )

                if tweets:
                    return tweets
                errors.append(f"{url} -> 解析到 0 条推文")
            except Exception as e:
                errors.append(f"{url} -> {e}")

        logger.warning(
            f"[TwitterRSS] 账号 {account} 所有订阅源均获取失败：\n"
            + "\n".join(f"  - {err}" for err in errors[:4])
        )
        return []

    def _parse_fxtwitter_json(self, json_text: str, account: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(json_text)
        except Exception:
            return []

        raw_list: list[Any] = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            for key in ("results", "statuses", "tweets", "timeline", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    raw_list = val
                    break
            if not raw_list and isinstance(data.get("status"), dict):
                raw_list = [data["status"]]
            elif not raw_list and isinstance(data.get("tweet"), dict):
                raw_list = [data["tweet"]]

        tweets: list[dict[str, Any]] = []
        username_fallback = account.split("/")[-1] if account.startswith("http") else account

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            st = item.get("status") if isinstance(item.get("status"), dict) else item
            st = st.get("tweet") if isinstance(st.get("tweet"), dict) else st

            tid = str(st.get("id") or st.get("id_str") or st.get("url") or "").strip()
            text = str(
                st.get("text")
                or st.get("full_text")
                or (st.get("raw_text", {}) if isinstance(st.get("raw_text"), dict) else {}).get("text")
                or ""
            ).strip()

            author = st.get("author") or st.get("user") or {}
            if not isinstance(author, dict):
                author = {}
            username = str(
                author.get("screen_name")
                or author.get("handle")
                or username_fallback
            ).strip().lstrip("@")
            author_name = str(author.get("name") or username).strip()
            avatar_url = str(
                author.get("avatar_url")
                or author.get("profile_image_url_https")
                or ""
            ).strip()

            link = str(
                st.get("url")
                or (f"https://x.com/{username}/status/{tid}" if tid else "")
            ).strip()

            images: list[str] = []
            media = st.get("media")
            if isinstance(media, dict):
                for p in media.get("photos") or []:
                    if isinstance(p, dict) and p.get("url"):
                        images.append(str(p["url"]).strip())
                if not images:
                    for m in media.get("all") or []:
                        if isinstance(m, dict) and m.get("type") in ("photo", "image", "gif"):
                            u = m.get("url") or m.get("thumbnail_url")
                            if u:
                                images.append(str(u).strip())
            elif isinstance(media, list):
                for m in media:
                    if isinstance(m, dict):
                        u = m.get("url") or m.get("media_url_https")
                        if u:
                            images.append(str(u).strip())
                    elif isinstance(m, str):
                        images.append(m.strip())

            for u in st.get("mediaURLs") or []:
                if isinstance(u, str) and u not in images:
                    images.append(u.strip())

            quote = st.get("quote")
            if isinstance(quote, dict):
                q_author = (quote.get("author") or {}).get("screen_name") or ""
                q_text = quote.get("text") or ""
                if q_text:
                    text = f"{text}\n\n「引用 @{q_author}: {q_text}」".strip()
                if not images and isinstance(quote.get("media"), dict):
                    for p in quote["media"].get("photos") or []:
                        if isinstance(p, dict) and p.get("url"):
                            images.append(str(p["url"]).strip())

            created_ts = st.get("created_timestamp")
            if isinstance(created_ts, (int, float)) and created_ts > 0:
                ts = float(created_ts)
                dt = datetime.datetime.fromtimestamp(ts)
                pub_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                ts, pub_str = self._parse_pub_date(str(st.get("created_at") or ""))

            if not tid:
                tid = link or hashlib.md5(f"{username}:{text[:80]}".encode()).hexdigest()

            tweets.append(
                {
                    "id": tid,
                    "username": username,
                    "author_name": author_name,
                    "avatar_url": avatar_url,
                    "title": text[:60],
                    "text": text,
                    "images": images,
                    "link": link,
                    "timestamp": ts,
                    "pub_date": pub_str,
                }
            )

        tweets.sort(key=lambda x: x["timestamp"])
        return tweets

    def _parse_rss_xml(self, xml_text: str, account: str) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text.strip())
        except ET.ParseError:
            return []

        username_fallback = account.split("/")[-1] if account.startswith("http") else account
        channel_title = username_fallback
        channel_avatar = ""
        channel = root.find("channel")
        if channel is not None:
            ct = channel.findtext("title")
            if ct:
                cleaned_ct = re.sub(r"^(?:Twitter|X)\s*@?\s*", "", ct, flags=re.I).strip()
                channel_title = re.sub(r"\s*\(@[A-Za-z0-9_]+\)\s*$", "", cleaned_ct).strip() or username_fallback
            img_el = channel.find("image")
            if img_el is not None and img_el.findtext("url"):
                channel_avatar = img_el.findtext("url", "").strip()

        items_els = root.findall(".//item")
        is_atom = False
        if not items_els:
            items_els = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
            is_atom = True

        tweets: list[dict[str, Any]] = []
        for el in items_els:
            if is_atom:
                title = self._find_atom_text(el, "title")
                guid = self._find_atom_text(el, "id")
                link = ""
                for lk in el.findall("{http://www.w3.org/2005/Atom}link") + el.findall("link"):
                    href = lk.attrib.get("href", "")
                    if href:
                        link = href
                        break
                raw_html = (
                    self._find_atom_text(el, "content")
                    or self._find_atom_text(el, "summary")
                    or title
                )
                pub_raw = (
                    self._find_atom_text(el, "published")
                    or self._find_atom_text(el, "updated")
                )
                author_name = self._find_atom_text(el, "author/name") or channel_title
            else:
                title = (el.findtext("title") or "").strip()
                link = (el.findtext("link") or "").strip()
                guid = (el.findtext("guid") or link or title).strip()
                content_encoded = el.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                description = el.findtext("description")
                raw_html = (content_encoded or description or title).strip()
                pub_raw = (
                    el.findtext("pubDate")
                    or el.findtext("{http://purl.org/dc/elements/1.1/}date")
                    or ""
                ).strip()
                author_name = (
                    el.findtext("{http://purl.org/dc/elements/1.1/}creator")
                    or el.findtext("author")
                    or channel_title
                ).strip()
                author_name = re.sub(r"^@", "", author_name).strip() or channel_title

            images = self._extract_images(el, raw_html)
            clean_text = self._clean_html_to_text(raw_html)
            if not clean_text and title:
                clean_text = self._clean_html_to_text(title)

            ts, pub_str = self._parse_pub_date(pub_raw)
            username = username_fallback

            tweet_id = guid or link or hashlib.md5(f"{username}:{clean_text[:80]}".encode()).hexdigest()
            tweets.append(
                {
                    "id": tweet_id,
                    "username": username,
                    "author_name": author_name or username,
                    "avatar_url": channel_avatar,
                    "title": title,
                    "text": clean_text,
                    "images": images,
                    "link": link,
                    "timestamp": ts,
                    "pub_date": pub_str,
                }
            )

        tweets.sort(key=lambda x: x["timestamp"])
        return tweets

    @staticmethod
    def _find_atom_text(el: ET.Element, tag_path: str) -> str:
        ns = "{http://www.w3.org/2005/Atom}"
        parts = tag_path.split("/")
        ns_path = "/".join(f"{ns}{p}" for p in parts)
        val = el.findtext(ns_path) or el.findtext(tag_path)
        return (val or "").strip()

    @staticmethod
    def _extract_images(item_el: ET.Element, raw_html: str) -> list[str]:
        urls: list[str] = []
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, flags=re.I):
            u = html.unescape(match.group(1)).strip()
            if u and not u.startswith("data:") and "emoji" not in u.lower():
                urls.append(u)

        for child in item_el.iter():
            tag_lower = child.tag.lower()
            if tag_lower.endswith("enclosure") or tag_lower.endswith("content") or tag_lower.endswith("thumbnail"):
                u = child.attrib.get("url", "").strip()
                mtype = child.attrib.get("type", "").lower()
                medium = child.attrib.get("medium", "").lower()
                if u and (
                    "image" in mtype
                    or medium == "image"
                    or any(ext in u.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", "format=jpg", "format=png", "pbs.twimg.com/media"))
                ):
                    urls.append(html.unescape(u))

        seen: set[str] = set()
        deduped: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    @staticmethod
    def _clean_html_to_text(raw_html: str) -> str:
        if not raw_html:
            return ""
        text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
        text = re.sub(r"<blockquote[^>]*>", "\n「引用：", text, flags=re.I)
        text = re.sub(r"</blockquote\s*>", "」\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        lines = [line.strip() for line in text.splitlines()]
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @staticmethod
    def _parse_pub_date(pub_raw: str) -> tuple[float, str]:
        now_ts = time.time()
        if not pub_raw:
            dt = datetime.datetime.fromtimestamp(now_ts)
            return now_ts, dt.strftime("%Y-%m-%d %H:%M")
        try:
            dt = email.utils.parsedate_to_datetime(pub_raw)
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            return dt.timestamp(), dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        try:
            iso_str = pub_raw.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(iso_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            return dt.timestamp(), dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            dt = datetime.datetime.fromtimestamp(now_ts)
            return now_ts, dt.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _split_tweet_body_and_tags(raw_text: str) -> tuple[str, list[str]]:
        """
        将推文拆分为 (正文文本 orig_body, 蓝色标签列表 orig_tags)。
        若推文只有标签没有正文，则 orig_body 为空字符串 ""。
        """
        if not raw_text:
            return "", []

        tags: list[str] = []
        tag_pattern = re.compile(r"(?:^|(?<=\s))[#＃]([^\s#＃]+)")
        for m in tag_pattern.finditer(raw_text):
            tag_val = f"#{m.group(1).strip()}"
            if tag_val not in tags:
                tags.append(tag_val)

        body_without_tags = tag_pattern.sub("", raw_text)
        lines = [line.strip() for line in body_without_tags.splitlines()]
        body_cleaned = "\n".join(line for line in lines if line)
        body_cleaned = re.sub(r"\n{3,}", "\n\n", body_cleaned).strip()
        return body_cleaned, tags

    async def _download_image_cached(self, url: str) -> tuple[str | None, str | None]:
        if not url:
            return None, None
        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        existing = list(self.image_cache_dir.glob(f"{url_hash}.*"))
        if existing:
            local_path = existing[0]
            data_uri = await asyncio.to_thread(self._file_to_data_uri, local_path)
            return str(local_path), data_uri

        try:
            resp = await self.http_client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            ext = mimetypes.guess_extension(content_type) or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                ext = ".jpg"
            local_path = self.image_cache_dir / f"{url_hash}{ext}"
            content_bytes = resp.content

            def _save_and_encode() -> str:
                local_path.write_bytes(content_bytes)
                b64 = base64.b64encode(content_bytes).decode("ascii")
                return f"data:{content_type};base64,{b64}"

            data_uri = await asyncio.to_thread(_save_and_encode)
            return str(local_path), data_uri
        except Exception as e:
            logger.warning(f"[TwitterRSS] 下载推文图片失败 ({url}): {e}")
            return None, None

    @staticmethod
    def _file_to_data_uri(path: pathlib.Path) -> str:
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "image/jpeg"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    async def _prepare_tweet_media(self, tweet: dict[str, Any]) -> dict[str, Any]:
        """预下载推文头像、配图并拆分正文与标签，供多群复用"""
        if "_media_prepared" in tweet:
            return tweet

        orig_body, orig_tags = self._split_tweet_body_and_tags(tweet.get("text", ""))
        avatar_data_uri = ""
        if tweet.get("avatar_url"):
            _, avatar_b64 = await self._download_image_cached(tweet["avatar_url"])
            avatar_data_uri = avatar_b64 or tweet["avatar_url"]

        local_image_paths: list[str] = []
        display_image_srcs: list[str] = []
        for img_url in tweet.get("images", []):
            local_path, data_uri = await self._download_image_cached(img_url)
            local_image_paths.append(local_path or img_url)
            display_image_srcs.append(data_uri or img_url)

        prepared = dict(tweet)
        prepared["orig_body"] = orig_body
        prepared["orig_tags"] = orig_tags
        prepared["avatar_src"] = avatar_data_uri
        prepared["local_images"] = local_image_paths
        prepared["display_images"] = display_image_srcs
        prepared["translated_body"] = ""
        prepared["translated_tags"] = []
        prepared["_media_prepared"] = True
        return prepared

    # =========================================================================
    # AI 模型调用、分群标签过滤与推文正文/标签翻译
    # =========================================================================

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str = "",
        provider_id: str = "",
        image_urls: list[str] | None = None,
    ) -> str:
        """按照用户在配置面板中手动选择的提供商调用 AstrBot 大模型 / 视觉模型"""
        prov = None
        if provider_id:
            try:
                prov = self.context.get_provider_by_id(provider_id)
            except Exception as e:
                logger.warning(f"[TwitterRSS] 获取手动选择的模型提供商 {provider_id} 失败: {e}")

        if prov is None:
            try:
                prov = self.context.get_using_provider()
            except Exception:
                all_provs = self.context.get_all_providers()
                if all_provs:
                    prov = all_provs[0]

        if prov is not None and hasattr(prov, "text_chat"):
            kwargs: dict[str, Any] = {
                "prompt": prompt,
                "system_prompt": system_prompt,
            }
            if image_urls:
                kwargs["image_urls"] = image_urls
            resp = await prov.text_chat(**kwargs)
            return (resp.completion_text or "").strip()

        if hasattr(self.context, "llm_generate"):
            target_id = provider_id
            if not target_id and prov is not None and hasattr(prov, "meta"):
                target_id = prov.meta().id
            resp = await self.context.llm_generate(
                chat_provider_id=target_id,
                prompt=f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
            )
            return (resp.completion_text or "").strip()

        raise RuntimeError("未找到可用的 AstrBot 大语言模型提供商，请在 WebUI 中配置并选择模型提供商。")

    @staticmethod
    def _extract_json_dict(raw_text: str) -> dict[str, Any]:
        if not raw_text:
            return {}
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return {}

    @staticmethod
    def _normalize_translated_tags(raw_tags: Any) -> list[str]:
        if isinstance(raw_tags, str):
            parts = re.findall(r"[#＃][^\s#＃]+", raw_tags) or raw_tags.split()
        elif isinstance(raw_tags, list):
            parts = [str(x).strip() for x in raw_tags if str(x).strip()]
        else:
            parts = []

        normalized: list[str] = []
        for p in parts:
            clean_p = p.strip().lstrip("#＃")
            if clean_p:
                tag_str = f"#{clean_p}"
                if tag_str not in normalized:
                    normalized.append(tag_str)
        return normalized

    async def _evaluate_vision_for_group(
        self, prepared_tweet: dict[str, Any], group_rule: dict[str, Any]
    ) -> dict[str, Any]:
        """
        根据指定群聊的独立标签规则调用视觉模型：
        - must_include_image_tags：必须全部命中
        - any_include_image_tags：只需匹配到任意一条即通过
        - exclude_image_tags：命中任意一条即拦截
        同时返回推文的正文直译 (translated_body) 与标签翻译 (translated_tags)。
        """
        must_tags = self._clean_str_list(group_rule.get("must_include_image_tags", []))
        any_tags = self._clean_str_list(group_rule.get("any_include_image_tags", []))
        exclude_tags = self._clean_str_list(group_rule.get("exclude_image_tags", []))

        vision_provider_id = str(
            self.config.get("vision_provider_id", "")
            or self.config.get("text_provider_id", "")
            or ""
        ).strip()

        orig_body = prepared_tweet.get("orig_body", "")
        orig_tags = prepared_tweet.get("orig_tags", [])
        local_imgs = prepared_tweet.get("local_images", [])

        system_prompt = (
            "你是一个专业的图像标签识别与推文直译助手。请仔细观察图片并严格返回 JSON 对象，绝不要输出任何多余解释或分析。"
        )
        prompt = (
            f"1. 要求检查的【必须包含标签】列表: {json.dumps(must_tags, ensure_ascii=False)}\n"
            f"2. 要求检查的【其他任意标签】列表: {json.dumps(any_tags, ensure_ascii=False)}\n"
            f"3. 要求检查的【禁止包含(排除)标签】列表: {json.dumps(exclude_tags, ensure_ascii=False)}\n"
            f"4. 原推文正文 (不含标签): {json.dumps(orig_body, ensure_ascii=False)}\n"
            f"5. 原推文标签列表: {json.dumps(orig_tags, ensure_ascii=False)}\n\n"
            "请完成以下任务：\n"
            "- 判断图片中命中了【必须包含标签】里的哪些标签，原样放入 matched_must_tags 数组。\n"
            "- 判断图片中命中了【其他任意标签】里的哪些标签，原样放入 matched_any_tags 数组。\n"
            "- 判断图片中命中了【禁止包含(排除)标签】里的哪些标签，原样放入 matched_exclude_tags 数组。\n"
            "- 若【原推文正文】非空，请将其直接翻译为自然流畅的中文放入 translated_body（只输出纯翻译译文，严禁添加“疑似…”、“画师…”、“意思是…”等任何解释说明；若原推文正文为空字符串，则 translated_body 必须为空字符串 \"\"）。\n"
            "- 若【原推文标签列表】非空，请将每个标签翻译为中文标签放入 translated_tags 数组（每个元素以 # 开头，如 [\"#古明地恋\", \"#东方Project\"]；若原推文无标签，则可结合画面补充 1~3 个核心中文 #标签 放入 translated_tags）。\n\n"
            "请严格按以下 JSON 格式返回：\n"
            "{\n"
            '  "matched_must_tags": [],\n'
            '  "matched_any_tags": [],\n'
            '  "matched_exclude_tags": [],\n'
            '  "translated_body": "",\n'
            '  "translated_tags": []\n'
            "}"
        )

        try:
            raw_resp = await self._call_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_id=vision_provider_id,
                image_urls=local_imgs[:4],
            )
            data = self._extract_json_dict(raw_resp)
        except Exception as e:
            logger.error(f"[TwitterRSS] 调用视觉模型识别图片标签失败: {e}")
            return {
                "passed": False,
                "translated_body": "",
                "translated_tags": [],
                "reason": f"视觉模型调用失败: {e}",
            }

        matched_must = self._clean_str_list(data.get("matched_must_tags"))
        matched_any = self._clean_str_list(data.get("matched_any_tags"))
        matched_exc = self._clean_str_list(data.get("matched_exclude_tags"))

        # 如果原推文没有正文，强制省略正文翻译
        translated_body = (
            str(data.get("translated_body") or "").strip() if orig_body else ""
        )
        translated_tags = self._normalize_translated_tags(data.get("translated_tags"))

        # 1. 检查排除标签
        if exclude_tags and matched_exc:
            return {
                "passed": False,
                "translated_body": translated_body,
                "translated_tags": translated_tags,
                "reason": f"图片包含排除标签: {', '.join(matched_exc)}",
            }

        # 2. 检查必须包含标签（必须全部命中）
        if must_tags:
            matched_must_lower = {m.lower() for m in matched_must}
            missing_must = [t for t in must_tags if t.lower() not in matched_must_lower]
            if missing_must:
                return {
                    "passed": False,
                    "translated_body": translated_body,
                    "translated_tags": translated_tags,
                    "reason": f"图片未命中必须包含标签: {', '.join(missing_must)}",
                }

        # 3. 检查其他任意标签（只需匹配到一条即通过）
        if any_tags:
            matched_any_lower = {m.lower() for m in matched_any}
            hit_any = [t for t in any_tags if t.lower() in matched_any_lower] or matched_any
            if not hit_any:
                return {
                    "passed": False,
                    "translated_body": translated_body,
                    "translated_tags": translated_tags,
                    "reason": f"图片未匹配到任何一条任意标签 ({', '.join(any_tags)})",
                }

        return {
            "passed": True,
            "translated_body": translated_body,
            "translated_tags": translated_tags,
            "reason": "通过视觉标签过滤",
        }

    async def _evaluate_text_for_group(
        self, prepared_tweet: dict[str, Any], group_rule: dict[str, Any]
    ) -> dict[str, Any]:
        """根据指定群聊的文本筛选标准评估推文并翻译正文与标签"""
        text_provider_id = str(self.config.get("text_provider_id", "") or "").strip()
        custom_criteria = str(
            group_rule.get("text_filter_prompt")
            or "请判断该推文是否具有推送价值。"
        ).strip()

        orig_body = prepared_tweet.get("orig_body", "")
        orig_tags = prepared_tweet.get("orig_tags", [])

        system_prompt = (
            "你是一个专业的推特资讯筛选与直译助手。请根据筛选标准评估推文是否值得推送，并提供正文与标签的直接中文翻译，严格返回 JSON 对象。"
        )
        prompt = (
            f"【本群筛选标准】\n{custom_criteria}\n\n"
            f"【待评估推文】\n"
            f"作者: {prepared_tweet['author_name']} (@{prepared_tweet['username']})\n"
            f"原推文正文 (不含标签): {json.dumps(orig_body, ensure_ascii=False)}\n"
            f"原推文标签列表: {json.dumps(orig_tags, ensure_ascii=False)}\n\n"
            "请严格返回如下 JSON 格式：\n"
            "{\n"
            '  "worth_pushing": true,\n'
            '  "translated_body": "若原推文正文非空，直接输出正文的纯中文译文（严禁添加疑似/解释说明）；若原推文正文为空，必须输出空字符串 \"\"",\n'
            '  "translated_tags": ["#标签中文译文1", "#标签中文译文2"],\n'
            '  "reason": "简短原因"\n'
            "}"
        )

        try:
            raw_resp = await self._call_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_id=text_provider_id,
            )
            data = self._extract_json_dict(raw_resp)
            worth = bool(data.get("worth_pushing", True))
            translated_body = (
                str(data.get("translated_body") or "").strip() if orig_body else ""
            )
            translated_tags = self._normalize_translated_tags(data.get("translated_tags"))
            return {
                "worth_pushing": worth,
                "translated_body": translated_body,
                "translated_tags": translated_tags,
                "reason": str(data.get("reason") or "").strip(),
            }
        except Exception as e:
            logger.error(f"[TwitterRSS] 调用文本模型评估推文失败: {e}")
            return {
                "worth_pushing": True,
                "translated_body": "",
                "translated_tags": [],
                "reason": "模型调用异常，默认放行",
            }

    async def evaluate_tweet_for_group(
        self, prepared_tweet: dict[str, Any], group_rule: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        """针对单个群聊的独立规则评估推文是否值得推送"""
        text = prepared_tweet.get("text", "").strip()
        if self.config.get("skip_retweets", False) and re.match(r"^RT\s+@", text, flags=re.I):
            return False, prepared_tweet
        if self.config.get("skip_replies", True) and re.match(r"^(?:Re\s+@|@)", text, flags=re.I):
            return False, prepared_tweet

        enriched = dict(prepared_tweet)
        has_images = len(enriched.get("local_images", [])) > 0
        vision_enabled = bool(group_rule.get("enable_vision_tag_filter", True))
        text_ai_enabled = bool(group_rule.get("enable_text_ai_filter", True))
        bypass_text = bool(self.config.get("image_tweet_bypass_text_filter", True))

        if has_images and vision_enabled:
            v_res = await self._evaluate_vision_for_group(enriched, group_rule)
            if v_res.get("translated_body") and enriched.get("orig_body"):
                enriched["translated_body"] = v_res["translated_body"]
            if v_res.get("translated_tags"):
                enriched["translated_tags"] = v_res["translated_tags"]

            if not v_res.get("passed", False):
                logger.info(
                    f"[TwitterRSS] 群[{group_rule.get('group_name')}] 推文 {enriched['id']} (@{enriched['username']}) 未通过视觉筛选: {v_res.get('reason')}"
                )
                return False, enriched

            if bypass_text:
                return True, enriched

        if text_ai_enabled:
            t_res = await self._evaluate_text_for_group(enriched, group_rule)
            if t_res.get("translated_body") and enriched.get("orig_body"):
                enriched["translated_body"] = t_res["translated_body"]
            if t_res.get("translated_tags") and not enriched.get("translated_tags"):
                enriched["translated_tags"] = t_res["translated_tags"]

            if not t_res.get("worth_pushing", True):
                logger.info(
                    f"[TwitterRSS] 群[{group_rule.get('group_name')}] 推文 {enriched['id']} (@{enriched['username']}) 未通过文本筛选: {t_res.get('reason')}"
                )
                return False, enriched

        return True, enriched

    # =========================================================================
    # 无黑边卡片渲染 + 原图单独发送 + 按群轮询/测试/每日新闻
    # =========================================================================

    @staticmethod
    def _trim_rendered_image_sync(img_path: str):
        """
        使用 Pillow 自动裁切截图四周可能存在的黑边 (#000000 / #0f172a) 或视口底部填充色 (#fefefe)，
        确保最终发出的推文卡片图片 100% 贴合纯白卡片边缘、无任何黑边。
        """
        try:
            from PIL import Image, ImageChops
        except ImportError:
            return

        p = pathlib.Path(img_path)
        if not p.exists() or not p.is_file():
            return

        try:
            with Image.open(p) as im:
                rgb = im.convert("RGB")
                w, h = rgb.size
                px = rgb.load()

                def is_border_pixel(r: int, g: int, b: int) -> bool:
                    # 识别 html 视口底色 (#fefefe) 或暗色黑边 (r,g,b < 45)
                    if r == 254 and g == 254 and b == 254:
                        return True
                    if r < 45 and g < 45 and b < 60:
                        return True
                    return False

                top = 0
                while top < h - 10 and all(is_border_pixel(*px[x, top]) for x in range(0, w, max(1, w // 20))):
                    top += 1

                bottom = h - 1
                while bottom > top + 10 and all(is_border_pixel(*px[x, bottom]) for x in range(0, w, max(1, w // 20))):
                    bottom -= 1

                left = 0
                while left < w - 10 and all(is_border_pixel(*px[left, y]) for y in range(top, bottom + 1, max(1, (bottom - top) // 20))):
                    left += 1

                right = w - 1
                while right > left + 10 and all(is_border_pixel(*px[right, y]) for y in range(top, bottom + 1, max(1, (bottom - top) // 20))):
                    right -= 1

                if top > 0 or left > 0 or bottom < h - 1 or right < w - 1:
                    cropped = rgb.crop((left, top, right + 1, bottom + 1))
                    cropped.save(p, format="PNG")
        except Exception as e:
            logger.debug(f"[TwitterRSS] 自动裁切图片边缘跳过: {e}")

    async def _render_html_to_image(
        self, template_str: str, render_data: dict[str, Any]
    ) -> str:
        options = {
            "full_page": True,
            "type": "png",
            "scale": "device",
        }
        try:
            res = await self.html_render(
                template_str, render_data, return_url=False, options=options
            )
        except TypeError:
            res = await self.html_render(template_str, render_data, options=options)

        if res and not str(res).startswith(("http://", "https://")):
            await asyncio.to_thread(self._trim_rendered_image_sync, str(res))
        return res

    @staticmethod
    def _make_image_comp(path_or_url: str) -> Comp.Image:
        if path_or_url.startswith(("http://", "https://")):
            return Comp.Image.fromURL(path_or_url)
        return Comp.Image.fromFileSystem(path_or_url)

    async def push_tweet_to_umo(self, enriched_tweet: dict[str, Any], target_umo: str):
        """将通过筛选的推文渲染为无黑边推文卡片，并按【渲染推文图片 + 原图单独发送】推送到指定群聊"""
        umo = self._resolve_target_umo(target_umo)
        if not umo:
            return

        author_name = enriched_tweet.get("author_name") or enriched_tweet.get("username", "X")
        orig_body = enriched_tweet.get("orig_body", "")
        orig_tags = enriched_tweet.get("orig_tags", [])
        # 如果没有正文，则严格省略正文翻译；标签保留蓝色字体
        translated_body = enriched_tweet.get("translated_body", "") if orig_body else ""
        translated_tags = enriched_tweet.get("translated_tags", [])

        render_payload = {
            "author_name": author_name,
            "author_initial": author_name[:1].upper(),
            "username": enriched_tweet.get("username", ""),
            "avatar_src": enriched_tweet.get("avatar_src", ""),
            "orig_body": orig_body,
            "orig_tags": orig_tags,
            "translated_body": translated_body,
            "translated_tags": translated_tags,
            "display_images": enriched_tweet.get("display_images", []),
            "pub_date": enriched_tweet.get("pub_date", ""),
        }

        rendered_card_path = await self._render_html_to_image(TWEET_CARD_TMPL, render_payload)
        raw_images = enriched_tweet.get("local_images", [])
        send_mode = str(self.config.get("push_send_mode", "separate_messages") or "separate_messages")

        try:
            if send_mode == "single_chain":
                chain_comps = [self._make_image_comp(rendered_card_path)]
                for raw_img in raw_images:
                    chain_comps.append(self._make_image_comp(raw_img))
                await self.context.send_message(umo, MessageChain(chain_comps))
            else:
                await self.context.send_message(
                    umo, MessageChain([self._make_image_comp(rendered_card_path)])
                )
                for raw_img in raw_images:
                    await asyncio.sleep(0.6)
                    await self.context.send_message(
                        umo, MessageChain([self._make_image_comp(raw_img)])
                    )
        except Exception as e:
            logger.error(f"[TwitterRSS] 向群聊会话 {umo} 推送推文失败: {e}")

    async def check_all_accounts(
        self, manual: bool = False, target_rule: dict[str, Any] | None = None
    ) -> dict[str, int]:
        """遍历所有分群订阅配置（或指定群聊配置），拉取新推文并按各群独立规则筛选推送"""
        async with self._lock:
            rules = [target_rule] if target_rule is not None else self._get_group_rules()
            stats = {"fetched": 0, "new": 0, "pushed": 0}
            if not rules:
                return stats

            seen_map: dict[str, list[str]] = self.state.setdefault("seen_ids", {})
            init_keys: list[str] = self.state.setdefault("initialized_keys", [])
            first_run_mark_seen = bool(self.config.get("first_run_mark_seen", True))
            existing_hist_map = {h["id"]: h for h in self.history_tweets}

            # 按账号缓存本轮拉取结果，避免多个群订阅同一画师时重复请求 RSS
            account_tweets_cache: dict[str, list[dict[str, Any]]] = {}

            for rule in rules:
                umo = self._resolve_target_umo(rule.get("target_umo", ""))
                accounts = self._get_rule_accounts(rule)
                if not umo or not accounts:
                    continue

                for account in accounts:
                    if account not in account_tweets_cache:
                        fetched_list = await self._fetch_account_tweets(account)
                        account_tweets_cache[account] = fetched_list
                        stats["fetched"] += len(fetched_list)
                    tweets = account_tweets_cache[account]
                    if not tweets:
                        continue

                    state_key = f"{umo}::{account}"
                    acct_seen = set(seen_map.get(state_key, []))
                    is_first_init = state_key not in init_keys

                    new_tweets = [t for t in tweets if t["id"] not in acct_seen]
                    if not new_tweets:
                        if is_first_init:
                            init_keys.append(state_key)
                        continue

                    for nt in new_tweets:
                        if nt["id"] not in existing_hist_map:
                            self.history_tweets.append(dict(nt))
                            existing_hist_map[nt["id"]] = self.history_tweets[-1]

                    if is_first_init and first_run_mark_seen and not manual:
                        for nt in new_tweets:
                            acct_seen.add(nt["id"])
                        seen_map[state_key] = list(acct_seen)[-300:]
                        init_keys.append(state_key)
                        continue

                    if is_first_init:
                        init_keys.append(state_key)
                        eval_candidates = new_tweets[-2:]
                        for nt in new_tweets[:-2]:
                            acct_seen.add(nt["id"])
                    else:
                        eval_candidates = new_tweets

                    for idx_t, tweet in enumerate(eval_candidates):
                        stats["new"] += 1
                        acct_seen.add(tweet["id"])
                        prepared = await self._prepare_tweet_media(tweet)
                        eval_Candidates_item = prepared
                        worth, enriched = await self.evaluate_tweet_for_group(
                            eval_Candidates_item, rule
                        )
                        if tweet["id"] in existing_hist_map:
                            existing_hist_map[tweet["id"]]["ai_summary"] = enriched.get(
                                "translated_body", ""
                            )

                        if worth:
                            await self.push_tweet_to_umo(enriched, umo)
                            stats["pushed"] += 1

                    seen_map[state_key] = list(acct_seen)[-300:]

            await self._save_state()
            await self._save_history()
            return stats

    async def test_push_for_group(
        self,
        group_rule: dict[str, Any],
        limit_per_account: int = 3,
        target_account: str = "",
    ) -> dict[str, int]:
        """
        按当前群聊的独立订阅与独立标签过滤规则，获取每个账号过去的 N 条推文（默认 3 条）进行筛选并推送
        """
        async with self._lock:
            umo = self._resolve_target_umo(group_rule.get("target_umo", ""))
            if target_account.strip():
                accounts = [target_account.strip().lstrip("@")]
            else:
                accounts = self._get_rule_accounts(group_rule)

            stats = {
                "accounts": len(accounts),
                "fetched": 0,
                "evaluated": 0,
                "pushed": 0,
                "filtered": 0,
            }
            if not accounts or not umo:
                return stats

            seen_map: dict[str, list[str]] = self.state.setdefault("seen_ids", {})
            existing_hist_map = {h["id"]: h for h in self.history_tweets}

            for account in accounts:
                tweets = await self._fetch_account_tweets(account)
                stats["fetched"] += len(tweets)
                if not tweets:
                    continue

                past_tweets = tweets[-limit_per_account:]
                state_key = f"{umo}::{account}"
                acct_seen = set(seen_map.get(state_key, []))

                for tweet in past_tweets:
                    stats["evaluated"] += 1
                    acct_seen.add(tweet["id"])

                    prepared = await self._prepare_tweet_media(tweet)
                    worth, enriched = await self.evaluate_tweet_for_group(
                        prepared, group_rule
                    )

                    if tweet["id"] not in existing_hist_map:
                        rec = dict(tweet)
                        rec["ai_summary"] = enriched.get("translated_body", "")
                        self.history_tweets.append(rec)
                        existing_hist_map[tweet["id"]] = rec

                    if worth:
                        await self.push_tweet_to_umo(enriched, umo)
                        stats["pushed"] += 1
                    else:
                        stats["filtered"] += 1

                seen_map[state_key] = list(acct_seen)[-300:]

            await self._save_state()
            await self._save_history()
            return stats

    async def run_daily_digest(
        self, target_rule: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        """按群聊各自订阅的账号汇总过去 24 小时推文，渲染马卡龙色系《今日要闻》长图并推送"""
        rules = (
            [target_rule]
            if target_rule is not None
            else [
                r
                for r in self._get_group_rules()
                if r.get("enable_daily_digest", True) and r.get("target_umo")
            ]
        )
        if not rules:
            return False, "未找到已启用每日简报的群聊配置。"

        cutoff = time.time() - 24 * 3600
        if not any(t.get("timestamp", 0) >= cutoff for t in self.history_tweets):
            await self.check_all_accounts(manual=False)

        max_items = max(3, int(self.config.get("daily_digest_max_items", 8) or 8))
        digest_prompt_cfg = str(
            self.config.get("daily_digest_prompt", "")
            or "请从过去24小时的推文中精选重要动态，整理为今日要闻简讯。"
        ).strip()
        text_provider_id = str(self.config.get("text_provider_id", "") or "").strip()

        pushed_any = False
        last_img_path = ""

        for rule in rules:
            umo = self._resolve_target_umo(rule.get("target_umo", ""))
            group_accts = {a.lower() for a in self._get_rule_accounts(rule)}
            if not umo:
                continue

            recent_tweets = [
                t
                for t in self.history_tweets
                if t.get("timestamp", 0) >= cutoff
                and (not group_accts or str(t.get("username", "")).lower() in group_accts)
            ]
            if not recent_tweets:
                continue

            recent_slice = recent_tweets[-40:]
            candidates_lines: list[str] = []
            for idx, t in enumerate(recent_slice):
                text_snippet = (t.get("text") or "").replace("\n", " ").strip()[:240]
                trans_hint = (t.get("ai_summary") or "").replace("\n", " ").strip()[:120]
                has_img_tag = "含插画配图" if t.get("images") else "纯文字"
                line = f"[{idx}] @{t.get('username')} ({t.get('author_name')}, {t.get('pub_date')}, {has_img_tag}): {text_snippet}"
                if trans_hint:
                    line += f" | 参考译文: {trans_hint}"
                candidates_lines.append(line)

            system_prompt = (
                "你是一位干练、克制的新闻简报编辑。请根据过去24小时的推文素材，提炼出简明扼要的《今日要闻》条目，严格输出 JSON 格式。"
            )
            prompt = (
                f"【编辑要求】\n{digest_prompt_cfg}\n"
                f"最多精选 {max_items} 条重点推文动态。\n\n"
                "【撰写铁律（必须严格执行）】\n"
                "1. 新闻简讯口吻：title（8~18字）与 summary（20~50字，1~2句话）均采用客观、洗练的新闻报道口吻，直接陈述作者发布了什么主题的插画、设计或动态，有话则长、无话则短。\n"
                "2. 严禁出现废话或提及未知信息：绝对禁止输出“无法判断…”、“未进一步说明…”、“未透露…”、“素材未包含…”、“暂不清楚…”、“未提及…”、“无法核验…”等任何关于信息缺失的表述！只陈述推文已有的明确信息。\n"
                "3. 严禁使用任何 Emoji 表情符号。\n\n"
                f"【过去24小时推文素材列表】\n" + "\n".join(candidates_lines) + "\n\n"
                "请严格返回如下 JSON 格式：\n"
                "{\n"
                '  "items": [\n'
                "    {\n"
                '      "tweet_index": 0,\n'
                '      "category": "分类标签（2~6字，如 角色设计 / 插画作品 / 联动企划）",\n'
                '      "title": "简明新闻标题（8~18字，不含Emoji）",\n'
                '      "summary": "客观精炼的新闻简讯正文（20~50字，只陈述已有事实，严禁写无法判断或未说明等废话）"\n'
                "    }\n"
                "  ]\n"
                "}"
            )

            try:
                raw_resp = await self._call_llm(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    provider_id=text_provider_id,
                )
                digest_json = self._extract_json_dict(raw_resp)
            except Exception as e:
                logger.error(f"[TwitterRSS] 生成每日24小时要闻简报调用模型失败: {e}")
                digest_json = {}

            raw_items = digest_json.get("items") or []

            # 随机洗牌马卡龙色系调色板，保证每次日报主题与各卡片配色清新柔和且富有变化
            shuffled_palettes = list(MACARON_PALETTES)
            random.shuffle(shuffled_palettes)
            theme_palette = random.choice(shuffled_palettes)

            rendered_items: list[dict[str, Any]] = []
            for i, entry in enumerate(raw_items[:max_items]):
                idx = entry.get("tweet_index", 0)
                src_tweet = (
                    recent_slice[idx]
                    if isinstance(idx, int) and 0 <= idx < len(recent_slice)
                    else recent_slice[i % len(recent_slice)]
                )
                thumb_src = ""
                if src_tweet.get("images"):
                    _, b64_uri = await self._download_image_cached(src_tweet["images"][0])
                    thumb_src = b64_uri or src_tweet["images"][0]

                clean_cat = _clean_digest_text(str(entry.get("category") or "资讯速递"), is_summary=False)
                clean_title = _clean_digest_text(
                    str(entry.get("title") or src_tweet.get("title") or f"@{src_tweet.get('username')} 发布新动态"),
                    is_summary=False,
                )
                clean_summary = _clean_digest_text(
                    str(entry.get("summary") or src_tweet.get("ai_summary") or src_tweet.get("text") or ""),
                    is_summary=True,
                )

                rendered_items.append(
                    {
                        "category": clean_cat or "资讯速递",
                        "username": src_tweet.get("username", ""),
                        "author_name": _clean_digest_text(src_tweet.get("author_name", ""), is_summary=False),
                        "pub_date": src_tweet.get("pub_date", ""),
                        "title": clean_title,
                        "summary": clean_summary,
                        "thumb_src": thumb_src,
                        "palette": shuffled_palettes[i % len(shuffled_palettes)],
                    }
                )

            if not rendered_items:
                for i, src_tweet in enumerate(reversed(recent_slice[-max_items:])):
                    thumb_src = ""
                    if src_tweet.get("images"):
                        _, b64_uri = await self._download_image_cached(src_tweet["images"][0])
                        thumb_src = b64_uri or src_tweet["images"][0]
                    fallback_text = _clean_digest_text(
                        src_tweet.get("ai_summary") or src_tweet.get("text") or "发布了全新插画作品动态。",
                        is_summary=True,
                    )
                    rendered_items.append(
                        {
                            "category": "动态速递",
                            "username": src_tweet.get("username", ""),
                            "author_name": _clean_digest_text(src_tweet.get("author_name", ""), is_summary=False),
                            "pub_date": src_tweet.get("pub_date", ""),
                            "title": f"@{src_tweet.get('username')} 发布最新动态",
                            "summary": fallback_text,
                            "thumb_src": thumb_src,
                            "palette": shuffled_palettes[i % len(shuffled_palettes)],
                        }
                    )

            now = datetime.datetime.now()
            render_data = {
                "date_str": now.strftime("%Y.%m.%d"),
                "total_count": len(recent_tweets),
                "account_count": len(group_accts),
                "theme": theme_palette,
                "items": rendered_items,
            }

            digest_img_path = await self._render_html_to_image(DAILY_DIGEST_TMPL, render_data)
            try:
                await self.context.send_message(
                    umo, MessageChain([self._make_image_comp(digest_img_path)])
                )
                pushed_any = True
                last_img_path = digest_img_path
            except Exception as e:
                logger.error(f"[TwitterRSS] 向会话 {umo} 推送24小时要闻长图失败: {e}")

        if not pushed_any:
            return False, "本群过去 24 小时内暂无收录的推文内容。"
        return True, last_img_path

    # =========================================================================
    # 聊天管理指令组 (/tw ...) —— 所有指令均按当前群聊独立配置操作！
    # =========================================================================

    @filter.command_group("tw")
    def tw(self):
        """推特 RSS 分群独立订阅与标签过滤管理指令组"""
        pass

    @tw.command("sub")
    async def tw_sub(self, event: AstrMessageEvent, group_name: str = ""):
        """绑定/初始化当前群聊的独立订阅配置"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        if group_name.strip():
            rule["group_name"] = group_name.strip()
            self._save_plugin_config()
        yield event.plain_result(
            f"✅ 已绑定并启用当前群聊的独立订阅配置！\n"
            f"• 群聊名称: {rule.get('group_name')}\n"
            f"• 会话 ID: {rule.get('target_umo')}\n"
            f"可发送 `/tw add <账号>` 添加本群订阅，或发送 `/tw list` 查看本群标签过滤规则。"
        )

    @tw.command("unsub")
    async def tw_unsub(self, event: AstrMessageEvent):
        """移除当前群聊的独立订阅配置"""
        rule = self._find_or_create_group_rule(event, create_if_missing=False)
        if not rule:
            yield event.plain_result("当前群聊尚未绑定任何订阅配置。")
            return
        rules = self._get_group_rules()
        if rule in rules:
            rules.remove(rule)
            self.config["group_subscriptions"] = rules
            self._save_plugin_config()
        yield event.plain_result(f"🗑️ 已移除当前群聊 ({rule.get('group_name')}) 的推特订阅配置。")

    @tw.command("add")
    async def tw_add(self, event: AstrMessageEvent, account: str):
        """为当前群聊添加订阅的推特账号"""
        acct = account.strip().lstrip("@")
        if not acct:
            yield event.plain_result("请提供推特账号名（如 `/tw add rasra25`）。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        accounts = self._get_rule_accounts(rule)
        if acct in accounts:
            yield event.plain_result(f"账号 @{acct} 已在当前群聊 ({rule.get('group_name')}) 的订阅列表中。")
            return
        accounts.append(acct)
        rule["twitter_accounts"] = accounts
        self._save_plugin_config()
        yield event.plain_result(
            f"✅ 已为当前群聊【{rule.get('group_name')}】添加推特订阅: @{acct}\n"
            f"本群当前订阅数: {len(accounts)} 个"
        )

    @tw.command("del")
    async def tw_del(self, event: AstrMessageEvent, account: str):
        """从当前群聊移除订阅的推特账号"""
        acct = account.strip().lstrip("@")
        rule = self._find_or_create_group_rule(event, create_if_missing=False)
        if not rule:
            yield event.plain_result("当前群聊尚未创建订阅配置。")
            return
        accounts = self._get_rule_accounts(rule)
        if acct not in accounts:
            yield event.plain_result(f"当前群聊订阅列表中未找到账号: @{acct}")
            return
        accounts.remove(acct)
        rule["twitter_accounts"] = accounts
        self._save_plugin_config()
        yield event.plain_result(f"🗑️ 已从当前群聊【{rule.get('group_name')}】移除推特订阅: @{acct}")

    @tw.command("must_add")
    async def tw_must_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊添加【必须包含】图片标签（全部命中才通过）"""
        t = tag.strip().lstrip("#＃")
        if not t:
            yield event.plain_result("请指定要添加的必须包含标签，例如 `/tw must_add 萝莉`。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        tags = self._clean_str_list(rule.get("must_include_image_tags", []))
        if t not in tags:
            tags.append(t)
            rule["must_include_image_tags"] = tags
            self._save_plugin_config()
        yield event.plain_result(
            f"✅ 本群【{rule.get('group_name')}】已添加必须包含标签: #{t}\n"
            f"当前必须包含标签（全部命中才通过）: {', '.join(tags)}"
        )

    @tw.command("must_del")
    async def tw_must_del(self, event: AstrMessageEvent, tag: str):
        """从当前群聊移除【必须包含】图片标签"""
        t = tag.strip().lstrip("#＃")
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        tags = self._clean_str_list(rule.get("must_include_image_tags", []))
        if t in tags:
            tags.remove(t)
            rule["must_include_image_tags"] = tags
            self._save_plugin_config()
        yield event.plain_result(
            f"🗑️ 本群【{rule.get('group_name')}】已移除必须包含标签: #{t}\n"
            f"当前必须包含标签: {', '.join(tags) if tags else '不限'}"
        )

    @tw.command("any_add")
    async def tw_any_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊添加【其他任意】图片标签（命中任意一条即通过）"""
        t = tag.strip().lstrip("#＃")
        if not t:
            yield event.plain_result("请指定要添加的任意标签，例如 `/tw any_add 插画`。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        tags = self._clean_str_list(rule.get("any_include_image_tags", []))
        if t not in tags:
            tags.append(t)
            rule["any_include_image_tags"] = tags
            self._save_plugin_config()
        yield event.plain_result(
            f"✅ 本群【{rule.get('group_name')}】已添加其他任意标签: #{t}\n"
            f"当前其他任意标签（匹配1条即通过）: {', '.join(tags)}"
        )

    @tw.command("any_del")
    async def tw_any_del(self, event: AstrMessageEvent, tag: str):
        """从当前群聊移除【其他任意】图片标签"""
        t = tag.strip().lstrip("#＃")
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        tags = self._clean_str_list(rule.get("any_include_image_tags", []))
        if t in tags:
            tags.remove(t)
            rule["any_include_image_tags"] = tags
            self._save_plugin_config()
        yield event.plain_result(
            f"🗑️ 本群【{rule.get('group_name')}】已移除其他任意标签: #{t}\n"
            f"当前其他任意标签: {', '.join(tags) if tags else '不限'}"
        )

    @tw.command("exc_add")
    async def tw_exc_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊添加【禁止包含】排除标签"""
        t = tag.strip().lstrip("#＃")
        if not t:
            yield event.plain_result("请指定要添加的排除标签，例如 `/tw exc_add NSFW`。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        tags = self._clean_str_list(rule.get("exclude_image_tags", []))
        if t not in tags:
            tags.append(t)
            rule["exclude_image_tags"] = tags
            self._save_plugin_config()
        yield event.plain_result(
            f"✅ 本群【{rule.get('group_name')}】已添加排除标签: #{t}\n"
            f"当前排除标签: {', '.join(tags)}"
        )

    @tw.command("exc_del")
    async def tw_exc_del(self, event: AstrMessageEvent, tag: str):
        """从当前群聊移除【禁止包含】排除标签"""
        t = tag.strip().lstrip("#＃")
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        tags = self._clean_str_list(rule.get("exclude_image_tags", []))
        if t in tags:
            tags.remove(t)
            rule["exclude_image_tags"] = tags
            self._save_plugin_config()
        yield event.plain_result(
            f"🗑️ 本群【{rule.get('group_name')}】已移除排除标签: #{t}\n"
            f"当前排除标签: {', '.join(tags) if tags else '无'}"
        )

    @tw.command("list")
    async def tw_list(self, event: AstrMessageEvent):
        """查看当前群聊的独立订阅与标签过滤配置"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        accounts = self._get_rule_accounts(rule)
        must_tags = self._clean_str_list(rule.get("must_include_image_tags", []))
        any_tags = self._clean_str_list(rule.get("any_include_image_tags", []))
        exc_tags = self._clean_str_list(rule.get("exclude_image_tags", []))
        test_count = max(1, int(self.config.get("test_push_tweet_count", 3) or 3))
        all_rules = self._get_group_rules()

        msg = (
            f"📡 【当前群聊独立配置：{rule.get('group_name')}】\n"
            f"• 会话 ID: {rule.get('target_umo')}\n"
            f"• 本群订阅账号 ({len(accounts)}): {', '.join(accounts) if accounts else '暂无 (发送 /tw add <账号> 添加)'}\n"
            f"• 本群视觉标签过滤: {'开启' if rule.get('enable_vision_tag_filter', True) else '关闭'}\n"
            f"  - 必须包含标签 (全部命中): {', '.join(must_tags) if must_tags else '不限'}\n"
            f"  - 其他任意标签 (命中1条即可): {', '.join(any_tags) if any_tags else '不限'}\n"
            f"  - 禁止包含标签 (排除): {', '.join(exc_tags) if exc_tags else '无'}\n"
            f"• 本群文本价值判断: {'开启' if rule.get('enable_text_ai_filter', True) else '关闭'}\n"
            f"• 本群每日24h简报: {'开启' if rule.get('enable_daily_digest', True) else '关闭'} "
            f"(时间点: {self.config.get('daily_digest_time', '08:30')})\n"
            f"• 测试推送条数: 每账号过去 {test_count} 条 | 全局已配置群聊总数: {len(all_rules)} 个"
        )
        yield event.plain_result(msg)

    @tw.command("check")
    async def tw_check(self, event: AstrMessageEvent):
        """立即手动检查当前群聊订阅账号的新推文并推送"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        accounts = self._get_rule_accounts(rule)
        if not accounts:
            yield event.plain_result("当前群聊还没有订阅任何推特账号，请先使用 `/tw add <账号名>` 添加。")
            return
        yield event.plain_result(
            f"🔄 正在按本群【{rule.get('group_name')}】独立规则检查 {len(accounts)} 个推特账号的新推文，请稍候..."
        )
        stats = await self.check_all_accounts(manual=True, target_rule=rule)
        yield event.plain_result(
            f"✅ 本群检查完成！共拉取 {stats['fetched']} 条推文，发现 {stats['new']} 条新推文，通过本群规则筛选并推送 {stats['pushed']} 条。"
        )

    @tw.command("test")
    async def tw_test(self, event: AstrMessageEvent, account: str = ""):
        """测试推送：按本群独立规则获取每个订阅账号过去的N条推文（默认3条）进行筛选并推送"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        limit = max(1, int(self.config.get("test_push_tweet_count", 3) or 3))
        target_acct = account.strip().lstrip("@") if account else ""
        accounts = [target_acct] if target_acct else self._get_rule_accounts(rule)

        if not accounts:
            yield event.plain_result(
                "当前群聊还没有订阅任何推特账号，请先使用 `/tw add <账号名>` 添加，或直接发送 `/tw test <账号名>` 测试指定账号。"
            )
            return

        scope_desc = f"账号 @{target_acct}" if target_acct else f"本群全部 {len(accounts)} 个订阅账号"
        yield event.plain_result(
            f"🧪 开始本群测试推送：正在获取 {scope_desc} 各自过去的 {limit} 条推文，并按本群【{rule.get('group_name')}】的标签过滤规则进行筛选推送，请稍候..."
        )

        stats = await self.test_push_for_group(
            group_rule=rule,
            limit_per_account=limit,
            target_account=target_acct,
        )
        if stats["fetched"] == 0:
            yield event.plain_result(
                "⚠️ 未能从任何订阅源获取到推文。如果您处于国内网络环境，请在插件配置的 `http_proxy` 项填入本地代理地址（例如 `http://127.0.0.1:7890`）后重试。"
            )
            return

        yield event.plain_result(
            f"✅ 本群【{rule.get('group_name')}】测试推送完成！\n"
            f"• 检查账号数: {stats['accounts']} 个\n"
            f"• 获取并评估历史推文: {stats['evaluated']} 条（每个账号最多取过去 {limit} 条）\n"
            f"• 通过本群规则并渲染推送: {stats['pushed']} 条\n"
            f"• 未通过本群规则被拦截: {stats['filtered']} 条"
        )

    @tw.command("digest")
    async def tw_digest(self, event: AstrMessageEvent):
        """立即按当前群聊订阅账号汇总过去24小时推文并生成精选新闻长图推送到本群"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        yield event.plain_result(
            f"正在整理本群【{rule.get('group_name')}】过去 24 小时的推文并生成《今日要闻》长图，请稍候..."
        )
        ok, info = await self.run_daily_digest(target_rule=rule)
        if not ok:
            yield event.plain_result(f"⚠️ 无法生成每日新闻简报：{info}")
