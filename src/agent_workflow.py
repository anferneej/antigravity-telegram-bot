"""
AntiGravity 原生驅動的智慧情報擷取、繁體中文深度摘要與 Telegram 推播流程
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# 將當前檔案所在目錄的父目錄加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scraper import (
    load_sites, load_settings, load_history, save_history,
    scrape_rss, scrape_html, get_current_date_info, HISTORY_FILE
)
from src.telegram_notifier import send_message, check_credentials, CHAT_ID
from src.scheduler_service import write_push_log
import pytz


def get_pending_today_articles():
    """
    抓取今日所有監控站點中尚未推播的文章（包含全文或主要內文），
    返回給 AntiGravity 進行深度繁體中文智能摘要。
    """
    settings = load_settings()
    sites = load_sites()
    history = load_history()
    sent_links = history.get("sent_links", {})

    tz_name = settings.get("timezone", "Asia/Taipei")
    try:
        target_tz = pytz.timezone(tz_name)
    except Exception:
        target_tz = pytz.timezone("Asia/Taipei")

    now, today_str = get_current_date_info(tz_name)
    max_items = settings.get("max_items_per_site", 5)
    timeout = settings.get("request_timeout_seconds", 15)

    pending_articles = []

    for site in sites:
        if not site.get("enabled", True):
            continue

        site_type = site.get("type", "rss").lower()
        if site_type == "rss":
            items = scrape_rss(site, now, sent_links, max_items, timeout, target_tz)
        else:
            items = scrape_html(site, now, sent_links, max_items, timeout, target_tz)

        for item in items:
            pending_articles.append(item)

    return today_str, pending_articles


def push_summarized_cards_to_telegram(today_str: str, cards: list):
    """
    將 AntiGravity 處理好的一目瞭然繁體中文卡片推播至 Telegram 並記錄去重與日誌。
    cards 格式:
    [
        {
            "title": "...",
            "site_name": "...",
            "link": "...",
            "time_str": "...",
            "bullets": ["重點1...", "重點2...", "重點3..."]
        }
    ]
    """
    check_credentials()
    if not cards:
        msg = f"[{today_str}] 檢查完成：目前沒有符合條件的新文章需推播。"
        print(msg)
        write_push_log(msg)
        return False, "無新消息"

    history = load_history()
    sent_links = history.get("sent_links", {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 組合 Telegram HTML
    lines = [
        f"🗞️ <b>【今日情報精華・AntiGravity 智能摘要】</b>",
        f"📅 <i>日期：{today_str} ｜ 共精選 {len(cards)} 篇重點情報</i>",
        "─────────────────────────"
    ]

    for idx, c in enumerate(cards, 1):
        title = c.get("title", "無標題")
        site = c.get("site_name", "來源站點")
        link = c.get("link", "#")
        time_tag = f" <code>[{c.get('time_str')}]</code>" if c.get('time_str') else ""
        bullets = c.get("bullets", [])

        card_text = [
            f"\n📌 <b>{idx}. {title}</b>{time_tag}",
            f"🏷️ 來源：<b>{site}</b>",
            "💡 <b>核心重點摘要（一目瞭然）：</b>"
        ]
        for b in bullets:
            clean_b = b.lstrip("•- 1234567890.、")
            card_text.append(f"  • {clean_b}")

        card_text.append(f"🔗 <a href=\"{link}\">點此閱讀全文 ↗</a>")
        lines.append("\n".join(card_text))

        # 標記為已發送
        sent_links[link] = {
            "title": title,
            "site_name": site,
            "sent_at": now_str
        }

    lines.append("\n─────────────────────────")
    lines.append("🤖 <i>來自 AntiGravity AI 深度摘要與推播</i>")

    full_html = "\n".join(lines)
    success = send_message(full_html)

    if success:
        history["sent_links"] = sent_links
        save_history(history)
        log_msg = f"🎉 成功推播 {len(cards)} 篇一目瞭然繁體中文摘要至 Telegram！"
        print(log_msg)
        write_push_log(log_msg)
        return True, log_msg
    else:
        err = "⚠️ 推送至 Telegram 失敗，請檢查網路連線或 Token。"
        print(err, file=sys.stderr)
        write_push_log(err)
        return False, err
