# 全球遊戲情報中心 V1（免費雲端 MVP）

這是可部署的第一版：每小時透過 GitHub Actions 檢查多地區 Google News RSS、指定 YouTube 頻道 RSS 和自訂 RSS，保存歷史情報、生成 Excel、提供 GitHub Pages 網頁，並可選擇 Telegram 通知。

## 1. 建立 GitHub 專案

1. 在 GitHub 建立**公開** repository（例如 `game-intel`）。公開專案的 GitHub Pages 與 Actions 免費使用情況通常比較適合本方案，但須遵守 GitHub 的最新政策及配額。
2. 將本資料夾內的所有檔案（包括 `.github` 隱藏資料夾）上傳到 repository 的 `main` 分支。建議用 Git CLI：
   ```bash
   git init
   git add .
   git commit -m "Initial game intelligence monitor"
   git branch -M main
   git remote add origin https://github.com/你的帳號/game-intel.git
   git push -u origin main
   ```
3. GitHub → Settings → Actions → General → Workflow permissions，允許 **Read and write permissions**（若組織政策禁止，需改用其他提交方案）。
4. GitHub → Actions → `Game intelligence hourly monitor` → **Run workflow**，先手動執行一次。
5. GitHub → Settings → Pages → Build and deployment → Source: **Deploy from a branch** → Branch: `main` → Folder: `/docs` → Save。
6. 稍等部署完成後，網址通常是 `https://你的帳號.github.io/game-intel/`。

## 2. 新增指定 YouTube 頻道

編輯 `config/sources.json` 中 `youtube_channels`，填入**真正的 Channel ID**（以 `UC` 開頭的 24 字元 ID），而不是 `@handle` 或影片網址：

```json
"youtube_channels": [
  {"name": "我的遊戲頻道", "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx"}
]
```

上述 `UCxxxxxxxxxxxxxxxxxxxxxx` 只是格式示意，請替換成實際頻道 ID。每個頻道新增一個物件，注意 JSON 逗號。可透過頻道頁面資訊或 YouTube API 找到 Channel ID。

## 3. 新增網站 RSS

編輯 `config/sources.json` 中 `rss_feeds`：

```json
"rss_feeds": [
  {"name":"遊戲網站 A", "region":"日本", "url":"https://example.com/feed.xml"}
]
```

請替換為網站實際提供的 RSS/Atom URL。不是所有網站都提供 RSS；不支援 RSS 的網站需要另外寫專屬擷取器並遵守網站條款。

## 4. 啟用 Telegram 通知（可選）

1. 在 Telegram 透過官方 `@BotFather` 建立機器人，取得 token。
2. 與機器人開始對話，透過 Telegram API `getUpdates` 取得你的 chat ID。
3. GitHub → Settings → Secrets and variables → Actions → New repository secret，新增：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. 下次偵測到新情報時會發送通知；首次啟動可能一次出現大量「新情報」。

請勿將 token、chat ID 或其他私人資料放進公開程式碼或設定檔。

## 5. 本機測試

```bash
python -m pip install -r requirements.txt
python scripts/collect.py
python -m http.server 8000 --directory docs
```

瀏覽 `http://localhost:8000`，或在 GitHub Pages 查看。

## 已實作與限制

- 已實作：RSS/Atom 收集、指定 YouTube 頻道新影片、標題/摘要關鍵字分類、重複合併、首次發現與最後異動時間、歷史事件、Excel 匯出、靜態儀表板、Telegram 新情報通知。
- 尚未實作：影片字幕取得與完整語音分析、可靠的遊戲實體辨識、逐地區正式上市日期結構化驗證、完整遊戲商店 API 連接、瀏覽器 Web Push、真正的每小時 SLA、所有遊戲攻略/兌換碼有效性驗證。
- Google News 搜尋結果不是全球所有遊戲的完整清單；其索引、地域及新聞排序可能遺漏資訊。
- GitHub Actions 定時任務可能延遲或漏跑。公開 repo 會公開收集資料，請勿加入私人資料。
- GitHub repository 內保存 JSON 歷史資料，規模增長後需要移轉資料庫，避免 repository 過大。
- YouTube RSS 只提供影片元資料，不會自動取得完整字幕；此版不使用 YouTube Data API 配額。
- 系統預設不把候選兌換碼判定為有效，也不把新聞提及的日期當作已確認上市日。
- 若資料來源網站拒絕存取或變更格式，該來源可能失效，需人工維護。
