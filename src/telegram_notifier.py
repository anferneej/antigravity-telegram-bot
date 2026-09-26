import os
import sys
import html
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
ENV_PATH = CONFIG_DIR / ".env"
BOTS_CONFIG_FILE = CONFIG_DIR / "bots.json"

load_dotenv(dotenv_path=ENV_PATH)

DEFAULT_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def load_bots_definition():
    """載入 bots.json 定義"""
    if BOTS_CONFIG_FILE.exists():
        try:
            with open(BOTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "default": {
            "name": "綜合預設 Bot",
            "token_env": "TELEGRAM_BOT_TOKEN",
            "chat_id_env": "TELEGRAM_CHAT_ID"
        }
    }


def parse_chat_ids(raw_chat_id_str: str) -> list:
    """將可能以逗號分隔的 Chat ID 字串解析為列表，支援個人與群組 ID"""
    if not raw_chat_id_str:
        return []
    ids = []
    for item in raw_chat_id_str.split(","):
        cid = item.strip()
        if cid:
            ids.append(cid)
    return ids


def get_bot_credentials(channel: str = "default"):
    """
    取得指定頻道的 Telegram Bot Token 與目標 Chat ID 列表。
    若該頻道未單獨設定，則自動安全回退 (Fallback) 至預設 Bot。
    """
    bots_def = load_bots_definition()
    bot_info = bots_def.get(channel, bots_def.get("default", {}))

    token_var = bot_info.get("token_env", "TELEGRAM_BOT_TOKEN")
    chat_id_var = bot_info.get("chat_id_env", "TELEGRAM_CHAT_ID")

    token = os.getenv(token_var, "").strip()
    raw_chat_id = os.getenv(chat_id_var, "").strip()

    # 回退至預設 Bot
    if not token or not raw_chat_id:
        token = DEFAULT_BOT_TOKEN
        raw_chat_id = DEFAULT_CHAT_ID
        channel_name = f"{bot_info.get('name', channel)} (使用預設 Bot 轉發)"
    else:
        channel_name = bot_info.get("name", channel)

    chat_ids = parse_chat_ids(raw_chat_id)
    return token, chat_ids, channel_name


def check_credentials():
    """檢查預設憑證是否齊全"""
    if not DEFAULT_BOT_TOKEN or not DEFAULT_CHAT_ID:
        raise ValueError(
            "【錯誤】尚未在 config/.env 中填入 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID！\n"
            "請先編輯 config/.env 填入您的 Telegram 機器人資訊。"
        )


def send_message(html_content: str, channel: str = "default") -> bool:
    """
    發送 HTML 格式的訊息至指定頻道的 Telegram 機器人。
    支援廣播至多個 Chat ID（個人或群組），並自動處理超長內容分段。
    """
    token, chat_ids, channel_name = get_bot_credentials(channel)
    if not token or not chat_ids:
        print(f"[Telegram Error] 頻道 '{channel}' 尚未設定有效的 Bot Token 或 Chat ID！", file=sys.stderr)
        return False

    api_base = f"https://api.telegram.org/bot{token}"
    send_url = f"{api_base}/sendMessage"
    max_len = 3800  # 安全上限

    # 拆分訊息（避免超過 4096 字元）
    chunks = []
    if len(html_content) <= max_len:
        chunks.append(html_content)
    else:
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

    all_delivered = True
    for cid in chat_ids:
        for chunk in chunks:
            payload = {
                "chat_id": cid,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            try:
                resp = requests.post(send_url, json=payload, timeout=15)
                data = resp.json()
                if not data.get("ok"):
                    all_delivered = False
                    print(f"[Telegram Error] 推播至 Chat ID ({cid}) 失敗: {data.get('description')}", file=sys.stderr)
            except Exception as e:
                all_delivered = False
                print(f"[Telegram Network Error] 發送異常 ({cid}): {e}", file=sys.stderr)

    return all_delivered


def test_connection(channel: str = "default"):
    """測試指定頻道 Bot 的連線狀況"""
    token, chat_ids, channel_name = get_bot_credentials(channel)
    if not token or not chat_ids:
        return False, f"頻道 '{channel}' 未設定 Token 或 Chat ID"

    api_base = f"https://api.telegram.org/bot{token}"
    try:
        resp = requests.get(f"{api_base}/getMe", timeout=10)
        data = resp.json()
        if not data.get("ok"):
            return False, f"驗證 Bot 失敗: {data.get('description')}"

        bot_username = data["result"].get("username", "Unknown")
        target_display = ", ".join(chat_ids)

        send_url = f"{api_base}/sendMessage"
        payload = {
            "chat_id": chat_ids[0],
            "text": f"🎉 <b>AntiGravity 【{channel_name}】連線成功！</b>\n機器人：@{bot_username}\n目標端：{target_display}\n多頻道推播功能運作正常！",
            "parse_mode": "HTML"
        }
        send_resp = requests.post(send_url, json=payload, timeout=10)
        send_data = send_resp.json()

        if not send_data.get("ok"):
            return False, f"Bot Token 正確，但發送訊息至 Chat ID ({chat_ids[0]}) 失敗: {send_data.get('description')}"

        return True, f"【{channel_name}】連線測試成功！機器人為 @{bot_username}，已發送至 {target_display}"
    except Exception as e:
        return False, f"連線異常: {e}"


def format_channel_news_message(channel_name: str, date_str: str, news_by_site: dict) -> str:
    """
    將特定頻道抓取到的情報排版成漂亮的 Telegram HTML 格式。
    """
    total_news = sum(len(items) for items in news_by_site.values())
    if total_news == 0:
        return f"📅 <b>【{channel_name}・今日情報】{date_str}</b>\n\n本日目前尚無新發布情報。"

    lines = [
        f"🗞️ <b>【{channel_name}・今日情報精華】</b>",
        f"📅 <i>日期：{date_str} ｜ 共精選 {total_news} 則最新情報</i>",
        "─────────────────────────"
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
            bullets = item.get("bullets", [])

            card_text = [f"\n<b>{idx}. {title}</b>{time_tag}"]
            if bullets:
                card_text.append("💡 <b>AI 核心重點摘要：</b>")
                for b in bullets:
                    card_text.append(f"  • {html.escape(b)}")
            else:
                summary = item.get("summary", "點擊全文閱讀詳細內容。")
                card_text.append(f"💡 <b>摘要：</b> {html.escape(summary)}")

            card_text.append(f"🔗 <a href=\"{link}\">點此閱讀全文 ↗</a>")
            lines.append("\n".join(card_text))

    lines.append("\n─────────────────────────")
    lines.append("🤖 <i>來自 AntiGravity 智慧情報分流系統</i>")
    return "\n".join(lines)
