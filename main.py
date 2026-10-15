"""
AstrBot 推特 RSS 智能订阅、分群独立标签过滤与每日24h新闻简报插件 (astrbot_plugin_twitter_rss)
"""

from __future__ import annotations

import asyncio
import base64
import colorsys
import copy
import datetime
import email.utils
import hashlib
import html
import io
import json
import math
import mimetypes
import pathlib
import random
import re
import shutil
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

# 直接内嵌最新 HTML 模板，确保在 AstrBot 热重载 main.py 时不会因 sys.modules 缓存旧的 templates.py 而导致样式不更新
TWEET_CARD_TMPL = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<style>\n  * {\n    box-sizing: border-box;\n    margin: 0;\n    padding: 0;\n  }\n  html {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #fefefe;\n  }\n  body {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #ffffff;\n    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;\n    color: #0f172a;\n    -webkit-font-smoothing: antialiased;\n  }\n  .card {\n    width: 100%;\n    background: #ffffff;\n    padding: 28px 32px;\n  }\n  .retweet-banner {\n    display: flex;\n    align-items: center;\n    gap: 8px;\n    margin-bottom: 12px;\n    padding-left: 8px;\n    font-size: 13.5px;\n    font-weight: 700;\n    color: #059669;\n  }\n  .retweet-icon {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    width: 20px;\n    height: 20px;\n    border-radius: 6px;\n    background: rgba(16, 185, 129, 0.12);\n    color: #059669;\n    font-size: 13px;\n    font-weight: 900;\n  }\n  .retweet-mini-avatar {\n    width: 20px;\n    height: 20px;\n    border-radius: 50%;\n    overflow: hidden;\n    background: #10b981;\n    flex-shrink: 0;\n    border: 1px solid #d1fae5;\n  }\n  .retweet-mini-avatar img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n  }\n  .header {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    margin-bottom: 16px;\n  }\n  .author-box {\n    display: flex;\n    align-items: center;\n    gap: 14px;\n  }\n  .avatar {\n    width: 52px;\n    height: 52px;\n    border-radius: 50%;\n    background: #1d9bf0;\n    color: #ffffff;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    font-size: 22px;\n    font-weight: 700;\n    overflow: hidden;\n    flex-shrink: 0;\n    border: 1px solid #e2e8f0;\n  }\n  .avatar img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n  }\n  .author-meta {\n    display: flex;\n    flex-direction: column;\n    gap: 3px;\n  }\n  .author-name-row {\n    display: flex;\n    align-items: center;\n    gap: 6px;\n  }\n  .author-name {\n    font-size: 19px;\n    font-weight: 800;\n    color: #0f172a;\n  }\n  .verified-badge {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    width: 18px;\n    height: 18px;\n    border-radius: 50%;\n    background: #1d9bf0;\n    color: #ffffff;\n    font-size: 11px;\n    font-weight: 900;\n  }\n  .author-sub {\n    font-size: 14px;\n    color: #64748b;\n    font-weight: 500;\n  }\n  .brand-logo {\n    width: 34px;\n    height: 34px;\n    border-radius: 9px;\n    background: #0f172a;\n    color: #ffffff;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    font-size: 19px;\n    font-weight: 900;\n  }\n  .tweet-section {\n    margin-bottom: 12px;\n  }\n  .tweet-body {\n    font-size: 18px;\n    line-height: 1.65;\n    color: #0f172a;\n    white-space: pre-wrap;\n    word-break: break-word;\n  }\n  .tweet-tags {\n    margin-top: 4px;\n    font-size: 17px;\n    line-height: 1.6;\n    color: #1d9bf0;\n    font-weight: 500;\n    word-break: break-word;\n  }\n  .trans-section {\n    margin-top: 8px;\n    margin-bottom: 14px;\n    padding-top: 10px;\n    border-top: 1px solid #f1f5f9;\n  }\n  .trans-body {\n    font-size: 16.5px;\n    line-height: 1.65;\n    color: #334155;\n    white-space: pre-wrap;\n    word-break: break-word;\n  }\n  .trans-tags {\n    margin-top: 4px;\n    font-size: 16.5px;\n    line-height: 1.6;\n    color: #1d9bf0;\n    font-weight: 500;\n    word-break: break-word;\n  }\n  .media-grid {\n    display: grid;\n    gap: 10px;\n    margin-top: 12px;\n    border-radius: 16px;\n    overflow: hidden;\n  }\n  .media-grid.count-1 {\n    grid-template-columns: 1fr;\n  }\n  .media-grid.count-2, .media-grid.count-3, .media-grid.count-4 {\n    grid-template-columns: 1fr 1fr;\n  }\n  .media-item {\n    width: 100%;\n    overflow: hidden;\n    background: #f8fafc;\n    border-radius: 14px;\n    border: 1px solid #e2e8f0;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n  }\n  .media-grid.count-1 .media-item img {\n    width: 100%;\n    height: auto;\n    display: block;\n  }\n  .media-grid.count-2 .media-item img,\n  .media-grid.count-3 .media-item img,\n  .media-grid.count-4 .media-item img {\n    width: 100%;\n    height: 320px;\n    object-fit: cover;\n    display: block;\n  }\n  /* 引用转发 (Quote Tweet) 嵌套卡片样式 */\n  .quote-card {\n    margin-top: 14px;\n    border: 1.5px solid #cbd5e1;\n    border-radius: 16px;\n    background: #f8fafc;\n    padding: 16px 18px;\n    overflow: hidden;\n  }\n  .quote-header {\n    display: flex;\n    align-items: center;\n    gap: 9px;\n    margin-bottom: 8px;\n  }\n  .quote-avatar {\n    width: 26px;\n    height: 26px;\n    border-radius: 50%;\n    background: #1d9bf0;\n    color: #ffffff;\n    font-size: 13px;\n    font-weight: 700;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    overflow: hidden;\n    flex-shrink: 0;\n  }\n  .quote-avatar img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    display: block;\n  }\n  .quote-author-name {\n    font-size: 15px;\n    font-weight: 800;\n    color: #0f172a;\n  }\n  .quote-author-handle {\n    font-size: 13.5px;\n    font-weight: 500;\n    color: #64748b;\n  }\n  .quote-body {\n    font-size: 15.5px;\n    line-height: 1.58;\n    color: #1e293b;\n    white-space: pre-wrap;\n    word-break: break-word;\n  }\n  .quote-tags {\n    margin-top: 4px;\n    font-size: 15px;\n    line-height: 1.55;\n    color: #1d9bf0;\n    font-weight: 500;\n    word-break: break-word;\n  }\n</style>\n</head>\n<body>\n  <div class="card" id="tweet-card">\n    {% if is_retweet and retweeter_username %}\n    <div class="retweet-banner">\n      <span class="retweet-icon">↻</span>\n      {% if retweeter_avatar_src %}\n      <span class="retweet-mini-avatar">\n        <img src="{{ retweeter_avatar_src }}" onerror="this.parentNode.style.display=\'none\';" />\n      </span>\n      {% endif %}\n      <span>{{ retweeter_name }} (@{{ retweeter_username }}) 已转推</span>\n    </div>\n    {% endif %}\n\n    <div class="header">\n      <div class="author-box">\n        <div class="avatar">\n          {% if avatar_src %}\n          <img src="{{ avatar_src }}" onerror="this.style.display=\'none\';this.parentNode.innerText=\'{{ author_initial }}\';" />\n          {% else %}\n          {{ author_initial }}\n          {% endif %}\n        </div>\n        <div class="author-meta">\n          <div class="author-name-row">\n            <span class="author-name">{{ author_name }}</span>\n            <span class="verified-badge">✓</span>\n          </div>\n          <span class="author-sub">@{{ username }}{% if pub_date %} · {{ pub_date }}{% endif %}</span>\n        </div>\n      </div>\n      <div class="brand-logo">𝕏</div>\n    </div>\n\n    {% if orig_body or orig_tags %}\n    <div class="tweet-section">\n      {% if orig_body %}\n      <div class="tweet-body">{{ orig_body }}</div>\n      {% endif %}\n      {% if orig_tags %}\n      <div class="tweet-tags">{{ orig_tags|join(\' \') }}</div>\n      {% endif %}\n    </div>\n    {% endif %}\n\n    {% if translated_body or translated_tags %}\n    <div class="trans-section">\n      {% if orig_body and translated_body %}\n      <div class="trans-body">{{ translated_body }}</div>\n      {% endif %}\n      {% if translated_tags %}\n      <div class="trans-tags">{{ translated_tags|join(\' \') }}</div>\n      {% endif %}\n    </div>\n    {% endif %}\n\n    {% if vision_matched_tags %}\n    <div style="margin: 10px 0; padding: 10px 12px; background: #ecfdf5; border-radius: 10px; color: #065f46; font-size: 14px; line-height: 1.8; overflow-wrap: anywhere;">\n      <span style="font-weight: 600;">视觉筛选命中：</span>\n      {% for tag in vision_matched_tags %}\n      <span style="display: inline-block; margin: 2px 4px; padding: 1px 8px; border: 1px solid #a7f3d0; border-radius: 12px;">{{ tag | e }}</span>\n      {% endfor %}\n    </div>\n    {% endif %}\n    {% if quote_info %}\n    <div class="quote-card">\n      <div class="quote-header">\n        <div class="quote-avatar">\n          {% if quote_info.avatar_src %}\n          <img src="{{ quote_info.avatar_src }}" onerror="this.style.display=\'none\';this.parentNode.innerText=\'{{ quote_info.author_initial }}\';" />\n          {% else %}\n          {{ quote_info.author_initial }}\n          {% endif %}\n        </div>\n        <span class="quote-author-name">{{ quote_info.author_name }}</span>\n        <span class="quote-author-handle">@{{ quote_info.username }}</span>\n      </div>\n      {% if quote_info.orig_body %}\n      <div class="quote-body">{{ quote_info.orig_body }}</div>\n      {% endif %}\n      {% if quote_info.orig_tags %}\n      <div class="quote-tags">{{ quote_info.orig_tags|join(\' \') }}</div>\n      {% endif %}\n      {% if quote_info.display_images %}\n      <div class="media-grid count-{{ quote_info.display_images|length if quote_info.display_images|length <= 4 else 4 }}">\n        {% for img_src in quote_info.display_images[:4] %}\n        <div class="media-item">\n          <img src="{{ img_src }}" onerror="this.parentNode.style.display=\'none\';" />\n        </div>\n        {% endfor %}\n      </div>\n      {% endif %}\n    </div>\n    {% endif %}\n\n    {% if display_images %}\n    <div class="media-grid count-{{ display_images|length if display_images|length <= 4 else 4 }}">\n      {% for img_src in display_images[:4] %}\n      <div class="media-item">\n        <img src="{{ img_src }}" onerror="this.parentNode.style.display=\'none\';" />\n      </div>\n      {% endfor %}\n    </div>\n    {% endif %}\n  </div>\n</body>\n</html>\n'

DAILY_DIGEST_TMPL = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<style>\n  * {\n    box-sizing: border-box;\n    margin: 0;\n    padding: 0;\n  }\n  html {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #fefefe;\n  }\n  body {\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    background: #ffffff;\n    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;\n    color: #181e29;\n    -webkit-font-smoothing: antialiased;\n  }\n  .digest-page {\n    width: 100%;\n    background: linear-gradient(\n      180deg,\n      rgba(var(--theme-rgb, 254, 228, 238), 0.62) 0%,\n      rgba(var(--theme-mid-rgb, 255, 255, 255), 0.28) 50%,\n      rgba(var(--theme-end-rgb, 235, 228, 255), 0.58) 100%\n    );\n    padding: 34px 36px 38px 36px;\n    position: relative;\n    overflow: hidden;\n  }\n  .page-deco-circle {\n    position: absolute;\n    top: -90px;\n    right: -70px;\n    width: 260px;\n    height: 260px;\n    border-radius: 50%;\n    background: radial-gradient(\n      circle,\n      rgba(var(--theme-accent-rgb, 112, 72, 232), 0.10) 0%,\n      rgba(var(--theme-accent-rgb, 112, 72, 232), 0) 70%\n    );\n    pointer-events: none;\n    z-index: 0;\n  }\n  .digest-header {\n    position: relative;\n    z-index: 2;\n    display: flex;\n    align-items: flex-end;\n    justify-content: space-between;\n    gap: 20px;\n  }\n  .header-left {\n    display: flex;\n    align-items: center;\n    gap: 16px;\n  }\n  .header-accent-bar {\n    width: 8px;\n    height: 46px;\n    border-radius: 99px;\n    background: linear-gradient(\n      180deg,\n      var(--theme-accent, #d6336c) 0%,\n      var(--theme-mid-accent, var(--theme-accent, #d6336c)) 100%\n    );\n    box-shadow: 0 4px 14px rgba(var(--theme-accent-rgb, 214, 51, 108), 0.30);\n    flex-shrink: 0;\n  }\n  .header-title-wrap {\n    display: flex;\n    flex-direction: column;\n    gap: 4px;\n  }\n  .header-title {\n    font-size: 32px;\n    font-weight: 900;\n    color: #141923;\n    letter-spacing: 1.5px;\n    line-height: 1.1;\n  }\n  .header-sub {\n    font-size: 11px;\n    font-weight: 800;\n    letter-spacing: 2.4px;\n    text-transform: uppercase;\n    color: var(--theme-accent, #7048e8);\n    opacity: 0.88;\n  }\n  .header-right {\n    display: flex;\n    flex-direction: column;\n    align-items: flex-end;\n    gap: 7px;\n  }\n  .date-badge {\n    background: rgba(var(--theme-rgb, 236, 229, 255), 0.95);\n    color: var(--theme-accent, #7048e8);\n    border: 1px solid var(--theme-border, #d0bfff);\n    padding: 5px 14px;\n    border-radius: 99px;\n    font-size: 12.5px;\n    font-weight: 800;\n    letter-spacing: 0.8px;\n  }\n  .stats-row {\n    display: flex;\n    align-items: center;\n    gap: 8px;\n    font-size: 12px;\n    font-weight: 600;\n    color: #64748b;\n  }\n  .stats-row strong {\n    color: #1e293b;\n    font-weight: 800;\n  }\n  .stats-dot {\n    width: 4px;\n    height: 4px;\n    border-radius: 50%;\n    background: var(--theme-accent, #7048e8);\n    opacity: 0.45;\n  }\n  .header-divider {\n    position: relative;\n    z-index: 2;\n    height: 2.5px;\n    margin: 20px 0 24px 0;\n    border-radius: 99px;\n    background: linear-gradient(\n      90deg,\n      var(--theme-accent, #d6336c) 0%,\n      var(--theme-mid-accent, var(--theme-border, #f9b8d4)) 45%,\n      rgba(var(--theme-end-accent-rgb, var(--theme-accent-rgb, 214, 51, 108)), 0.22) 100%\n    );\n  }\n  .digest-list {\n    position: relative;\n    z-index: 2;\n    display: flex;\n    flex-direction: column;\n    gap: 18px;\n  }\n  .news-card {\n    position: relative;\n    width: 100%;\n    border-radius: 22px;\n    overflow: hidden;\n    background: linear-gradient(\n      90deg,\n      rgb(var(--card-rgb)) 0%,\n      rgb(var(--card-soft-rgb)) 100%\n    );\n    border: 1.5px solid var(--card-border);\n    box-shadow:\n      0 10px 26px -10px rgba(var(--accent-rgb), 0.15),\n      inset 0 1px 0 rgba(255, 255, 255, 0.75);\n    display: flex;\n    align-items: stretch;\n  }\n  .news-card.has-image {\n    min-height: 178px;\n  }\n  .news-card.no-image {\n    min-height: 136px;\n  }\n  .card-accent-strip {\n    width: 6px;\n    background: var(--accent);\n    flex-shrink: 0;\n    z-index: 3;\n  }\n  .card-body {\n    position: relative;\n    z-index: 3;\n    display: flex;\n    flex-direction: column;\n    justify-content: center;\n  }\n  .news-card.has-image .card-body {\n    width: 64%;\n    padding: 22px 18px 22px 22px;\n  }\n  .news-card.no-image .card-body {\n    width: 100%;\n    padding: 22px 28px 22px 22px;\n  }\n  .card-meta {\n    display: flex;\n    align-items: center;\n    flex-wrap: wrap;\n    gap: 8px;\n    margin-bottom: 9px;\n  }\n  .card-num {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    height: 22px;\n    padding: 0 9px;\n    border-radius: 99px;\n    background: var(--accent);\n    color: #ffffff;\n    font-size: 11.5px;\n    font-weight: 800;\n    letter-spacing: 0.6px;\n    box-shadow: 0 2px 6px rgba(var(--accent-rgb), 0.25);\n  }\n  .card-cat {\n    display: inline-flex;\n    align-items: center;\n    height: 22px;\n    padding: 0 10px;\n    border-radius: 99px;\n    background: var(--tag-bg);\n    color: var(--accent);\n    border: 1px solid rgba(var(--accent-rgb), 0.24);\n    font-size: 11.5px;\n    font-weight: 700;\n    letter-spacing: 0.3px;\n  }\n  .card-author {\n    font-size: 12.5px;\n    font-weight: 700;\n    color: #334155;\n  }\n  .card-time {\n    font-size: 11.5px;\n    font-weight: 500;\n    color: #64748b;\n  }\n  .card-title {\n    font-size: 19px;\n    font-weight: 850;\n    color: #141923;\n    line-height: 1.38;\n    margin-bottom: 7px;\n    letter-spacing: 0.2px;\n  }\n  .card-summary {\n    font-size: 14.5px;\n    font-weight: 500;\n    color: #2d3748;\n    line-height: 1.66;\n    word-break: break-word;\n  }\n  /* 使用 CSS mask-image 控制图片自身的 Alpha 透明度，从右向左逐渐透明融入卡片马卡龙底色，绝不发白、绝无接缝 */\n  .card-artwork {\n    position: absolute;\n    top: 0;\n    right: 0;\n    bottom: 0;\n    width: 58%;\n    z-index: 1;\n    overflow: hidden;\n    -webkit-mask-image: linear-gradient(\n      90deg,\n      rgba(0, 0, 0, 0) 0%,\n      rgba(0, 0, 0, 0.04) 12%,\n      rgba(0, 0, 0, 0.18) 28%,\n      rgba(0, 0, 0, 0.48) 48%,\n      rgba(0, 0, 0, 0.80) 68%,\n      rgba(0, 0, 0, 0.96) 85%,\n      rgba(0, 0, 0, 1) 100%\n    );\n    mask-image: linear-gradient(\n      90deg,\n      rgba(0, 0, 0, 0) 0%,\n      rgba(0, 0, 0, 0.04) 12%,\n      rgba(0, 0, 0, 0.18) 28%,\n      rgba(0, 0, 0, 0.48) 48%,\n      rgba(0, 0, 0, 0.80) 68%,\n      rgba(0, 0, 0, 0.96) 85%,\n      rgba(0, 0, 0, 1) 100%\n    );\n  }\n  .card-artwork img {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    object-position: center 20%;\n    display: block;\n  }\n  .card-watermark-num {\n    position: absolute;\n    right: 22px;\n    bottom: -10px;\n    font-size: 76px;\n    font-weight: 900;\n    line-height: 1;\n    letter-spacing: -2px;\n    color: rgba(var(--accent-rgb), 0.08);\n    pointer-events: none;\n    z-index: 1;\n    user-select: none;\n  }\n</style>\n</head>\n<body>\n  <div\n    class="digest-page"\n    style="\n      --theme-rgb: {{ theme.card_rgb }};\n      --theme-soft-rgb: {{ theme.card_soft_rgb }};\n      --theme-border: {{ theme.card_border }};\n      --theme-accent: {{ theme.accent }};\n      --theme-accent-rgb: {{ theme.accent_rgb }};\n      --theme-mid-rgb: {{ (theme_mid or theme).card_rgb }};\n      --theme-mid-accent: {{ (theme_mid or theme).accent }};\n      --theme-end-rgb: {{ (theme_end or theme).card_soft_rgb }};\n      --theme-end-accent-rgb: {{ (theme_end or theme).accent_rgb }};\n    "\n  >\n    <div class="page-deco-circle"></div>\n\n    <div class="digest-header">\n      <div class="header-left">\n        <div class="header-accent-bar"></div>\n        <div class="header-title-wrap">\n          <div class="header-title">今日要闻</div>\n          <div class="header-sub">DAILY CURATED BRIEFING</div>\n        </div>\n      </div>\n\n      <div class="header-right">\n        <div class="date-badge">{{ date_str }}</div>\n        <div class="stats-row">\n          <span>24H 收录 <strong>{{ total_count }}</strong></span>\n          <span class="stats-dot"></span>\n          <span>精选 <strong>{{ items|length }}</strong></span>\n          <span class="stats-dot"></span>\n          <span>订阅 <strong>{{ account_count }}</strong></span>\n        </div>\n      </div>\n    </div>\n\n    <div class="header-divider"></div>\n\n    <div class="digest-list">\n      {% for item in items %}\n      <div\n        class="news-card {% if item.thumb_src %}has-image{% else %}no-image{% endif %}"\n        style="\n          --card-rgb: {{ item.palette.card_rgb }};\n          --card-soft-rgb: {{ item.palette.card_soft_rgb }};\n          --card-border: {{ item.palette.card_border }};\n          --accent: {{ item.palette.accent }};\n          --accent-rgb: {{ item.palette.accent_rgb }};\n          --tag-bg: {{ item.palette.tag_bg }};\n        "\n      >\n        <div class="card-accent-strip"></div>\n\n        <div class="card-body">\n          <div class="card-meta">\n            <span class="card-num">{{ "%02d"|format(loop.index) }}</span>\n            <span class="card-cat">{{ item.category or "资讯速递" }}</span>\n            <span class="card-author">@{{ item.username }}{% if item.author_name and item.author_name != item.username %} · {{ item.author_name }}{% endif %}</span>\n            {% if item.pub_date %}\n            <span class="card-time">{{ item.pub_date }}</span>\n            {% endif %}\n          </div>\n          <div class="card-title">{{ item.title }}</div>\n          <div class="card-summary">{{ item.summary }}</div>\n        </div>\n\n        {% if item.thumb_src %}\n        <div class="card-artwork">\n          <img src="{{ item.thumb_src }}" onerror="this.parentNode.style.display=\'none\';" />\n        </div>\n        {% else %}\n        <div class="card-watermark-num">{{ "%02d"|format(loop.index) }}</div>\n        {% endif %}\n      </div>\n      {% endfor %}\n    </div>\n  </div>\n</body>\n</html>\n'


# 内置多源回退路由列表
DEFAULT_HASHTAG_SEARCH_URL = "https://nitter.kareem.one/search/rss?f=tweets&q={query}"
DEFAULT_HASHTAG_FALLBACK_URLS = [
    "https://nitter.meowing.monster/search/rss?f=tweets&q={query}",
    "https://nitter.pp.ua/search/rss?f=tweets&q={query}",
    "https://nitter.netbub.com/search/rss?f=tweets&q={query}",
]

FALLBACK_SOURCE_TEMPLATES = [
    "https://fxtwitter.com/{username}/feed.xml",
    "https://fixupx.com/{username}/feed.xml",
    "https://api.fxtwitter.com/2/profile/{username}/statuses",
    "https://rsshub.rssforever.com/twitter/user/{username}",
    "https://rsshub.pseudoyu.com/twitter/user/{username}",
    "https://hub.slarker.me/twitter/user/{username}",
    "https://nitter.poast.org/{username}/rss",
]

CONFIG_SECTIONS = {
    "global_push_config": ("全局推送配置", ["default_push_image", "default_push_text", "skip_replies", "skip_retweets", "default_push_retweet", "default_push_reply"]),
    "push_format_config": ("推送样式与链接", ["include_external_links", "push_send_mode", "enable_merge_forward_over_3", "merge_forward_image_threshold", "merge_forward_uin"]),
    "ai_config": ("AI 模型与筛选", ["text_provider_id", "vision_provider_id", "image_tweet_bypass_text_filter"]),
    "fetch_config": ("抓取与并发配置", ["poll_interval_minutes", "fetch_concurrency", "processing_concurrency", "request_interval_seconds", "first_run_mark_seen", "test_push_tweet_count"]),
    "source_config": ("订阅源与网络配置", ["rss_base_url", "enable_multi_source_fallback", "hashtag_search_url", "hashtag_search_fallback_urls", "http_proxy"]),
    "digest_config": ("每日简报配置", ["enable_daily_digest", "daily_digest_time", "daily_digest_max_items", "daily_digest_prompt"]),
}


MACARON_PALETTES: list[dict[str, str]] = [
    {
        "name": "sakura_blush",
        "card_rgb": "254, 228, 238",
        "card_soft_rgb": "252, 216, 230",
        "card_border": "#F9B8D4",
        "accent": "#D6336C",
        "accent_rgb": "214, 51, 108",
        "tag_bg": "rgba(214, 51, 108, 0.12)",
    },
    {
        "name": "mint_seafoam",
        "card_rgb": "220, 246, 236",
        "card_soft_rgb": "204, 240, 226",
        "card_border": "#8CE9C6",
        "accent": "#0D9488",
        "accent_rgb": "13, 148, 136",
        "tag_bg": "rgba(13, 148, 136, 0.12)",
    },
    {
        "name": "apricot_cream",
        "card_rgb": "254, 233, 212",
        "card_soft_rgb": "253, 222, 192",
        "card_border": "#FDBA8C",
        "accent": "#DD5B19",
        "accent_rgb": "221, 91, 25",
        "tag_bg": "rgba(221, 91, 25, 0.12)",
    },
    {
        "name": "taro_lavender",
        "card_rgb": "235, 228, 255",
        "card_soft_rgb": "224, 214, 254",
        "card_border": "#C4B5FD",
        "accent": "#7048E8",
        "accent_rgb": "112, 72, 232",
        "tag_bg": "rgba(112, 72, 232, 0.12)",
    },
    {
        "name": "soda_sky",
        "card_rgb": "222, 239, 255",
        "card_soft_rgb": "208, 231, 254",
        "card_border": "#93C5FD",
        "accent": "#0284C7",
        "accent_rgb": "2, 132, 199",
        "tag_bg": "rgba(2, 132, 199, 0.12)",
    },
    {
        "name": "lemon_butter",
        "card_rgb": "254, 242, 200",
        "card_soft_rgb": "253, 234, 178",
        "card_border": "#FCD34D",
        "accent": "#B45309",
        "accent_rgb": "180, 83, 9",
        "tag_bg": "rgba(180, 83, 9, 0.12)",
    },
    {
        "name": "matcha_pistachio",
        "card_rgb": "224, 244, 222",
        "card_soft_rgb": "210, 238, 207",
        "card_border": "#86EFAC",
        "accent": "#15803D",
        "accent_rgb": "21, 128, 61",
        "tag_bg": "rgba(21, 128, 61, 0.12)",
    },
    {
        "name": "berry_coral",
        "card_rgb": "254, 226, 230",
        "card_soft_rgb": "253, 212, 218",
        "card_border": "#FDA4AF",
        "accent": "#E11D48",
        "accent_rgb": "225, 29, 72",
        "tag_bg": "rgba(225, 29, 72, 0.12)",
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



def _extract_macaron_palette_from_image_sync(
    img_path: str, fallback: dict[str, str]
) -> dict[str, str]:
    """
    从推文插画中提取主导色相 (Dominant Hue)，并转换为与插画无缝融合的马卡龙色卡：
    - 优先采样画面左半侧（与文字渐变交界处）及全图的高饱和像素，按色相分桶加权统计主色调
    - 将主色相转换为高明度低饱和的马卡龙背景色 (card_rgb / card_soft_rgb)、边框色与高对比度强调色 (accent)
    """
    try:
        from PIL import Image
    except ImportError:
        return fallback

    p = pathlib.Path(img_path)
    if not p.exists() or not p.is_file():
        return fallback

    try:
        with Image.open(p) as im:
            rgb_im = im.convert("RGB").resize((64, 64))
            w, h = rgb_im.size
            px = rgb_im.load()

            num_bins = 24
            bin_weights = [0.0] * num_bins
            bin_h_sum = [0.0] * num_bins
            bin_s_sum = [0.0] * num_bins

            for y in range(h):
                for x in range(w):
                    r, g, b = px[x, y]
                    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
                    hue, light, sat = colorsys.rgb_to_hls(rf, gf, bf)

                    # 过滤接近纯白、纯黑或无彩度灰阶背景像素
                    if light < 0.12 or light > 0.94 or sat < 0.12:
                        continue

                    # 处于卡片左半侧（与渐变文字区交界处）的像素赋予更高权重，使渐变过渡更自然
                    pos_weight = 1.45 if x < (w * 0.55) else 1.0
                    weight = (sat ** 1.15) * (1.0 - abs(light - 0.58)) * pos_weight
                    if weight <= 0:
                        continue

                    b_idx = int(hue * num_bins) % num_bins
                    bin_weights[b_idx] += weight
                    bin_h_sum[b_idx] += hue * weight
                    bin_s_sum[b_idx] += sat * weight

            best_bin = max(range(num_bins), key=lambda i: bin_weights[i])
            if bin_weights[best_bin] <= 0.01:
                return fallback

            dom_h = (bin_h_sum[best_bin] / bin_weights[best_bin]) % 1.0

            def hls_to_rgb_tuple(h_val: float, l_val: float, s_val: float) -> tuple[int, int, int]:
                rr, gg, bb = colorsys.hls_to_rgb(h_val, l_val, s_val)
                return (
                    max(0, min(255, int(round(rr * 255)))),
                    max(0, min(255, int(round(gg * 255)))),
                    max(0, min(255, int(round(bb * 255)))),
                )

            # 1. 马卡龙卡片主背景色 (柔和马卡龙粉彩 L=0.915, S=0.75，避免过白)
            c_r, c_g, c_b = hls_to_rgb_tuple(dom_h, 0.915, 0.75)
            # 2. 马卡龙卡片右侧衔接底色 (L=0.895, S=0.78)
            cs_r, cs_g, cs_b = hls_to_rgb_tuple(dom_h, 0.895, 0.78)
            # 3. 马卡龙边框色 (L=0.84, S=0.75)
            cb_r, cb_g, cb_b = hls_to_rgb_tuple(dom_h, 0.84, 0.75)
            # 4. 胶囊徽章与装饰条强调色 (L=0.44, S=0.76，保证白字与标签文字清晰可读)
            ac_r, ac_g, ac_b = hls_to_rgb_tuple(dom_h, 0.44, 0.76)

            return {
                "name": "image_adaptive_macaron",
                "card_rgb": f"{c_r}, {c_g}, {c_b}",
                "card_soft_rgb": f"{cs_r}, {cs_g}, {cs_b}",
                "card_border": f"#{cb_r:02X}{cb_g:02X}{cb_b:02X}",
                "accent": f"#{ac_r:02X}{ac_g:02X}{ac_b:02X}",
                "accent_rgb": f"{ac_r}, {ac_g}, {ac_b}",
                "tag_bg": f"rgba({ac_r}, {ac_g}, {ac_b}, 0.11)",
            }
    except Exception:
        return fallback



_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter|fxtwitter|fixupx|vxtwitter)\.com/([A-Za-z0-9_]+)/status/(\d+)\S*",
    re.I,
)



def _compute_harmonious_digest_theme(
    rendered_items: list[dict[str, Any]], fallback: dict[str, str]
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    综合所有新闻词条的颜色（而非仅看第 01 条），在色相环上通过余弦亲和度聚类与圆周向量合成，
    计算出最契合整期所有词条的全局主题马卡龙色卡 (theme, theme_mid, theme_end)：
    - 对所有词条提取色相角 (2*pi*H)，含插画词条赋予更高权重
    - 计算每个词条与全局所有词条的色相余弦亲和度得分，找出整期日报的主导色系中心
    - 对主导色系簇内的所有词条进行圆周向量加权平均，合成和谐统一的顶部标题 UI 配色（绝不因互补色直接相加而发灰发脏）
    """
    if not rendered_items:
        return fallback, fallback, fallback

    item_hues: list[tuple[float, float, dict[str, str]]] = []
    for idx, item in enumerate(rendered_items):
        pal = item.get("palette") or fallback
        ac_rgb_str = str(pal.get("accent_rgb") or "214, 51, 108")
        try:
            parts = [int(x.strip()) for x in ac_rgb_str.split(",")]
            r, g, b = parts[0] / 255.0, parts[1] / 255.0, parts[2] / 255.0
            h_val, l_val, s_val = colorsys.rgb_to_hls(r, g, b)
        except Exception:
            h_val, l_val, s_val = 0.94, 0.44, 0.76

        # 含插画提取色的词条权重更高
        w = 1.4 if item.get("thumb_src") else 1.0
        item_hues.append((h_val, w, pal))

    # 1. 计算每个词条在整期所有词条中的色相亲和度得分，找出全局主导色系中心
    best_center_h = item_hues[0][0]
    best_score = -1.0
    for h_i, w_i, _ in item_hues:
        score = 0.0
        for h_j, w_j, _ in item_hues:
            angle_diff = 2.0 * math.pi * (h_i - h_j)
            affinity = max(0.0, math.cos(angle_diff))
            score += w_j * (affinity ** 1.5)
        if score > best_score:
            best_score = score
            best_center_h = h_i

    # 2. 对同属主导色系簇（色相差在 ±50° 内）的所有词条进行圆周向量平均，合成全局代表色相
    sin_sum = 0.0
    cos_sum = 0.0
    for h_j, w_j, _ in item_hues:
        angle_diff = 2.0 * math.pi * (h_j - best_center_h)
        if math.cos(angle_diff) >= math.cos(math.radians(50)):
            rad = 2.0 * math.pi * h_j
            sin_sum += w_j * math.sin(rad)
            cos_sum += w_j * math.cos(rad)

    if abs(sin_sum) > 1e-6 or abs(cos_sum) > 1e-6:
        synth_h = (math.atan2(sin_sum, cos_sum) / (2.0 * math.pi)) % 1.0
    else:
        synth_h = best_center_h

    def build_palette_from_hue(h_val: float) -> dict[str, str]:
        def hls_rgb(hh: float, ll: float, ss: float) -> tuple[int, int, int]:
            rr, gg, bb = colorsys.hls_to_rgb(hh, ll, ss)
            return (
                max(0, min(255, int(round(rr * 255)))),
                max(0, min(255, int(round(gg * 255)))),
                max(0, min(255, int(round(bb * 255)))),
            )

        c_r, c_g, c_b = hls_rgb(h_val, 0.915, 0.75)
        cs_r, cs_g, cs_b = hls_rgb(h_val, 0.895, 0.78)
        cb_r, cb_g, cb_b = hls_rgb(h_val, 0.83, 0.75)
        ac_r, ac_g, ac_b = hls_rgb(h_val, 0.43, 0.76)
        return {
            "name": "digest_AllItems_harmonic",
            "card_rgb": f"{c_r}, {c_g}, {c_b}",
            "card_soft_rgb": f"{cs_r}, {cs_g}, {cs_b}",
            "card_border": f"#{cb_r:02X}{cb_g:02X}{cb_b:02X}",
            "accent": f"#{ac_r:02X}{ac_g:02X}{ac_b:02X}",
            "accent_rgb": f"{ac_r}, {ac_g}, {ac_b}",
            "tag_bg": f"rgba({ac_r}, {ac_g}, {ac_b}, 0.12)",
        }

    main_theme = build_palette_from_hue(synth_h)

    # 3. 找出与主色相搭配的第二代表色（用于渐变过渡条与中段背景）及收尾色
    secondary_candidates = [
        (h_j, w_j)
        for h_j, w_j, _ in item_hues
        if math.cos(2.0 * math.pi * (h_j - synth_h)) < math.cos(math.radians(25))
    ]
    if secondary_candidates:
        sec_h = secondary_candidates[0][0]
        mid_theme = build_palette_from_hue(sec_h)
    else:
        mid_theme = build_palette_from_hue((synth_h + 0.04) % 1.0)

    end_theme = rendered_items[-1].get("palette") or mid_theme
    return main_theme, mid_theme, end_theme


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
        if self._migrate_grouped_config() and hasattr(self.config, "save_config"):
            self.config.save_config()

        # 自动检测并迁移旧版失效的 rsshub.app 官方默认地址
        curr_base = str(self._get_setting("rss_base_url", "") or "").strip()
        if "rsshub.app/twitter/" in curr_base:
            self.config.setdefault("source_config", {})["rss_base_url"] = "https://fxtwitter.com/{username}/feed.xml"
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
        self.digest_archive_dir = self.data_dir / "digest_archive"
        self.digest_archive_dir.mkdir(parents=True, exist_ok=True)
        self.digest_archive_file = self.data_dir / "digest_archive.json"

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
        self.digest_archive: dict[str, dict[str, Any]] = self._load_json_sync(
            self.digest_archive_file, default={}
        )

        # 自动将旧版全局配置平滑迁移到按群聊分类的 group_subscriptions 中
        self._migrate_legacy_config()
        self._sync_subscribed_accounts_to_schema()

        self.http_client: httpx.AsyncClient | None = None
        self._not_found_accounts: set[str] = set()
        self._user_profile_cache: dict[str, dict[str, str]] = {}
        self._status_detail_cache: dict[str, dict[str, Any]] = {}
        self._poll_task: asyncio.Task | None = None
        self._digest_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._http_reinit_lock = asyncio.Lock()
        self._started = False

        # 确保在 WebUI 保存配置或热重载重新实例化插件时，即使未再次触发 on_astrbot_loaded 也能自动启动后台轮询与日志输出
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._ensure_started())
        except RuntimeError:
            pass

    def _migrate_legacy_config(self):
        """如果旧配置中有全局 twitter_accounts 或 push_targets，且 group_subscriptions 为空，则自动迁移"""
        groups = self._get_setting("group_subscriptions")
        if isinstance(groups, list) and len(groups) > 0:
            return

        old_targets = [
            str(x).strip()
            for x in (self._get_setting("push_targets", []) or [])
            if str(x).strip()
        ]
        old_accounts = [
            str(x).strip().lstrip("@")
            for x in (self._get_setting("twitter_accounts", []) or [])
            if str(x).strip()
        ]
        if not old_targets and not old_accounts:
            return

        old_must = [
            str(x).strip()
            for x in (self._get_setting("must_include_image_tags", []) or [])
            if str(x).strip()
        ]
        old_any = [
            str(x).strip()
            for x in (
                self._get_setting("any_include_image_tags")
                or self._get_setting("include_image_tags")
                or ["插画", "二次元"]
            )
            if str(x).strip()
        ]
        old_exc = [
            str(x).strip()
            for x in (
                self._get_setting("exclude_image_tags")
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
                        self._get_setting("enable_vision_tag_filter", True)
                    ),
                    "must_include_image_tags": list(old_must),
                    "any_include_image_tags": list(old_any),
                    "exclude_image_tags": list(old_exc),
                    "enable_text_ai_filter": bool(
                        self._get_setting("enable_text_ai_filter", True)
                    ),
                    "text_filter_prompt": str(
                        self._get_setting(
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
        try:
            await self._init_http_client()
        except (ValueError, ImportError) as exc:
            self._started = False
            logger.error(f"[TwitterRSS] HTTP 客户端初始化失败，后台任务暂未启动：{exc}。请修改代理配置后重载插件。")
            return
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._digest_task = asyncio.create_task(self._digest_loop())
        rules = self._get_group_rules()
        total_accts = sum(len(self._get_rule_accounts(r)) for r in rules)
        interval_min = max(2, int(self._get_setting("poll_interval_minutes", 15) or 15))
        logger.info(
            f"[TwitterRSS] 插件后台服务已启动 | 分群规则数: {len(rules)} 个 | 累计订阅账号: {total_accts} 个 | 轮询间隔: {interval_min} 分钟"
        )

    @staticmethod
    def _normalize_proxy_url(value: Any) -> str | None:
        proxy = str(value or "").strip()
        if not proxy:
            return None
        if proxy.startswith("//"):
            proxy = "http:" + proxy
        elif "://" not in proxy:
            proxy = "http://" + proxy
        try:
            parsed = urlsplit(proxy)
            if parsed.scheme.lower() not in {"http", "https", "socks5", "socks5h"}:
                raise ValueError
            if not parsed.hostname or any(ch.isspace() for ch in parsed.hostname):
                raise ValueError
            if parsed.port is not None and parsed.port < 1:
                raise ValueError
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError
        except ValueError:
            raise ValueError("代理地址格式无效，支持 127.0.0.1:7890 或 http://127.0.0.1:7890 等格式") from None
        return parsed._replace(scheme=parsed.scheme.lower()).geturl()

    async def _init_http_client(self):
        proxy = self._normalize_proxy_url(self._get_setting("http_proxy", ""))
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
        try:
            new_client = httpx.AsyncClient(
                headers=headers,
                proxy=proxy,
                timeout=httpx.Timeout(14.0, connect=7.0, pool=3.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                follow_redirects=True,
            )
        except ImportError:
            raise ImportError("当前环境缺少 SOCKS 代理依赖，请安装 socksio 或改用 HTTP 代理") from None
        except (ValueError, httpx.InvalidURL):
            raise ValueError("无法创建 HTTP 客户端，请检查代理地址的协议、主机及端口格式") from None
        old_client = self.http_client
        self.http_client = new_client
        if old_client and not old_client.is_closed:
            await old_client.aclose()

    async def _http_get_with_recovery(self, url: str) -> httpx.Response:
        """GET with one client reset when the connection pool is exhausted."""
        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        client = self.http_client
        try:
            return await client.get(url)
        except httpx.PoolTimeout:
            # Do not close a shared client while concurrent requests are using it.
            async with self._http_reinit_lock:
                await asyncio.sleep(0.3)
                logger.warning(f"[TwitterRSS] HTTP 连接池繁忙，等待后重试: {url}")
                return await self.http_client.get(url)

    def _feed_host(self, url: str) -> str:
        host = (urlsplit(url).hostname or "").lower()
        # These aliases share an upstream and should share a rate budget.
        return "fxtwitter.com" if host in {"fxtwitter.com", "fixupx.com", "api.fxtwitter.com"} else host

    def _feed_hosts(self) -> dict[str, dict[str, Any]]:
        if not hasattr(self, "_feed_host_states"):
            self._feed_host_states = {}
        return self._feed_host_states

    def _prioritize_feed_urls(self, urls: list[str]) -> list[str]:
        hosts = self._feed_hosts()
        now = time.monotonic()
        def priority(url):
            state = hosts.get(self._feed_host(url), {})
            return (state.get("cooldown", 0) > now, state.get("pending", 0), state.get("next", 0))
        return sorted(urls, key=priority)

    def _cool_down_feed(self, url: str, seconds: float = 30) -> None:
        state = self._feed_hosts().setdefault(self._feed_host(url), {})
        state["cooldown"] = max(state.get("cooldown", 0), time.monotonic() + seconds)

    async def _fetch_feed_response(self, url: str) -> httpx.Response:
        """Serialize feed requests per upstream; other upstreams remain concurrent."""
        state = self._feed_hosts().setdefault(self._feed_host(url), {})
        lock = state.setdefault("lock", asyncio.Lock())
        state["pending"] = state.get("pending", 0) + 1
        try:
            async with lock:
                if state.get("cooldown", 0) > time.monotonic():
                    raise RuntimeError("源站冷却中，尝试其他源")
                delay = state.get("next", 0) - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                interval = max(0.3, float(self._get_setting("request_interval_seconds", 1.5) or 1.5))
                state["next"] = time.monotonic() + interval
                try:
                    resp = await self._http_get_with_recovery(url)
                except httpx.RequestError:
                    self._cool_down_feed(url)
                    raise
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "60")
                    try:
                        seconds = float(retry_after)
                    except (ValueError, TypeError):
                        try:
                            seconds = email.utils.parsedate_to_datetime(retry_after).timestamp() - time.time()
                        except (ValueError, TypeError, OverflowError):
                            seconds = 60
                    self._cool_down_feed(url, max(1, seconds))
                elif resp.status_code == 403 or resp.status_code >= 500:
                    self._cool_down_feed(url, 60)
                return resp
        finally:
            state["pending"] -= 1

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
        if not hasattr(self, "_state_write_lock"):
            self._state_write_lock = asyncio.Lock()
        async with self._state_write_lock:
            payload = json.dumps(self.state, ensure_ascii=False, indent=2)
            def _write():
                temporary = self.state_file.with_suffix(".json.tmp")
                temporary.write_text(payload, encoding="utf-8")
                temporary.replace(self.state_file)
            await asyncio.to_thread(_write)

    async def _save_digest_archive(self):
        def _write():
            self.digest_archive_file.write_text(
                json.dumps(self.digest_archive, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        await asyncio.to_thread(_write)

    @staticmethod
    def _parse_query_date(date_str: str) -> str:
        """
        将用户输入的日期解析为标准的 YYYY-MM-DD 格式：
        支持：今天/昨天/前天、2026-10-14、2026.10.14、2026/10/14、20261014、10-14、10.14、10月14日
        """
        s = (date_str or "").strip()
        if not s:
            return ""
        now = datetime.datetime.now()
        if s in ("今天", "今日", "today", "Today"):
            return now.strftime("%Y-%m-%d")
        if s in ("昨天", "昨日", "yesterday", "Yesterday"):
            return (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        if s in ("前天", "前日"):
            return (now - datetime.timedelta(days=2)).strftime("%Y-%m-%d")

        if re.match(r"^\d{8}$", s):
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

        m_full = re.match(r"^(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})日?$", s)
        if m_full:
            y, m, d = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
            return f"{y:04d}-{m:02d}-{d:02d}"

        m_short = re.match(r"^(\d{1,2})[-./月](\d{1,2})日?$", s)
        if m_short:
            m, d = int(m_short.group(1)), int(m_short.group(2))
            return f"{now.year:04d}-{m:02d}-{d:02d}"

        return ""

    async def _archive_daily_digest(
        self,
        umo: str,
        group_name: str,
        date_key: str,
        digest_img_path: str,
        render_data: dict[str, Any],
    ) -> str:
        """将生成的每日要闻长图及元数据持久化归档到本地 digest_archive 目录"""
        umo_hash = hashlib.md5(umo.encode("utf-8")).hexdigest()[:12]
        archived_img_path = self.digest_archive_dir / f"digest_{umo_hash}_{date_key}.png"

        def _copy_img():
            src_p = pathlib.Path(digest_img_path)
            if src_p.exists() and src_p.is_file():
                shutil.copy2(src_p, archived_img_path)

        await asyncio.to_thread(_copy_img)

        light_items: list[dict[str, Any]] = []
        for it in render_data.get("items", []):
            light_items.append(
                {
                    "category": it.get("category", ""),
                    "username": it.get("username", ""),
                    "author_name": it.get("author_name", ""),
                    "pub_date": it.get("pub_date", ""),
                    "title": it.get("title", ""),
                    "summary": it.get("summary", ""),
                    "raw_image_url": it.get("raw_image_url", ""),
                    "palette": it.get("palette", {}),
                }
            )

        group_bucket = self.digest_archive.setdefault(umo, {})
        group_bucket[date_key] = {
            "date_key": date_key,
            "date_str": render_data.get("date_str", date_key.replace("-", ".")),
            "group_name": group_name,
            "umo": umo,
            "image_path": str(archived_img_path),
            "total_count": render_data.get("total_count", 0),
            "account_count": render_data.get("account_count", 0),
            "item_count": len(light_items),
            "theme": render_data.get("theme", {}),
            "theme_mid": render_data.get("theme_mid", {}),
            "theme_end": render_data.get("theme_end", {}),
            "items_meta": light_items,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        await self._save_digest_archive()
        return str(archived_img_path)

    async def _get_or_rerender_archived_digest(
        self, umo: str, date_key: str
    ) -> tuple[bool, str]:
        """根据群聊 UMO 与日期 YYYY-MM-DD 调取本地归档的日报图片；若原图被清理则根据归档元数据重新渲染"""
        group_bucket = self.digest_archive.get(umo, {})
        record = group_bucket.get(date_key)

        if not record:
            umo_tail = umo.split(":")[-1]
            for k_umo, bucket in self.digest_archive.items():
                if k_umo.endswith(umo_tail) and date_key in bucket:
                    record = bucket[date_key]
                    break

        if not record:
            return False, ""

        img_path_str = str(record.get("image_path") or "")
        if img_path_str and pathlib.Path(img_path_str).exists():
            return True, img_path_str

        items_meta = record.get("items_meta") or []
        if not items_meta:
            return False, ""

        rebuilt_items: list[dict[str, Any]] = []
        for it in items_meta:
            thumb_src = ""
            raw_u = it.get("raw_image_url", "")
            if raw_u:
                _, b64_uri = await self._download_image_cached(raw_u)
                thumb_src = b64_uri or raw_u
            rebuilt_items.append(
                {
                    "category": it.get("category", "资讯速递"),
                    "username": it.get("username", ""),
                    "author_name": it.get("author_name", ""),
                    "pub_date": it.get("pub_date", ""),
                    "title": it.get("title", ""),
                    "summary": it.get("summary", ""),
                    "thumb_src": thumb_src,
                    "palette": it.get("palette") or MACARON_PALETTES[0],
                }
            )

        render_data = {
            "date_str": record.get("date_str") or date_key.replace("-", "."),
            "total_count": record.get("total_count", len(rebuilt_items)),
            "account_count": record.get("account_count", 0),
            "theme": record.get("theme") or MACARON_PALETTES[0],
            "theme_mid": record.get("theme_mid") or MACARON_PALETTES[0],
            "theme_end": record.get("theme_end") or MACARON_PALETTES[0],
            "items": rebuilt_items,
        }
        new_img_path = await self._render_html_to_image(DAILY_DIGEST_TMPL, render_data)
        umo_hash = hashlib.md5(umo.encode("utf-8")).hexdigest()[:12]
        archived_img_path = self.digest_archive_dir / f"digest_{umo_hash}_{date_key}.png"
        try:
            shutil.copy2(new_img_path, archived_img_path)
            record["image_path"] = str(archived_img_path)
            await self._save_digest_archive()
            return True, str(archived_img_path)
        except Exception:
            return True, new_img_path

    async def _clear_local_cache(self, scope: str = "cache") -> dict[str, Any]:
        """
        清理本地缓存：
        - scope="cache" (默认): 清理本地推文缓存 (history_tweets.json)、图片缓存 (img_cache/) 及内存缓存，保留日报归档与已读记录
        - scope="archive": 仅清理历史日报归档 (digest_archive/ 与 digest_archive.json)
        - scope="all": 清理所有本地缓存（推文缓存、图片缓存、历史日报归档、已读 seen_ids）
        """
        scope_clean = (scope or "cache").strip().lower()
        removed_files = 0
        freed_bytes = 0

        def _delete_dir_files(directory: pathlib.Path):
            nonlocal removed_files, freed_bytes
            if not directory.exists():
                return
            for p in directory.iterdir():
                if p.is_file():
                    try:
                        freed_bytes += p.stat().st_size
                        p.unlink()
                        removed_files += 1
                    except Exception:
                        pass

        cleared_tweets = 0
        cleared_archives = 0

        if scope_clean in ("cache", "default", "tweets", "images", "all"):
            cleared_tweets = len(self.history_tweets)
            self.history_tweets = []
            await self._save_history()
            await asyncio.to_thread(_delete_dir_files, self.image_cache_dir)
            self._user_profile_cache.clear()
            self._status_detail_cache.clear()
            self._not_found_accounts.clear()

        if scope_clean in ("archive", "digest", "all"):
            for bucket in self.digest_archive.values():
                cleared_archives += len(bucket)
            self.digest_archive = {}
            await self._save_digest_archive()
            await asyncio.to_thread(_delete_dir_files, self.digest_archive_dir)

        if scope_clean == "all":
            self.state["seen_ids"] = {}
            self.state["initialized_keys"] = []
            await self._save_state()

        return {
            "scope": scope_clean,
            "removed_files": removed_files,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
            "cleared_tweets": cleared_tweets,
            "cleared_archives": cleared_archives,
        }

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
        self._sync_subscribed_accounts_to_schema()

    @staticmethod
    def _extract_clean_handle(raw_str: Any) -> str:
        """
        从可能带有状态圆点/修改标记的显示字符串（如 '🟠 ProjMoonStudio [纯文字:直接推送]' 或 '⚪ rasra25'）
        中提取纯净的推特账号名（如 'ProjMoonStudio'）。
        """
        s = str(raw_str or "").strip()
        if not s:
            return ""
        if s.startswith(("http://", "https://")):
            return s.split()[0].strip()
        tag_match = re.match(r"^[^\w@#＃]*[#＃](\w+)", s, flags=re.UNICODE)
        if tag_match:
            return f"#{tag_match.group(1)}"
        # 移除开头的彩色圆点 Emoji 或特殊符号
        s = re.sub(r"^[^A-Za-z0-9_@]+", "", s).strip()
        # 截取空白符、方括号、圆括号或全角括号之前的账号主体
        s = re.split(r"[\s\[\(（【]", s, maxsplit=1)[0].strip().lstrip("@")
        return s

    @classmethod
    def _format_override_summary(cls, ov_dict: dict[str, Any]) -> str:
        """生成单账号已修改开关的简短中文摘要，如 '转贴:推送,纯文字:直接推送'"""
        if not isinstance(ov_dict, dict) or not ov_dict:
            return ""
        label_map = {"retweet": "转贴", "reply": "回复", "text": "纯文字", "image": "图片"}
        mode_cn = {"direct": "直接推送", "push": "推送", "skip": "不推送"}
        parts: list[str] = []
        for k in ("retweet", "reply", "text", "image"):
            if k in ov_dict:
                m = cls._parse_switch_mode(ov_dict.get(k))
                if m in mode_cn:
                    parts.append(f"{label_map[k]}:{mode_cn[m]}")
        return ",".join(parts)

    @classmethod
    def _account_switch_panels(cls, switches: Any) -> dict[str, Any]:
        if isinstance(switches, list):
            return {
                cls._extract_clean_handle(entry.get("account")): entry
                for entry in switches
                if isinstance(entry, dict) and cls._extract_clean_handle(entry.get("account"))
            }
        if not isinstance(switches, dict):
            return {}
        panels = dict(switches)
        for key, value in switches.items():
            if key.startswith("ov_") and "__push_" in key:
                account, field = key[3:].split("__", 1)
                panels.setdefault(account, {})[field] = value
        return panels

    def _ingest_account_switches_from_rules(self) -> bool:
        """
        将各群 group_rule['account_switches'] 中每个订阅账号各自独立的四项开关面板同步持久化到
        group_rule['account_type_overrides'] 中，并自动为已修改账号在列表与面板标题中加上 🟠 颜色标记。
        """
        dirty = False
        key_map = {
            "retweet": "push_retweet",
            "reply": "push_reply",
            "text": "push_text",
            "image": "push_image",
        }
        mode_to_ui = {"direct": "直接推送", "push": "推送", "skip": "不推送"}

        for r in self._get_group_rules():
            overrides_map = r.setdefault("account_type_overrides", {})
            if not isinstance(overrides_map, dict):
                overrides_map = {}
                r["account_type_overrides"] = overrides_map

            # 1. 先将 overrides_map 中旧的 bool 值统一规范化为 'push'/'skip'/'direct'
            for k_acct, ov_val in list(overrides_map.items()):
                if isinstance(ov_val, dict):
                    norm_ov: dict[str, str] = {}
                    for ks, mv in ov_val.items():
                        pm = self._parse_switch_mode(mv)
                        if pm is not None:
                            norm_ov[ks] = pm
                    if norm_ov:
                        overrides_map[k_acct] = norm_ov
                    else:
                        overrides_map.pop(k_acct, None)

            sw = self._account_switch_panels(r.get("account_switches"))
            if not isinstance(sw, dict):
                sw = {}
                r["account_switches"] = sw

            # 2. 兼容读取旧版顶层选中的 account 字段（若存在）
            legacy_acct = self._extract_clean_handle(sw.get("account"))
            if legacy_acct and any(k_cfg in sw for k_cfg in key_map.values()):
                acct_lower = legacy_acct.lower()
                legacy_ov: dict[str, str] = {}
                for k_short, k_cfg in key_map.items():
                    pm = self._parse_switch_mode(sw.get(k_cfg))
                    if pm is not None:
                        legacy_ov[k_short] = pm
                if legacy_ov:
                    overrides_map[acct_lower] = legacy_ov
                    dirty = True
                for old_k in ("account", "push_retweet", "push_reply", "push_text", "push_image"):
                    if old_k in sw:
                        sw.pop(old_k, None)
                        dirty = True

            # 3. 读取每个账号自己独立的子面板 sw[acct_key] = {"push_retweet": ..., "push_reply": ..., "push_text": ..., "push_image": ...}
            for sub_key, sub_val in list(sw.items()):
                if not isinstance(sub_val, dict):
                    continue
                raw_k = sub_key[3:] if sub_key.startswith("ov_") else sub_key
                clean_sub_acct = self._extract_clean_handle(raw_k)
                if not clean_sub_acct:
                    continue
                acct_lower = clean_sub_acct.lower()
                new_ov: dict[str, str] = {}
                for k_short, k_cfg in key_map.items():
                    pm = self._parse_switch_mode(sub_val.get(k_cfg))
                    if pm is not None:
                        new_ov[k_short] = pm
                if new_ov:
                    if overrides_map.get(acct_lower) != new_ov:
                        overrides_map[acct_lower] = new_ov
                        dirty = True
                elif acct_lower in overrides_map:
                    overrides_map.pop(acct_lower, None)
                    dirty = True

            # 4. 按照本群当前订阅的纯净账号列表，规范化构建每个账号在 sw 中的独立开关字典，并给已修改账号在 twitter_accounts 中标上 🟠
            clean_accts = self._get_rule_accounts(r)
            switch_targets = clean_accts + [f"#{tag}" for tag in self._get_rule_hashtags(r)]
            decorated_list: list[str] = []
            normalized_sw: dict[str, str] = {}
            selected = self._extract_clean_handle(sw.get("account")).lower()

            for a in switch_targets:
                ov = overrides_map.get(a.lower(), {})
                summary = self._format_override_summary(ov)
                if a in clean_accts:
                    if summary:
                        decorated_list.append(f"🟠 {a} [{summary}]")
                    else:
                        decorated_list.append(a)

                display = f"{a} [已修改: {summary}]" if summary else a
                if a.lower() == selected or "account" not in normalized_sw:
                    normalized_sw["account"] = display
                for k_short, k_cfg in key_map.items():
                    normalized_sw[f"ov_{a}__{k_cfg}"] = mode_to_ui.get(ov.get(k_short, ""), "默认")

            if r.get("twitter_accounts") != decorated_list:
                r["twitter_accounts"] = decorated_list
                dirty = True

            if r.get("account_switches") != normalized_sw:
                r["account_switches"] = normalized_sw
                dirty = True

        return dirty

    def _get_setting(self, key: str, default: Any = None) -> Any:
        for section, (_, fields) in CONFIG_SECTIONS.items():
            if key in fields:
                values = self.config.get(section)
                if isinstance(values, dict) and key in values:
                    return values[key]
                break
        return self.config.get(key, default)

    def _migrate_grouped_config(self) -> bool:
        """Move legacy flat settings into sections, preserving saved values over new defaults."""
        changed = False
        for section, (_, fields) in CONFIG_SECTIONS.items():
            for field in fields:
                if field in self.config:
                    if not isinstance(self.config.get(section), dict):
                        self.config[section] = {}
                    self.config[section][field] = self.config.pop(field)
                    changed = True
        return changed

    @staticmethod
    def _group_config_schema(schema: dict[str, Any]) -> None:
        for section, (label, fields) in CONFIG_SECTIONS.items():
            existing = schema.get(section, {}).get("items", {})
            items = {}
            for field in fields:
                definition = schema.pop(field, existing.get(field))
                if definition is not None:
                    items[field] = definition
            schema[section] = {"description": label, "type": "object", "items": items}

    def _sync_subscribed_accounts_to_schema(self):
        """
        为每个群聊生成可独立编辑的账号列表，每个账号保存四项推送策略。
        """
        try:
            import copy
            dirty = self._ingest_account_switches_from_rules()

            rules = self._get_group_rules()
            per_group_sw_items: dict[str, tuple[str, dict[str, Any]]] = {}

            for idx, r in enumerate(rules):
                t_key = "group_rule" if idx == 0 else f"group_rule_{idx}"
                if r.get("__template_key") != t_key:
                    r["__template_key"] = t_key
                    dirty = True
                gname = str(r.get("group_name") or f"群聊 {idx + 1}")
                accts = self._get_rule_accounts(r) + [f"#{tag}" for tag in self._get_rule_hashtags(r)]
                ov_map = r.get("account_type_overrides") or {}

                acct_panels: dict[str, Any] = {}
                for a in accts:
                    ov = ov_map.get(a.lower(), {}) if isinstance(ov_map, dict) else {}
                    summary = self._format_override_summary(ov)
                    desc_title = (
                        f"🟠 @{a} 【已修改: {summary}】"
                        if summary
                        else f"⚪ @{a} （默认全局设置）"
                    )
                    acct_panels[a] = {
                        "description": desc_title,
                        "type": "object",
                        "items": {
                            "push_retweet": {
                                "description": "转贴 (RT)",
                                "type": "string",
                                "options": ["默认", "推送", "直接推送", "不推送"],
                                "default": "默认",
                            },
                            "push_reply": {
                                "description": "回复",
                                "type": "string",
                                "options": ["默认", "推送", "直接推送", "不推送"],
                                "default": "默认",
                            },
                            "push_text": {
                                "description": "纯文字",
                                "type": "string",
                                "options": ["默认", "推送", "直接推送", "不推送"],
                                "default": "默认",
                            },
                            "push_image": {
                                "description": "图片",
                                "type": "string",
                                "options": ["默认", "推送", "直接推送", "不推送"],
                                "default": "默认",
                            },
                        },
                    }
                per_group_sw_items[t_key] = (gname, acct_panels)

            if not per_group_sw_items:
                per_group_sw_items["group_rule"] = ("群聊独立订阅与标签配置", {})

            # 若配置数据发生了规范化或持久化更新，立即写回配置文件磁盘，防止刷新页面丢失！
            if dirty and hasattr(self.config, "save_config"):
                try:
                    self.config.save_config()
                except Exception as save_err:
                    logger.debug(f"[TwitterRSS] 保存单账号开关配置跳过: {save_err}")

            def _apply_options_to_schema_dict(s_dict: dict[str, Any]) -> bool:
                original_schema = copy.deepcopy(s_dict)
                changed_flag = False
                s_dict["include_external_links"] = {
                    "description": "推送时附带站外链接", "type": "bool", "default": True,
                    "hint": "自动附带推文正文、RSS 超链接及引用推文中的站外 HTTP(S) 链接，以可点击文本发送并去重。排除 X/Twitter、自有媒体域名及常见推特镜像；短链优先使用订阅源提供的展开地址。",
                }
                test_field = copy.deepcopy(s_dict.get("test_push_tweet_count") or s_dict.get("fetch_config", {}).get("items", {}).get("test_push_tweet_count", {}))
                test_field.update({
                    "description": "随机测试默认订阅数量", "type": "int", "default": 3,
                    "hint": "/tw test 3 只随机测试本群 3 个订阅，各抽取 1 条推文，失败或无候选时不扩展到其他订阅。/tw test <账号> 2 仅从指定账号随机抽取 2 条。沿用本群筛选规则。",
                })
                s_dict["test_push_tweet_count"] = test_field
                s_dict["http_proxy"] = {
                    "description": "HTTP/HTTPS 代理地址（可选）", "type": "string", "default": "",
                    "hint": "支持 127.0.0.1:7890，省略协议时自动补 http://；也可填写完整 HTTP/HTTPS 或 SOCKS5 地址（SOCKS 需 socksio）。留空不指定代理。格式无效时记录错误并暂停后台任务，修正后重载生效。",
                }
                concurrency_fields = {
                    "fetch_concurrency": {
                        "description": "订阅抓取并发数", "type": "int", "default": 4,
                        "hint": "同时抓取不同账号或标签的任务数，范围 1~12。优先分散到不同站点；同一源站串行并保留请求间隔。",
                    },
                    "processing_concurrency": {
                        "description": "分群筛选推送并发数", "type": "int", "default": 3,
                        "hint": "同时执行分群 AI 筛选与推送的任务数，范围 1~8。各群独立评估，同一群按队列处理。",
                    },
                    "request_interval_seconds": {
                        "description": "同源站订阅抓取间隔秒数（防高频限流）", "type": "float", "default": 1.5,
                        "hint": "同一源站两次订阅请求开始时间的最小间隔；不同站点可并发。FxTwitter、FixupX 和 FxTwitter API 共用限速。429 按 Retry-After 冷却并回退。",
                    },
                }
                for field, definition in concurrency_fields.items():
                    if s_dict.get(field) != definition:
                        s_dict[field] = definition
                        changed_flag = True
                search_field = {
                    "description": "标签搜索 RSS 接口地址",
                    "type": "string", "default": DEFAULT_HASHTAG_SEARCH_URL,
                    "hint": "默认使用公开 Nitter 搜索 RSS，无需密钥。{query} 自动替换为编码后的 #标签；留空也使用默认源。也可填写自建 RSSHub 搜索 URL。公共实例可能限流或停用。",
                }
                if s_dict.get("hashtag_search_url") != search_field:
                    s_dict["hashtag_search_url"] = search_field
                    changed_flag = True
                fallback_field = {
                    "description": "标签搜索回退源（按顺序尝试）",
                    "type": "list", "default": list(DEFAULT_HASHTAG_FALLBACK_URLS),
                    "hint": "主源失败后按列表顺序回退。预选 meowing.monster、pp.ua、netbub.com；后两者当前出口可能遇到 403。均需含 {query}。可增删或调整顺序，清空列表关闭回退。",
                }
                if s_dict.get("hashtag_search_fallback_urls") != fallback_field:
                    s_dict["hashtag_search_fallback_urls"] = fallback_field
                    changed_flag = True
                try:
                    templates_dict = s_dict.get("group_subscriptions", {}).get("templates", {})
                    if not isinstance(templates_dict, dict) or "group_rule" not in templates_dict:
                        return False
                    base_tmpl = copy.deepcopy(templates_dict["group_rule"])

                    for old_k in list(templates_dict.keys()):
                        if old_k.startswith("group_rule_") and old_k not in per_group_sw_items:
                            templates_dict.pop(old_k, None)
                            changed_flag = True

                    for t_key, (gname, acct_panels) in per_group_sw_items.items():
                        if t_key not in templates_dict:
                            templates_dict[t_key] = copy.deepcopy(base_tmpl)
                            changed_flag = True
                        tmpl_obj = templates_dict[t_key]
                        tag_field = {
                            "description": "本群订阅的推特标签列表",
                            "type": "list", "default": [],
                            "hint": "按 #标签 搜索不限账号的推文，例如 原神、ブルアカ，可省略 #。需配置标签搜索 RSS 接口；与图片 AI 筛选标签不同。",
                        }
                        if tmpl_obj["items"].get("twitter_hashtags") != tag_field:
                            reordered = {}
                            for field_key, field_value in tmpl_obj["items"].items():
                                if field_key == "twitter_hashtags":
                                    continue
                                reordered[field_key] = field_value
                                if field_key == "twitter_accounts":
                                    reordered["twitter_hashtags"] = tag_field
                            tmpl_obj["items"] = reordered
                            changed_flag = True
                        expected_name = (
                            "群聊独立订阅与标签配置"
                            if t_key == "group_rule"
                            else f"群聊独立订阅与标签配置 ({gname})"
                        )
                        if tmpl_obj.get("name") != expected_name:
                            tmpl_obj["name"] = expected_name
                            changed_flag = True

                        sw_obj = tmpl_obj.get("items", {}).get("account_switches")
                        if isinstance(sw_obj, dict):
                            group = next((rule for rule in rules if rule.get("__template_key") == t_key), {})
                            overrides = group.get("account_type_overrides", {})
                            choices = []
                            fields = {}
                            for account in acct_panels:
                                summary = self._format_override_summary(overrides.get(account.lower(), {}))
                                choice = f"{account} [已修改: {summary}]" if summary else account
                                choices.append(choice)
                                for key, label in (("push_retweet", "转贴 (RT)"), ("push_reply", "回复"), ("push_text", "纯文字"), ("push_image", "图片")):
                                    fields[f"ov_{account}__{key}"] = {
                                        "description": label, "type": "string", "default": "默认",
                                        "options": ["默认", "推送", "直接推送", "不推送"],
                                        "condition": {"account_switches.account": choice},
                                    }
                            fields = {"account": {"description": "账号", "type": "string", "default": choices[0] if choices else "", "options": choices}, **fields}
                            expected = {
                                "description": "单账号独立推送开关",
                                "type": "object",
                                "items": fields,
                            }
                            if sw_obj != expected:
                                tmpl_obj["items"]["account_switches"] = expected
                                changed_flag = True
                except Exception:
                    pass
                self._group_config_schema(s_dict)
                return s_dict != original_schema

            # 1. 更新内存中的 config.schema 及 AstrBot StarMetadata.config_schema（实时生效无需重启）
            mem_schema = getattr(self.config, "schema", None)
            if isinstance(mem_schema, dict):
                _apply_options_to_schema_dict(mem_schema)

            ctx_obj = getattr(self, "context", None)
            if ctx_obj is not None and hasattr(ctx_obj, "get_all_stars"):
                try:
                    for star_meta in ctx_obj.get_all_stars() or []:
                        if getattr(star_meta, "name", "") == "astrbot_plugin_twitter_rss":
                            cs = getattr(star_meta, "config_schema", None)
                            if isinstance(cs, dict):
                                _apply_options_to_schema_dict(cs)
                except Exception:
                    pass

            # 2. 更新插件目录下的 _conf_schema.json 文件
            schema_file = pathlib.Path(__file__).resolve().parent / "_conf_schema.json"
            if schema_file.exists():
                disk_schema = json.loads(schema_file.read_text(encoding="utf-8"))
                if _apply_options_to_schema_dict(disk_schema):
                    schema_file.write_text(
                        json.dumps(disk_schema, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
        except Exception as e:
            logger.debug(f"[TwitterRSS] 同步已订阅账号至下拉选项跳过: {e}")

    def _get_group_rules(self) -> list[dict[str, Any]]:
        raw = self._get_setting("group_subscriptions", [])
        if not isinstance(raw, list):
            return []
        return [
            r
            for r in raw
            if isinstance(r, dict)
            and str(r.get("__template_key", "group_rule")).startswith("group_rule")
        ]

    def _get_account_rule_cards(self) -> list[dict[str, Any]]:
        """获取在 group_subscriptions 中添加的所有【单账号独立推送开关 (account_rule)】卡片"""
        raw = self._get_setting("group_subscriptions", [])
        cards: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for r in raw:
                if isinstance(r, dict) and r.get("__template_key") == "account_rule":
                    cards.append(r)
                elif isinstance(r, dict) and isinstance(r.get("account_rules"), list):
                    for sub_r in r["account_rules"]:
                        if isinstance(sub_r, dict):
                            cards.append(sub_r)
        return cards

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

        if not create_if_missing:
            return None

        # 如果有一条未绑定 target_umo 的模板配置，自动将其绑定到当前会话
        for r in rules:
            if not str(r.get("target_umo", "") or "").strip():
                r["target_umo"] = umo
                if not r.get("group_name") or r.get("group_name") == "未命名群聊":
                    r["group_name"] = f"群聊 {gid}" if gid else f"会话 {umo.split(':')[-1]}"
                self._save_plugin_config()
                return r

        new_rule: dict[str, Any] = {
            "__template_key": "group_rule",
            "group_name": f"群聊 {gid}" if gid else f"会话 {umo.split(':')[-1]}",
            "target_umo": umo,
            "twitter_accounts": [],
            "twitter_hashtags": [],
            "account_switches": {},
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
        raw_list = cls._clean_str_list(rule.get("twitter_accounts", []))
        res: list[str] = []
        seen_lower: set[str] = set()
        for item in raw_list:
            clean_h = cls._extract_clean_handle(item)
            if clean_h and clean_h.lower() not in seen_lower:
                seen_lower.add(clean_h.lower())
                res.append(clean_h)
        return res

    @classmethod
    def _get_rule_hashtags(cls, rule: dict[str, Any]) -> list[str]:
        tags: dict[str, str] = {}
        for raw in cls._clean_str_list(rule.get("twitter_hashtags", [])):
            tag = raw.lstrip("#＃").strip()
            if tag and re.fullmatch(r"\w+", tag, flags=re.UNICODE):
                tags.setdefault(tag.casefold(), tag)
        return list(tags.values())

    @staticmethod
    def _tweet_identity(tweet_or_id: Any) -> str:
        if isinstance(tweet_or_id, dict):
            raw = str(tweet_or_id.get("id") or "")
            link = str(tweet_or_id.get("link") or "")
        else:
            raw, link = str(tweet_or_id), ""
        match = re.search(r"/status(?:es)?/(\d+)", raw) or re.search(r"/status(?:es)?/(\d+)", link)
        return match.group(1) if match else raw

    def _matches_rule_subscription(self, tweet: dict[str, Any], rule: dict[str, Any]) -> bool:
        accounts = {account.casefold() for account in self._get_rule_accounts(rule)}
        tags = {tag.casefold() for tag in self._get_rule_hashtags(rule)}
        matched_tags = {str(tag).casefold() for tag in tweet.get("subscription_hashtags", [])}
        if tweet.get("subscription_hashtag"):
            matched_tags.add(str(tweet["subscription_hashtag"]).casefold())
        return str(tweet.get("username", "")).casefold() in accounts or bool(tags & matched_tags)

    def _build_hashtag_search_url(self, tag: str, template: str | None = None) -> str:
        template = str((self._get_setting("hashtag_search_url", "") if template is None else template) or "").strip()
        if not template:
            template = DEFAULT_HASHTAG_SEARCH_URL
        if "{query}" not in template or urlsplit(template).scheme not in ("http", "https"):
            raise ValueError("hashtag_search_url 必须是包含 {query} 的 HTTP(S) URL")
        return template.replace("{query}", quote("#" + tag, safe=""))

    def _get_hashtag_search_urls(self, tag: str) -> list[str]:
        fallbacks = self._get_setting("hashtag_search_fallback_urls", DEFAULT_HASHTAG_FALLBACK_URLS)
        if not isinstance(fallbacks, list):
            logger.warning("[TwitterRSS] hashtag_search_fallback_urls 必须为列表，已跳过回退配置")
            fallbacks = []
        templates = [self._get_setting("hashtag_search_url") or DEFAULT_HASHTAG_SEARCH_URL, *fallbacks]
        urls = []
        for template in templates:
            if not isinstance(template, str) or not template.strip():
                continue
            try:
                url = self._build_hashtag_search_url(tag, template)
            except ValueError as exc:
                logger.warning(f"[TwitterRSS] 标签搜索源配置无效，已跳过: {exc}")
                continue
            if url not in urls:
                urls.append(url)
        return urls

    def _parse_hashtag_feed(self, body: str, tag: str) -> list[dict[str, Any]]:
        root = ET.fromstring(body)
        if root.tag != "rss" or root.find("channel") is None:
            raise ValueError("标签搜索接口必须返回 RSS 2.0，不能是 HTML 或 JSON")
        tweets = []
        for item in root.findall("./channel/item"):
            link = (item.findtext("link") or "").strip()
            match = re.search(r"/([A-Za-z0-9_]{1,15})/status/(\d+)", urlsplit(link).path)
            if not match:
                logger.warning(f"[TwitterRSS] 标签 #{tag} 搜索结果缺少作者与推文链接，已跳过一条")
                continue
            username, status_id = match.groups()
            item.find("link").text = f"https://x.com/{username}/status/{status_id}"
            # Nitter search feeds include 'RT by @retweeter:' titles while the
            # item link and creator identify the original author.
            title = item.find("title")
            if title is not None and title.text:
                title.text = re.sub(
                    r"^RT by @[A-Za-z0-9_]+:\s*", f"RT @{username}: ", title.text
                )
            for field in ("description", "{http://purl.org/rss/1.0/modules/content/}encoded"):
                content = item.find(field)
                if content is not None and content.text:
                    origin = urlsplit(link)
                    content.text = re.sub(
                        re.escape(f"{origin.scheme}://{origin.netloc}") + r"/([A-Za-z0-9_]{1,15})/status/(\d+)",
                        r"https://x.com/\1/status/\2", content.text,
                    )
            # Parse each item under its actual author; a search feed mixes authors.
            rss = ET.Element("rss", version="2.0")
            channel = ET.SubElement(rss, "channel")
            creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator") or item.findtext("author") or username
            ET.SubElement(channel, "title").text = creator
            channel.append(item)
            parsed = self._parse_rss_xml(ET.tostring(rss, encoding="unicode"), username)
            for tweet in parsed:
                tweet["id"] = status_id
                tweet["subscription_hashtag"] = tag
            tweets.extend(parsed)
        if root.findall("./channel/item") and not tweets:
            raise ValueError("搜索结果没有可识别的推文链接，无法确认作者")
        return sorted(tweets, key=lambda tweet: tweet["timestamp"])

    async def _fetch_hashtag_tweets(self, tag: str) -> list[dict[str, Any]]:
        urls = self._prioritize_feed_urls(self._get_hashtag_search_urls(tag))
        empty_feed_seen = False
        for index, url in enumerate(urls):
            try:
                resp = await self._fetch_feed_response(url)
                resp.raise_for_status()
                tweets = await asyncio.to_thread(self._parse_hashtag_feed, resp.text, tag)
                if not tweets:
                    empty_feed_seen = True
                    logger.info(f"[TwitterRSS] 标签 #{tag} 搜索源 {urlsplit(url).netloc} 返回空 RSS，尝试其他源")
                    continue
                logger.info(f"[TwitterRSS] 标签 #{tag} 搜索成功: {len(tweets)} 条推文，源 {urlsplit(url).netloc}（候选 {index + 1}/{len(urls)}）")
                return tweets
            except Exception as exc:
                if isinstance(exc, (ValueError, ET.ParseError)):
                    self._cool_down_feed(url)
                logger.warning(f"[TwitterRSS] 标签 #{tag} 搜索源 {urlsplit(url).netloc} 失败: {type(exc).__name__}: {str(exc).strip() or repr(exc)}")
        if not empty_feed_seen:
            logger.warning(f"[TwitterRSS] 标签 #{tag} 所有搜索源均失败（{len(urls)} 个候选）")
        return []

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

            interval_min = max(2, int(self._get_setting("poll_interval_minutes", 15) or 15))
            await asyncio.sleep(interval_min * 60)

    async def _digest_loop(self):
        await asyncio.sleep(15)
        while self._started:
            try:
                if self._get_setting("enable_daily_digest", True):
                    target_time = str(self._get_setting("daily_digest_time", "08:30") or "08:30").strip()
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
            self._get_setting("rss_base_url", "https://fxtwitter.com/{username}/feed.xml")
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

        if self._get_setting("enable_multi_source_fallback", True):
            for tmpl in FALLBACK_SOURCE_TEMPLATES:
                u = self._format_template_url(tmpl, username)
                if u not in candidates:
                    candidates.append(u)
        return candidates

    async def _check_user_not_found_on_twitter(
        self, account: str, explicit_404_hits: int
    ) -> bool:
        """
        向权威接口 (api.fxtwitter.com/{username}) 核验该推特 ID 是否确实不存在 (404 Not Found)。
        避免把单一公共 RSSHub 节点故障误判为账号不存在。
        """
        acct_clean = account.strip().lstrip("@")
        if not acct_clean:
            return True
        if not acct_clean.startswith(("http://", "https://")):
            if not re.match(r"^[A-Za-z0-9_]{1,15}$", acct_clean):
                return True
            username = acct_clean
        else:
            username = acct_clean.rstrip("/").split("/")[-1].lstrip("@")

        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        try:
            check_url = f"https://api.fxtwitter.com/{username}"
            resp = await self._fetch_feed_response(check_url)
            if resp.status_code == 404:
                return True
            if resp.status_code == 200:
                data = resp.json()
                code_val = data.get("code")
                msg_val = str(data.get("message") or "").lower()
                if code_val == 404 or "not found" in msg_val or "suspended" in msg_val:
                    return True
                if data.get("user"):
                    return False
        except Exception:
            pass

        return explicit_404_hits >= 2

    def _auto_remove_invalid_account(
        self, account: str, target_rule: dict[str, Any] | None = None
    ) -> list[str]:
        """当确认某个推特 ID 不存在时，自动将其从订阅列表中移除并保存配置"""
        acct_lower = account.strip().lstrip("@").lower()
        removed_group_names: list[str] = []

        rules_to_check = (
            [target_rule]
            if target_rule is not None
            else self._get_group_rules()
        )
        all_rules = self._get_group_rules()
        changed = False

        for r in all_rules:
            if target_rule is not None and r is not target_rule:
                continue
            accts = self._get_rule_accounts(r)
            new_accts = [a for a in accts if a.lower() != acct_lower]
            if len(new_accts) != len(accts):
                r["twitter_accounts"] = new_accts
                gname = str(r.get("group_name") or r.get("target_umo") or "未命名群聊")
                removed_group_names.append(gname)
                changed = True

        # 同步清理旧版全局顶层列表（若存在）
        legacy_accts = self._clean_str_list(self._get_setting("twitter_accounts", []))
        if any(a.lstrip("@").lower() == acct_lower for a in legacy_accts):
            self.config["twitter_accounts"] = [
                a for a in legacy_accts if a.lstrip("@").lower() != acct_lower
            ]
            changed = True

        if not self.state.get("migrated_skip_rt_v142"):
            self.config.setdefault("global_push_config", {})["skip_retweets"] = True
            for r in self._get_setting("group_subscriptions", []):
                if isinstance(r, dict) and "skip_retweets" not in r:
                    r["skip_retweets"] = True
            self.state["migrated_skip_rt_v142"] = True
            changed = True
            try:
                self.state_file.write_text(
                    json.dumps(self.state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

        if changed:
            self._save_plugin_config()
            logger.warning(
                f"[TwitterRSS] 检测到推特账号 @{account} 不存在 (404)，已自动从订阅列表 {removed_group_names} 中移除。"
            )
        return removed_group_names

    async def _fetch_account_tweets(self, account: str) -> list[dict[str, Any]]:
        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        acct_key = account.strip().lstrip("@").lower()
        self._not_found_accounts.discard(acct_key)

        acct_clean = account.strip().lstrip("@")
        if not acct_clean.startswith(("http://", "https://")) and not re.match(
            r"^[A-Za-z0-9_]{1,15}$", acct_clean
        ):
            self._not_found_accounts.add(acct_key)
            logger.warning(f"[TwitterRSS] 账号 ID 格式无效 ({account})，标记为不存在。")
            return []

        candidate_urls = self._prioritize_feed_urls(self._get_candidate_urls(account))
        errors: list[str] = []
        explicit_404_hits = 0

        for url in candidate_urls:
            try:
                resp = await self._fetch_feed_response(url)
                final_url = str(resp.url)
                if "google.com/404" in final_url or "x.com/i/flow/login" in final_url:
                    errors.append(f"{url} -> 重定向至无效页面 ({final_url})")
                    continue

                if resp.status_code == 404:
                    if any(
                        d in url
                        for d in ("fxtwitter.com", "fixupx.com", "api.fxtwitter.com")
                    ):
                        explicit_404_hits += 1
                    errors.append(f"{url} -> HTTP 404 Not Found")
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
                    try:
                        jdata = json.loads(body_text)
                        if isinstance(jdata, dict) and (
                            jdata.get("code") == 404
                            or "not found" in str(jdata.get("message") or "").lower()
                        ):
                            explicit_404_hits += 1
                            errors.append(f"{url} -> User not found (404)")
                            continue
                    except Exception:
                        pass
                    tweets = await asyncio.to_thread(
                        self._parse_fxtwitter_json, body_text, account
                    )
                else:
                    tweets = await asyncio.to_thread(
                        self._parse_rss_xml, body_text, account
                    )

                if tweets:
                    logger.info(
                        f"[TwitterRSS] 账号 @{acct_clean} 抓取成功: 从 {url} 解析到 {len(tweets)} 条推文"
                    )
                    return tweets
                errors.append(f"{url} -> 解析到 0 条推文")
                if "<html" in body_text.lower() or "<!doctype html" in body_text.lower():
                    self._cool_down_feed(url, 60)
            except httpx.TimeoutException as e:
                errors.append(f"{url} -> 请求超时 ({type(e).__name__})")
            except Exception as e:
                if isinstance(e, (ValueError, ET.ParseError)):
                    self._cool_down_feed(url)
                err_detail = str(e).strip() or repr(e)
                errors.append(f"{url} -> {type(e).__name__}: {err_detail}")

        if explicit_404_hits and await self._check_user_not_found_on_twitter(account, explicit_404_hits):
            self._not_found_accounts.add(acct_key)
            logger.warning(f"[TwitterRSS] 经核验推特账号 @{account} 不存在 (404 User Not Found)。")
            return []

        logger.warning(
            f"[TwitterRSS] 账号 {account} 所有订阅源均获取失败：\n"
            + "\n".join(f"  - {err}" for err in errors[:4])
        )
        return []


    async def _fetch_user_profile_cached(self, username: str) -> dict[str, str]:
        """
        从权威接口 https://api.fxtwitter.com/{username} 获取该画师本人的真实头像与昵称，
        彻底解决 RSS <channel><image> 因最新一条是转推而错误变成被转发对象头像的问题。
        """
        uname = username.strip().lstrip("@")
        if not uname or uname.startswith(("http://", "https://")):
            return {}
        key = uname.lower()
        if key in self._user_profile_cache:
            return self._user_profile_cache[key]

        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        try:
            resp = await self._http_get_with_recovery(
                f"https://api.fxtwitter.com/{uname}"
            )
            if resp.status_code == 200:
                data = resp.json()
                user_obj = data.get("user")
                if isinstance(user_obj, dict):
                    prof = {
                        "username": str(user_obj.get("screen_name") or uname).strip(),
                        "author_name": str(user_obj.get("name") or uname).strip(),
                        "avatar_url": str(
                            user_obj.get("avatar_url")
                            or user_obj.get("profile_image_url_https")
                            or ""
                        ).strip(),
                    }
                    if prof["avatar_url"]:
                        self._user_profile_cache[key] = prof
                        return prof
        except Exception as e:
            logger.debug(f"[TwitterRSS] 获取用户 @{uname} 个人资料跳过: {e}")

        return {}

    @staticmethod
    def _extract_media_from_fx_dict(media: Any) -> tuple[list[str], list[str], bool]:
        """
        从 FxTwitter 的 media 字典或列表中提取:
        - images: 图片与视频/GIF封面快照 (.jpg/.png) URL 列表（对 video/gif 优先取 thumbnail_url 快照！）
        - video_urls: 原始视频 (.mp4) URL 列表
        - has_video: 是否包含视频或动图视频流
        """
        images: list[str] = []
        video_urls: list[str] = []
        has_video = False

        def _add_img(u: Any):
            s = str(u or "").strip()
            if s and not s.lower().endswith((".mp4", ".m3u8", ".webm")) and "video.twimg.com" not in s.lower():
                if s not in images:
                    images.append(s)

        def _add_vid(u: Any):
            nonlocal has_video
            s = str(u or "").strip()
            if s:
                has_video = True
                if s not in video_urls:
                    video_urls.append(s)

        if isinstance(media, dict):
            for p in media.get("photos") or []:
                if isinstance(p, dict):
                    _add_img(p.get("url") or p.get("media_url_https"))
            for v in media.get("videos") or []:
                if isinstance(v, dict):
                    has_video = True
                    _add_img(
                        v.get("thumbnail_url")
                        or v.get("poster")
                        or v.get("preview_image_url")
                    )
                    _add_vid(v.get("url"))
            for m in media.get("all") or []:
                if not isinstance(m, dict):
                    continue
                mtype = str(m.get("type") or "").lower()
                if mtype in ("photo", "image"):
                    _add_img(m.get("url") or m.get("thumbnail_url"))
                elif mtype in ("video", "gif", "animated_gif"):
                    has_video = True
                    # 关键：对视频和动图必须优先取 thumbnail_url 快照图片，绝不能把 .mp4 url 当成图片！
                    _add_img(
                        m.get("thumbnail_url")
                        or m.get("poster")
                        or m.get("preview_image_url")
                    )
                    _add_vid(m.get("url"))
        elif isinstance(media, list):
            for m in media:
                if isinstance(m, dict):
                    mtype = str(m.get("type") or "").lower()
                    if mtype in ("video", "gif", "animated_gif") or str(m.get("url") or "").lower().endswith(".mp4"):
                        has_video = True
                        _add_img(
                            m.get("thumbnail_url")
                            or m.get("poster")
                            or m.get("preview_image_url")
                            or m.get("media_url_https")
                        )
                        _add_vid(m.get("url"))
                    else:
                        _add_img(m.get("url") or m.get("media_url_https") or m.get("thumbnail_url"))
                elif isinstance(m, str):
                    if m.lower().endswith((".mp4", ".m3u8")) or "video.twimg.com" in m.lower():
                        _add_vid(m)
                    else:
                        _add_img(m)

        return images, video_urls, has_video

    async def _fetch_single_status_cached(
        self, target_user: str, status_id: str
    ) -> dict[str, Any]:
        """
        根据转推或引用推文的 (username, status_id) 从 api.fxtwitter.com 获取原推真实作者、头像、正文与配图
        """
        skey = f"{target_user.lower()}::{status_id}"
        if skey in self._status_detail_cache:
            return self._status_detail_cache[skey]

        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        try:
            url = f"https://api.fxtwitter.com/{target_user}/status/{status_id}"
            resp = await self._http_get_with_recovery(url)
            if resp.status_code == 200:
                data = resp.json()
                tw = data.get("tweet") or data.get("status")
                if isinstance(tw, dict):
                    author = tw.get("author") or tw.get("user") or {}
                    q_uname = str(author.get("screen_name") or target_user).strip().lstrip("@")
                    q_name = str(author.get("name") or q_uname).strip()
                    q_avatar = str(
                        author.get("avatar_url")
                        or author.get("profile_image_url_https")
                        or ""
                    ).strip()
                    q_text = str(tw.get("text") or tw.get("full_text") or "").strip()
                    q_imgs, q_vids, q_has_vid = self._extract_media_from_fx_dict(tw.get("media"))
                    res = {
                        "username": q_uname,
                        "author_name": q_name,
                        "avatar_url": q_avatar,
                        "text": q_text,
                        "external_links": self._tweet_external_links(tw),
                        "images": q_imgs,
                        "video_urls": q_vids,
                        "has_video": q_has_vid,
                    }
                    self._status_detail_cache[skey] = res
                    return res
        except Exception as e:
            logger.debug(f"[TwitterRSS] 获取引用/原推详情 {target_user}/{status_id} 失败: {e}")

        return {}

    @classmethod
    def _analyze_retweet_and_quote(
        cls,
        raw_text: str,
        title: str,
        link: str,
        creator_handle: str,
        subscribed_username: str,
        explicit_is_rt: bool = False,
        explicit_quote: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        精准识别【纯转发 (is_retweet)】与【引用转发 (is_quote)】：
        1. 若正文去掉 https://x.com/xxx/status/yyy 链接后为空（如截图中仅有一条原推链接的转推），
           或 <link>/<dc:creator> 指向其他账号，或以 RT @ 开头 -> 判定为纯转发 (is_retweet=True)，并提取原推作者与 status_id。
        2. 若本人有配文 且 包含其他推文状态链接或 quote 对象 -> 判定为引用转发 (is_quote=True)，剔除正文中的裸链接。
        """
        sub_lower = subscribed_username.strip().lstrip("@").lower()
        text = (raw_text or "").strip()
        title_str = (title or "").strip()

        # 清理旧式「引用：https://x.com/...」包装，提取其中的状态链接
        url_matches = list(_STATUS_URL_RE.finditer(text))
        link_match = _STATUS_URL_RE.search(link or "")

        link_user = link_match.group(1) if link_match else ""
        link_sid = link_match.group(2) if link_match else ""

        creator_clean = re.sub(r"^@", "", (creator_handle or "").strip())
        # 提取括号内的 @handle（若有，如 "xxx (@handle)"）
        m_handle = re.search(r"\(@([A-Za-z0-9_]+)\)", creator_clean)
        if m_handle:
            creator_clean = m_handle.group(1)

        # 移除正文中的所有推文状态链接及空的引用括号
        text_no_urls = _STATUS_URL_RE.sub("", text)
        text_no_urls = re.sub(r"「引用[：:]\s*」", "", text_no_urls)
        # 移除 RT @xxx: 前缀以便检查是否有本人正文
        rt_prefix_match = re.match(
            r"^(?:RT|R\s+to|Retweet)\s+@?([A-Za-z0-9_]+)[：:\s]*",
            text_no_urls,
            flags=re.I,
        )
        title_rt_match = re.match(
            r"^(?:RT|R\s+to|Retweet)\s+@?([A-Za-z0-9_]+)",
            title_str,
            flags=re.I,
        )
        text_no_urls = text_no_urls.strip()

        is_retweet = bool(explicit_is_rt or rt_prefix_match or title_rt_match)
        rt_user = ""
        rt_sid = ""

        if rt_prefix_match:
            rt_user = rt_prefix_match.group(1)
        elif title_rt_match:
            rt_user = title_rt_match.group(1)

        # 检查 <link> 是否指向其他人的推文
        if link_user and sub_lower and link_user.lower() != sub_lower:
            is_retweet = True
            rt_user = link_user
            rt_sid = link_sid

        # 检查正文是否仅由一条推文链接构成（即 FxTwitter 把纯转推/无配文引用解析成了裸链接！）
        if not is_retweet and url_matches and not text_no_urls:
            first_u, first_sid = url_matches[0].group(1), url_matches[0].group(2)
            is_retweet = True
            rt_user = first_u
            rt_sid = first_sid

        if is_retweet:
            if not rt_user and url_matches:
                rt_user, rt_sid = url_matches[0].group(1), url_matches[0].group(2)
            elif not rt_sid and url_matches:
                rt_sid = url_matches[0].group(2)
            elif not rt_sid and link_sid:
                rt_sid = link_sid
            cleaned_main_text = re.sub(
                r"^(?:RT|R\s+to|Retweet)\s+@?[A-Za-z0-9_]+[：:\s]*",
                "",
                text_no_urls,
                flags=re.I,
            ).strip()
            return {
                "is_retweet": True,
                "is_quote": False,
                "clean_text": cleaned_main_text,
                "rt_username": rt_user,
                "rt_status_id": rt_sid,
                "quote_username": "",
                "quote_status_id": "",
                "quote_data": None,
            }

        # 检查是否为带配文的引用转发 (Quote Tweet)
        is_quote = False
        q_user = ""
        q_sid = ""
        q_data = explicit_quote if isinstance(explicit_quote, dict) else None

        if q_data:
            is_quote = True
            q_author = q_data.get("author") or q_data.get("user") or {}
            q_user = str(q_author.get("screen_name") or "").strip().lstrip("@")
            q_sid = str(q_data.get("id") or q_data.get("id_str") or "").strip()
        elif url_matches and text_no_urls:
            for um in url_matches:
                u_name, u_sid = um.group(1), um.group(2)
                if not link_sid or u_sid != link_sid:
                    is_quote = True
                    q_user = u_name
                    q_sid = u_sid
                    break

        return {
            "is_retweet": False,
            "is_quote": is_quote,
            "clean_text": text_no_urls if (is_quote or url_matches) else text,
            "rt_username": "",
            "rt_status_id": "",
            "quote_username": q_user,
            "quote_status_id": q_sid,
            "quote_data": q_data,
        }

    @staticmethod
    def _extract_external_links(text: str = "", raw_html: str = "") -> list[str]:
        anchors = re.findall(r'''\bhref\s*=\s*["'](https?://[^"']+)["']''', raw_html, flags=re.I)
        candidates = re.findall(r'''https?://[^\s<>"'，。！？；、【】「」『』]+''', html.unescape(str(text or "")), flags=re.I)
        excluded = {"x.com", "twitter.com", "t.co", "twimg.com", "fxtwitter.com", "fixupx.com", "vxtwitter.com", "fixvx.com", "twitfix.com", "xcancel.com"}
        links = []
        for raw in candidates + anchors:
            url = html.unescape(raw).rstrip(".,;:!?，。！？；：）】")
            while url.endswith(")") and url.count(")") > url.count("("):
                url = url[:-1]
            try:
                parts = urlsplit(url)
                host = (parts.hostname or "").lower().rstrip(".")
                if parts.scheme.lower() not in {"http", "https"} or not host:
                    continue
            except ValueError:
                continue
            if any(host == domain or host.endswith(f".{domain}") for domain in excluded) or host.startswith("nitter."):
                continue
            if url not in links:
                links.append(url)
        return links

    @classmethod
    def _tweet_external_links(cls, tweet: dict[str, Any]) -> list[str]:
        """Collect original content/expanded entity links, never model-generated translations or media URLs."""
        links = []
        def add(value):
            if isinstance(value, str):
                for url in cls._extract_external_links(value):
                    if url not in links:
                        links.append(url)
            elif isinstance(value, list):
                for item in value:
                    add(item)
            elif isinstance(value, dict):
                expanded = value.get("unwound_url") or value.get("expanded_url") or value.get("url")
                if expanded:
                    add(expanded)
                for key in ("text", "urls", "facets", "features", "replacement", "uri"):
                    if key in value:
                        add(value[key])
        for field in ("external_links", "text", "full_text", "orig_body", "raw_text", "entities"):
            add(tweet.get(field))
        for field in ("quote_data", "quote_info", "quote", "retweeted_status"):
            nested = tweet.get(field)
            if isinstance(nested, dict):
                add(cls._tweet_external_links(nested))
        return links

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
        username_fallback = (
            account.rstrip("/").split("/")[-1].lstrip("@")
            if account.startswith(("http://", "https://"))
            else account.strip().lstrip("@")
        )

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            st = item.get("status") if isinstance(item.get("status"), dict) else item
            st = st.get("tweet") if isinstance(st.get("tweet"), dict) else st

            rt_obj = st.get("retweeted_status") or item.get("retweeted_status")
            explicit_is_rt = isinstance(rt_obj, dict)

            tid = str(st.get("id") or st.get("id_str") or st.get("url") or "").strip()
            raw_text = str(
                st.get("text")
                or st.get("full_text")
                or (st.get("raw_text", {}) if isinstance(st.get("raw_text"), dict) else {}).get("text")
                or ""
            ).strip()

            author = st.get("author") or st.get("user") or {}
            if not isinstance(author, dict):
                author = {}
            item_username = str(
                author.get("screen_name")
                or author.get("handle")
                or username_fallback
            ).strip().lstrip("@")
            item_author_name = str(author.get("name") or item_username).strip()
            item_avatar_url = str(
                author.get("avatar_url")
                or author.get("profile_image_url_https")
                or ""
            ).strip()

            link = str(
                st.get("url")
                or (f"https://x.com/{item_username}/status/{tid}" if tid else "")
            ).strip()

            images, video_urls, has_video = self._extract_media_from_fx_dict(st.get("media"))
            for u in st.get("mediaURLs") or []:
                if isinstance(u, str):
                    u_clean = u.strip()
                    if u_clean.lower().endswith((".mp4", ".m3u8")) or "video.twimg.com" in u_clean.lower():
                        has_video = True
                        if u_clean not in video_urls:
                            video_urls.append(u_clean)
                    elif u_clean not in images:
                        images.append(u_clean)

            quote_obj = st.get("quote") if isinstance(st.get("quote"), dict) else None
            rt_analysis = self._analyze_retweet_and_quote(
                raw_text=raw_text,
                title=raw_text[:60],
                link=link,
                creator_handle=item_username,
                subscribed_username=username_fallback,
                explicit_is_rt=explicit_is_rt,
                explicit_quote=quote_obj,
            )

            created_ts = st.get("created_timestamp")
            if isinstance(created_ts, (int, float)) and created_ts > 0:
                ts = float(created_ts)
                dt = datetime.datetime.fromtimestamp(ts)
                pub_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                ts, pub_str = self._parse_pub_date(str(st.get("created_at") or ""))

            if not tid:
                tid = link or hashlib.md5(f"{username_fallback}:{raw_text[:80]}".encode()).hexdigest()

            # 只有当 item_username 确实是订阅账号本人时，才采用其 avatar_url，防止转推污染本人头像
            is_self_author = item_username.lower() == username_fallback.lower()
            safe_avatar = item_avatar_url if is_self_author else ""
            safe_author_name = item_author_name if is_self_author else username_fallback

            tweets.append(
                {
                    "id": tid,
                    "username": username_fallback,
                    "author_name": safe_author_name,
                    "avatar_url": safe_avatar,
                    "title": rt_analysis["clean_text"][:60],
                    "text": rt_analysis["clean_text"],
                    "external_links": self._tweet_external_links(st),
                    "images": images,
                    "video_urls": video_urls,
                    "has_video": has_video,
                    "link": link,
                    "timestamp": ts,
                    "pub_date": pub_str,
                    "is_retweet": rt_analysis["is_retweet"],
                    "is_quote": rt_analysis["is_quote"],
                    "rt_username": rt_analysis["rt_username"],
                    "rt_status_id": rt_analysis["rt_status_id"],
                    "quote_username": rt_analysis["quote_username"],
                    "quote_status_id": rt_analysis["quote_status_id"],
                    "quote_data": rt_analysis["quote_data"],
                }
            )

        tweets.sort(key=lambda x: x["timestamp"])
        return tweets

    def _parse_rss_xml(self, xml_text: str, account: str) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text.strip())
        except ET.ParseError:
            return []

        username_fallback = (
            account.rstrip("/").split("/")[-1].lstrip("@")
            if account.startswith(("http://", "https://"))
            else account.strip().lstrip("@")
        )
        channel_title = username_fallback
        channel = root.find("channel")
        if channel is not None:
            ct = channel.findtext("title")
            if ct:
                cleaned_ct = re.sub(r"^(?:Twitter|X)\s*@?\s*", "", ct, flags=re.I).strip()
                channel_title = re.sub(r"\s*\(@[A-Za-z0-9_]+\)\s*$", "", cleaned_ct).strip() or username_fallback

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
                creator_raw = self._find_atom_text(el, "author/name") or ""
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
                creator_raw = (
                    el.findtext("{http://purl.org/dc/elements/1.1/}creator")
                    or el.findtext("author")
                    or ""
                ).strip()

            # 提取 HTML 中可能内嵌的其它推文链接（例如 <a href="https://x.com/ienu0ienu/status/...">）
            embedded_status_urls: list[str] = []
            for m_href in re.finditer(r"""href=["'](https?://[^"']+/status/\d+[^"']*)["']""", raw_html, flags=re.I):
                u_href = html.unescape(m_href.group(1)).strip()
                if u_href not in embedded_status_urls:
                    embedded_status_urls.append(u_href)

            images, video_urls, has_video = self._extract_images_and_videos(el, raw_html)
            clean_text = self._clean_html_to_text(raw_html)
            if not clean_text and title:
                clean_text = self._clean_html_to_text(title)

            for eu in embedded_status_urls:
                if eu not in clean_text and eu != link:
                    clean_text = f"{clean_text}\n{eu}".strip()

            rt_analysis = self._analyze_retweet_and_quote(
                raw_text=clean_text,
                title=title,
                link=link,
                creator_handle=creator_raw,
                subscribed_username=username_fallback,
            )

            ts, pub_str = self._parse_pub_date(pub_raw)
            username = username_fallback
            tweet_id = guid or link or hashlib.md5(f"{username}:{clean_text[:80]}".encode()).hexdigest()

            # 注意：绝不使用 FxTwitter RSS 的 <channel><image><url>，因为当第一条是转推时它会变成被转发人的头像！
            # 订阅者本人的真实头像与名称统一在 _prepare_tweet_media 中通过 _fetch_user_profile_cached(username) 获取。
            tweets.append(
                {
                    "id": tweet_id,
                    "username": username,
                    "author_name": channel_title or username,
                    "avatar_url": "",
                    "title": title,
                    "text": rt_analysis["clean_text"],
                    "external_links": self._extract_external_links(clean_text, raw_html),
                    "images": images,
                    "video_urls": video_urls,
                    "has_video": has_video,
                    "link": link,
                    "timestamp": ts,
                    "pub_date": pub_str,
                    "is_retweet": rt_analysis["is_retweet"],
                    "is_quote": rt_analysis["is_quote"],
                    "rt_username": rt_analysis["rt_username"],
                    "rt_status_id": rt_analysis["rt_status_id"],
                    "quote_username": rt_analysis["quote_username"],
                    "quote_status_id": rt_analysis["quote_status_id"],
                    "quote_data": rt_analysis["quote_data"],
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

    @classmethod
    def _extract_images_and_videos(
        cls, item_el: ET.Element, raw_html: str
    ) -> tuple[list[str], list[str], bool]:
        """
        从 RSS XML 条目中同时提取:
        - image_urls: 静态图片及 <video poster="..."> 视频封面快照 URL
        - video_urls: .mp4 视频流 URL
        - has_video: 是否包含视频
        """
        img_urls: list[str] = []
        vid_urls: list[str] = []
        has_video = False

        # 1. 提取 <img src="...">
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, flags=re.I):
            u = html.unescape(match.group(1)).strip()
            if u and not u.startswith("data:") and "emoji" not in u.lower():
                if u.lower().endswith((".mp4", ".m3u8")) or "video.twimg.com" in u.lower():
                    has_video = True
                    vid_urls.append(u)
                else:
                    img_urls.append(u)

        # 2. 提取 <video poster="..."> 视频封面快照与 <video src="..."> / <source src="...">
        for match in re.finditer(r'<video[^>]+poster=["\']([^"\']+)["\']', raw_html, flags=re.I):
            has_video = True
            poster_u = html.unescape(match.group(1)).strip()
            if poster_u and not poster_u.startswith("data:"):
                img_urls.append(poster_u)

        for match in re.finditer(r'<(?:video|source)[^>]+src=["\']([^"\']+)["\']', raw_html, flags=re.I):
            has_video = True
            v_u = html.unescape(match.group(1)).strip()
            if v_u:
                vid_urls.append(v_u)

        # 3. 扫描 raw_html 中可能内嵌的推特视频缩略图域名 (ext_tw_video_thumb / tweet_video_thumb / amplify_video_thumb)
        for match in re.finditer(
            r'https?://pbs\.twimg\.com/(?:ext_tw_video_thumb|tweet_video_thumb|amplify_video_thumb)/[^\s"\'<>]+',
            raw_html,
            flags=re.I,
        ):
            has_video = True
            thumb_u = html.unescape(match.group(0)).strip()
            if thumb_u:
                img_urls.append(thumb_u)

        # 4. 检查 XML 节点 (<enclosure>, <media:content>, <media:thumbnail>)
        for child in item_el.iter():
            tag_lower = child.tag.lower()
            if tag_lower.endswith(("enclosure", "content", "thumbnail")):
                u = html.unescape(child.attrib.get("url", "").strip())
                mtype = child.attrib.get("type", "").lower()
                medium = child.attrib.get("medium", "").lower()
                if not u:
                    continue
                if (
                    "video" in mtype
                    or medium == "video"
                    or u.lower().endswith((".mp4", ".m3u8", ".webm"))
                    or "video.twimg.com" in u.lower()
                ):
                    has_video = True
                    vid_urls.append(u)
                elif (
                    "image" in mtype
                    or medium == "image"
                    or tag_lower.endswith("thumbnail")
                    or any(
                        ext in u.lower()
                        for ext in (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".webp",
                            "format=jpg",
                            "format=png",
                            "pbs.twimg.com/",
                        )
                    )
                ):
                    img_urls.append(u)

        dedup_imgs = list(dict.fromkeys(img_urls))
        dedup_vids = list(dict.fromkeys(vid_urls))
        return dedup_imgs, dedup_vids, has_video

    @classmethod
    def _extract_images(cls, item_el: ET.Element, raw_html: str) -> list[str]:
        imgs, _, _ = cls._extract_images_and_videos(item_el, raw_html)
        return imgs

    @staticmethod
    def _clean_html_to_text(raw_html: str) -> str:
        if not raw_html:
            return ""
        text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
        text = re.sub(r"</?blockquote[^>]*>", "\n", text, flags=re.I)
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

    @staticmethod
    def _normalize_image_bytes_sync(raw_bytes: bytes, out_stem: pathlib.Path) -> tuple[pathlib.Path, str] | None:
        """
        使用 Pillow 校验并将任何 WebP / 16-bit / CMYK / 非标图片统一转换为 QQ 官方接口 (qq_official) 100% 支持的标准 8-bit RGB JPEG 或 PNG，
        彻底解决 QQOfficial upload_group_and_c2c_image 报错「ServerError: 富媒体文件格式不支持」的问题。
        """
        if not raw_bytes or len(raw_bytes) < 64:
            return None
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw_bytes)) as im:
                fmt = (im.format or "").upper()
                # 若是动图 GIF 且帧数 > 1，保留标准 GIF
                if fmt == "GIF" and getattr(im, "is_animated", False):
                    out_path = out_stem.with_suffix(".gif")
                    out_path.write_bytes(raw_bytes)
                    b64 = base64.b64encode(raw_bytes).decode("ascii")
                    return out_path, f"data:image/gif;base64,{b64}"

                # 限制最大边长不超过 2560，防止超大原图超出 QQ 官方富媒体大小限制
                max_side = 2560
                w, h = im.size
                if w > max_side or h > max_side:
                    scale = max_side / float(max(w, h))
                    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

                # 统一转换为标准 8-bit RGB JPEG（若含透明通道则转为白底 RGB JPEG 或标准 RGBA PNG）
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    rgb_im = bg
                else:
                    rgb_im = im.convert("RGB")

                buf = io.BytesIO()
                rgb_im.save(buf, format="JPEG", quality=92, optimize=True)
                jpg_bytes = buf.getvalue()
                out_path = out_stem.with_suffix(".jpg")
                out_path.write_bytes(jpg_bytes)
                b64 = base64.b64encode(jpg_bytes).decode("ascii")
                return out_path, f"data:image/jpeg;base64,{b64}"
        except Exception:
            return None

    @staticmethod
    def _extract_frame_from_mp4_bytes_sync(
        mp4_bytes: bytes, out_stem: pathlib.Path
    ) -> tuple[pathlib.Path, str] | None:
        """
        当仅有 .mp4 视频流而无现成封面 URL 时，使用本地 ffmpeg 或 OpenCV (cv2) 从视频流前部提取高清快照帧，
        并统一转换为标准 8-bit RGB JPEG。
        """
        if not mp4_bytes or len(mp4_bytes) < 512:
            return None
        tmp_mp4 = out_stem.with_suffix(".tmp.mp4")
        tmp_jpg = out_stem.with_suffix(".frame.jpg")
        try:
            tmp_mp4.write_bytes(mp4_bytes)
            frame_bytes: bytes | None = None

            # 方式 A: 若系统安装了 ffmpeg，优先用 ffmpeg 截取第 0.5 秒或首帧
            ffmpeg_bin = shutil.which("ffmpeg")
            if ffmpeg_bin:
                import subprocess
                for seek_t in ("00:00:00.500", "00:00:00.000"):
                    subprocess.run(
                        [
                            ffmpeg_bin,
                            "-y",
                            "-ss",
                            seek_t,
                            "-i",
                            str(tmp_mp4),
                            "-frames:v",
                            "1",
                            "-q:v",
                            "2",
                            str(tmp_jpg),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=8,
                    )
                    if tmp_jpg.exists() and tmp_jpg.stat().st_size > 128:
                        frame_bytes = tmp_jpg.read_bytes()
                        break

            # 方式 B: 若环境装有 opencv-python (cv2)，使用 VideoCapture 抽帧
            if not frame_bytes:
                try:
                    import cv2  # type: ignore
                    cap = cv2.VideoCapture(str(tmp_mp4))
                    ok, frame = cap.read()
                    cap.release()
                    if ok and frame is not None:
                        ok_enc, buf = cv2.imencode(".jpg", frame)
                        if ok_enc:
                            frame_bytes = bytes(buf)
                except Exception:
                    pass

            if frame_bytes:
                return TwitterRssPlugin._normalize_image_bytes_sync(frame_bytes, out_stem)
        except Exception:
            pass
        finally:
            tmp_mp4.unlink(missing_ok=True)
            tmp_jpg.unlink(missing_ok=True)
        return None

    async def _download_video_snapshot_cached(
        self, video_url: str
    ) -> tuple[str | None, str | None]:
        """从 .mp4 视频 URL 抓取前 3MB 数据并提取视频帧快照图片"""
        if not video_url:
            return None, None
        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        url_hash = hashlib.md5(f"vid_snap::{video_url}".encode("utf-8")).hexdigest()
        out_stem = self.image_cache_dir / url_hash
        existing = [
            p
            for p in self.image_cache_dir.glob(f"{url_hash}.*")
            if p.suffix.lower() in (".jpg", ".jpeg", ".png")
        ]
        if existing:
            local_path = existing[0]
            data_uri = await asyncio.to_thread(self._file_to_data_uri, local_path)
            return str(local_path), data_uri

        try:
            # 仅请求前 3MB 字节即可包含 MP4 moov + 首帧关键帧，避免下载整个大视频
            resp = await self.http_client.get(
                video_url, headers={"Range": "bytes=0-3145728"}
            )
            if resp.status_code not in (200, 206):
                return None, None
            norm_res = await asyncio.to_thread(
                self._extract_frame_from_mp4_bytes_sync, resp.content, out_stem
            )
            if norm_res:
                return str(norm_res[0]), norm_res[1]
        except Exception as e:
            logger.debug(f"[TwitterRSS] 视频流抽帧回退跳过 ({video_url}): {e}")
        return None, None

    async def _download_image_cached(self, url: str) -> tuple[str | None, str | None]:
        if not url:
            return None, None
        if not self.http_client or self.http_client.is_closed:
            await self._init_http_client()

        # 将 pbs.twimg.com 链接中的 format=webp 自动替换为 format=jpg
        fetch_url = re.sub(r"([?&]format=)webp\b", r"\1jpg", url, flags=re.I)
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        out_stem = self.image_cache_dir / url_hash

        existing = [
            p for p in self.image_cache_dir.glob(f"{url_hash}.*")
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif")
        ]
        if existing:
            local_path = existing[0]
            data_uri = await asyncio.to_thread(self._file_to_data_uri, local_path)
            return str(local_path), data_uri

        # 若旧缓存中存在 .webp 文件，自动转换升级为 .jpg 并删除旧 .webp
        old_webp = self.image_cache_dir / f"{url_hash}.webp"
        if old_webp.exists():
            try:
                raw_b = await asyncio.to_thread(old_webp.read_bytes)
                norm_res = await asyncio.to_thread(self._normalize_image_bytes_sync, raw_b, out_stem)
                old_webp.unlink(missing_ok=True)
                if norm_res:
                    return str(norm_res[0]), norm_res[1]
            except Exception:
                pass

        try:
            resp = await self._http_get_with_recovery(fetch_url)
            resp.raise_for_status()
            content_bytes = resp.content
            norm_res = await asyncio.to_thread(
                self._normalize_image_bytes_sync, content_bytes, out_stem
            )
            if not norm_res:
                logger.warning(f"[TwitterRSS] 忽略不支持或损坏的媒体文件 ({url})")
                return None, None
            return str(norm_res[0]), norm_res[1]
        except Exception as e:
            logger.warning(f"[TwitterRSS] 下载推文图片失败 ({url}): {type(e).__name__}: {e}")
            return None, None

    @staticmethod
    def _file_to_data_uri(path: pathlib.Path) -> str:
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "image/jpeg"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    @staticmethod
    def _parse_switch_mode(val: Any) -> str | None:
        """
        解析四态开关配置：
        - '直接推送' / 'direct' -> 'direct' (不经AI判断内容直接推送)
        - '推送' / True -> 'push' (允许推送，经过群AI筛选)
        - '不推送' / False -> 'skip' (直接跳过不推送)
        - '默认' / None / '' -> None (跟随全局默认设置)
        """
        if val is None:
            return None
        if isinstance(val, bool):
            return "push" if val else "skip"
        s = str(val).strip().lower()
        if not s or s in ("默认", "默认(跟随全局)", "跟随全局", "default", "inherit", "auto", "reset"):
            return None
        if s in ("直接推送", "直推", "免审", "免ai", "直接", "direct", "force", "bypass"):
            return "direct"
        if s in ("推送", "开启", "开", "是", "允许", "true", "on", "yes", "1", "push"):
            return "push"
        if s in ("不推送", "跳过", "关闭", "关", "否", "禁止", "false", "off", "no", "0", "skip"):
            return "skip"
        return None

    @classmethod
    def _parse_tri_state(cls, val: Any) -> bool | None:
        mode = cls._parse_switch_mode(val)
        if mode is None:
            return None
        return mode in ("push", "direct")

    def _get_global_type_defaults(self, group_rule: dict[str, Any] | None = None) -> dict[str, bool]:
        """
        获取全局默认的 4 类推文推送开关：
        - retweet (转贴): 默认由 default_push_retweet 或 (not skip_retweets) 决定
        - reply (回复): 默认由 default_push_reply 或 (not skip_replies) 决定
        - text (纯文字): 默认由 default_push_text 决定（默认 True）
        - image (图片): 默认由 default_push_image 决定（默认 True）
        """
        if self._get_setting("default_push_retweet") is not None:
            def_rt = bool(self._get_setting("default_push_retweet", False))
        else:
            skip_rt = bool(
                group_rule.get("skip_retweets", self._get_setting("skip_retweets", True))
                if isinstance(group_rule, dict) and "skip_retweets" in group_rule
                else self._get_setting("skip_retweets", True)
            )
            def_rt = not skip_rt

        if self._get_setting("default_push_reply") is not None:
            def_rep = bool(self._get_setting("default_push_reply", False))
        else:
            def_rep = not bool(self._get_setting("skip_replies", True))

        def_text = bool(self._get_setting("default_push_text", True))
        def_image = bool(self._get_setting("default_push_image", True))

        return {
            "retweet": def_rt,
            "reply": def_rep,
            "text": def_text,
            "image": def_image,
        }

    def _get_account_type_policy(
        self, account: str, group_rule: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        获取指定订阅账号在当前群聊下的 4 类推文（转贴/回复/纯文字/图片）推送策略：
        - policy[k]: bool (是否允许进入推送流程)
        - policy['modes'][k]: 'push' | 'direct' | 'skip' ('direct' 表示不经过 AI 判断内容直接推送)
        - policy['sources'][k]: '单独设置' | '全局默认'
        """
        defaults = self._get_global_type_defaults(group_rule)
        modes: dict[str, str] = {
            k: ("push" if defaults[k] else "skip")
            for k in ("retweet", "reply", "text", "image")
        }
        sources: dict[str, str] = {
            "retweet": "全局默认",
            "reply": "全局默认",
            "text": "全局默认",
            "image": "全局默认",
        }

        acct_clean = self._extract_clean_handle(account)
        acct_lower = acct_clean.lower()
        if acct_lower and isinstance(group_rule, dict):
            key_map = {
                "retweet": "push_retweet",
                "reply": "push_reply",
                "text": "push_text",
                "image": "push_image",
            }
            # 1. 先读取本群持久化的多账号独立开关字典 account_type_overrides
            overrides_map = group_rule.get("account_type_overrides")
            if isinstance(overrides_map, dict):
                acct_ov = overrides_map.get(acct_lower)
                if isinstance(acct_ov, dict):
                    for k_short in ("retweet", "reply", "text", "image"):
                        pm = self._parse_switch_mode(acct_ov.get(k_short))
                        if pm is not None:
                            modes[k_short] = pm
                            sources[k_short] = "单独设置"

            # 2. 读取本群配置卡片内的子类 account_switches (支持每个账号独立子面板 sw[acct] 及旧式顶层字段)
            sw = self._account_switch_panels(group_rule.get("account_switches"))
            if isinstance(sw, dict):
                sw_acct = self._extract_clean_handle(sw.get("account")).lower()
                if sw_acct == acct_lower:
                    for k_short, k_cfg in key_map.items():
                        pm = self._parse_switch_mode(sw.get(k_cfg))
                        if pm is not None:
                            modes[k_short] = pm
                            sources[k_short] = "单独设置"
                for sub_k, sub_v in sw.items():
                    if isinstance(sub_v, dict) and self._extract_clean_handle(sub_k).lower() == acct_lower:
                        for k_short, k_cfg in key_map.items():
                            pm = self._parse_switch_mode(sub_v.get(k_cfg))
                            if pm is not None:
                                modes[k_short] = pm
                                sources[k_short] = "单独设置"

        return {
            "retweet": modes["retweet"] != "skip",
            "reply": modes["reply"] != "skip",
            "text": modes["text"] != "skip",
            "image": modes["image"] != "skip",
            "modes": modes,
            "sources": sources,
        }

    def _is_direct_push_tweet(
        self, tweet: dict[str, Any], group_rule: dict[str, Any] | None = None
    ) -> bool:
        """判断该推文是否命中了当前账号的【直接推送（不经 AI 判断内容直接推送）】选项"""
        acct = str(
            (f"#{tweet['subscription_hashtag']}" if tweet.get("subscription_hashtag") else "")
            or tweet.get("retweeter_username")
            or tweet.get("username")
            or ""
        ).strip()
        policy = self._get_account_type_policy(acct, group_rule)
        modes = policy.get("modes", {})

        text = str(tweet.get("text") or "").strip()
        is_rt = bool(
            tweet.get("is_retweet")
            or re.match(r"^(?:RT|R\s+to|Retweet)\s+@", text, flags=re.I)
        )
        is_rep = bool(
            tweet.get("is_reply")
            or re.match(r"^(?:Re\s+@|@)", text, flags=re.I)
        )
        has_images = (
            bool(tweet.get("images"))
            or bool(tweet.get("local_images"))
            or bool(tweet.get("has_video"))
            or bool(tweet.get("video_urls"))
        )
        if not has_images and isinstance(tweet.get("quote_info"), dict):
            has_images = bool(tweet["quote_info"].get("display_images"))

        if is_rt and modes.get("retweet") == "direct":
            return True
        if is_rep and modes.get("reply") == "direct":
            return True
        if has_images and modes.get("image") == "direct":
            return True
        if not has_images and modes.get("text") == "direct":
            return True
        return False

    def _should_skip_tweet(
        self,
        tweet: dict[str, Any],
        group_rule: dict[str, Any] | None = None,
        media_prepared: bool = False,
    ) -> bool:
        """
        根据订阅账号的独立四类推文开关（未单独配置则跟随全局默认）判断是否跳过该推文：
        支持控制：转贴 (retweet)、回复 (reply)、纯文字 (text)、图片 (image)
        """
        acct = str(
            (f"#{tweet['subscription_hashtag']}" if tweet.get("subscription_hashtag") else "")
            or tweet.get("retweeter_username")
            or tweet.get("username")
            or ""
        ).strip().lstrip("@")
        policy = self._get_account_type_policy(acct, group_rule)

        text = str(tweet.get("text") or "").strip()
        is_rt = bool(
            tweet.get("is_retweet")
            or re.match(r"^(?:RT|R\s+to|Retweet)\s+@", text, flags=re.I)
        )
        is_rep = bool(
            tweet.get("is_reply")
            or re.match(r"^(?:Re\s+@|@)", text, flags=re.I)
        )

        # 1. 转贴 (Retweet) 开关判断
        if is_rt and not policy["retweet"]:
            return True

        # 2. 回复 (Reply) 开关判断
        if is_rep and not policy["reply"]:
            return True

        # 3. 图片 (Image) 与 纯文字 (Text) 开关判断
        has_images = (
            bool(tweet.get("images"))
            or bool(tweet.get("local_images"))
            or bool(tweet.get("has_video"))
            or bool(tweet.get("video_urls"))
        )
        if not has_images and isinstance(tweet.get("quote_info"), dict):
            has_images = bool(tweet["quote_info"].get("display_images"))
        if not has_images and isinstance(tweet.get("quote_data"), dict):
            qd_media = tweet["quote_data"].get("media")
            if isinstance(qd_media, dict) and (qd_media.get("photos") or qd_media.get("all")):
                has_images = True

        # 若是尚未拉取原推详情的转贴（且该账号允许推送转贴），留到 _prepare_tweet_media 展开原推后再判断是否有图
        if is_rt and not media_prepared and not has_images and tweet.get("rt_status_id"):
            return False

        if has_images:
            if not policy["image"]:
                return True
        else:
            if not policy["text"]:
                return True

        return False

    async def _prepare_tweet_media(self, tweet: dict[str, Any]) -> dict[str, Any]:
        """
        预下载推文真实头像、配图并拆分正文与标签，同时处理：
        1. 通过 _fetch_user_profile_cached 获取订阅画师本人的真实头像与昵称（绝不混用转推对象头像）
        2. 若为未跳过的转推 (is_retweet)，拉取被转推原帖信息并组装转推横幅数据
        3. 若为引用转发 (is_quote)，拉取被引用原帖信息并组装嵌套引用卡片 (quote_info)
        """
        if "_media_prepared" in tweet:
            return tweet

        prepared = dict(tweet)
        sub_username = str(prepared.get("username") or "").strip().lstrip("@")

        # 1. 权威获取订阅画师本人的真实头像与昵称
        sub_prof = await self._fetch_user_profile_cached(sub_username)
        if sub_prof.get("author_name"):
            prepared["author_name"] = sub_prof["author_name"]
        if sub_prof.get("avatar_url"):
            prepared["avatar_url"] = sub_prof["avatar_url"]

        sub_avatar_src = ""
        if prepared.get("avatar_url"):
            _, sub_b64 = await self._download_image_cached(prepared["avatar_url"])
            sub_avatar_src = sub_b64 or prepared["avatar_url"]

        # 2. 若是转推 (is_retweet=True，且用户关闭了 skip_retweets 选择渲染转推)
        if prepared.get("is_retweet"):
            prepared["retweeter_username"] = sub_username
            prepared["retweeter_name"] = prepared.get("author_name") or sub_username
            prepared["retweeter_avatar_src"] = sub_avatar_src

            rt_user = str(prepared.get("rt_username") or "").strip().lstrip("@")
            rt_sid = str(prepared.get("rt_status_id") or "").strip()
            if rt_user and rt_sid:
                rt_detail = await self._fetch_single_status_cached(rt_user, rt_sid)
                if rt_detail:
                    prepared["external_links"] = list(dict.fromkeys(
                        prepared.get("external_links", []) + self._tweet_external_links(rt_detail)
                    ))
                    prepared["username"] = rt_detail["username"]
                    prepared["author_name"] = rt_detail["author_name"]
                    prepared["avatar_url"] = rt_detail["avatar_url"]
                    if rt_detail.get("text"):
                        prepared["text"] = rt_detail["text"]
                    if rt_detail.get("images"):
                        prepared["images"] = rt_detail["images"]
            elif rt_user:
                rt_prof = await self._fetch_user_profile_cached(rt_user)
                prepared["username"] = rt_user
                prepared["author_name"] = rt_prof.get("author_name") or rt_user
                prepared["avatar_url"] = rt_prof.get("avatar_url") or ""

        # 3. 下载当前主展示作者的头像
        avatar_data_uri = sub_avatar_src
        if prepared.get("username", "").lower() != sub_username.lower():
            avatar_data_uri = ""
            if prepared.get("avatar_url"):
                _, b64_rt = await self._download_image_cached(prepared["avatar_url"])
                avatar_data_uri = b64_rt or prepared["avatar_url"]

        # 4. 若是引用推文 (is_quote=True)，组装嵌套引用框 quote_info
        quote_info: dict[str, Any] | None = None
        if prepared.get("is_quote"):
            q_user = str(prepared.get("quote_username") or "").strip().lstrip("@")
            q_sid = str(prepared.get("quote_status_id") or "").strip()
            q_detail: dict[str, Any] = {}
            if q_user and q_sid:
                q_detail = await self._fetch_single_status_cached(q_user, q_sid)
            if not q_detail and isinstance(prepared.get("quote_data"), dict):
                qd = prepared["quote_data"]
                qa = qd.get("author") or qd.get("user") or {}
                q_imgs: list[str] = []
                if qd.get("media"):
                    q_imgs, _, _ = self._extract_media_from_fx_dict(qd.get("media"))
                q_detail = {
                    "username": str(qa.get("screen_name") or q_user or "x").strip(),
                    "author_name": str(qa.get("name") or qa.get("screen_name") or q_user or "X").strip(),
                    "avatar_url": str(qa.get("avatar_url") or qa.get("profile_image_url_https") or "").strip(),
                    "text": str(qd.get("text") or qd.get("full_text") or "").strip(),
                    "images": q_imgs,
                    "external_links": self._tweet_external_links(qd),
                }
            if q_detail:
                q_body, q_tags = self._split_tweet_body_and_tags(q_detail.get("text", ""))
                q_avatar_src = ""
                if q_detail.get("avatar_url"):
                    _, qb64 = await self._download_image_cached(q_detail["avatar_url"])
                    q_avatar_src = qb64 or q_detail["avatar_url"]
                q_disp_imgs: list[str] = []
                for q_img_url in q_detail.get("images", []):
                    _, q_img_b64 = await self._download_image_cached(q_img_url)
                    q_disp_imgs.append(q_img_b64 or q_img_url)
                q_aname = q_detail.get("author_name") or q_detail.get("username") or "X"
                quote_info = {
                    "username": q_detail.get("username", ""),
                    "author_name": q_aname,
                    "author_initial": q_aname[:1].upper(),
                    "avatar_src": q_avatar_src,
                    "orig_body": q_body,
                    "external_links": self._tweet_external_links(q_detail),
                    "orig_tags": q_tags,
                    "display_images": q_disp_imgs,
                }

        orig_body, orig_tags = self._split_tweet_body_and_tags(prepared.get("text", ""))

        # 5. 若推文包含视频 (has_video / video_urls)，或 RSS 仅给出了视频而缺少快照图片 URL：
        #    优先通过 api.fxtwitter.com 单帖详情接口拉取官方高清视频封面快照 (thumbnail_url)！
        if not prepared.get("images") and (
            prepared.get("has_video") or prepared.get("video_urls")
        ):
            sid = ""
            m_link = _STATUS_URL_RE.search(str(prepared.get("link") or ""))
            if m_link:
                sid = m_link.group(2)
            elif str(prepared.get("id") or "").isdigit():
                sid = str(prepared["id"])
            target_u = str(prepared.get("username") or sub_username).strip().lstrip("@")
            if target_u and sid:
                st_detail = await self._fetch_single_status_cached(target_u, sid)
                if st_detail.get("images"):
                    prepared["images"] = list(st_detail["images"])
                    prepared["has_video"] = True
                    logger.info(
                        f"[TwitterRSS] 已为视频推文 {sid} (@{target_u}) 获取官方视频快照封面: {prepared['images'][0]}"
                    )

        local_image_paths: list[str] = []
        display_image_srcs: list[str] = []
        for img_url in prepared.get("images", []):
            if str(img_url).lower().endswith((".mp4", ".m3u8")) or "video.twimg.com" in str(img_url).lower():
                local_path, data_uri = await self._download_video_snapshot_cached(img_url)
            else:
                local_path, data_uri = await self._download_image_cached(img_url)
            if local_path:
                local_image_paths.append(local_path)
            if data_uri:
                display_image_srcs.append(data_uri)

        # 若仍无快照且有 .mp4 视频链接，尝试本地抽帧提取视频快照
        if not local_image_paths and prepared.get("video_urls"):
            for v_url in prepared.get("video_urls", [])[:2]:
                local_path, data_uri = await self._download_video_snapshot_cached(v_url)
                if local_path:
                    local_image_paths.append(local_path)
                if data_uri:
                    display_image_srcs.append(data_uri)

        # 若引用推文自身带图而外层推文无图，也将引用推文的图片纳入原图发送与视觉评估列表
        if not local_image_paths and quote_info and q_detail.get("images"):
            for img_url in q_detail["images"]:
                local_path, _ = await self._download_image_cached(img_url)
                if local_path:
                    local_image_paths.append(local_path)

        prepared["orig_body"] = orig_body
        prepared["orig_tags"] = orig_tags
        prepared["avatar_src"] = avatar_data_uri
        prepared["local_images"] = local_image_paths
        prepared["display_images"] = display_image_srcs
        prepared["quote_info"] = quote_info
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
            self._get_setting("vision_provider_id", "")
            or self._get_setting("text_provider_id", "")
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
            "- 【人名尽量不翻译】：翻译正文与标签时，遇到人名（包括画师名、歌手/唱见名、VTuber/虚拟主播名、创作者昵称、声优名、角色名，尤其是日文假名/英文名如 ちょこ、ななひら、桃寝ちのい、名取さな、somunia 等）请直接保留原文，严禁强行音译或意译成生硬的中文！\n"
            "- 若【原推文标签列表】非空，请将每个标签翻译为中文标签放入 translated_tags 数组（每个元素以 # 开头，涉及人名/专有创作者名的标签保留原文；若原推文无标签，则可结合画面补充 1~3 个核心中文 #标签 放入 translated_tags）。\n\n"
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
        hit_must = [t for t in must_tags if t.lower() in {m.lower() for m in matched_must}]
        hit_any = [t for t in any_tags if t.lower() in {m.lower() for m in matched_any}]
        hit_exc = [t for t in exclude_tags if t.lower() in {m.lower() for m in matched_exc}]
        missing_must = [t for t in must_tags if t not in hit_must]

        # 如果原推文没有正文，强制省略正文翻译
        translated_body = (
            str(data.get("translated_body") or "").strip() if orig_body else ""
        )
        translated_tags = self._normalize_translated_tags(data.get("translated_tags"))

        # Report all failed conditions together so partial matches remain visible.
        reasons = []
        if hit_exc:
            reasons.append(f"图片包含排除标签: {', '.join(hit_exc)}")
        if missing_must:
            reasons.append(f"图片未命中必须包含标签: {', '.join(missing_must)}")
        if any_tags and not hit_any:
            reasons.append(f"图片未匹配到任何一条任意标签 ({', '.join(any_tags)})")

        return {
            "passed": not reasons,
            "translated_body": translated_body,
            "translated_tags": translated_tags,
            "reason": "；".join(reasons) if reasons else "通过视觉标签过滤",
            "matched_must_tags": hit_must,
            "matched_any_tags": hit_any,
            "matched_exclude_tags": hit_exc,
            "missing_must_tags": missing_must,
        }

    async def _evaluate_text_for_group(
        self, prepared_tweet: dict[str, Any], group_rule: dict[str, Any]
    ) -> dict[str, Any]:
        """根据指定群聊的文本筛选标准评估推文并翻译正文与标签"""
        text_provider_id = str(self._get_setting("text_provider_id", "") or "").strip()
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
            "【翻译注意】遇到人名（如画师、歌手、VTuber、创作者昵称、角色名，尤其是日文假名/英文名如 ちょこ、ななひら、桃寝ちのい、名取さな 等）请尽量保留原文不翻译，不要强行音译或意译成生硬的中文。\n\n"
            "请严格返回如下 JSON 格式：\n"
            "{\n"
            '  "worth_pushing": true,\n'
            '  "translated_body": "若原推文正文非空，直接输出正文的纯中文译文（人名保留原文，严禁添加疑似/解释说明）；若原推文正文为空，必须输出空字符串 \"\"",\n'
            '  "translated_tags": ["#标签译文1(人名保留原文)", "#标签译文2"],\n'
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

    async def _translate_only_without_filter(
        self, prepared_tweet: dict[str, Any]
    ) -> dict[str, str | list[str]]:
        """用于【直接推送】模式：不做任何 AI 价值/标签淘汰判断，仅对非空正文和标签进行中文直译"""
        orig_body = str(prepared_tweet.get("orig_body") or "").strip()
        orig_tags = prepared_tweet.get("orig_tags") or []
        if not orig_body and not orig_tags:
            return {"translated_body": "", "translated_tags": []}

        text_provider_id = str(self._get_setting("text_provider_id", "") or "").strip()
        system_prompt = "你是一个专业的推文直译助手。请直接将推文正文与标签翻译为中文，严格返回 JSON 对象。"
        prompt = (
            f"原推文正文: {json.dumps(orig_body, ensure_ascii=False)}\n"
            f"原推文标签列表: {json.dumps(orig_tags, ensure_ascii=False)}\n\n"
            "【要求】遇到人名（如画师、歌手、VTuber、创作者昵称、角色名）请尽量保留原文不翻译。\n"
            "请严格返回如下 JSON 格式：\n"
            "{\n"
            '  "translated_body": "若原推文正文非空，输出纯中文译文；若原推文正文为空，输出 \"\"",\n'
            '  "translated_tags": ["#标签译文1", "#标签译文2"]\n'
            "}"
        )
        try:
            raw_resp = await self._call_llm(
                prompt=prompt, system_prompt=system_prompt, provider_id=text_provider_id
            )
            data = self._extract_json_dict(raw_resp)
            return {
                "translated_body": str(data.get("translated_body") or "").strip() if orig_body else "",
                "translated_tags": self._normalize_translated_tags(data.get("translated_tags")),
            }
        except Exception as e:
            logger.debug(f"[TwitterRSS] 直接推送模式翻译跳过: {e}")
            return {"translated_body": "", "translated_tags": []}

    async def evaluate_tweet_for_group(
        self, prepared_tweet: dict[str, Any], group_rule: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        """针对单个群聊的独立规则评估推文是否值得推送"""
        if self._should_skip_tweet(prepared_tweet, group_rule, media_prepared=True):
            logger.info(
                f"[TwitterRSS] 推文 {prepared_tweet.get('id')} (@{prepared_tweet.get('username')}) 命中推文类型过滤开关（转贴/回复/纯文字/图片），已按配置自动跳过。"
            )
            return False, prepared_tweet

        enriched = dict(prepared_tweet)
        # Visual matches belong to this group's evaluation, not shared media.
        enriched.pop("vision_matched_tags", None)

        # 若该账号对应推文类型设置为【直接推送】，则不经过 AI 判断内容是否值得推送，直接翻译并放行！
        if self._is_direct_push_tweet(enriched, group_rule):
            logger.info(
                f"[TwitterRSS] 群[{group_rule.get('group_name')}] 推文 {enriched.get('id')} (@{enriched.get('username')}) 命中单账号【直接推送】开关，跳过 AI 过滤判断直接推送！"
            )
            tr = await self._translate_only_without_filter(enriched)
            if tr.get("translated_body") and enriched.get("orig_body"):
                enriched["translated_body"] = tr["translated_body"]
            if tr.get("translated_tags"):
                enriched["translated_tags"] = tr["translated_tags"]
            return True, enriched
        has_images = len(enriched.get("local_images", [])) > 0
        vision_enabled = bool(group_rule.get("enable_vision_tag_filter", True))
        text_ai_enabled = bool(group_rule.get("enable_text_ai_filter", True))
        bypass_text = bool(self._get_setting("image_tweet_bypass_text_filter", True))

        if has_images and vision_enabled:
            v_res = await self._evaluate_vision_for_group(enriched, group_rule)
            if v_res.get("translated_body") and enriched.get("orig_body"):
                enriched["translated_body"] = v_res["translated_body"]
            if v_res.get("translated_tags"):
                enriched["translated_tags"] = v_res["translated_tags"]

            if not v_res.get("passed", False):
                match_details = ""
                if "matched_must_tags" in v_res:
                    match_details = (
                        f" | 已命中必须标签: {'、'.join(v_res['matched_must_tags']) or '无'}"
                        f" | 已命中任意标签: {'、'.join(v_res.get('matched_any_tags', [])) or '无'}"
                        f" | 命中排除标签: {'、'.join(v_res.get('matched_exclude_tags', [])) or '无'}"
                    )
                logger.info(
                    f"[TwitterRSS] 群[{group_rule.get('group_name')}] 推文 {enriched['id']} (@{enriched['username']}) 未通过视觉筛选: {v_res.get('reason')}{match_details}"
                )
                return False, enriched

            enriched["vision_matched_tags"] = list(dict.fromkeys(
                v_res.get("matched_must_tags", []) + v_res.get("matched_any_tags", [])
            ))
            matched_label = "、".join(enriched["vision_matched_tags"]) or "未配置包含标签"
            logger.info(
                f"[TwitterRSS] 群[{group_rule.get('group_name')}] 推文 {enriched['id']} (@{enriched['username']}) 通过视觉标签筛选 | 命中标签: {matched_label}"
            )
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
            logger.info(
                f"[TwitterRSS] 群[{group_rule.get('group_name')}] 推文 {enriched['id']} (@{enriched['username']}) 通过文本价值筛选"
            )

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

        if res and str(res).startswith(("http://", "https://")):
            local_p, _ = await self._download_image_cached(str(res))
            if local_p:
                res = local_p

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
            return False

        author_name = enriched_tweet.get("author_name") or enriched_tweet.get("username", "X")
        orig_body = enriched_tweet.get("orig_body", "")
        orig_tags = enriched_tweet.get("orig_tags", [])
        # 如果没有正文，则严格省略正文翻译；标签保留蓝色字体
        translated_body = enriched_tweet.get("translated_body", "") if orig_body else ""
        translated_tags = enriched_tweet.get("translated_tags", [])

        render_payload = {
            "is_retweet": bool(enriched_tweet.get("is_retweet", False)),
            "retweeter_username": enriched_tweet.get("retweeter_username", ""),
            "retweeter_name": enriched_tweet.get("retweeter_name", ""),
            "retweeter_avatar_src": enriched_tweet.get("retweeter_avatar_src", ""),
            "author_name": author_name,
            "author_initial": author_name[:1].upper(),
            "username": enriched_tweet.get("username", ""),
            "avatar_src": enriched_tweet.get("avatar_src", ""),
            "orig_body": orig_body,
            "orig_tags": orig_tags,
            "translated_body": translated_body,
            "translated_tags": translated_tags,
            "quote_info": enriched_tweet.get("quote_info"),
            "display_images": enriched_tweet.get("display_images", []),
            "pub_date": enriched_tweet.get("pub_date", ""),
            "vision_matched_tags": enriched_tweet.get("vision_matched_tags", []),
        }

        logger.info(
            f"[TwitterRSS] 正在为群聊 {umo} 渲染推文卡片: @{enriched_tweet.get('username')} ({enriched_tweet.get('id')})"
        )
        rendered_card_path = await self._render_html_to_image(TWEET_CARD_TMPL, render_payload)
        raw_images = enriched_tweet.get("local_images", [])
        external_links = self._tweet_external_links(enriched_tweet) if self._get_setting("include_external_links", True) else []
        link_components = [Comp.Plain("\n站外链接：\n" + "\n".join(external_links))] if external_links else []
        send_mode = str(self._get_setting("push_send_mode", "separate_messages") or "separate_messages")

        # 合并转发判断：当开启 enable_merge_forward_over_3 且（原图数 > 3 或 渲染卡+原图总数 > 3）时，使用合并转发
        enable_merge_forward = bool(self._get_setting("enable_merge_forward_over_3", True))
        merge_threshold = max(1, int(self._get_setting("merge_forward_image_threshold", 3) or 3))
        total_img_count = 1 + len(raw_images)  # 1张渲染推文卡 + N张原图
        use_merge_forward = enable_merge_forward and (
            len(raw_images) > merge_threshold or total_img_count > merge_threshold
        )

        try:
            if use_merge_forward:
                sender_name = f"{author_name} (@{enriched_tweet.get('username', 'X')})"
                bot_uin = str(self._get_setting("merge_forward_uin", "10000") or "10000").strip()
                if not bot_uin.isdigit():
                    bot_uin = "10000"

                # 判断是否为 QQ 官方机器人会话（umo 含 qq_official 或群号为 32 位十六进制 OpenID）
                umo_tail = umo.split(":")[-1]
                is_qq_official = (
                    "qq_official" in umo.lower()
                    or "qqofficial" in umo.lower()
                    or bool(re.match(r"^[0-9A-Fa-f]{32}$", umo_tail))
                )

                # 若是 OneBot v11 (aiocqhttp) 等支持 Comp.Node 的平台，构造合并转发节点
                if not is_qq_official and hasattr(Comp, "Node"):
                    try:
                        node_list = [
                            Comp.Node(
                                uin=int(bot_uin),
                                name=sender_name,
                                content=[self._make_image_comp(rendered_card_path)] + link_components,
                            )
                        ]
                        for raw_img in raw_images:
                            node_list.append(
                                Comp.Node(
                                    uin=int(bot_uin),
                                    name=sender_name,
                                    content=[self._make_image_comp(raw_img)],
                                )
                            )
                        forward_comp = (
                            Comp.Nodes(node_list)
                            if hasattr(Comp, "Nodes")
                            else node_list
                        )
                        chain_items = (
                            [forward_comp]
                            if not isinstance(forward_comp, list)
                            else forward_comp
                        )
                        await self.context.send_message(umo, MessageChain(chain_items))
                        return
                    except Exception as fwd_err:
                        logger.warning(
                            f"[TwitterRSS] 合并转发 (Comp.Nodes) 发送失败，自动回退为单条合并消息链发送: {fwd_err}"
                        )

                # 若当前平台为 qq_official（腾讯官方接口不支持伪造合并转发节点）或合并转发异常，自动回退为单条消息链合并发送
                chain_comps = [self._make_image_comp(rendered_card_path)]
                for raw_img in raw_images:
                    chain_comps.append(self._make_image_comp(raw_img))
                chain_comps.extend(link_components)
                await self.context.send_message(umo, MessageChain(chain_comps))
                return

            if send_mode == "single_chain":
                chain_comps = [self._make_image_comp(rendered_card_path)]
                for raw_img in raw_images:
                    chain_comps.append(self._make_image_comp(raw_img))
                chain_comps.extend(link_components)
                await self.context.send_message(umo, MessageChain(chain_comps))
            else:
                await self.context.send_message(
                    umo, MessageChain([self._make_image_comp(rendered_card_path)] + link_components)
                )
                for raw_img in raw_images:
                    await asyncio.sleep(0.6)
                    try:
                        await self.context.send_message(
                            umo, MessageChain([self._make_image_comp(raw_img)])
                        )
                    except Exception as img_err:
                        logger.warning(f"[TwitterRSS] 发送单张原图 ({raw_img}) 失败，已跳过该原图: {img_err}")
            logger.info(
                f"[TwitterRSS] 已向群聊 {umo} 推送推文 @{enriched_tweet.get('username')} ({enriched_tweet.get('id')})，附带原图 {len(raw_images)} 张"
            )
        except Exception as e:
            logger.error(f"[TwitterRSS] 向群聊会话 {umo} 推送推文失败: {e}")
            return False

    async def check_all_accounts(
        self, manual: bool = False, target_rule: dict[str, Any] | None = None
    ) -> dict[str, int]:
        """Fetch each subscription once, then fan out to independent group consumers."""
        if manual and target_rule is None:
            raise ValueError("手动检查必须指定当前群聊规则，禁止回退到全局扫描")
        async with self._lock:
            rules = [target_rule] if target_rule is not None else self._get_group_rules()
            scope = f"群[{target_rule.get('group_name') or target_rule.get('target_umo')}]" if target_rule is not None else "全部群聊"
            operation = "手动检查" if manual else "后台扫描"
            stats = {"fetched": 0, "new": 0, "pushed": 0}
            if not rules:
                return stats
            fetch_limit = max(1, min(12, int(self._get_setting("fetch_concurrency", 4) or 4)))
            process_limit = max(1, min(8, int(self._get_setting("processing_concurrency", 3) or 3)))
            fetch_slots = asyncio.Semaphore(fetch_limit)
            process_slots = asyncio.Semaphore(process_limit)
            media_slots = asyncio.Semaphore(process_limit)
            seen_map = self.state.setdefault("seen_ids", {})
            init_keys = self.state.setdefault("initialized_keys", [])
            first_run_mark_seen = bool(self._get_setting("first_run_mark_seen", True))
            history = {self._tweet_identity(t): t for t in self.history_tweets}
            prepared_tasks: dict[str, asyncio.Task] = {}
            subscribers: dict[str, list[asyncio.Queue]] = {}
            sources: dict[str, tuple[str, bool]] = {}
            group_seen: dict[str, set[str]] = {}
            group_locks: dict[str, asyncio.Lock] = {}
            consumers = []
            queues = []

            async def prepare_shared(tweet):
                # Keep source-specific hashtag metadata out of the shared media result.
                async with media_slots:
                    base = copy.deepcopy(tweet)
                    base.pop("subscription_hashtag", None)
                    base.pop("subscription_hashtags", None)
                    return await self._prepare_tweet_media(base)

            async def process_source(rule, umo, key, account, is_hashtag, tweets):
                if not tweets:
                    if not is_hashtag and account.strip().lstrip("@").lower() in self._not_found_accounts:
                        self._auto_remove_invalid_account(account, target_rule=rule)
                        stats.setdefault("removed_accounts", []).append(account)
                        try:
                            await self.context.send_message(umo, MessageChain([Comp.Plain(
                                f"🗑️ [TwitterRSS] 账号 @{account} 不存在，已从本群订阅中移除。"
                            )]))
                        except Exception as exc:
                            logger.warning(f"[TwitterRSS] 发送无效账号通知失败: {exc}")
                    return
                state_key = f"{umo}::{key}"
                # Migrate older case-sensitive account keys without replaying history.
                for old_key in list(seen_map):
                    if old_key.startswith(f"{umo}::") and old_key[len(umo) + 2:].casefold() == key and old_key != state_key:
                        seen_map[state_key] = list(dict.fromkeys(seen_map.get(state_key, []) + seen_map.pop(old_key)))
                        if old_key in init_keys:
                            init_keys.remove(old_key)
                            if state_key not in init_keys:
                                init_keys.append(state_key)
                read_order = dict.fromkeys(seen_map.get(state_key, []))
                seen = group_seen[umo]
                first = state_key not in init_keys
                candidates = []
                for tweet in tweets:
                    identity = self._tweet_identity(tweet)
                    prior = history.get(identity)
                    if prior is not None and is_hashtag:
                        prior["subscription_hashtags"] = list(dict.fromkeys(
                            prior.get("subscription_hashtags", [])
                            + ([prior["subscription_hashtag"]] if prior.get("subscription_hashtag") else [])
                            + [account[1:]]
                        ))
                    if tweet["id"] in read_order:
                        continue
                    if identity in seen or self._should_skip_tweet(tweet, rule):
                        read_order[tweet["id"]] = None
                        continue
                    if prior is None:
                        prior = copy.deepcopy(tweet)
                        history[identity] = prior
                        self.history_tweets.append(prior)
                    candidates.append(tweet)
                if first and first_run_mark_seen and not manual:
                    mark_only, candidates = candidates, []
                    logger.info(f"[TwitterRSS] 群[{rule.get('group_name')}] 订阅 {account} 首次初始化，标记 {len(mark_only)} 条历史已读")
                elif first:
                    mark_only, candidates = candidates[:-2], candidates[-2:]
                else:
                    mark_only = []
                for tweet in mark_only:
                    read_order[tweet["id"]] = None
                    seen.add(self._tweet_identity(tweet))
                # Initialization applies to this subscription, not each process restart.
                if first:
                    init_keys.append(state_key)
                seen_map[state_key] = list(read_order)[-300:]
                for tweet in candidates:
                    identity = self._tweet_identity(tweet)
                    if identity in seen:
                        read_order[tweet["id"]] = None
                        continue
                    stats["new"] += 1
                    try:
                        media_key = (identity, tweet.get("username"), bool(tweet.get("is_retweet")), tweet.get("rt_status_id"))
                        if media_key not in prepared_tasks:
                            prepared_tasks[media_key] = asyncio.create_task(prepare_shared(tweet))
                        prepared = copy.deepcopy(await prepared_tasks[media_key])
                        for field in ("subscription_hashtag", "subscription_hashtags"):
                            if field in tweet:
                                prepared[field] = copy.deepcopy(tweet[field])
                        async with process_slots:
                            worth, enriched = await self.evaluate_tweet_for_group(prepared, rule)
                            if worth:
                                sent = await self.push_tweet_to_umo(enriched, umo)
                                if sent is False:
                                    raise RuntimeError("推送失败")
                                stats["pushed"] += 1
                        history[identity]["ai_summary"] = enriched.get("translated_body", "")
                        read_order[tweet["id"]] = None
                        seen.add(identity)
                        seen_map[state_key] = list(read_order)[-300:]
                        # Persist completed deliveries while other groups are still processing.
                        await self._save_state()
                    except Exception as exc:
                        logger.error(f"[TwitterRSS] 群[{rule.get('group_name')}] 处理推文 {identity} 失败，将在下轮重试: {exc}")
                seen_map[state_key] = list(read_order)[-300:]

            async def consume(rule, umo, queue):
                while True:
                    item = await queue.get()
                    if item is None:
                        return
                    key, account, is_hashtag, tweets = item
                    try:
                        async with group_locks[umo]:
                            await process_source(rule, umo, key, account, is_hashtag, tweets)
                    except Exception as exc:
                        logger.error(f"[TwitterRSS] 群[{rule.get('group_name')}] 处理订阅 {account} 失败: {exc}")

            for rule in rules:
                umo = self._resolve_target_umo(rule.get("target_umo", ""))
                if not umo:
                    continue
                queue = asyncio.Queue()
                queues.append(queue)
                group_locks.setdefault(umo, asyncio.Lock())
                group_seen.setdefault(umo, {
                    self._tweet_identity(tweet_id)
                    for key, ids in seen_map.items() if key.startswith(f"{umo}::")
                    for tweet_id in ids
                })
                subscriptions = [(a, False) for a in self._get_rule_accounts(rule)] + [(f"#{t}", True) for t in self._get_rule_hashtags(rule)]
                for account, is_hashtag in subscriptions:
                    key = account if account.startswith(("http://", "https://")) else account.casefold()
                    sources.setdefault(key, (account, is_hashtag))
                    subscribers.setdefault(key, []).append(queue)
                consumers.append(asyncio.create_task(consume(rule, umo, queue)))

            async def produce(key, account, is_hashtag):
                tweets = []
                try:
                    async with fetch_slots:
                        tweets = await self._fetch_hashtag_tweets(account[1:]) if is_hashtag else await self._fetch_account_tweets(account)
                    stats["fetched"] += len(tweets)
                except Exception as exc:
                    logger.warning(f"[TwitterRSS] 抓取订阅 {account} 失败: {exc}")
                for queue in subscribers[key]:
                    queue.put_nowait((key, account, is_hashtag, tweets))

            producers = [asyncio.create_task(produce(key, *source)) for key, source in sources.items()]
            logger.info(f"[TwitterRSS] {operation} {scope} 开始：{len(sources)} 个唯一订阅，抓取并发 {fetch_limit}，处理并发 {process_limit}")
            try:
                await asyncio.gather(*producers)
                for queue in queues:
                    queue.put_nowait(None)
                await asyncio.gather(*consumers, return_exceptions=True)
            finally:
                tasks = producers + consumers + list(prepared_tasks.values())
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await self._save_state()
                await self._save_history()
            logger.info(f"[TwitterRSS] {operation} {scope} 完成：累计拉取 {stats['fetched']} 条，发现新推文 {stats['new']} 条，筛选通过并推送 {stats['pushed']} 条。")
            return stats

    async def test_push_for_group(
        self,
        group_rule: dict[str, Any],
        limit: int = 3,
        target_account: str = "",
    ) -> dict[str, Any]:
        """Test N random local subscriptions once each, or N tweets from an explicit account."""
        if limit < 1:
            raise ValueError("测试条数必须为正整数")
        async with self._lock:
            umo = self._resolve_target_umo(group_rule.get("target_umo", ""))
            if target_account.strip():
                sources = [(target_account.strip().lstrip("@"), False)]
            else:
                sources = [(a, False) for a in self._get_rule_accounts(group_rule)]
                sources += [(f"#{tag}", True) for tag in self._get_rule_hashtags(group_rule)]
            stats = {"accounts": 0, "subscriptions": 0, "fetched": 0, "sampled": 0,
                     "evaluated": 0, "pushed": 0, "filtered": 0, "failed": 0, "removed_accounts": []}
            if not sources or not umo:
                return stats
            if not target_account.strip():
                sources = random.sample(sources, min(limit, len(sources)))
            concurrency = max(1, min(12, int(self._get_setting("fetch_concurrency", 4) or 4)))
            selected = []
            selected_ids = set()
            logger.info(
                f"[TwitterRSS] 随机测试 群[{group_rule.get('group_name') or umo}]："
                f"仅抓取选中的 {len(sources)} 个订阅：{', '.join(account for account, _ in sources)}"
            )

            async def fetch_source(account, is_hashtag):
                stats["subscriptions"] += 1
                if not is_hashtag:
                    stats["accounts"] += 1
                try:
                    tweets = await self._fetch_hashtag_tweets(account[1:]) if is_hashtag else await self._fetch_account_tweets(account)
                except Exception as exc:
                    logger.warning(f"[TwitterRSS] 测试抓取 {account} 失败: {exc}")
                    return account, []
                stats["fetched"] += len(tweets)
                if not tweets and not is_hashtag and account.strip().lstrip("@").lower() in self._not_found_accounts:
                    self._auto_remove_invalid_account(account, target_rule=group_rule)
                    stats["removed_accounts"].append(account)
                return account, tweets

            for offset in range(0, len(sources), concurrency):
                batch = sources[offset:offset + concurrency]
                tasks = [asyncio.create_task(fetch_source(*source)) for source in batch]
                try:
                    results = await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                for account, tweets in results:
                    pool = {}
                    for tweet in tweets:
                        identity = self._tweet_identity(tweet)
                        if identity not in selected_ids and identity not in pool and not self._should_skip_tweet(tweet, group_rule):
                            pool[identity] = (account, tweet)
                    count = limit if target_account.strip() else 1
                    for entry in random.sample(list(pool.values()), min(count, len(pool))):
                        selected.append(entry)
                        selected_ids.add(self._tweet_identity(entry[1]))

            stats["sampled"] = len(selected)
            seen_map = self.state.setdefault("seen_ids", {})
            history = {self._tweet_identity(tweet): tweet for tweet in self.history_tweets}
            try:
                for account, tweet in selected:
                    stats["evaluated"] += 1
                    try:
                        prepared = await self._prepare_tweet_media(copy.deepcopy(tweet))
                        worth, enriched = await self.evaluate_tweet_for_group(prepared, group_rule)
                        if worth:
                            if await self.push_tweet_to_umo(enriched, umo) is False:
                                raise RuntimeError("推送失败")
                            stats["pushed"] += 1
                        else:
                            stats["filtered"] += 1
                        identity = self._tweet_identity(tweet)
                        if identity not in history:
                            history[identity] = copy.deepcopy(tweet)
                            self.history_tweets.append(history[identity])
                        history[identity]["ai_summary"] = enriched.get("translated_body", "")
                        key = account if account.startswith(("http://", "https://")) else account.casefold()
                        state_key = f"{umo}::{key}"
                        seen_map[state_key] = list(dict.fromkeys(seen_map.get(state_key, []) + [tweet["id"]]))[-300:]
                        await self._save_state()
                    except Exception as exc:
                        stats["failed"] += 1
                        logger.error(f"[TwitterRSS] 测试处理推文 {tweet.get('id')} 失败: {exc}")
            finally:
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

        max_items = max(3, int(self._get_setting("daily_digest_max_items", 8) or 8))
        digest_prompt_cfg = str(
            self._get_setting("daily_digest_prompt", "")
            or "请从过去24小时的推文中精选重要动态，整理为今日要闻简讯。"
        ).strip()
        text_provider_id = str(self._get_setting("text_provider_id", "") or "").strip()

        pushed_any = False
        last_img_path = ""

        for rule in rules:
            umo = self._resolve_target_umo(rule.get("target_umo", ""))
            if not umo:
                continue

            recent_tweets = [
                t
                for t in self.history_tweets
                if t.get("timestamp", 0) >= cutoff
                and self._matches_rule_subscription(t, rule)
            ]
            if not recent_tweets:
                continue

            # 将过去24小时的全部推文（最多取最近100条，不再只截断40条）交给 AI 自主筛选
            pool_limit = max(100, max_items * 4)
            recent_slice = recent_tweets[-pool_limit:]

            candidates_lines: list[str] = []
            for idx, t in enumerate(recent_slice):
                text_snippet = (t.get("text") or "").replace("\n", " ").strip()[:240]
                if not text_snippet:
                    text_snippet = "（无文字配文，仅发布了插画图片）" if t.get("images") else "（无文字内容）"
                trans_hint = (t.get("ai_summary") or "").replace("\n", " ").strip()[:120]
                has_img_tag = "含插画配图" if t.get("images") else "纯文字"
                line = f"[{idx}] @{t.get('username')} ({t.get('author_name')}, {t.get('pub_date')}, {has_img_tag}): {text_snippet}"
                if trans_hint:
                    line += f" | 参考译文: {trans_hint}"
                candidates_lines.append(line)

            system_prompt = (
                "你是一位干练、克制的新闻简报主编。请根据过去24小时的推文素材，自主判断并筛选出真正具备新闻/资讯/作品发布价值的《今日要闻》条目，严格输出 JSON 格式。"
            )
            prompt = (
                f"【编辑要求】\n{digest_prompt_cfg}\n"
                f"【条数上限与自主精选规则】\n"
                f"- 本期要闻的条数上限为 **{max_items} 条**（最多不超过 {max_items} 条）。\n"
                f"- 请由你自主评估下方每一条候选推文是否算作值得报道的“要闻”（例如：新作/新曲发布、角色设计公开、活动/演出预告、联动周边发售、众筹/企划进展、重要动态更新等算作要闻；单纯早安晚安寒暄、无实质内容的闲聊水帖不算要闻）。\n"
                f"- **宁缺毋滥、实事求是**：在不超过 {max_items} 条上限的前提下，你认为有几条真正算新闻，就输出几条（例如若只有 5 条算新闻就只输出 5 条；若有 14 条算新闻就输出 14 条，不要为了凑满上限而塞入水帖，也不要固定停在 8 条）。\n\n"
                "【撰写铁律（必须严格执行）】\n"
                "1. 新闻简讯口吻：title（8~18字）与 summary（20~50字，1~2句话）均采用客观、洗练的新闻报道口吻，直接陈述作者发布了什么主题的插画、设计或动态，有话则长、无话则短。\n"
                "2. 人名尽量保留原文不翻译：在 title 和 summary 中提及画师、歌手、VTuber、创作者昵称或角色名（尤其是日文假名/汉字/英文名，如 ちょこ、ななひら、桃寝ちのい、名取さな、somunia、中村さんそ 等）时，请直接保留原名，严禁将其强行音译或意译为生硬中文（例如不要把 ななひら 译成“奈奈平”，不要把 名取さな 译成“名取纱那”，不要把 桃寝ちのい 简写或改译）！\n"
                "3. 严禁出现废话或提及未知信息：绝对禁止输出“无法判断…”、“未进一步说明…”、“未透露…”、“素材未包含…”、“暂不清楚…”、“未提及…”、“无法核验…”等任何关于信息缺失的表述！只陈述推文已有的明确信息。\n"
                "4. 严禁使用任何 Emoji 表情符号。\n\n"
                f"【过去24小时推文素材列表（共 {len(recent_slice)} 条）】\n" + "\n".join(candidates_lines) + "\n\n"
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
            used_indices: set[int] = set()

            for i, entry in enumerate(raw_items[:max_items]):
                idx = entry.get("tweet_index", -1)
                if not isinstance(idx, int) or idx < 0 or idx >= len(recent_slice) or idx in used_indices:
                    continue
                used_indices.add(idx)
                src_tweet = recent_slice[idx]

                thumb_src = ""
                item_palette = shuffled_palettes[len(rendered_items) % len(shuffled_palettes)]
                if src_tweet.get("images"):
                    local_img_path, b64_uri = await self._download_image_cached(src_tweet["images"][0])
                    thumb_src = b64_uri or src_tweet["images"][0]
                    if local_img_path:
                        item_palette = await asyncio.to_thread(
                            _extract_macaron_palette_from_image_sync,
                            local_img_path,
                            item_palette,
                        )

                clean_cat = _clean_digest_text(str(entry.get("category") or "资讯速递"), is_summary=False)
                clean_title = _clean_digest_text(
                    str(entry.get("title") or src_tweet.get("title") or f"@{src_tweet.get('username')} 发布新动态"),
                    is_summary=False,
                )
                clean_summary = _clean_digest_text(
                    str(entry.get("summary") or src_tweet.get("ai_summary") or src_tweet.get("text") or "发布了最新作品动态。"),
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
                        "raw_image_url": src_tweet["images"][0] if src_tweet.get("images") else "",
                        "palette": item_palette,
                    }
                )

            if not rendered_items:
                for i, src_tweet in enumerate(reversed(recent_slice[-max_items:])):
                    thumb_src = ""
                    item_palette = shuffled_palettes[i % len(shuffled_palettes)]
                    if src_tweet.get("images"):
                        local_img_path, b64_uri = await self._download_image_cached(src_tweet["images"][0])
                        thumb_src = b64_uri or src_tweet["images"][0]
                        if local_img_path:
                            item_palette = await asyncio.to_thread(
                                _extract_macaron_palette_from_image_sync,
                                local_img_path,
                                item_palette,
                            )
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
                            "raw_image_url": src_tweet["images"][0] if src_tweet.get("images") else "",
                            "palette": item_palette,
                        }
                    )

            # 综合下方所有新闻词条的颜色进行色相环聚类与向量合成，取出最契合整期所有词条的全局主题配色
            lead_palette, mid_palette, end_palette = _compute_harmonious_digest_theme(
                rendered_items, theme_palette
            )

            now = datetime.datetime.now()
            render_data = {
                "date_str": now.strftime("%Y.%m.%d"),
                "total_count": len(recent_tweets),
                "account_count": len(self._get_rule_accounts(rule)) + len(self._get_rule_hashtags(rule)),
                "theme": lead_palette,
                "theme_mid": mid_palette,
                "theme_end": end_palette,
                "items": rendered_items,
            }

            digest_img_path = await self._render_html_to_image(DAILY_DIGEST_TMPL, render_data)
            date_key = now.strftime("%Y-%m-%d")
            archived_path = await self._archive_daily_digest(
                umo=umo,
                group_name=str(rule.get("group_name") or umo),
                date_key=date_key,
                digest_img_path=digest_img_path,
                render_data=render_data,
            )
            send_img_path = archived_path if pathlib.Path(archived_path).exists() else digest_img_path
            try:
                await self.context.send_message(
                    umo, MessageChain([self._make_image_comp(send_img_path)])
                )
                pushed_any = True
                last_img_path = send_img_path
            except Exception as e:
                logger.error(f"[TwitterRSS] 向会话 {umo} 推送24小时要闻长图失败: {e}")

        if not pushed_any:
            return False, "本群过去 24 小时内暂无收录的推文内容。"
        return True, last_img_path

    # =========================================================================
    # 聊天管理指令组 (/tw ...) —— 所有指令均按当前群聊独立配置操作！
    # =========================================================================

    @staticmethod
    def _has_admin_permission(event: AstrMessageEvent) -> bool:
        """
        检查发送者是否具备群聊管理员/群主权限或 AstrBot 机器人管理员权限：
        兼容 AstrBot 原生 event.is_admin()、event.role、message_obj.sender.role 以及 OneBot/QQ官方 raw_message 角色字段
        """
        try:
            if hasattr(event, "is_admin") and callable(event.is_admin) and event.is_admin():
                return True
        except Exception:
            pass

        role_str = str(getattr(event, "role", "") or "").lower()
        if role_str in ("admin", "owner", "administrator", "creator", "superuser"):
            return True

        msg_obj = getattr(event, "message_obj", None)
        if msg_obj is not None:
            sender = getattr(msg_obj, "sender", None)
            if sender is not None:
                s_role = str(getattr(sender, "role", "") or "").lower()
                if s_role in ("admin", "owner", "administrator", "creator"):
                    return True
            raw_msg = getattr(msg_obj, "raw_message", None)
            if isinstance(raw_msg, dict):
                raw_sender = raw_msg.get("sender")
                if isinstance(raw_sender, dict):
                    r_role = str(raw_sender.get("role") or "").lower()
                    if r_role in ("admin", "owner", "administrator", "creator"):
                        return True

        return False

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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("unsub")
    async def tw_unsub(self, event: AstrMessageEvent):
        """移除当前群聊的独立订阅配置"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

        # 立即核验该推特 ID 是否存在，若不存在则自动移除
        await self._fetch_account_tweets(acct)
        if acct.lower() in self._not_found_accounts:
            self._auto_remove_invalid_account(acct, target_rule=rule)
            yield event.plain_result(
                f"🗑️ 检测到推特 ID @{acct} 不存在或已注销，已自动从当前群聊【{rule.get('group_name')}】订阅列表中移除。"
            )
            return

        yield event.plain_result(
            f"✅ 已为当前群聊【{rule.get('group_name')}】添加推特订阅: @{acct}\n"
            f"本群当前订阅数: {len(self._get_rule_accounts(rule))} 个"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("del")
    async def tw_del(self, event: AstrMessageEvent, account: str):
        """从当前群聊移除订阅的推特账号"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("tag_add")
    async def tw_tag_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊订阅推特话题标签。"""
        if not self._has_admin_permission(event):
            yield event.plain_result("权限不足：仅管理员可修改订阅标签。")
            return
        normalized = self._get_rule_hashtags({"twitter_hashtags": [tag]})
        if not normalized:
            yield event.plain_result("请填写单个标签，如 /tw tag_add 原神；标签不能包含空格或搜索运算符。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        rule["twitter_hashtags"] = self._get_rule_hashtags({"twitter_hashtags": self._get_rule_hashtags(rule) + normalized})
        self._save_plugin_config()
        yield event.plain_result(f"已订阅标签 #{normalized[0]}，将通过配置的搜索源或默认 Nitter 源抓取。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("tag_del")
    async def tw_tag_del(self, event: AstrMessageEvent, tag: str):
        """移除当前群聊的标签订阅。"""
        if not self._has_admin_permission(event):
            yield event.plain_result("权限不足：仅管理员可修改订阅标签。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=False)
        if not rule:
            yield event.plain_result("当前群聊尚未创建订阅配置。")
            return
        normalized = tag.strip().lstrip("#＃").casefold()
        rule["twitter_hashtags"] = [value for value in self._get_rule_hashtags(rule) if value.casefold() != normalized]
        self._save_plugin_config()
        yield event.plain_result(f"已移除标签订阅 #{tag.strip().lstrip('#＃')}。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("must_add")
    async def tw_must_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊添加【必须包含】图片标签（全部命中才通过）"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("must_del")
    async def tw_must_del(self, event: AstrMessageEvent, tag: str):
        """从当前群聊移除【必须包含】图片标签"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("any_add")
    async def tw_any_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊添加【其他任意】图片标签（命中任意一条即通过）"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("any_del")
    async def tw_any_del(self, event: AstrMessageEvent, tag: str):
        """从当前群聊移除【其他任意】图片标签"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("exc_add")
    async def tw_exc_add(self, event: AstrMessageEvent, tag: str):
        """为当前群聊添加【禁止包含】排除标签"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("exc_del")
    async def tw_exc_del(self, event: AstrMessageEvent, tag: str):
        """从当前群聊移除【禁止包含】排除标签"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
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

    def _format_account_with_overrides(self, account: str, rule: dict[str, Any]) -> str:
        clean_a = self._extract_clean_handle(account)
        pol = self._get_account_type_policy(clean_a, rule)
        srcs = pol.get("sources", {})
        modes = pol.get("modes", {})
        label_map = {"retweet": "转贴", "reply": "回复", "text": "纯文字", "image": "图片"}
        mode_short = {"direct": "直推", "push": "开", "skip": "关"}
        custom_parts: list[str] = []
        for k, cn in label_map.items():
            if srcs.get(k) == "单独设置":
                custom_parts.append(f"{cn}:{mode_short.get(modes.get(k, ''), '开')}")
        if custom_parts:
            return f"🟠{clean_a}[{','.join(custom_parts)}]"
        return clean_a

    @tw.command("list")
    async def tw_list(self, event: AstrMessageEvent):
        """查看当前群聊的独立订阅、各账号独立类型开关与标签过滤配置"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        accounts = self._get_rule_accounts(rule)
        formatted_accounts = [self._format_account_with_overrides(a, rule) for a in accounts]
        hashtags = self._get_rule_hashtags(rule)
        must_tags = self._clean_str_list(rule.get("must_include_image_tags", []))
        any_tags = self._clean_str_list(rule.get("any_include_image_tags", []))
        exc_tags = self._clean_str_list(rule.get("exclude_image_tags", []))
        test_count = max(1, int(self._get_setting("test_push_tweet_count", 3) or 3))
        all_rules = self._get_group_rules()
        g_defs = self._get_global_type_defaults(rule)

        msg = (
            f"📡 【当前群聊独立配置：{rule.get('group_name')}】\n"
            f"• 会话 ID: {rule.get('target_umo')}\n"
            f"• 本群订阅账号 ({len(accounts)}): {', '.join(formatted_accounts) if formatted_accounts else '暂无 (发送 /tw add <账号> 添加)'}\n"
            f"• 本群订阅标签 ({len(hashtags)}): {', '.join('#' + tag for tag in hashtags) if hashtags else '暂无 (发送 /tw tag_add <标签> 添加)'}\n"
            f"• 全局默认推文类型开关: "
            f"转贴={'推送' if g_defs['retweet'] else '跳过'} | "
            f"回复={'推送' if g_defs['reply'] else '跳过'} | "
            f"纯文字={'推送' if g_defs['text'] else '跳过'} | "
            f"图片={'推送' if g_defs['image'] else '跳过'}\n"
            f"  (发送 `/tw set <账号> <转贴|回复|纯文字|图片> <开启|关闭|默认>` 可为单个账号独立设置)\n"
            f"• 本群视觉标签过滤: {'开启' if rule.get('enable_vision_tag_filter', True) else '关闭'}\n"
            f"  - 必须包含标签 (全部命中): {', '.join(must_tags) if must_tags else '不限'}\n"
            f"  - 其他任意标签 (命中1条即可): {', '.join(any_tags) if any_tags else '不限'}\n"
            f"  - 禁止包含标签 (排除): {', '.join(exc_tags) if exc_tags else '无'}\n"
            f"• 本群文本价值判断: {'开启' if rule.get('enable_text_ai_filter', True) else '关闭'}\n"
            f"• 本群每日24h简报: {'开启' if rule.get('enable_daily_digest', True) else '关闭'} "
            f"(时间点: {self._get_setting('daily_digest_time', '08:30')})\n"
            f"• 随机测试: 本群 {test_count} 个订阅，各 1 条 | 全局已配置群聊总数: {len(all_rules)} 个"
        )
        yield event.plain_result(msg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("set")
    async def tw_set(
        self,
        event: AstrMessageEvent,
        account: str = "",
        tweet_type: str = "",
        state_str: str = "",
    ):
        """
        为单个订阅账号独立设置是否推送【转贴 / 回复 / 纯文字 / 图片】四类推文（未单独配置则跟随全局默认）：
        用法示例：
        - /tw set ProjMoonStudio             (查看该账号当前的四类推文推送设置)
        - /tw set ProjMoonStudio 转贴 开启    (单独允许推送该账号的转贴)
        - /tw set ProjMoonStudio 纯文字 关闭  (单独关闭该账号的纯文字推文，仅看带图推文)
        - /tw set ProjMoonStudio 回复 开启    (单独允许推送该账号的回复推文)
        - /tw set ProjMoonStudio 图片 开启    (单独开启该账号的图片推文推送)
        - /tw set ProjMoonStudio 全部 默认    (清除该账号的单独设置，恢复跟随全局默认设置)
        """
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return

        acct = account.strip().lstrip("@")
        if not acct:
            yield event.plain_result(
                "请提供要查看或设置的推特账号名，例如：\n"
                "• 查看账号设置：`/tw set ProjMoonStudio`\n"
                "• 单独开启转贴：`/tw set ProjMoonStudio 转贴 开启`\n"
                "• 单独关闭纯文字：`/tw set ProjMoonStudio 纯文字 关闭`\n"
                "• 恢复全局默认：`/tw set ProjMoonStudio 全部 默认`"
            )
            return

        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        umo = self._resolve_target_umo(rule.get("target_umo", "")) or event.unified_msg_origin

        type_alias_map = {
            "转贴": "retweet",
            "转推": "retweet",
            "转发": "retweet",
            "rt": "retweet",
            "retweet": "retweet",
            "回复": "reply",
            "评论": "reply",
            "reply": "reply",
            "纯文字": "text",
            "文字": "text",
            "文本": "text",
            "text": "text",
            "图片": "image",
            "带图": "image",
            "插画": "image",
            "image": "image",
            "img": "image",
            "全部": "all",
            "所有": "all",
            "all": "all",
            "reset": "all",
        }
        cn_label = {"retweet": "转贴", "reply": "回复", "text": "纯文字", "image": "图片"}
        cfg_field_map = {
            "retweet": "push_retweet",
            "reply": "push_reply",
            "text": "push_text",
            "image": "push_image",
        }

        mode_desc = {
            "direct": "⚡ 直接推送 (免AI审核)",
            "push": "✅ 推送 (经AI筛选)",
            "skip": "🚫 不推送",
        }
        if not tweet_type.strip():
            pol = self._get_account_type_policy(acct, rule)
            srcs = pol.get("sources", {})
            modes = pol.get("modes", {})
            yield event.plain_result(
                f"⚙️ 账号 @{acct} 在本群【{rule.get('group_name')}】的推文类型推送策略：\n"
                f"• 转贴 (retweet): {mode_desc.get(modes.get('retweet', 'skip'))} （{srcs['retweet']}）\n"
                f"• 回复 (reply): {mode_desc.get(modes.get('reply', 'skip'))} （{srcs['reply']}）\n"
                f"• 纯文字 (text): {mode_desc.get(modes.get('text', 'push'))} （{srcs['text']}）\n"
                f"• 图片 (image): {mode_desc.get(modes.get('image', 'push'))} （{srcs['image']}）\n\n"
                f"💡 修改示例：`/tw set {acct} <转贴|回复|纯文字|图片|全部> <直接推送|推送|不推送|默认>`"
            )
            return

        t_key = type_alias_map.get(tweet_type.strip().lower())
        if not t_key:
            yield event.plain_result(
                f"⚠️ 未知的推文类型：{tweet_type}\n"
                f"支持的类型：`转贴`、`回复`、`纯文字`、`图片`、`全部`"
            )
            return

        if t_key == "all" and not state_str.strip():
            state_str = "默认"

        parsed_mode = self._parse_switch_mode(state_str)
        is_reset_default = state_str.strip().lower() in (
            "默认", "默认(跟随全局)", "跟随全局", "default", "inherit", "auto", "reset"
        )
        if parsed_mode is None and not is_reset_default:
            yield event.plain_result(
                f"⚠️ 请指定有效的开关状态（`直接推送` / `推送` / `不推送` / `默认`），例如：\n"
                f"`/tw set {acct} {tweet_type} 直接推送` 或 `/tw set {acct} {tweet_type} 不推送` 或 `/tw set {acct} {tweet_type} 默认`"
            )
            return

        target_keys = ["retweet", "reply", "text", "image"] if t_key == "all" else [t_key]

        # 1. 更新本群 rule["account_type_overrides"]（支持本群对多个不同订阅账号分别保存独立开关）
        overrides_map = rule.setdefault("account_type_overrides", {})
        acct_ov = overrides_map.setdefault(acct.lower(), {})
        for tk in target_keys:
            if is_reset_default:
                acct_ov.pop(tk, None)
            else:
                acct_ov[tk] = str(parsed_mode)
        if not acct_ov:
            overrides_map.pop(acct.lower(), None)

        # 2. 同步更新本群子类面板 rule["account_switches"][acct]，与 WebUI 群聊卡片内的单账号独立面板保持一致
        mode_to_ui = {"direct": "直接推送", "push": "推送", "skip": "不推送"}
        sw = self._account_switch_panels(rule.get("account_switches"))
        sw = {key: value for key, value in sw.items() if not key.startswith("ov_")}
        if not isinstance(sw, dict):
            sw = {}
        curr_ov = overrides_map.get(acct.lower(), {})
        sw[acct] = {
            k_cfg: mode_to_ui.get(curr_ov.get(k_short, ""), "默认")
            for k_short, k_cfg in cfg_field_map.items()
        }
        rule["account_switches"] = sw
        self._save_plugin_config()

        pol = self._get_account_type_policy(acct, rule)
        srcs = pol.get("sources", {})
        modes = pol.get("modes", {})
        yield event.plain_result(
            f"✅ 已更新账号 @{acct} 在本群【{rule.get('group_name')}】的推文类型开关！\n"
            f"• 转贴 (retweet): {mode_desc.get(modes.get('retweet', 'skip'))} （{srcs['retweet']}）\n"
            f"• 回复 (reply): {mode_desc.get(modes.get('reply', 'skip'))} （{srcs['reply']}）\n"
            f"• 纯文字 (text): {mode_desc.get(modes.get('text', 'push'))} （{srcs['text']}）\n"
            f"• 图片 (image): {mode_desc.get(modes.get('image', 'push'))} （{srcs['image']}）"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("check")
    async def tw_check(self, event: AstrMessageEvent):
        """立即手动检查当前群聊订阅账号的新推文并推送"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=False)
        if rule is None:
            yield event.plain_result("当前群聊未绑定订阅配置，请先使用 `/tw sub` 绑定本群。")
            return
        accounts = self._get_rule_accounts(rule)
        hashtags = self._get_rule_hashtags(rule)
        if not accounts and not hashtags:
            yield event.plain_result("当前群聊尚无订阅，请使用 /tw add <账号> 或 /tw tag_add <标签> 添加。")
            return
        yield event.plain_result(
            f"🔄 正在按本群【{rule.get('group_name')}】独立规则检查 {len(accounts)} 个账号、{len(hashtags)} 个标签的新推文，请稍候..."
        )
        stats = await self.check_all_accounts(manual=True, target_rule=rule)
        removed_list = stats.get("removed_accounts") or []
        removed_tip = (
            f"\n🗑️ 已自动移除不存在的推特 ID: {', '.join('@' + a for a in removed_list)}"
            if removed_list
            else ""
        )
        yield event.plain_result(
            f"✅ 本群检查完成！共拉取 {stats['fetched']} 条推文，发现 {stats['new']} 条新推文，通过本群规则筛选并推送 {stats['pushed']} 条。{removed_tip}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("test")
    async def tw_test(self, event: AstrMessageEvent, account: str = "", count: str = ""):
        """/tw test N 随机测试本群 N 个订阅；/tw test <账号> N 测试该账号 N 条推文。"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
        target_acct = account.strip()
        count_arg = count.strip()
        if not count_arg and re.fullmatch(r"[+-]?[0-9]+", target_acct):
            count_arg, target_acct = target_acct, ""
        try:
            limit = int(count_arg) if count_arg else int(self._get_setting("test_push_tweet_count", 3) or 3)
            if limit < 1:
                raise ValueError
        except (ValueError, TypeError):
            yield event.plain_result("⚠️ 条数必须为正整数。用法：`/tw test 3` 或 `/tw test <账号> 2`。")
            return
        target_acct = target_acct.lstrip("@")
        rule = self._find_or_create_group_rule(event, create_if_missing=False)
        if rule is None:
            yield event.plain_result("当前群聊未绑定订阅配置，请先使用 `/tw sub` 绑定本群。")
            return
        if not target_acct and not (self._get_rule_accounts(rule) or self._get_rule_hashtags(rule)):
            yield event.plain_result("当前群聊没有订阅账号或标签。请先添加订阅，或使用 `/tw test <账号> 2` 测试指定账号。")
            return
        scope = f"从账号 @{target_acct} 随机抽取 {limit} 条推文" if target_acct else f"随机选择本群最多 {limit} 个订阅，每个订阅随机抽取 1 条推文"
        waiting_tip = ""
        if self._lock.locked():
            waiting_tip = (
                "⏳ 后台扫描或其他推文任务正在运行，本次测试已排队，尚未开始抓取。"
                "当前抓取日志属于正在运行的任务，不代表本次测试范围；"
                "轮到本次测试时只抓取下面指定的订阅范围。\n"
            )
            logger.info(
                f"[TwitterRSS] 随机测试 群[{rule.get('group_name')}] 已排队："
                f"等待当前任务完成；本次将{scope}"
            )
        yield event.plain_result(
            f"{waiting_tip}🧪 测试范围：{scope}，按本群【{rule.get('group_name')}】规则筛选后推送，请稍候..."
        )
        stats = await self.test_push_for_group(group_rule=rule, limit=limit, target_account=target_acct)
        if stats["fetched"] == 0:
            removed = stats.get("removed_accounts", [])
            tip = f"已自动移除不存在的账号：{'、'.join(removed)}。" if removed else "请检查订阅源与网络配置。"
            yield event.plain_result(f"⚠️ 未获取到推文。{tip}")
            return
        shortage = f"\n• 本次仅抽取 {stats['sampled']} 条：订阅不足，或选中的订阅无可用推文；未扩大测试范围" if stats["sampled"] < limit else ""
        yield event.plain_result(
            f"✅ 本群【{rule.get('group_name')}】随机测试完成！\n"
            f"• 检查订阅数: {stats['subscriptions']} 个\n"
            f"• 随机抽取并评估: {stats['evaluated']} 条（合计最多 {limit} 条）\n"
            f"• 通过规则并推送: {stats['pushed']} 条\n"
            f"• 被筛选拦截: {stats['filtered']} 条\n"
            f"• 处理失败: {stats['failed']} 条{shortage}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("digest")
    async def tw_digest(self, event: AstrMessageEvent, date_arg: str = ""):
        """立即生成今日24小时要闻长图（并归档到本地），或传入日期（如 2026-10-14 / 昨天）调取指定日期的要闻"""
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        if date_arg.strip():
            async for res in self._handle_query_digest_by_date(event, rule, date_arg.strip()):
                yield res
            return

        yield event.plain_result(
            f"正在整理本群【{rule.get('group_name')}】过去 24 小时的推文并生成《今日要闻》长图，请稍候..."
        )
        ok, info = await self.run_daily_digest(target_rule=rule)
        if not ok:
            yield event.plain_result(f"⚠️ 无法生成每日新闻简报：{info}")

    @tw.command("news")
    async def tw_news(self, event: AstrMessageEvent, date_arg: str = ""):
        """调取本群指定日期的本地归档《今日要闻》长图（如 /tw news 2026-10-14 或 /tw news 昨天），不填日期则列出已归档日期"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        async for res in self._handle_query_digest_by_date(event, rule, date_arg.strip()):
            yield res

    @tw.command("history")
    async def tw_history(self, event: AstrMessageEvent, date_arg: str = ""):
        """调取本群指定日期的本地归档《今日要闻》长图（同 /tw news）"""
        rule = self._find_or_create_group_rule(event, create_if_missing=True)
        async for res in self._handle_query_digest_by_date(event, rule, date_arg.strip()):
            yield res

    async def _handle_query_digest_by_date(
        self, event: AstrMessageEvent, rule: dict[str, Any], date_arg: str
    ):
        umo = self._resolve_target_umo(rule.get("target_umo", "")) or event.unified_msg_origin
        group_bucket = self.digest_archive.get(umo, {})
        if not group_bucket:
            umo_tail = umo.split(":")[-1]
            for k_umo, b in self.digest_archive.items():
                if k_umo.endswith(umo_tail) and b:
                    group_bucket = b
                    break

        if not date_arg:
            if not group_bucket:
                yield event.plain_result(
                    f"📂 本群【{rule.get('group_name')}】本地暂无已归档的历史《今日要闻》。\n"
                    f"每日定时生成或发送 `/tw digest` 生成后会自动保存在本地。"
                )
                return
            sorted_dates = sorted(group_bucket.keys(), reverse=True)
            lines = [f"📅 本群【{rule.get('group_name')}】已保存在本地的《今日要闻》归档（共 {len(sorted_dates)} 期）："]
            for d_key in sorted_dates[:20]:
                rec = group_bucket[d_key]
                lines.append(f"• {d_key}（精选 {rec.get('item_count', 0)} 条，生成于 {rec.get('created_at', '')}）")
            lines.append("\n💡 发送 `/tw news <日期>`（如 `/tw news 2026-10-14`、`/tw news 10-14` 或 `/tw news 昨天`）即可调取对应日期的要闻长图。")
            yield event.plain_result("\n".join(lines))
            return

        target_date = self._parse_query_date(date_arg)
        if not target_date:
            yield event.plain_result(
                f"⚠️ 日期格式无法识别：{date_arg}\n"
                f"支持格式示例：`2026-10-14`、`10-14`、`20261014`、`今天`、`昨天`、`前天`。"
            )
            return

        ok, img_path = await self._get_or_rerender_archived_digest(umo, target_date)
        if not ok or not img_path:
            avail = sorted(group_bucket.keys(), reverse=True)[:10]
            avail_tip = f"\n本群当前可调取的归档日期：{', '.join(avail)}" if avail else "\n本群本地暂无任何归档记录。"
            yield event.plain_result(
                f"⚠️ 未找到本群在 【{target_date}】 的本地《今日要闻》归档记录。{avail_tip}"
            )
            return

        yield event.chain_result([self._make_image_comp(img_path)])

    @filter.permission_type(filter.PermissionType.ADMIN)
    @tw.command("clear")
    async def tw_clear(self, event: AstrMessageEvent, scope: str = "cache"):
        """
        清除本地缓存指令：
        - /tw clear : 清理本地推文缓存 (history_tweets.json) 与图片缓存 (img_cache/)，保留日报归档与已读记录
        - /tw clear archive : 清理本地保存的历史《今日要闻》日报归档
        - /tw clear all : 清理全部本地缓存（含推文缓存、图片缓存、历史日报归档与已读记录）
        """
        if not self._has_admin_permission(event):
            yield event.plain_result("⚠️ 权限不足：该指令仅限群聊管理员或机器人管理员使用。")
            return
        res = await self._clear_local_cache(scope=scope)
        sc = res["scope"]
        if sc in ("archive", "digest"):
            yield event.plain_result(
                f"🗑️ 已清除本地《今日要闻》历史归档！\n"
                f"• 移除归档期数: {res['cleared_archives']} 期\n"
                f"• 清理文件数: {res['removed_files']} 个（释放空间 {res['freed_mb']} MB）"
            )
        elif sc == "all":
            yield event.plain_result(
                f"🗑️ 已彻底清空插件全部本地缓存！\n"
                f"• 清除缓存推文: {res['cleared_tweets']} 条\n"
                f"• 清除日报归档: {res['cleared_archives']} 期\n"
                f"• 清理图片与归档文件: {res['removed_files']} 个（释放空间 {res['freed_mb']} MB）\n"
                f"• 已读状态记录 (seen_ids) 已重置"
            )
        else:
            yield event.plain_result(
                f"🗑️ 已清除本地推文与图片缓存！\n"
                f"• 清除本地缓存推文: {res['cleared_tweets']} 条\n"
                f"• 清理本地缓存图片: {res['removed_files']} 个（释放空间 {res['freed_mb']} MB）\n"
                f"💡 历史《今日要闻》日报归档与订阅配置已保留（如需连同历史日报归档一并清空，可发送 `/tw clear all` 或 `/tw clear archive`）。"
            )
