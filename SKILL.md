---
name: telegram-news-bot
description: AntiGravity Telegram 情報推播與定時檢查技能。可抓取指定目標網站今日消息並自動推播至 Telegram，支援自訂多個指定檢查時間點與去重機制。
---

# Telegram 今日情報自動推播 Skill (telegram-news-bot)

本 Skill 負責讓 AntiGravity 透過 Telegram Bot API 進行雙向推播與狀態回報。由 AntiGravity 智能大腦自主負責文章內容分析，產出**一目瞭然的繁體中文條列式重點摘要**，並附帶原文連結推播至指定 Telegram。

## 🌟 核心特徵
1. **AntiGravity 原生驅動**：由 AntiGravity 大腦親自閱讀文章，提煉 2~3 個核心重點（條列分明、一秒掌握脈絡）。
2. **純繁體中文呈現**：所有標題、要點與來源標籤皆採標準繁體中文排版。
3. **全文直達**：每則消息皆附帶 `點此閱讀全文 ↗` 超連結，讀者想深讀時一鍵直達原文。
4. **去重與指定時間排程**：每日多個指定時間檢查，已發布過的消息絕不重複轟炸。

## 🎯 支援的主要指令與對話操作

當您在 AntiGravity 對話時，直接說以下句子即可觸發：

1. **「TG 開工」 / 「啟動 Telegram 推播」 / `tg-start`**：
   * 同時啟動**「定時主動推播（08:00, 12:00, 18:00）」**與**「手機雙向指令監聽」**。
   * 手機會自動收到上線通知與 4 個快捷按鈕。
   ```bash
   python src/main.py --listen
   ```
2. **「立即抓取」 / 「推播今日消息」 / `tg-check`**：
   * 立即執行一次掃描、繁中條列摘要並推播。
   ```bash
   python src/main.py --once
   ```
3. **「查看機器人頻道配置」**：
   ```bash
   python src/main.py --list-bots
   ```
4. **「測試所有 Bot 連線」**：
   ```bash
   python src/main.py --test-tg all
   ```
5. **「查看推播時間」**：
   ```bash
   python src/main.py --list-times
   ```
4. **「新增推播時間 [HH:MM]」**（例如：新增下午 16:00）：
   ```bash
   python src/main.py --add-time 16:00
   ```
5. **「移除推播時間 [HH:MM]」**：
   ```bash
   python src/main.py --remove-time 16:00
   ```
6. **「查看監控站點」**：
   ```bash
   python src/main.py --list-sites
   ```
7. **「檢視推播日誌」**：
   ```bash
   python src/main.py --show-log
   ```
8. **「清空推播紀錄」**（重新測試或補推今日消息）：
   ```bash
   python src/main.py --clear-history
   ```

## 📱 手機端可用功能（隨點隨查）
在手機 Telegram 對話框中：
* 點擊底部 **【📰 獲取今日最新情報】** 或輸入 `/today`：立即秒回今日最新繁中條列摘要與全文連結！
* 點擊 **【🔍 查看監控網站】** 或輸入 `/sites`：列出 8 大監控站點清單。
* 點擊 **【⏰ 查看推播時間】** 或輸入 `/time`：查看每日排程時間。

## ⚙️ 核心設定檔說明

* [`.env`](file:///e:/antigravity-telegeam/config/.env)：填寫 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID`。
* [`sites.json`](file:///e:/antigravity-telegeam/config/sites.json)：目標網站清單，支援 RSS 與 HTML 爬蟲模式。
* [`settings.json`](file:///e:/antigravity-telegeam/config/settings.json)：時區與多組指定排程時間列表。
* [`history.json`](file:///e:/antigravity-telegeam/data/history.json)：已推送過的連結網址紀錄，避免重複轟炸。
