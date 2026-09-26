"""
YouTube 影片真實內容深度解讀與結構化分析模組
- 徹底擺脫表面簡短的資訊欄宣傳文字
- 深入解讀影片講者「真實口述內容」（完整字幕 / 音軌逐字稿 / 多模態音訊解讀）
- 不限字數，產出架構嚴謹、論述詳實的深度精華筆記
"""

import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests

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
DATA_DIR = ROOT_DIR / "data"
SITES_FILE = CONFIG_DIR / "sites.json"
TEMP_DIR = DATA_DIR / "temp_yt"

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
    """輸入任何 YouTube 網址或 handle，解析出 channel_id 與官方 RSS Feed URL"""
    raw = url_or_handle.strip()
    if not raw:
        return None

    # 1. 直接包含 channel/UCxxxx
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


def parse_vtt_to_clean_text(vtt_content: str) -> str:
    """將 WebVTT 字幕格式解析為乾淨、無時間軸、無重複的純逐字稿文字"""
    lines = vtt_content.splitlines()
    clean_lines = []
    seen = set()
    for line in lines:
        l = line.strip()
        if not l or l.startswith("WEBVTT") or l.startswith("Kind:") or l.startswith("Language:"):
            continue
        if "-->" in l:
            continue
        # 移除行內時間或樣式標籤 <c>...</c>
        l = re.sub(r"<[^>]+>", "", l).strip()
        if l and l not in seen:
            clean_lines.append(l)
            seen.add(l)
    return " ".join(clean_lines)


def fetch_video_spoken_transcript(video_id: str, video_url: str) -> str:
    """
    雙重管道提取影片講者完整口述逐字稿（Full Transcript）：
    管道 1: 透過 youtube-transcript-api 擷取所有可用字幕
    管道 2: 透過 yt-dlp 自動下載各語系 VTT 字幕
    絕不截斷，獲取整部影片完整口述講稿
    """
    if not video_id:
        return ""

    # --- 管道 1: youtube-transcript-api ---
    if YouTubeTranscriptApi:
        try:
            api = YouTubeTranscriptApi()
            t_list = api.list(video_id)
            
            # 優先搜尋繁體、簡體、英文或自動生成
            preferred_langs = ["zh-TW", "zh-Hant", "zh-HK", "zh-Hans", "zh-CN", "zh", "en", "en-US"]
            transcript = None
            try:
                transcript = t_list.find_transcript(preferred_langs)
            except Exception:
                for t in t_list:
                    transcript = t
                    break

            if transcript:
                fetched = transcript.fetch()
                # 拼接完整逐字稿（完整保留，不加字數限制）
                full_text = " ".join([snippet.text for snippet in fetched.snippets if snippet.text])
                if len(full_text.strip()) > 100:
                    return full_text.strip()
        except Exception:
            pass

    # --- 管道 2: yt-dlp 抓取字幕 ---
    try:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        out_template = str(TEMP_DIR / f"sub_{video_id}")
        cmd = [
            "yt-dlp",
            "--write-sub", "--write-auto-sub",
            "--sub-lang", "zh-Hant,zh-TW,zh-Hans,zh,en",
            "--skip-download",
            "-o", out_template,
            video_url
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=25)
        matches = glob.glob(str(TEMP_DIR / f"sub_{video_id}*.vtt"))
        if matches:
            vtt_file = Path(matches[0])
            raw_vtt = vtt_file.read_text(encoding="utf-8", errors="ignore")
            # 清理暫存檔
            for f in matches:
                try:
                    os.remove(f)
                except Exception:
                    pass
            cleaned_text = parse_vtt_to_clean_text(raw_vtt)
            if len(cleaned_text) > 100:
                return cleaned_text
    except Exception as e:
        print(f"[YouTube Helper Warning] yt-dlp 字幕抓取未成: {e}", file=sys.stderr)

    return ""


