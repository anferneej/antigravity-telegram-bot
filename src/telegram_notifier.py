import os
import sys
import html
import requests
from pathlib import Path
from dotenv import load_dotenv

# 載入 .env
ENV_PATH = Path(__file__).resolve().parent.parent / "config" / ".env"
load_dotenv(dotenv_path=ENV_PATH)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def check_credentials():
    """檢查是否已設定 Token 與 Chat ID"""
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError(
            "【錯誤】尚未在 config/.env 中填入 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID！\n"
            "請先編輯 config/.env 填入您的 Telegram 機器人資訊。"
        )


def test_connection():
    """測試與 Telegram Bot 的連線並發送測試訊息"""
    check_credentials()
    url = f"{TELEGRAM_API_BASE}/getMe"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            return False, f"驗證 Bot Token 失敗: {data.get('description', '未知錯誤')}"

        bot_name = data["result"].get("first_name", "Bot")
        bot_username = data["result"].get("username", "Unknown")

        # 嘗試發送測試訊息至 CHAT_ID
        send_url = f"{TELEGRAM_API_BASE}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": f"🎉 <b>AntiGravity Telegram 連線成功！</b>\n機器人：@{bot_username}\n時鐘：連線與推播功能運作正常。",
            "parse_mode": "HTML"
        }
        send_resp = requests.post(send_url, json=payload, timeout=10)
        send_data = send_resp.json()

        if not send_data.get("ok"):
            return False, f"Bot Token 正確，但發送訊息至 Chat ID ({CHAT_ID}) 失敗: {send_data.get('description')}"

        return True, f"連線測試成功！已發送測試訊息至 Chat ID ({CHAT_ID})，機器人為 @{bot_username}"

    except Exception as e:
        return False, f"網路請求發生異常: {str(e)}"


def send_message(html_content: str):
    """
    發送 HTML 格式的訊息至 Telegram。
    如果長度超過 4000 字元，會自動拆分為多則發送。
    """
    check_credentials()
    send_url = f"{TELEGRAM_API_BASE}/sendMessage"
    max_len = 3800  # 安全上限，避開 4096 邊界

    # 拆分訊息（若有需要）
    chunks = []
    if len(html_content) <= max_len:
        chunks.append(html_content)
    else:
        # 按行分割以保留 HTML 標籤完整性
        lines = html_content.split("\n")
        current_chunk = ""
        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_len:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk = f"{current_chunk}\n{line}" if current_chunk else line
        if current_chunk:
            chunks.append(current_chunk)

    success_count = 0
    for idx, chunk in enumerate(chunks, 1):
        payload = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        try:
            resp = requests.post(send_url, json=payload, timeout=15)
            data = resp.json()
            if data.get("ok"):
                success_count += 1
            else:
                print(f"[Telegram Error] 第 {idx} 段發送失敗: {data.get('description')}", file=sys.stderr)
        except Exception as e:
            print(f"[Telegram Network Error] 發送異常: {e}", file=sys.stderr)

    return success_count == len(chunks)


def format_daily_news_message(date_str: str, news_by_site: dict) -> str:
    """
    將各站點抓取到的今日情報排版成漂亮的 Telegram HTML 格式，包含 AI 摘要與全文連結。
    """
    total_news = sum(len(items) for items in news_by_site.values())
    if total_news == 0:
        return f"📅 <b>【今日情報推播】{date_str}</b>\n\n本日目前尚無符合條件的新更新消息。"

    lines = [
        f"🗞️ <b>【今日情報推播】{date_str}</b>",
        f"<i>共為您整理並摘要 {total_news} 則最新精選情報：</i>",
        "─────────────────"
    ]

    for site_name, items in news_by_site.items():
        if not items:
            continue
        lines.append(f"\n🏷️ <b>【{html.escape(site_name)}】</b> ({len(items)} 則)")

        for idx, item in enumerate(items, 1):
            title = html.escape(item.get("title", "無標題"))
            link = item.get("link", "#")
            pub_time = item.get("time_str", "")
            time_tag = f" <code>[{pub_time}]</code>" if pub_time else ""
            summary = html.escape(item.get("summary", "（暫無摘要）"))

            card = [
                f"\n<b>{idx}. {title}</b>{time_tag}",
                f"💡 <b>AI 摘要：</b> {summary}",
                f"🔗 <a href=\"{link}\">點此閱讀全文 ↗</a>"
            ]
            lines.append("\n".join(card))

    lines.append("\n─────────────────")
    lines.append("🤖 <i>來自 AntiGravity AI 智能推播系統</i>")
    return "\n".join(lines)
