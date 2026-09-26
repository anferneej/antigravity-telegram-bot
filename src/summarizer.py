import os
import re
import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / "config" / ".env"
load_dotenv(dotenv_path=ENV_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


def extract_web_article_text(url: str, max_chars=2000) -> str:
    """嘗試從目標網址擷取正文文字，過濾導覽列與頁尾雜訊"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除干擾元素
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside", "svg"]):
            tag.decompose()

        # 優先尋找文章正文容器
        article_node = soup.select_one("article, .entry-content, .post-content, .article-content, #article-content, main")
        if not article_node:
            article_node = soup.body

        if article_node:
            text = article_node.get_text(separator="\n", strip=True)
            # 清理連續空白與換行
            lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 10]
            clean_text = "\n".join(lines)
            return clean_text[:max_chars]
    except Exception:
        pass
    return ""


def clean_summary_text(raw_text: str) -> str:
    """清理 HTML 標籤並截取適當長度"""
    if not raw_text:
        return ""
    # 去除 HTML tag
    text = re.sub(r"<[^>]+>", "", raw_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def summarize_article(title: str, link: str, raw_description: str = "") -> str:
    """
    使用 AntiGravity / Gemini 模型為文章產生繁體中文重點摘要。
    若未設定 GEMINI_API_KEY 或 API 不可用，則自動降級為高品質內文智慧摘要。
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY

    # 1. 準備文章內文素材
    article_content = clean_summary_text(raw_description)
    if len(article_content) < 80:
        fetched_text = extract_web_article_text(link)
        if fetched_text:
            article_content = fetched_text

    # 2. 如果有設定 GEMINI_API_KEY，調用 Google GenAI SDK 產生高品質摘要
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = (
                f"你是一位專業的新聞與情報摘要助手。請閱讀以下文章標題與內容，"
                f"用繁體中文輸出 2~3 句精確簡練的重點摘要（約 60~120 字，可使用條列符號 •），"
                f"直切核心要點，不要有任何客套話或前言結語：\n\n"
                f"【文章標題】：{title}\n"
                f"【內容片段】：{article_content[:1500]}\n"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            # 若 API 發生異常，不讓整個流程崩潰，記錄後降級
            print(f"[Summarizer Warning] Gemini API 調用未成 ({e})，使用內文智慧摘要", file=sys.stderr)

    # 3. 降級備用模式：利用提取出的文章內文產生乾淨摘要
    if article_content:
        # 取前 150 字作為摘要
        summary = article_content[:150].strip()
        if not summary.endswith(("。", "！", "？", "…", ".")):
            summary += "..."
        return summary

    return "（本文暫無提供預覽摘要，請點擊全文連結閱讀）"