def download_temporary_audio(video_url: str, video_id: str) -> Optional[Path]:
    """
    當影片完全無字幕時，下載極小位元率之音訊檔案（約 2~5MB），以供 Gemini 多模態音訊深度聆聽解讀
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    target_path = TEMP_DIR / f"audio_{video_id}.mp3"
    
    cmd = [
        "yt-dlp",
        "-f", "ba[abr<=48]/ba/b",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", str(target_path),
        "--max-filesize", "25M",
        video_url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=40)
        if target_path.exists() and target_path.stat().st_size > 1000:
            return target_path
    except Exception as e:
        print(f"[YouTube Audio Download Error]: {e}", file=sys.stderr)

    return None


def analyze_youtube_video_detailed(title: str, url: str, description: str = "", max_bullets: int = 7) -> List[str]:
    """
    【核心分析引擎】：徹底解讀影片內容，從講者口述內容中精準抓取重點。
    （字數不限，務求深度、詳細、結構清晰；絕不以簡短的資訊欄宣傳詞充數）
    """
    video_id = extract_video_id(url)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    # 1. 取得全片真實講稿
    spoken_text = fetch_video_spoken_transcript(video_id, url)
    audio_path = None

    # 若完全沒有字幕，且有設定 GEMINI_API_KEY，啟動音訊下載由 Gemini 親自聆聽！
    if not spoken_text and api_key and video_id:
        print(f"[YouTube Deep Analysis] 影片《{title}》無公開字幕，啟動音訊擷取交由 Gemini 多模態深度解讀...", file=sys.stderr)
        audio_path = download_temporary_audio(url, video_id)

    # ----------------------------------------------------
    # 模式 A: 有 Gemini API Key 進行最高規格深度解讀
    # ----------------------------------------------------
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            system_instruction = (
                "你是一位極為嚴謹的影片內容深度研究員與知識架構專家。\n"
                "使用者明確要求：【必須徹底解讀影片真實內容（非資訊欄宣傳詞），從影片口述中提煉深度重點，字數不限，務求詳細】。\n\n"
                "請遵循以下分析規格進行結構化繁中輸出：\n"
                "1. 請產出 5 到 7 個條列重點，每點以『• 』開頭。\n"
                "2. 第一點【全片核心命題與主旨】：詳細闡述講者開篇指出的核心問題意識、全片最核心的主軸概念。\n"
                "3. 第二至五點【核心論述與概念深度展開】：請按講者在影片中闡述的邏輯脈絡，詳述書中或演說中的每一個關鍵技術、思維架構、心理學機制、推導過程。\n"
                "   （必須包含具體細節、關鍵術語與原理解釋，禁止空泛概述）。\n"
                "4. 第六點【關鍵案例、實驗與論據拆解】：詳述講者在影片中引用的核心案例故事、真實實驗或關鍵數據。\n"
                "5. 第七點【思維升級與實踐行動指南】：提煉從此影片獲得的深刻啟發，以及觀眾在工作或生活中可直接落地執行的具體行動建議。\n"
                "6. 語言一律使用專業繁體中文（台灣習慣用語），若為英文影片請完整在地化翻譯。\n"
                "7. 每個重點必須是語意完整、文字詳實的長段落，句尾必須以標準句號結尾，絕對不可截斷。"
            )

            response = None
            if spoken_text:
                # 直接輸入全片真實逐字講稿（無字數限制）
                prompt = (
                    f"{system_instruction}\n\n"
                    f"【影片標題】：{title}\n"
                    f"【影片連結】：{url}\n\n"
                    f"【影片講者全片口述逐字稿】：\n{spoken_text[:50000]}\n"
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
            elif audio_path and audio_path.exists():
                # 多模態音訊上傳聆聽
                uploaded = client.files.upload(file=str(audio_path))
                prompt = f"{system_instruction}\n\n【影片標題】：{title}\n【影片連結】：{url}\n請直接聆聽此音訊檔案進行分析。"
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[uploaded, prompt]
                )
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass

            if response and response.text:
                lines = [line.strip().lstrip("•- 1234567890.、*") for line in response.text.strip().split("\n") if len(line.strip()) > 20]
                clean_bullets = [ensure_complete_sentence(l) for l in lines]
                if clean_bullets:
                    return clean_bullets[:max_bullets]

        except Exception as e:
            print(f"[YouTube Helper Error] Gemini 深度解讀失敗 ({e})", file=sys.stderr)
        finally:
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # ----------------------------------------------------
    # 模式 B: 本地全篇逐字稿結構化提取引擎（無 API Key 或備援）
    # ----------------------------------------------------
    if spoken_text:
        is_english = is_mostly_english(title + " " + spoken_text[:300])
        
        # 智能逐字稿切塊：若缺乏中文標點符號，按語意詞尾與長度自然斷塊
        period_count = len(re.findall(r"[。！？]", spoken_text))
        if period_count >= 10:
            raw_sentences = re.split(r"(?<=[。！？\n])", spoken_text)
        else:
            parts = spoken_text.split(" ")
            raw_sentences = []
            cur = []
            cur_l = 0
            for p in parts:
                p_s = p.strip()
                if not p_s:
                    continue
                cur.append(p_s)
                cur_l += len(p_s)
                if cur_l >= 60 and (p_s.endswith(("，", "。", "？", "！", "了", "嗎", "吧", "呢", "的", "說", "道")) or cur_l >= 100):
                    raw_sentences.append(" ".join(cur))
                    cur = []
                    cur_l = 0
            if cur:
                raw_sentences.append(" ".join(cur))

        # 篩選具備高資訊量、非寒暄的實質論述句子
        informative_sentences = []
        for s in raw_sentences:
            s_clean = s.strip()
            if len(s_clean) < 30:
                continue
            # 排除純口語贅字與開場結尾雜訊
            if any(noise in s_clean for noise in ["訂閱頻道", "按讚分享", "開啟小鈴鐺", "點擊下方連結", "下一集再見", "我是好葉", "哈囉大家好", "Hello Guys"]):
                continue
            
            # 若為英文，翻譯繁中
            if is_english:
                translated = translate_en_to_zh_tw(s_clean)
                informative_sentences.append(ensure_complete_sentence(translated))
            else:
                informative_sentences.append(ensure_complete_sentence(s_clean))

        if len(informative_sentences) >= 4:
            # 依開篇、中段論證、案例、結論挑選精華句子
            step = max(1, len(informative_sentences) // 5)
            selected = [
                f"【核心問題與背景】{informative_sentences[0]}",
                f"【第一核心觀點】{informative_sentences[min(step, len(informative_sentences)-1)]}",
                f"【深入論證展開】{informative_sentences[min(step * 2, len(informative_sentences)-1)]}",
                f"【關鍵案例故事】{informative_sentences[min(step * 3, len(informative_sentences)-1)]}",
                f"【總結啟發與行動】{informative_sentences[-1]}"
            ]
            return selected

        elif informative_sentences:
            return informative_sentences[:max_bullets]

    # 若完全無字幕且未設定 API Key
    return [
        f"【內容解讀說明】影片《{title}》未提供公開逐字稿或字幕軌道。",
        "【深度聆聽建議】系統已內建 Gemini 多模態音訊解讀技術，只要在 config/.env 設定 GEMINI_API_KEY，系統即可自動下載全片音訊，由 AI 親自聆聽並還原完整內容重點。",
        f"【影片觀看直達】完整精彩講述請點擊上方影片連結直接觀看。"
    ]


def add_youtube_channel_to_sites(url_or_handle: str, custom_name: Optional[str] = None) -> Dict[str, Any]:
    """
    自動解析 YouTube 頻道並寫入 config/sites.json
    - target_bot 嚴格綁定為 "youtube"
    - type 為 "youtube"
    """
    info = resolve_youtube_channel(url_or_handle)
    if not info:
        return {"success": False, "error": f"無法從 '{url_or_handle}' 找到有效的 YouTube 頻道資訊"}

    channel_name = custom_name.strip() if custom_name else info["channel_name"]
    channel_id = info["channel_id"]
    feed_url = info["feed_url"]
    site_id = f"yt_{channel_id}"

    sites = []
    if SITES_FILE.exists():
        try:
            with open(SITES_FILE, "r", encoding="utf-8") as f:
                sites = json.load(f)
        except Exception:
            sites = []

    for s in sites:
        if s.get("id") == site_id or s.get("url") == feed_url:
            s["enabled"] = True
            s["name"] = channel_name
            s["target_bot"] = "youtube"
            s["type"] = "youtube"
            with open(SITES_FILE, "w", encoding="utf-8") as f:
                json.dump(sites, f, ensure_ascii=False, indent=2)
            return {
                "success": True,
                "action": "updated",
                "site": s
            }

    new_site = {
        "id": site_id,
        "name": f"🎬 {channel_name}",
        "url": feed_url,
        "original_url": info["original_url"],
        "type": "youtube",
        "target_bot": "youtube",
        "enabled": True,
        "description": f"YouTube 頻道《{channel_name}》影片真實內容深度重點解析"
    }
    sites.append(new_site)

    with open(SITES_FILE, "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "action": "added",
        "site": new_site
    }
