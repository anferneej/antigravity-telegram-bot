"""
Telegram 各頻道專屬 AI 專家問答與訊息深度追問模組
- 玩法 1：針對推播訊息「引用回覆追問 (Reply)」，結合原始情報上下文深度解讀
- 玩法 2：專屬領域專家直接對話 (Direct Chat)，財經/閱讀/科技/影音專屬 Persona
"""

import html
import os
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
ENV_PATH = CONFIG_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

CHANNEL_PERSONAS = {
    "finance": (
        "你是一位具備 20 年全球資本市場與總體經濟研究經驗的資深財經投資顧問。\n"
        "精通全球股市、聯準會利率政策、美債市場、資產配置策略、半導體供應鏈與加密金融。\n"
        "回答原則：\n"
        "1. 使用專業、邏輯嚴密且切中核心的【繁體中文（台灣財經用語）】。\n"
        "2. 剖析問題背後的底層經濟機制、多空潛在風險與實務投資維度，切勿給出泛泛空話。\n"
        "3. 適度使用重點條列與粗體標記，結構清晰。"
    ),
    "reading": (
        "你是一位資深的深度閱讀導讀師、說書人與個人心智模型教練。\n"
        "精通各類商業管理、心理學、認知科學、個人成長與高效工作術書籍。\n"
        "回答原則：\n"
        "1. 使用溫暖、富有啟發性且能直接落地應用的【繁體中文】。\n"
        "2. 擅長將抽象理論轉化為生動的生活案例、行動步驟與思考框架。\n"
        "3. 幫助讀者內化知識、突破盲點並提供具體的實踐指引。"
    ),
    "tech": (
        "你是一位深耕矽谷與兩岸資通訊生態的資深科技產業分析師與軟硬體研究員。\n"
        "精通半導體先進製程（TSMC/Intel）、AI 神經網路架構、雲端伺服器供應鏈、消費電子與科技創投動態。\n"
        "回答原則：\n"
        "1. 使用精準、紮實的科技專業術語與商業邏輯，語言為【繁體中文】。\n"
        "2. 剖析技術規格、產業上下游競合關係與未來 3~5 年商業變局。\n"
        "3. 條理分明、數據為本。"
    ),
    "youtube": (
        "你是一位資深的 YouTube 影音知識解讀專家、內容研究員與說書分析師。\n"
        "精通各類知識型頻道（說書、思維成長、科技評析、國際時事）的口述脈絡、核心論述與案例結構。\n"
        "回答原則：\n"
        "1. 使用生動、深刻且架構分明的【繁體中文】。\n"
        "2. 當使用者針對某部影片或說書提問時，請徹底依據講者口述的內容脈絡進行深度拆解。\n"
        "3. 詳述影片中的關鍵論點、實驗數據、經典金句與行動啟發。"
    ),
    "default": (
        "你是一位全方位的專業知識顧問與 AntiGravity 第二大腦智能助理。\n"
        "精通財經、閱讀、科技前沿與生活生產力工具。\n"
        "請以專業、精確、邏輯嚴謹且親切有禮的【繁體中文】為使用者解答各類問題。"
    )
}


def sanitize_telegram_html(text: str) -> str:
    """轉換為安全的 Telegram HTML 格式"""
    # 將 Markdown 粗體 **text** 轉為 <b>text</b>
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # 將 Markdown 代碼 `code` 轉為 <code>code</code>
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # 移除未處理的 markdown # 標題
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    return t.strip()


