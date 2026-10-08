# 設計與方法

## 既有方法的來源

此專案承接使用者已建立的三段工作方式：context-save 保存 raw 與六段 structured，writer／evaluator 校驗摘要；context-publish 留發布紀錄；context-recall 從 NotebookLM 取引用並回原文核對。既有設計將「穩定規則」「特定對話論述」「目前任務狀態」分開。

本次讀取原技能定義、提取 schema、context_log 與發布紀錄作為設計材料。原始技能及私人對話沒有複製進 repository。沒有以新 Python 程式冒稱為歷史原始實作，也沒有執行雲端發布。

## 本次工程範圍

新增 `recall.py` 與 `import_context.py`：explicit manifest → immutable index snapshot → ranked excerpts → citation validation。沒有重新訓練模型權重，也沒有實作生成式摘要。SQLite 保存資料，Python 執行排序；目前不使用 FTS、embedding 或 reranker。

單一目的：給下一個 session 一份可回查的歷史證據包。正式規則仍應讀其 canonical 入口，不能從搜尋結果推定最新指令。

## 資料契約

`examples/manifest.json` 是完整可用範例，`version=1`，每個來源有：

| 欄位 | 意義 |
|---|---|
| id | 唯一、穩定的本機來源 ID |
| path | 相對於 manifest 的檔案路徑，也接受絕對路徑；清單是信任輸入 |
| title | 顯示名稱 |
| kind | raw 或 structured，原始素材與衍生摘要分開 |
| provenance | transcript／reconstructed／unknown／synthetic，由操作者宣告，不由檔名猜測 |
| review | pass／unresolved／unknown，只是宣告狀態，不是使用者批准 |
| raw_id | structured 必填，必須指向已列入的 raw |

匯入器以共同檔名前綴配對 raw／structured；它不校驗 structured 內的 `source:` 欄位，配對不是語意支持證明。歷史 metrics 無稿件 hash 時，無法證明 verdict 審的是現在這一版。匯入器只辨識開頭 frontmatter 中單一、未加引號的小寫 status 欄位；其餘 YAML 格式不解析。若與 metrics 不一致，標 unknown 並在 audit 列出兩者，不自動選邊。

## 檢索與引用

依原文每 12 行起一個最多 20 行的視窗；保留原行號，視窗可能截在論述中間，讀者可回原檔擴讀。英文按詞、中文按連續雙字詞。每個查詢詞權重為 `log(1 + (片段數+1)/(含詞片段數+1))`；分數為命中權重占查詢總權重比例。排序後抑制同文件重疊視窗。

不存在最小分數門檻：只要有詞元交集就可回傳候選，**分數不是答案正確率**。無詞元命中時回 `no_match`；這只證明此檢索方式沒找到，不證明資料庫沒有語意相關內容。

每次搜尋回查來源 hash；raw 變動時，連配對 structured 一起排除。驗證以同一份讀入 bytes 同時計算 hash 與核對逐行引用，避免兩次讀檔間變更造成新文字配舊指紋。這是讀取當下的一致性，不能保證驗證後檔案永遠不變。

## 寫入與失敗

索引與 JSON 寫到同目錄暫存檔，使用排他 hard link 發布；既有路徑一律拒絕，不用 overwrite。HTML 使用排他建立。新版本應另選目錄，保留舊證據。程式支援本機支援 hard link 的檔案系統；未測試網路磁碟。

CLI 缺檔、錯誤 schema、空查詢回 exit 2；引用核對失敗回 exit 1。匯入器是受信任本機管理工具；錯誤會中止並保留已產生資料，不提供 rollback 整個 run。

HTML 轉義來源文字，不執行原文 HTML。來源字句不會作為 shell 或工具指令執行。下游 LLM 必須另行防止把取回的文字當成指令，本工具沒有提供模型隔離沙箱。

## 取捨

選本機可重跑詞彙基線，是為了先測引用與失敗邊界，避免把外部服務的回答能力誤算成自己的檢索工程能力。代價是語意召回較弱、全檔 hash 與全片段掃描不適合大規模資料。

未做自動決策抽取、NotebookLM adapter、向量索引、衝突裁決或自動 memory 更新。這些應依查詢集與實際需求分別驗收，不能由本版的 citation PASS 推論已完成。
