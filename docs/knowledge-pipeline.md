# 從協作紀錄形成 Wiki 與 skill

[回首頁](../README.md)

## 研究背景與目標

跨 session 留下的摘要容易只剩結論，遺失問題如何被發現、方案為何被修正。保留 raw 的價值，是讓未來能帶著新問題重新閱讀；structured 則降低定位成本。目標是把協作經驗轉成有來源的知識與可重用操作方法。

## 材料與方法

本案例核對 2026-04-22 的 context 儲存設計紀錄、配對 structured、現存 context-extract 原型，以及協作 Wiki 的來源保留規則。原始私人資料只留本機；此頁為去識別化概念摘要。歷史 raw 含整理後的執行描述，不視為完整逐字工具軌跡。

先用 structured 定位議題，再回查 raw 區分使用者要求與 AI 提案，最後核對留下的設定檔。這次是文件回溯，沒有執行新的模型提取實驗。

## 真實案例：提取流程不能每次隨意改

| 階段 | 可核對的內容 | 意義 |
|---|---|---|
| Nio 發現問題 | 要求 raw 與格式化資料分開，詢問未來提取 skill／subagent 應用哪一層 | 原始紀錄是可再次使用的素材 |
| Nio 定義要求 | 提取必須使用固定 prompt 或作業流程 | 讓下游建立在可檢查的方法上 |
| Claude 展開方案 | 建議 structured 作為中介，設計固定 schema | 屬於 AI 的具體方案，並非全由作者手寫 |
| 留下操作原型 | context-extract 有輸入、六段輸出格式、引用規則與使用步驟 | 已有可供 agent 使用的操作規格 |
| Wiki 提供約束 | 保留 raw，規則同時保存原因與邊界 | 知識整理不能取代來源；這是現存關聯規則，不宣稱由本事件首次產生 |
| 待驗證 | 多樣本重跑、語意保真、規則提升條件 | 規格存在不等於方法效果已證明 |

原型的六段為 Events（事件）、Key Insights（洞察）、Rules Proposed（候選規則）、Pending Actions（待辦）、Artifacts Mentioned（產物）、Unresolved（未解問題）。其中候選規則與待辦必須分開：一次任務的狀態不應直接變成長期 Wiki 規則。

## 本 repo 和歷史系統的關係

| 層次 | 現況 | 邊界 |
|---|---|---|
| 本機 Python 檢索與引用核對 | 已實作 build／search／verify | 找到原文，不判定概念正確 |
| 歷史 NotebookLM recall skill | 本機保留操作規格 | 與本 repo 為不同實作；本輪未驗證外部服務 |
| raw → structured 提取 | 保留 context-extract 原型 | 未在本 repo 自動串接 |
| Wiki 與 skill 提煉 | 有方法與相關歷史材料 | 本輪未建立自動升級流程或新正式 skill |

## 如何由一次回溯形成可驗證的方法？

1. 找到問題及修正的原始段落，保留引用版本。
2. Agent 提出規則、原因、適用條件，以及反例或未知。
3. 若適合長期參考，整理為 Wiki 候選；若可重複操作，整理為 skill 候選。
4. 為 skill 明定觸發、輸入、步驟、失敗停止條件與輸出驗收。
5. 用新案例試跑並由 reviewer 對照來源；發現問題回修，未通過不升為正式方法。

以上是本作品的下游設計，不是 recall.py 已執行的功能。

## 結果與討論

證據支持 Nio 以 prompt 主導資料分層、可重用目的與固定流程要求，Claude 完成原型細節，Codex 完成本機檢索元件與此次核對。Nio 沒有親自逐項審查或編寫全部程式。

歷史原型聲稱「相同 raw + SOP → 相同 structured」，但固定 prompt 本身不能保證 LLM 確定性。固定 schema 可以限制格式；語意是否保真仍須獨立評估。Structured 是導覽與候選解讀，遇到歧義必須回查 raw，不能直接當成已驗證真相。

**結論：Context Recall 讓經驗提煉有可回查的基底；Wiki 與 skill 仍須經過判讀、試跑與審查。**

Author: Nio (Master) · Source audit and implementation: Codex · 2026-10-17
