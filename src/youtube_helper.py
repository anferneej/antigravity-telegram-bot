"""
YouTube 頻道 RSS 自動解析與影片詳細深度分析模組
- 支援任意 YouTube 網址 (@handle, channel_id, watch url 等) 自動解析出官方 RSS
- 自動抓取影片字幕與資訊欄，使用 AI 深度提煉不限字數的詳細結構化重點
- 預設推播至 default Bot (@Anf_home_bot)
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

from .summarizer import (
    clean_html_tags,
    ensure_complete_sentence,
    filter_paywall_noise,
    translate_en_to_zh_tw,
    is_mostly_english
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
SITES_FILE = CONFIG_DIR / "sites.json"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}


def extract_video_id(url: str) -> Optional[str]:
    """從各類 YouTube 連結中提取 11 碼 video_id"""
    if not url:
        return None
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$"
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def resolve_youtube_channel(url_or_handle: str) -> Optional[Dict[str, str]]:
    """
    輸入任何 YouTube 網址或 handle，解析出 channel_id 與官方 RSS Feed URL
    支援格式：
    - @username
    - https://www.youtube.com/@username
    - https://www.youtube.com/channel/UCxxxxxxxxx
    - https://www.youtube.com/c/CustomName
    - https://www.youtube.com/watch?v=xxxxxxxxx (影片頁面)
    """
    raw = url_or_handle.strip()
    if not raw:
        return None

    # 1. 檢查是否直接含有 channel/UCxxxx
    m_direct = re.search(r"/channel/(UC[a-zA-Z0-9_-]{22})", raw)
    if m_direct:
        cid = m_direct.group(1)
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        return {
            "channel_id": cid,
            "channel_name": f"YouTube 頻道 ({cid[:8]})",
            "feed_url": feed_url,
            "original_url": f"https://www.youtube.com/channel/{cid}"
        }

    # 2. 規格化 URL
    target_url = raw
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        if target_url.startswith("@"):
            target_url = f"https://www.youtube.com/{target_url}"
        else:
            target_url = f"https://www.youtube.com/@{target_url}"

    try:
        resp = requests.get(target_url, headers=DEFAULT_HEADERS, timeout=12)
        resp.encoding = "utf-8"
        html = resp.text

        # 找 channelId
        cid = None
        cid_match = re.search(r'itemprop="channelId"\s+content="(UC[a-zA-Z0-9_-]{22})"', html)
        if cid_match:
            cid = cid_match.group(1)
        if not cid:
            cid_match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html)
            if cid_match:
                cid = cid_match.group(1)
        if not cid:
            cid_match = re.search(r'channel_id=(UC[a-zA-Z0-9_-]{22})', html)
            if cid_match:
                cid = cid_match.group(1)

        # 找頻道標題
        title = "YouTube 頻道"
        t_match = re.search(r'<meta property="og:title"\s+content="([^"]+)"', html)
        if t_match:
            title = t_match.group(1).replace(" - YouTube", "").strip()
        else:
            t_match2 = re.search(r'<title>([^-<]+) - YouTube</title>', html)
            if t_match2:
                title = t_match2.group(1).strip()

        if cid:
            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
            return {
                "channel_id": cid,
                "channel_name": title,
                "feed_url": feed_url,
                "original_url": target_url
            }

    except Exception as e:
        print(f"[YouTube Helper Error] 解析頻道網址失敗 ({raw}): {e}", file=sys.stderr)

    return None


def fetch_video_transcript(video_id: str) -> str:
    """
    抓取影片的字幕內容（優先繁中、簡中，其次英文）
    若有字幕，返回合併之文字文本
    """
    if not YouTubeTranscriptApi or not video_id:
        return ""

    try:
        api = YouTubeTranscriptApi()
        # 取得字幕列表
        transcript_list = api.list(video_id)
        
        # 優先尋找繁體中文、簡體中文
        preferred_langs = ["zh-TW", "zh-Hant", "zh-HK", "zh-Hans", "zh-CN", "zh", "en", "en-US"]
        transcript = None
        
        try:
            transcript = transcript_list.find_transcript(preferred_langs)
        except Exception:
            # 嘗試找任何可用的字幕（包含自動產生）
            for t in transcript_list:
                transcript = t
                break
                
        if transcript:
            fetched = transcript.fetch()
            # 組合出文本（限制長度避免超出 context）
            full_text = " ".join([snippet.text for snippet in fetched.snippets if snippet.text])
            return full_text[:4000]

    except Exception:
        # 字幕可能被作者停用或無字幕
        pass

    return ""


def analyze_youtube_video_detailed(title: str, url: str, description: str, max_bullets: int = 6) -> List[str]:
    """
    分析 YouTube 影片後做成詳細重點（字數不限，務求詳細）
    1. 嘗試提取影片字幕
    2. 結合標題、資訊欄與字幕，送交 AI 或本地深度分析引擎
    3. 產出詳細的條列重點與核心結論
    """
    video_id = extract_video_id(url)
    transcript_text = ""
    if video_id:
        transcript_text = fetch_video_transcript(video_id)

    # 組合影片完整素材
    combined_content = ""
    if transcript_text:
        combined_content += f"【影片字幕逐字摘錄】\n{transcript_text}\n\n"
    if description:
        clean_desc = clean_html_tags(description)
        clean_desc = filter_paywall_noise(clean_desc)
        combined_content += f"【影片資訊欄說明】\n{clean_desc}"

    if not combined_content.strip():
        combined_content = f"影片標題：{title}。請深入分析此標題傳遞之核心概念與技術重點。"

    is_english = is_mostly_english(title + " " + combined_content[:200])
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    # 1. 若有設定 GEMINI_API_KEY，進行全方位深度分析
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = (
                "你是一位資深的內容研究員與知識提煉專家。\n"
                "請針對以下這部 YouTube 影片的標題、資訊欄說明與逐字稿摘錄，進行全方位的專業深度分析。\n"
                "【使用者核心要求】：字數不限，但務必詳細、精準提煉影片重點、架構嚴謹。\n\n"
                "分析規格：\n"
                "1. 請產出 4 到 6 個結構化的深度重點，請以『• 』開頭。\n"
                "2. 第一點清楚說明這部影片的【核心主題與為觀眾解決的問題】。\n"
                "3. 中間幾點詳細展開【關鍵論點、實際案例、教學步驟或核心知識】，必須具體且有實質資訊量，禁止空洞寒暄。\n"
                "4. 針對關鍵細節（如數據、步驟、注意事項）進行補充說明。\n"
                "5. 最後一點給出【核心結論、延伸啟發或實務行動建議】。\n"
                "6. 一律使用專業繁體中文（台灣習慣用語），若是英文影片請完整在地化翻譯。\n"
                "7. 每個重點請以完整的標點符號結尾，切勿截斷。\n\n"
                f"【影片標題】：{title}\n"
                f"【影片內容素材】：{combined_content[:3800]}\n"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if response and response.text:
                lines = [line.strip().lstrip("•- 1234567890.、*") for line in response.text.strip().split("\n") if len(line.strip()) > 15]
                clean_bullets = [ensure_complete_sentence(l) for l in lines]
                if clean_bullets:
                    return clean_bullets[:max_bullets]
        except Exception as e:
            print(f"[YouTube Helper Warning] Gemini 調用未成 ({e})，使用本地高規格分析引擎", file=sys.stderr)

    # 2. 本地高規格備援分析引擎
    sentences = re.split(r"(?<=[。！？\n])", combined_content) if not is_english else re.split(r"(?<=[.!?\n])\s+", combined_content)
    clean_sentences = []
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) < 20:
            continue
        # 過濾雜訊與網址連結
        if any(noise in s_clean for noise in ["訂閱頻道", "按讚分享", "開啟小鈴鐺", "點擊下方連結", "Instagram", "Facebook", "e-mail", "email"]):
            continue
        # 移除行內網址
        s_clean = re.sub(r"https?://\S+", "", s_clean).strip()
        if len(s_clean) < 15:
            continue

        if is_english:
            translated = translate_en_to_zh_tw(s_clean)
            clean_sentences.append(ensure_complete_sentence(translated))
        else:
            clean_sentences.append(ensure_complete_sentence(s_clean))

        if len(clean_sentences) >= max_bullets:
            break

    if clean_sentences:
        # 第一點標註主旨
        clean_sentences[0] = f"【主題解析】{clean_sentences[0]}"
        return clean_sentences

    return [
        f"【核心主題】本影片探討《{title}》之核心觀點與知識要點。",
        "【詳細內容】完整逐字論述與精華教學，歡迎點擊上方影片連結直接觀看。"
    ]


def add_youtube_channel_to_sites(url_or_handle: str, custom_name: Optional[str] = None) -> Dict[str, Any]:
    """
    自動解析 YouTube 頻道並寫入 config/sites.json
    - target_bot 嚴格綁定為 "default"
    - type 為 "youtube"
    """
    info = resolve_youtube_channel(url_or_handle)
    if not info:
        return {"success": False, "error": f"無法從 '{url_or_handle}' 找到有效的 YouTube 頻道資訊"}

    channel_name = custom_name.strip() if custom_name else info["channel_name"]
    channel_id = info["channel_id"]
    feed_url = info["feed_url"]
    site_id = f"yt_{channel_id}"

    # 讀取現有 sites.json
    sites = []
    if SITES_FILE.exists():
        try:
            with open(SITES_FILE, "r", encoding="utf-8") as f:
                sites = json.load(f)
        except Exception:
            sites = []

    # 檢查是否已存在
    for s in sites:
        if s.get("id") == site_id or s.get("url") == feed_url:
            s["enabled"] = True
            s["name"] = channel_name
            s["target_bot"] = "default"
            s["type"] = "youtube"
            with open(SITES_FILE, "w", encoding="utf-8") as f:
                json.dump(sites, f, ensure_ascii=False, indent=2)
            return {
                "success": True,
                "action": "updated",
                "site": s
            }

    # 新增站點
    new_site = {
        "id": site_id,
        "name": f"🎬 {channel_name}",
        "url": feed_url,
        "original_url": info["original_url"],
        "type": "youtube",
        "target_bot": "default",
        "enabled": True,
        "description": f"YouTube 頻道《{channel_name}》最新發布影片深度重點分析"
    }
    sites.append(new_site)

    with open(SITES_FILE, "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "action": "added",
        "site": new_site
    }
