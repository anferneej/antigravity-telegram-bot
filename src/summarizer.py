import os
import re
import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / "config" / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}

# 付費牆與網頁雜訊關鍵字過濾
PAYWALL_NOISE_KEYWORDS = [
    "會員登入", "忘記密碼", "重寄啟用信", "記住帳號密碼", "帳號啟用",
    "會員服務申請", "試用申請", "產業研究諮詢", "會員服務介紹", "常見問題",
    "申請專線", "會員信箱", "訂閱DIGITIMES", "關鍵字追蹤", "版權所有",
    "轉載請註明", "訂閱電子報", "請登入以閱讀全文", "付費會員限定", "廣告贊助"
]


def clean_html_tags(raw_text: str) -> str:
    """清理文字中的 HTML 標籤與多餘空白"""
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def filter_paywall_noise(text: str) -> str:
    """過濾掉付費牆、登入與版權宣告文字"""
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        l = line.strip()
        if not l or len(l) < 10:
            continue
        # 若包含付費牆關鍵字則丟棄該行
        if any(noise in l for noise in PAYWALL_NOISE_KEYWORDS):
            continue
        clean_lines.append(l)
    return "\n".join(clean_lines)


def extract_web_article_text(url: str, max_chars=4000) -> str:
    """從目標網頁擷取正文段落，嚴格排除會員登入與付費牆雜訊"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=12)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除干擾節點
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside", "svg", "button", "form"]):
            tag.decompose()

        # 針對特定 class 移除
        for bad_cls in ["login", "member", "paywall", "adv", "banner", "sidebar", "share"]:
            for el in soup.find_all(class_=re.compile(bad_cls, re.I)):
                el.decompose()

        # 尋找文章正文節點
        article_node = soup.select_one(
            "article, .content, .entry-content, .post-content, .article-content, #article-content, .news-content, .story-body, main"
        )
        if not article_node:
            article_node = soup.body

        if article_node:
            p_tags = article_node.find_all("p")
            if p_tags and len(p_tags) >= 2:
                paragraphs = [p.get_text(strip=True) for p in p_tags if len(p.get_text(strip=True)) > 20]
                text = "\n".join(paragraphs)
            else:
                text = article_node.get_text(separator="\n", strip=True)

            filtered = filter_paywall_noise(text)
            return filtered[:max_chars]
    except Exception:
        pass
    return ""


def ensure_complete_sentence(text: str) -> str:
    """確保文字段落以完整的句號或標點結尾，絕不突兀截斷"""
    t = text.strip().rstrip("…,.，、")
    if not t.endswith(("。", "！", "？", "。」", "！」")):
        t += "。"
    return t


def summarize_article_professional(title: str, link: str, raw_description: str = "") -> list:
    """
    以專業產業分析視角進行繁體中文深度全文摘要。
    回傳完整的繁體中文要點清單 (list of bullets)。
    嚴格要求：
    1. 100% 繁體中文（台灣專業財經科技慣用語）。
    2. 每個重點段落語意完整，句尾完整結尾，絕不截斷。
    3. 專業結構：涵蓋事件核心、關鍵數據/商業邏輯、產業影響。
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    raw_desc_clean = clean_html_tags(raw_description)
    raw_desc_clean = filter_paywall_noise(raw_desc_clean)

    article_body = ""
    if len(raw_desc_clean) < 250:
        article_body = extract_web_article_text(link)

    full_context = article_body if article_body else raw_desc_clean

    # 1. 若有設定 GEMINI_API_KEY，由 Gemini 進行資深分析師級深度提煉
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = (
                "你是一位資深的產業研究員與專業財經科技分析師。\n"
                "請針對以下文章進行全文深度重點提煉，必須遵守以下嚴格規則：\n"
                "1. 必須完全使用【繁體中文（台灣專業科技財經慣用語）】輸出。\n"
                "2. 請提煉 2~3 個【核心重點】，每個重點必須是【結構完整、語意通順的完整段落】，"
                "句尾必須以標準句號完結，【絕對不可在字句中間截斷】。\n"
                "3. 從專業視角深入剖析，重點需包含：\n"
                "   • 【核心事件與事實全貌】\n"
                "   • 【關鍵數據、技術規格或商業邏輯】\n"
                "   • 【對產業鏈、上下游或市場未來的實質影響】\n"
                "4. 每個重點請以『• 』開頭，不要有任何多餘的前言、結語或寒暄。\n\n"
                f"【文章標題】：{title}\n"
                f"【文章內容】：{full_context[:3500]}\n"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if response and response.text:
                lines = [line.strip().lstrip("•- 1234567890.、*") for line in response.text.strip().split("\n") if len(line.strip()) > 15]
                clean_bullets = [ensure_complete_sentence(l) for l in lines]
                if clean_bullets:
                    return clean_bullets[:3]
        except Exception as e:
            print(f"[Summarizer Warning] Gemini 調用未成 ({e})，使用本地專業繁中完整句提取", file=sys.stderr)

    # 2. 本地備援高品質繁中提取（以完整標點句號為界限，絕不截字）
    sentences = re.split(r"(?<=[。！？\n])", full_context)
    clean_sentences = []
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) < 25 or any(noise in s_clean for noise in PAYWALL_NOISE_KEYWORDS):
            continue
        clean_sentences.append(ensure_complete_sentence(s_clean))
        if len(clean_sentences) >= 3:
            break

    if clean_sentences:
        return clean_sentences

    if raw_desc_clean and len(raw_desc_clean) > 20:
        return [ensure_complete_sentence(raw_desc_clean)]

    return ["本篇詳細數據與專業深度分析，請點擊下方全文連結深入閱讀。"]
