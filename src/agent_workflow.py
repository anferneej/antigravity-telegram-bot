"""
AntiGravity 多 Bot 頻道智慧情報擷取、繁中專業摘要與分流推播工作流
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper import (
    load_sites, load_settings, load_history, save_history,
    scrape_rss, scrape_html, get_current_date_info, HISTORY_FILE
)
from src.telegram_notifier import (
    send_message, format_channel_news_message,
    load_bots_definition, check_credentials
)
from src.scheduler_service import write_push_log
import pytz


def get_pending_today_articles():
    """
    抓取今日所有監控站點中尚未推播的文章（包含全文摘要與 target_bot 分流標籤）
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
        target_bot = site.get("target_bot", "default")

        if site_type == "rss":
            items = scrape_rss(site, now, sent_links, max_items, timeout, target_tz)
        else:
            items = scrape_html(site, now, sent_links, max_items, timeout, target_tz)

        for item in items:
            item["target_bot"] = target_bot
            pending_articles.append(item)

    return today_str, pending_articles


def run_multi_bot_dispatch(today_str: str, articles: list):
    """
    依據 target_bot 將今日情報分流至不同的 Telegram Bot 頻道發送，
    並自動完成繁中排版、多目標廣播與去重保存。
    """
    if not articles:
        msg = f"[{today_str}] 檢查完成：目前沒有符合條件的新文章需推播。"
        print(msg)
        write_push_log(msg)
        return False, "無新消息"

    history = load_history()
    sent_links = history.get("sent_links", {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bots_def = load_bots_definition()

    # 1. 依 target_bot 頻道分組
    articles_by_channel = {}
    for a in articles:
        ch = a.get("target_bot", "default")
        articles_by_channel.setdefault(ch, []).append(a)

    total_pushed = 0
    pushed_details = []

    # 2. 逐一頻道發送至對應 Bot
    for channel_id, channel_items in articles_by_channel.items():
        channel_info = bots_def.get(channel_id, bots_def.get("default", {}))
        channel_name = channel_info.get("name", channel_id)

        # 整理為 {site_name: [items]}
        news_by_site = {}
        for it in channel_items:
            s_name = it.get("site_name", "精選資訊")
            news_by_site.setdefault(s_name, []).append(it)

        # 格式化訊息並推播至該頻道的 Bot
        msg_html = format_channel_news_message(channel_name, today_str, news_by_site)
        success = send_message(msg_html, channel=channel_id)

        if success:
            total_pushed += len(channel_items)
            pushed_details.append(f"【{channel_name}】：{len(channel_items)} 則")
            for it in channel_items:
                sent_links[it["link"]] = {
                    "title": it.get("title"),
                    "site_name": it.get("site_name"),
                    "target_bot": channel_id,
                    "sent_at": now_str
                }
        else:
            print(f"[Dispatch Warning] 頻道【{channel_name}】推播發生異常！", file=sys.stderr)

    if total_pushed > 0:
        history["sent_links"] = sent_links
        save_history(history)
        result_msg = f"🎉 成功分流推播共 {total_pushed} 篇情報至對應 Bot（{'，'.join(pushed_details)}）！"
        print(result_msg)
        write_push_log(result_msg)
        return True, result_msg
    else:
        err = "⚠️ 推送至 Telegram 失敗，請檢查網路連線或 Token。"
        print(err, file=sys.stderr)
        write_push_log(err)
        return False, err
