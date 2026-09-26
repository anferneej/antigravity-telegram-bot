"""
Telegram 多頻道 Bot 手機雙向互動監聽與定時推播守護服務
支援多個 Bot 分流監聽（財經、閱讀、科技、預設），在不同 Bot 點擊按鈕回傳對應分類情報，
同時在背景執行定時自動分流推播。
"""
import os
import sys
import time
import json
import threading
from datetime import datetime
from pathlib import Path
import requests
import schedule

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
LOGS_DIR = ROOT_DIR / "logs"

sys.path.insert(0, str(ROOT_DIR))

from src.telegram_notifier import (
    load_bots_definition, get_bot_credentials,
    send_message, check_credentials, format_channel_news_message
)
from src.scraper import load_sites, load_settings
from src.agent_workflow import get_pending_today_articles, run_multi_bot_dispatch
from src.scheduler_service import run_check_and_notify, write_push_log


def get_telegram_updates(api_base: str, offset=None, timeout=25):
    """長輪詢 Telegram 訊息"""
    url = f"{api_base}/getUpdates"
    params = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=timeout + 5)
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except Exception:
        pass
    return []


def send_reply_with_keyboard(api_base: str, chat_id: str, text: str, channel_id: str):
    """發送附帶底部快捷按鈕的訊息至手機 Telegram"""
    url = f"{api_base}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "keyboard": [
                [{"text": "📰 獲取今日最新情報"}, {"text": "🔍 查看監控網站"}],
                [{"text": "⏰ 查看推播時間"}, {"text": "❓ 說明指南"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[Listener Error] 發送按鈕失敗: {e}", file=sys.stderr)


def handle_today_request_for_channel(channel_id: str, channel_name: str):
    """處理特定頻道的 /today 請求"""
    send_message(f"⏳ <b>正在為您檢索【{channel_name}】今日最新情報與繁中摘要...</b>", channel=channel_id)
    today_str, pending_articles = get_pending_today_articles()

    # 若是特定專屬 Bot，只過濾該頻道的文章；若是 default 則顯示全部
    if channel_id != "default":
        filtered_articles = [a for a in pending_articles if a.get("target_bot") == channel_id]
    else:
        filtered_articles = pending_articles

    if not filtered_articles:
        send_message(
            f"📅 <b>【{channel_name}】{today_str}</b>\n\n"
            "目前該分類下，今天暫無尚未推播的新發布文章。\n"
            "（若剛發布過，系統已自動去重保護；有新發文時會立即推播！）",
            channel=channel_id
        )
        return

    # 按站點整理並發送
    news_by_site = {}
    for it in filtered_articles:
        s_name = it.get("site_name", "精選資訊")
        news_by_site.setdefault(s_name, []).append(it)

    msg_html = format_channel_news_message(channel_name, today_str, news_by_site)
    send_message(msg_html, channel=channel_id)


def handle_sites_request_for_channel(channel_id: str, channel_name: str):
    """處理 /sites 查看站點"""
    all_sites = load_sites()
    if channel_id != "default":
        sites = [s for s in all_sites if s.get("target_bot") == channel_id]
    else:
        sites = all_sites

    lines = [f"📋 <b>【{channel_name}・監控站點清單】</b>", "─────────────────"]
    for idx, s in enumerate(sites, 1):
        status = "✅ 啟用" if s.get("enabled", True) else "⛔ 停用"
        lines.append(f"{idx}. <b>{s.get('name')}</b> <code>[{status}]</code>")
        if s.get("description"):
            lines.append(f"   <i>{s.get('description')}</i>")
    lines.append("─────────────────")
    send_message("\n".join(lines), channel=channel_id)


def handle_time_request_for_channel(channel_id: str, channel_name: str):
    """處理 /time 檢視排程時間"""
    settings = load_settings()
    times = settings.get("schedule_times", [])
    lines = [f"⏰ <b>【{channel_name}・每日定時推播時間點】</b>", "─────────────────"]
    for idx, t in enumerate(times, 1):
        lines.append(f"  {idx}. 每日 <b>{t}</b>")
    lines.append(f"\n時區：<code>{settings.get('timezone', 'Asia/Taipei')}</code>")
    lines.append("─────────────────")
    lines.append("💡 <i>到達指定時間，系統將自動分流推播最新情報！</i>")
    send_message("\n".join(lines), channel=channel_id)


def run_single_bot_listener(channel_id: str, token: str, chat_ids: list, channel_name: str):
    """針對單一 Bot 運行長輪詢監聽執行緒"""
    api_base = f"https://api.telegram.org/bot{token}"

    # 發送歡迎與按鈕
    for cid in chat_ids:
        send_reply_with_keyboard(
            api_base, cid,
            f"🟢 <b>AntiGravity 【{channel_name}】守護服務已上線！</b>\n\n"
            f"• 每日將在指定時間定時推播本分類情報\n"
            f"• 隨時點選下方快捷按鈕獲取今日最新動態！",
            channel_id
        )

    offset = None
    while True:
        updates = get_telegram_updates(api_base, offset=offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue

            from_chat_id = str(message.get("chat", {}).get("id", ""))
            # 安全防護：僅回應在名單中的 chat_id
            if from_chat_id not in [str(c) for c in chat_ids]:
                continue

            text = message.get("text", "").strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}][{channel_name}] 收到指令: {text}", flush=True)

            if text in ["/start", "❓ 說明指南", "/help"]:
                msg = (
                    f"🤖 <b>【{channel_name}】操作指南</b>\n"
                    "─────────────────\n"
                    "• <b>📰 獲取今日最新情報</b>：立即抓取並提煉繁中重點摘要\n"
                    "• <b>🔍 查看監控網站</b>：檢視本頻道的資訊來源\n"
                    "• <b>⏰ 查看推播時間</b>：檢視每日定時推播時段\n"
                )
                send_message(msg, channel=channel_id)
            elif text in ["/today", "/news", "📰 獲取今日最新情報"]:
                handle_today_request_for_channel(channel_id, channel_name)
            elif text in ["/sites", "🔍 查看監控網站"]:
                handle_sites_request_for_channel(channel_id, channel_name)
            elif text in ["/time", "⏰ 查看推播時間"]:
                handle_time_request_for_channel(channel_id, channel_name)
            else:
                send_message("💡 收到您的訊息！可以直接點擊下方按鈕或輸入 <code>/today</code> 獲取最新情報。", channel=channel_id)

        time.sleep(1)


def run_scheduler_thread():
    """在背景執行緒中運行指定時間定時排程"""
    settings = load_settings()
    schedule_times = settings.get("schedule_times", ["08:00", "12:00", "18:00"])
    for t in schedule_times:
        schedule.every().day.at(t).do(run_check_and_notify)

    while True:
        schedule.run_pending()
        time.sleep(15)


def start_bot_listener():
    """啟動多頻道 Bot 雙向互動監聽與定時排程服務"""
    check_credentials()
    bots_def = load_bots_definition()

    # 1. 啟動背景定時推播執行緒
    sched_thread = threading.Thread(target=run_scheduler_thread, daemon=True)
    sched_thread.start()

    # 2. 盤點所有已設定的 Bot 頻道，避免重複監聽相同的 Token
    active_channels = {}
    tokens_seen = {}

    for ch_id, ch_info in bots_def.items():
        token, chat_ids, name = get_bot_credentials(ch_id)
        if token and chat_ids:
            if token not in tokens_seen:
                tokens_seen[token] = ch_id
                active_channels[ch_id] = (token, chat_ids, name)
            else:
                # 相同 token 共享監聽
                pass

    print("==================================================", flush=True)
    print(" 🚀 AntiGravity Telegram 多 Bot 分流守護服務已啟動！", flush=True)
    print(f" 🤖 活躍 Bot 頻道數：{len(active_channels)} 個", flush=True)
    for ch_id, (token, chat_ids, name) in active_channels.items():
        print(f"    - 【{name}】：監聽中（目標 Chat IDs: {', '.join(chat_ids)}）", flush=True)
    print(" ⏰ 每日定時推播排程已在背景同步守護（08:00, 12:00, 18:00）", flush=True)
    print(" 提示：按 Ctrl+C 可停止服務", flush=True)
    print("==================================================", flush=True)

    # 3. 為各個獨立 Bot 啟動監聽執行緒
    threads = []
    for ch_id, (token, chat_ids, name) in active_channels.items():
        t = threading.Thread(
            target=run_single_bot_listener,
            args=(ch_id, token, chat_ids, name),
            daemon=True
        )
        t.start()
        threads.append(t)

    # 主執行緒保持活躍
    while True:
        time.sleep(1)


if __name__ == "__main__":
    start_bot_listener()
