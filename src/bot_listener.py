"""
Telegram 手機雙向互動監聽與定時推播守護服務 (方案一 + 方案四並行)
支援在手機 Telegram 上透過指令或快捷按鈕隨時查詢今日情報、監控網站、排程時間，
同時在背景依指定排程時間自動執行主動推播。
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
    BOT_TOKEN, CHAT_ID, TELEGRAM_API_BASE,
    send_message, check_credentials
)
from src.scraper import load_sites, load_settings
from src.agent_workflow import get_pending_today_articles, push_summarized_cards_to_telegram
from src.scheduler_service import run_check_and_notify, write_push_log


def get_telegram_updates(offset=None, timeout=30):
    """長輪詢 Telegram 訊息 (Long Polling)"""
    url = f"{TELEGRAM_API_BASE}/getUpdates"
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


def send_reply_with_keyboard(chat_id: str, text: str):
    """發送附帶底部快捷按鈕的訊息至手機 Telegram"""
    url = f"{TELEGRAM_API_BASE}/sendMessage"
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
        print(f"[Listener Error] 發送回覆失敗: {e}", file=sys.stderr)


def handle_today_request():
    """處理 /today 或點擊獲取今日情報"""
    send_message("⏳ <b>正在為您檢索今日 8 大站點最新文章並進行繁中摘要...</b>\n請稍候 3~5 秒。")
    today_str, pending_articles = get_pending_today_articles()

    if not pending_articles:
        send_message(
            f"📅 <b>【今日情報】{today_str}</b>\n\n"
            "目前監控的 8 個站點中，今天暫無尚未推播的新發布文章。\n"
            "（若剛發布過，系統已自動去重保護；有新發文時會立即推播！）"
        )
        return

    # 由系統生成條列摘要並推播
    cards = []
    for item in pending_articles:
        title = item.get("title", "")
        site_name = item.get("site_name", "")
        link = item.get("link", "")
        time_str = item.get("time_str", "")
        raw_summary = item.get("summary", "")

        # 整理為乾淨條列
        bullets = []
        if raw_summary and raw_summary != "（暫無摘要）":
            bullets.append(f"核心重點：{raw_summary}")
        else:
            bullets.append("點擊下方全文連結即可直接閱讀完整內容。")

        cards.append({
            "title": title,
            "site_name": site_name,
            "link": link,
            "time_str": time_str,
            "bullets": bullets
        })

    push_summarized_cards_to_telegram(today_str, cards)


def handle_sites_request():
    """處理 /sites 或查看監控網站"""
    sites = load_sites()
    lines = ["📋 <b>【目前監控中的 8 大精選站點】</b>", "─────────────────"]
    for idx, s in enumerate(sites, 1):
        status = "✅ 啟用" if s.get("enabled", True) else "⛔ 停用"
        lines.append(f"{idx}. <b>{s.get('name')}</b> <code>[{status}]</code>")
        if s.get("description"):
            lines.append(f"   <i>{s.get('description')}</i>")
    lines.append("─────────────────")
    lines.append("💡 <i>如需新增或刪除站點，可直接在 AntiGravity 對話中吩咐我！</i>")
    send_message("\n".join(lines))


def handle_time_request():
    """處理 /time 或查看推播時間"""
    settings = load_settings()
    times = settings.get("schedule_times", [])
    lines = ["⏰ <b>【每日定時推播時間點】</b>", "─────────────────"]
    for idx, t in enumerate(times, 1):
        lines.append(f"  {idx}. 每日 <b>{t}</b>")
    lines.append(f"\n時區：<code>{settings.get('timezone', 'Asia/Taipei')}</code>")
    lines.append("─────────────────")
    lines.append("💡 <i>時間一到，系統將自動主動推播今日新消息！</i>")
    send_message("\n".join(lines))


def handle_help_request():
    """處理 /help 指南"""
    msg = (
        "🤖 <b>AntiGravity Telegram 情報秘書指南</b>\n"
        "─────────────────\n"
        "您可以在手機隨時點擊下方快捷按鈕或輸入指令：\n\n"
        "• <b>📰 獲取今日最新情報</b>：立即抓取並生成繁中重點摘要\n"
        "• <b>🔍 查看監控網站</b>：檢視目前訂閱的 8 個資訊來源\n"
        "• <b>⏰ 查看推播時間</b>：檢視每日定時推播時段\n"
        "• <b>/today</b>：手機快速抓取指令\n"
        "• <b>/sites</b>：查看站點指令\n\n"
        "<i>所有文章皆包含繁體中文摘要與原文全文超連結！</i>"
    )
    send_message(msg)


def run_scheduler_thread():
    """在背景執行緒中運行指定時間定時排程 (方案一)"""
    settings = load_settings()
    schedule_times = settings.get("schedule_times", ["08:00", "12:00", "18:00"])
    for t in schedule_times:
        schedule.every().day.at(t).do(run_check_and_notify)

    while True:
        schedule.run_pending()
        time.sleep(15)


def start_bot_listener():
    """啟動手機雙向互動監聽與定時排程服務"""
    check_credentials()

    # 1. 啟動背景定時推播執行緒
    sched_thread = threading.Thread(target=run_scheduler_thread, daemon=True)
    sched_thread.start()

    print("==================================================", flush=True)
    print(" 🚀 AntiGravity Telegram 智能守護服務已啟動！", flush=True)
    print(" 📱 功能 1：手機 Telegram 指令互動（/today、/sites、底部快捷按鈕）", flush=True)
    print(" ⏰ 功能 2：每日指定時間主動推播（08:00, 12:00, 18:00）", flush=True)
    print(" 提示：按 Ctrl+C 可停止服務", flush=True)
    print("==================================================", flush=True)

    # 2. 發送上線與快捷按鈕歡迎訊息到手機
    send_reply_with_keyboard(
        CHAT_ID,
        "🟢 <b>AntiGravity Telegram 守護服務已上線！</b>\n\n"
        "• 每日將在指定時間為您自動推播\n"
        "• 您也可以隨時點選下方【快捷按鈕】主動獲取今日最新情報！"
    )

    offset = None
    while True:
        updates = get_telegram_updates(offset=offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue

            from_chat_id = str(message.get("chat", {}).get("id", ""))
            # 安全防護：僅回應您本人的 Chat ID
            if from_chat_id != str(CHAT_ID):
                continue

            text = message.get("text", "").strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 收到手機指令: {text}")

            if text in ["/start", "❓ 說明指南", "/help"]:
                handle_help_request()
            elif text in ["/today", "/news", "📰 獲取今日最新情報"]:
                handle_today_request()
            elif text in ["/sites", "🔍 查看監控網站"]:
                handle_sites_request()
            elif text in ["/time", "⏰ 查看推播時間"]:
                handle_time_request()
            else:
                send_message("💡 收到您的訊息！您可以直接點擊下方按鈕或輸入 <code>/today</code> 獲取今日最新情報。")

        time.sleep(1)


if __name__ == "__main__":
    start_bot_listener()
