import json
import os
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import feedparser
from dateutil import parser as date_parser
import pytz

from .summarizer import summarize_article

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"

SITES_FILE = CONFIG_DIR / "sites.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


def load_settings():
    """載入設定檔"""
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "timezone": "Asia/Taipei",
        "schedule_times": ["09:00", "13:00", "18:30"],
        "max_items_per_site": 5,
        "request_timeout_seconds": 15
    }


def load_sites():
    """載入目標網站清單"""
    if SITES_FILE.exists():
        with open(SITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_history():
    """載入推播歷史紀錄以去重"""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"sent_links": {}}
    return {"sent_links": {}}


def save_history(history):
    """保存推播歷史紀錄"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_current_date_info(tz_name="Asia/Taipei"):
    """取得當前指定時區的日期物件與字串"""
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(tz)
    return now, now.strftime("%Y-%m-%d")


def is_published_today(entry_datetime, target_date):
    """比對新聞發布時間是否為今天"""
    if not entry_datetime:
        return False
    return entry_datetime.strftime("%Y-%m-%d") == target_date.strftime("%Y-%m-%d")


def parse_date_safely(date_input, target_tz):
    """將各類時間字串或 parsed_time 轉為本地時區 datetime"""
    if not date_input:
        return None
    try:
        if isinstance(date_input, (tuple, list)):  # time.struct_time
            dt = datetime(*date_input[:6], tzinfo=pytz.UTC)
            return dt.astimezone(target_tz)
        elif isinstance(date_input, str):
            dt = date_parser.parse(date_input)
            if dt.tzinfo is None:
                # 假設為當地時間
                dt = target_tz.localize(dt)
            else:
                dt = dt.astimezone(target_tz)
            return dt
    except Exception:
        return None
    return None


def scrape_rss(site, target_date, history_links, max_items, timeout, target_tz):
    """解析 RSS / Atom Feed"""
    url = site["url"]
    items = []
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.encoding = resp.apparent_encoding
        feed = feedparser.parse(resp.text)

        for entry in feed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue

            # 檢查是否已在歷史紀錄中
            if link in history_links:
                continue

            # 抓取發布時間
            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = parse_date_safely(entry.published_parsed, target_tz)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_date = parse_date_safely(entry.updated_parsed, target_tz)
            elif hasattr(entry, "published") and entry.published:
                pub_date = parse_date_safely(entry.published, target_tz)

            # 比對日期：如果明確解析出日期且不是今天，跳過
            if pub_date:
                if not is_published_today(pub_date, target_date):
                    continue
                time_str = pub_date.strftime("%H:%M")
            else:
                # 若無法解析具體日期，預設納入（但標記為今日更新）
                time_str = ""

            # 提取原始描述/內容以供摘要
            raw_desc = entry.get("summary", "") or entry.get("description", "")
            if not raw_desc and hasattr(entry, "content"):
                raw_desc = "".join([c.get("value", "") for c in entry.content])

            ai_summary = summarize_article(title, link, raw_desc)

            items.append({
                "title": title,
                "link": link,
                "time_str": time_str,
                "summary": ai_summary,
                "site_id": site.get("id", ""),
                "site_name": site.get("name", "未命名")
            })

            if len(items) >= max_items:
                break

    except Exception as e:
        print(f"[Scraper Error] RSS 抓取失敗 ({site.get('name')}): {e}", file=sys.stderr)

    return items


def scrape_html(site, target_date, history_links, max_items, timeout, target_tz):
    """解析一般 HTML 網頁列表（自訂或通用規則）"""
    url = site["url"]
    items = []
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        # 若使用者在 sites.json 指定了 CSS Selector
        item_selector = site.get("item_selector", "article, .post, .item, .news-item")
        title_selector = site.get("title_selector", "h1, h2, h3, a")
        link_selector = site.get("link_selector", "a")
        date_selector = site.get("date_selector", "time, .date, .time")

        elements = soup.select(item_selector)
        today_str = target_date.strftime("%Y-%m-%d")

        for el in elements:
            # 找連結
            a_tag = el.select_one(link_selector) if el.name != "a" else el
            if not a_tag or not a_tag.get("href"):
                continue

            link = urljoin(url, a_tag["href"].strip())
            if link in history_links:
                continue

            # 找標題
            t_tag = el.select_one(title_selector) if title_selector else a_tag
            title = t_tag.get_text(strip=True) if t_tag else a_tag.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            # 找時間
            time_str = ""
            if date_selector:
                d_tag = el.select_one(date_selector)
                if d_tag:
                    raw_time = d_tag.get_text(strip=True)
                    # 簡易比對是否有今日字眼或今天日期
                    if today_str not in raw_time and "今日" not in raw_time and "小時前" not in raw_time and "分鐘前" not in raw_time:
                        continue
                    time_str = raw_time[:16]

            ai_summary = summarize_article(title, link, "")

            items.append({
                "title": title,
                "link": link,
                "time_str": time_str,
                "summary": ai_summary,
                "site_id": site.get("id", ""),
                "site_name": site.get("name", "未命名")
            })

            if len(items) >= max_items:
                break

    except Exception as e:
        print(f"[Scraper Error] HTML 抓取失敗 ({site.get('name')}): {e}", file=sys.stderr)

    return items


def fetch_today_news():
    """
    主要抓取流程：
    1. 讀取所有啟用站點
    2. 過濾今日新消息與排除已發送記錄
    3. 返回結構化的站點消息字典與總新訊息清單
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

    results_by_site = {}
    new_sent_items = []

    for site in sites:
        if not site.get("enabled", True):
            continue

        site_type = site.get("type", "rss").lower()
        site_name = site.get("name", "未命名")

        if site_type == "rss":
            items = scrape_rss(site, now, sent_links, max_items, timeout, target_tz)
        else:
            items = scrape_html(site, now, sent_links, max_items, timeout, target_tz)

        if items:
            results_by_site[site_name] = items
            for item in items:
                sent_links[item["link"]] = {
                    "title": item["title"],
                    "sent_at": now.strftime("%Y-%m-%d %H:%M:%S")
                }
                new_sent_items.append(item)

    # 若有新消息發布，更新歷史紀錄
    if new_sent_items:
        history["sent_links"] = sent_links
        save_history(history)

    return today_str, results_by_site, new_sent_items
