import argparse
import json
import sys
from pathlib import Path

# 確保 Windows 終端能正常印出 UTF-8 與 Emoji
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 將當前檔案所在目錄的父目錄加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.telegram_notifier import test_connection
from src.scheduler_service import (
    run_check_and_notify,
    start_scheduler_daemon,
    add_schedule_time,
    remove_schedule_time
)
from src.scraper import load_settings, load_sites, DATA_DIR, HISTORY_FILE


def cmd_list_sites():
    """列出目前監控的所有網站及其歸屬 Bot"""
    sites = load_sites()
    print("\n📋 【目前監控的目標網站清單】")
    print("──────────────────────────────────────────────────")
    if not sites:
        print("（目前 sites.json 中沒有任何站點）")
        return
    for idx, s in enumerate(sites, 1):
        status = "✅ 啟用中" if s.get("enabled", True) else "⛔ 已停用"
        bot_tag = f" -> 🤖 頻道: {s.get('target_bot', 'default')}"
        print(f"{idx}. [{status}] {s.get('name')} ({s.get('type', 'rss').upper()}){bot_tag}")
        print(f"   網址: {s.get('url')}")
        if s.get("description"):
            print(f"   說明: {s.get('description')}")
    print("──────────────────────────────────────────────────\n")


def cmd_list_bots():
    """列出所有 Telegram Bot 頻道與連線配置狀態"""
    from src.telegram_notifier import load_bots_definition, get_bot_credentials
    bots_def = load_bots_definition()
    print("\n🤖 【Telegram Bot 頻道配置狀態】")
    print("──────────────────────────────────────────────────")
    for b_id, b_info in bots_def.items():
        token, chat_ids, name = get_bot_credentials(b_id)
        token_mask = f"{token[:8]}...{token[-4:]}" if token and len(token) > 12 else "（未設定）"
        target_display = ", ".join(chat_ids) if chat_ids else "（未設定）"
        print(f"• 頻道 ID: [{b_id}] ｜ 名稱: {name}")
        print(f"  Token: {token_mask}")
        print(f"  目標 Chat ID: {target_display}")
        print(f"  說明: {b_info.get('description', '')}\n")
    print("──────────────────────────────────────────────────\n")


def cmd_list_times():
    """列出目前的排程時間"""
    settings = load_settings()
    times = settings.get("schedule_times", [])
    print("\n⏰ 【目前設定的每日推播時間點】")
    print("──────────────────────────────────────────────────")
    if not times:
        print("（目前尚未設定任何推送時間，請用 --add-time HH:MM 加入）")
    else:
        for idx, t in enumerate(times, 1):
            print(f"  {idx}. 每日 {t}")
    print(f"時區：{settings.get('timezone', 'Asia/Taipei')}")
    print("──────────────────────────────────────────────────\n")


