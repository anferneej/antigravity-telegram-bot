import json
import time
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import schedule
import pytz

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
LOGS_DIR = ROOT_DIR / "logs"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
PUSH_LOG_FILE = LOGS_DIR / "push.log"

def write_push_log(message: str):
    """將推播事件與訊息內容記錄至 logs/push.log"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(PUSH_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

from .scraper import fetch_today_news, load_settings
from .telegram_notifier import send_message


def save_settings(settings):
    """保存設定檔"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def add_schedule_time(time_str: str):
    """新增指定排程時間 (格式 HH:MM)"""
    # 格式驗證
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        formatted_time = f"{h:02d}:{m:02d}"
    except Exception:
        return False, f"時間格式錯誤：請使用 24 小時制 'HH:MM'（例如 09:30 或 18:00），您輸入的是 '{time_str}'"

    settings = load_settings()
    times = settings.get("schedule_times", [])
    if formatted_time in times:
        return True, f"時間 {formatted_time} 已經存在於排程列表中！"

    times.append(formatted_time)
    times.sort()
    settings["schedule_times"] = times
    save_settings(settings)
    return True, f"已成功新增指定推送時間：{formatted_time}！目前排程列表：{', '.join(times)}"


def remove_schedule_time(time_str: str):
    """移除指定排程時間"""
    settings = load_settings()
    times = settings.get("schedule_times", [])
    formatted_time = time_str.strip()

    # 嘗試對齊補零
    if ":" in formatted_time:
        parts = formatted_time.split(":")
        try:
            formatted_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except Exception:
            pass

    if formatted_time not in times:
        return False, f"排程列表中找不到時間：{formatted_time}。目前清單為：{', '.join(times)}"

    times.remove(formatted_time)
    settings["schedule_times"] = times
    save_settings(settings)
    return True, f"已成功移除指定推送時間：{formatted_time}！目前剩餘排程：{', '.join(times) if times else '（目前無設定）'}"


def run_check_and_notify():
    """執行一次完整的今日情報抓取，並依 target_bot 分流推播至對應 Telegram Bot"""
    from src.agent_workflow import get_pending_today_articles, run_multi_bot_dispatch
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始執行目標站點今日消息抓取與多 Bot 分流...")
    today_str, pending_articles = get_pending_today_articles()
    success, msg = run_multi_bot_dispatch(today_str, pending_articles)
    return success, msg


def start_scheduler_daemon():
    """啟動多指定時間的常駐排程監聽器"""
    settings = load_settings()
    schedule_times = settings.get("schedule_times", ["09:00", "13:00", "18:30"])

    if not schedule_times:
        print("【警告】目前尚未設定任何指定推送時間！請先使用 --add-time 設定時間。", file=sys.stderr)
        return

    print("==================================================")
    print(" 🚀 AntiGravity Telegram 多時間定時推播服務已啟動")
    print(f" ⏰ 設定的每日檢查時間點（共 {len(schedule_times)} 次）：")
    for t in schedule_times:
        print(f"    - 每日 {t}")
    print(" 提示：按 Ctrl+C 可停止服務")
    print("==================================================")

    # 註冊每一個指定時間點
    for t in schedule_times:
        schedule.every().day.at(t).do(run_check_and_notify)

    while True:
        schedule.run_pending()
        time.sleep(15)  # 每 15 秒檢查一次排程隊列
