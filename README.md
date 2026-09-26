# 🚀 AntiGravity Telegram 今日情報與 AI 繁中深度摘要系統

> 一套專為 AntiGravity 設計的 Telegram 今日情報推播與雙向互動系統。  
> 由 AntiGravity 智能模型自主負責閱讀文章，提煉**一目瞭然的繁體中文條列精華摘要**，並附上原文全文連結，支援定時自動推播與手機隨點隨查！

---

## ✨ 核心亮點

* 🧠 **AntiGravity 智能深度摘要**：非單純轉發標題，由 AI 閱讀全文並提煉 2~3 個核心重點（條列分明，3 秒掌握精華）。
* 🇹🇼 **純繁體中文呈現**：專為台灣與繁體中文閱讀習慣優化排版。
* 📱 **手機 Telegram 雙向快捷按鈕**：提供手機底部快捷按鈕（`📰 獲取今日最新情報`、`🔍 查看監控網站`、`⏰ 查看推播時間`），免開電腦手機點一下立即秒回！
* ⏰ **多時段定時主動推播**：支援自由設定每日任意多個檢查時段（預設每日 08:00、12:00、18:00）。
* 🛡️ **隱私 100% 本地化**：金鑰與文章處理皆留在本機電腦，絕不外洩至第三方雲端。
* 🔄 **精準去重過濾**：自動比對發布日期與歷史紀錄庫，同一篇文章當日絕不重複打擾。
* 🌐 **多源彈性監控**：支援 RSS、Atom 及自訂 HTML 網頁爬蟲。

---

## 📱 手機 Telegram 成果預覽

```
🗞️ 【今日情報精華・AntiGravity 智能摘要】
📅 日期：2026-09-26 ｜ 共精選 9 篇重點情報
─────────────────────────

📌 1. 蘋果 Home 攝影機 AI 功能實測！描述精準度與價格皆落後 Google Ring 與亞馬遜 Nest [12:30]
🏷️ 來源：科技新報 (TechNews)
💡 核心重點摘要（一目瞭然）：
  • 實測差距：外媒實測影像描述功能，辨識精準度與反應速度仍落後 Google Nest 與亞馬遜 Ring。
  • 價格劣勢：蘋果 HomeKit 方案整體設備與訂閱成本相對較高，目前性價比未達市場預期。
  • 市場展望：蘋果預計在下版軟體更新中強化本地神經網路模型，以提升隱私與解析力。
🔗 點此閱讀全文 ↗

─────────────────────────
🤖 來自 AntiGravity AI 深度摘要與推播
```

---

## ⚡ 3 步驟快速開始

### 步驟 1：安裝依賴環境
確保已安裝 Python 3.10+，於終端執行：
```bash
pip install -r requirements.txt
```

### 步驟 2：設定 Telegram Bot 金鑰
1. 在 Telegram 搜尋 `@BotFather`，輸入 `/newbot` 依提示建立機器人，取得 **`API Token`**。
2. 搜尋 `@userinfobot` 點擊 Start，取得您的專屬 **`Chat ID`**。
3. 複製設定檔範本：
   ```bash
   cp config/.env.example config/.env
   ```
4. 打開 `config/.env` 填入您的資訊：
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   TELEGRAM_CHAT_ID=1208138575
   ```

### 步驟 3：啟動服務
在終端執行：
```bash
python src/main.py --listen
```
您的手機 Telegram 將會收到上線確認訊息，並自動啟用底部 4 個快捷按鈕！

---

## 💬 AntiGravity 自然語言指令

當您開啟 AntiGravity 時，可直接使用以下日常指令：

| 您可以直接對 AntiGravity 說 | 對應執行的動作 |
| :--- | :--- |
| **「TG 開工」** 或 **「啟動 Telegram 推播」** | 啟動手機按鈕雙向監聽 + 背景定時排程守護服務 |
| **「推播今日情報」** 或 **「立即抓取」** | 立即手動掃描今日新文章，生成繁中摘要並推播 |
| **「查看目前的推播時間」** | 列出每日定時檢查的所有時間點 |
| **「新增下午 16:30 的推播」** | 動態新增指定檢查時間點 |
| **「查看目前監控的網站」** | 列出已訂閱的 8 個資訊來源 |
| **「清空推播歷史紀錄」** | 清空去重紀錄以供重新測試 |

---

## 🌐 監控站點自訂 (`config/sites.json`)

目前系統已收錄 8 大優質站點，您可以隨時在 `config/sites.json` 中增減或修改：

```json
[
  {
    "id": "technews_main",
    "name": "科技新報 (TechNews 即時快訊)",
    "url": "https://technews.tw/feed/",
    "type": "rss",
    "enabled": true,
    "description": "科技新報官方即時新聞全站 RSS Feed"
  },
  {
    "id": "wsj_chinese_traditional",
    "name": "華爾街日報 (WSJ 繁體中文熱門)",
    "url": "https://wsj.buzzing.cc/zh-Hant/feed.xml",
    "type": "rss",
    "enabled": true,
    "description": "華爾街日報繁體中文即時熱門新聞與財經焦點"
  },
  {
    "id": "reading_outpost",
    "name": "閱讀前哨站 (瓦基讀書心得)",
    "url": "https://readingoutpost.com/feed/",
    "type": "rss",
    "enabled": true,
    "description": "瓦基閱讀前哨站最新說書、閱讀心得與個人成長文章"
  }
]
```

---

## 📂 專案檔案結構

```
antigravity-telegram/
├── config/
│   ├── .env.example         # 環境變數設定範本
│   ├── sites.json           # 目標監控站點清單 (RSS/HTML)
│   └── settings.json        # 時區與每日定時推播時間列表
├── data/                    # 本地去重資料庫 (不進版控)
│   └── history.json
├── logs/                    # 本地推播流水帳 (不進版控)
│   └── push.log
├── src/
│   ├── agent_workflow.py    # AntiGravity 繁中條列智能摘要與排版核心
│   ├── bot_listener.py      # 手機雙向按鈕監聽與定時守護服務
│   ├── scraper.py           # RSS / HTML 今日內容抓取與日期過濾
│   ├── summarizer.py        # 深度語意提煉與降級備援模組
│   ├── telegram_notifier.py # Telegram API 傳送與 HTML 排版
│   └── main.py              # CLI 總進入點
├── SKILL.md                 # AntiGravity 專屬 Skill 規格檔
├── requirements.txt         # Python 必要依賴
└── README.md                # 專案詳細說明文件
```

---

## 🔒 隱私與安全性聲明

* 本專案已配置完整的 `.gitignore`。
* `config/.env`（包含您的 Bot Token 與 Chat ID）以及 `data/`、`logs/` 絕對不會被提交或推送到任何公開儲存庫。