def cmd_clear_history():
    """清空歷史紀錄以重新測試"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"sent_links": {}}, f, ensure_ascii=False, indent=2)
    print("🧹 已清空推播歷史紀錄 (history.json)，下次抓取將重新視為新文章。")


def cmd_show_log(lines_count=20):
    """顯示最近推播日誌"""
    from src.scheduler_service import PUSH_LOG_FILE
    print("\n📜 【最近定期推播執行日誌】")
    print("──────────────────────────────────────────────────")
    if not PUSH_LOG_FILE.exists():
        print("（目前尚無推播日誌）")
    else:
        with open(PUSH_LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines_count:] if len(all_lines) > lines_count else all_lines
            for line in recent:
                print(line, end="")
    print("──────────────────────────────────────────────────\n")


def cmd_manage_windows_scheduler(action="install"):
    """調用 PowerShell 腳本註冊或移除 Windows 排程"""
    import subprocess
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "setup_scheduler.ps1"
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), "-Action", action]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="cp950", errors="replace")
        print(res.stdout)
        if res.stderr:
            print(res.stderr, file=sys.stderr)
    except Exception as e:
        print(f"執行排程設定失敗: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="AntiGravity Telegram 今日情報抓取與多時間排程推播系統"
    )
    parser.add_argument("--test-tg", type=str, nargs="?", const="all", help="測試 Telegram 機器人連線（可指定頻道如 finance, reading, tech 或 all）")
    parser.add_argument("--list-bots", action="store_true", help="檢視所有 Telegram Bot 頻道與設定狀態")
    parser.add_argument("--once", action="store_true", help="立即執行一次抓取並推播今日新消息")
    parser.add_argument("--daemon", action="store_true", help="啟動多時間點背景定時監聽服務")
    parser.add_argument("--list-times", action="store_true", help="檢視目前設定的所有指定推播時間")
    parser.add_argument("--add-time", type=str, help="新增指定推播時間（24小時制，如 16:30）")
    parser.add_argument("--remove-time", type=str, help="移除指定推播時間（如 16:30）")
    parser.add_argument("--list-sites", action="store_true", help="檢視目標網站清單")
    parser.add_argument("--listen", action="store_true", help="啟動手機雙向互動監聽 + 背景定時排程守護服務")
    parser.add_argument("--clear-history", action="store_true", help="清空去重紀錄")
    parser.add_argument("--show-log", action="store_true", help="檢視最近推播日誌")
    parser.add_argument("--install-scheduler", action="store_true", help="將指定時間自動註冊為 Windows 原生工作排程")
    parser.add_argument("--uninstall-scheduler", action="store_true", help="移除 Windows 上的定時排程")

    parser.add_argument("--resolve-yt", type=str, help="解析 YouTube 頻道網址或 handle 為官方 RSS Feed")
    parser.add_argument("--add-yt", type=str, help="自動解析 YouTube 網址並加入監控清單（預設推播至 default Bot）")
    parser.add_argument("--name", type=str, help="搭配 --add-yt 指定自訂頻道名稱（選填）")

    args = parser.parse_args()

    if args.resolve_yt:
        from src.youtube_helper import resolve_youtube_channel
        res = resolve_youtube_channel(args.resolve_yt)
        if res:
            print("\n✅ 【YouTube 頻道 RSS 解析成功】")
            print("──────────────────────────────────────────────────")
            print(f"頻道名稱: {res['channel_name']}")
            print(f"頻道 ID  : {res['channel_id']}")
            print(f"官方 RSS : {res['feed_url']}")
            print(f"原始網址: {res['original_url']}")
            print("──────────────────────────────────────────────────\n")
        else:
            print(f"❌ 無法解析 YouTube 網址：{args.resolve_yt}")
    elif args.add_yt:
        from src.youtube_helper import add_youtube_channel_to_sites
        res = add_youtube_channel_to_sites(args.add_yt, args.name)
        if res["success"]:
            site = res["site"]
            print(f"\n🎉 成功加入 YouTube 頻道監控！")
            print("──────────────────────────────────────────────────")
            print(f"名稱    : {site['name']}")
            print(f"頻道 ID : {site['id']}")
            print(f"RSS 網址: {site['url']}")
            print(f"推播 Bot: {site['target_bot']} (@Anf_home_bot)")
            print("──────────────────────────────────────────────────\n")
        else:
            print(f"❌ 加入失敗: {res.get('error')}")
    elif args.list_bots:
        cmd_list_bots()
    elif args.test_tg is not None:
        from src.telegram_notifier import load_bots_definition
        target_ch = args.test_tg
        if target_ch == "all":
            bots_def = load_bots_definition()
            print("🚀 開始測試所有已設定的 Bot 頻道連線...")
            for ch in bots_def.keys():
                success, msg = test_connection(ch)
                print(f"[{'成功' if success else '失敗'}] {msg}")
        else:
            success, msg = test_connection(target_ch)
            print(f"[{'成功' if success else '失敗'}] {msg}")
    elif args.once:
        run_check_and_notify()
    elif args.listen or args.daemon:
        from src.bot_listener import start_bot_listener
        start_bot_listener()
    elif args.list_times:
        cmd_list_times()
    elif args.add_time:
        success, msg = add_schedule_time(args.add_time)
        print(msg)
    elif args.remove_time:
        success, msg = remove_schedule_time(args.remove_time)
        print(msg)
    elif args.list_sites:
        cmd_list_sites()
    elif args.clear_history:
        cmd_clear_history()
    elif args.show_log:
        cmd_show_log()
    elif args.install_scheduler:
        cmd_manage_windows_scheduler("install")
    elif args.uninstall_scheduler:
        cmd_manage_windows_scheduler("uninstall")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