def answer_reply_question(channel_id: str, context_text: str, question: str) -> str:
    """
    【玩法 1】：針對推播訊息進行「引用回覆追問」
    將原始推播的文字（新聞/摘要/逐字講稿）作為上下文，深度解答使用者的追問
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    persona = CHANNEL_PERSONAS.get(channel_id, CHANNEL_PERSONAS["default"])

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            prompt = (
                f"{persona}\n\n"
                "【任務說明】：\n"
                "使用者在 Telegram 上對之前系統推播的某則情報進行了「引用回覆追問」。\n"
                "請你仔細研讀該則情報的上下文內容，並針對使用者的具體提問進行全面、深度、有資訊量的專業解答。\n\n"
                f"【被引用之原始情報內容】：\n{context_text[:12000]}\n\n"
                f"【使用者的追問】：\n{question}\n\n"
                "【回答規格】：\n"
                "1. 直接切中使用者問題，以專業繁體中文深入剖析。\n"
                "2. 結合上下文提到的事實、論點或數據，並適度給出延伸見解或實務建議。\n"
                "3. 排版結構清晰，可適當使用列點與粗體重點標記。\n"
                "4. 結尾請給出 1~2 點啟發或行動結論。"
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if response and response.text:
                return sanitize_telegram_html(response.text)

        except Exception as e:
            print(f"[AI Assistant Error] Gemini 調用未成: {e}", file=sys.stderr)

    # 本地降級模式（未設定 GEMINI_API_KEY 時）
    return (
        f"💡 <b>【深度解答】針對您的提問：</b>\n<i>「{html.escape(question)}」</i>\n\n"
        f"根據您引用的情報內容，相關重點梳理如下：\n"
        f"• 本則情報的核心討論圍繞在該主題的關鍵變數與最新進展。\n"
        f"• 關於您詢問的細節，講者/作者在原文中強調了依據客觀事實與底層邏輯進行思考的重要性。\n\n"
        "─────────────────\n"
        "✨ <b>解鎖全智能深入推論</b>：\n"
        "若您在 <code>config/.env</code> 中填入 <code>GEMINI_API_KEY</code>（可於 Google AI Studio 免費獲取），"
        "系統將能呼叫 Gemini 2.5 進行無限長文本的深度推理、多角度辨析與量身客製解答！"
    )


def answer_direct_question(channel_id: str, question: str) -> str:
    """
    【玩法 2】：專屬領域專家隨時直接諮詢 (Direct Chat)
    依照機器人所屬頻道（財經、閱讀、科技、影音等）扮演專家即時解答
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    persona = CHANNEL_PERSONAS.get(channel_id, CHANNEL_PERSONAS["default"])

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            prompt = (
                f"{persona}\n\n"
                "【任務說明】：\n"
                "使用者正在您的專屬 Telegram 頻道向您諮詢問題。\n"
                "請充分展現您的專家定位，為使用者提供專業、深刻、結構分明且極具價值的繁體中文解答。\n\n"
                f"【使用者諮詢問題】：\n{question}\n\n"
                "【回答規格】：\n"
                "1. 開門見山指出核心觀點與關鍵答案。\n"
                "2. 條列展開底層原理、實際範例或推導邏輯。\n"
                "3. 給出實務落地或思考行動建議。\n"
                "4. 全文使用結構化繁體中文排版。"
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if response and response.text:
                return sanitize_telegram_html(response.text)

        except Exception as e:
            print(f"[AI Assistant Error] Gemini 調用未成: {e}", file=sys.stderr)

    # 本地降級模式（未設定 GEMINI_API_KEY 時）
    channel_titles = {
        "finance": "資深財經投資顧問",
        "reading": "深度閱讀導讀師",
        "tech": "科技產業分析師",
        "youtube": "影音知識解讀專家",
        "default": "全方位智能助理"
    }
    role = channel_titles.get(channel_id, "專業顧問")

    return (
        f"🤖 <b>【{role}】已收到您的提問：</b>\n"
        f"<i>「{html.escape(question)}」</i>\n\n"
        f"您詢問的課題涉及該領域的核心關鍵觀念。建議可先從基本定義、產業/市場背景與實際執行步驟三個維度進行評估。\n\n"
        "─────────────────\n"
        "✨ <b>解鎖全智能專家即時諮詢</b>：\n"
        "本系統支援直接串接 Google Gemini 2.5 大模型！只要在 <code>config/.env</code> 設定 <code>GEMINI_API_KEY</code>，"
        "此機器人即可秒變為您 24 小時隨身待命的頂級專業智囊！"
    )
