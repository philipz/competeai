# BeverageTown 競價模擬實驗設計文件
# 可口可樂 vs 百事可樂：價格衝擊、交叉彈性與策略演化

> 本文件是 `docs/CompeteAI_Coke_vs_Pepsi.md` 的**可執行化**版本：補齊所有執行細節（參數、時序、API 契約、分析配方），讓實驗可被第三方複現。原始研究設計文件保留不動。

---

## 1. 實驗目標與研究問題

基於微軟 CompeteAI 框架（LLM 驅動自主 Agent 的社會經濟模擬），建構軟性飲料雙寡頭市場（Coca-Cola vs PepsiCo）的競價模擬：

1. **RQ1（XED 測量）**：可口可樂單邊漲價（+5% / +10% / +20%）時，百事可樂需求量與市占率的反應——量化需求交叉價格彈性（XED），與實證錨點 **+0.63** 對照。
2. **RQ2（策略演化）**：百事可樂 LLM 品牌 Agent 面對漲價衝擊時的自發策略——份額掠奪（Share Harvesting）vs 邊際跟進（Margin Matching）。
3. **RQ3（社交結構調節）**：單人 vs 群體消費者的 XED 差異（doc 預測單人 0.2–0.4、群體 0.8–1.3）。
4. **RQ4（對稱競價動態）**：兩家品牌同時自由定價時的價格戰、品質演化與 HHI 均衡。
5. **RQ5（外部效度）**：重現 2022 年百事漲價 12% 案例，檢驗可口可樂是否奪回約 2pp 市占。

## 2. 系統架構（混合 Agent 架構，Q3=b）

```
┌─────────────────────────────── BeverageTown ───────────────────────────────┐
│  Brand Agent (LLM, DeepSeek)                   Brand Agent (LLM, DeepSeek) │
│  ┌──────────────────────┐                     ┌──────────────────────┐    │
│  │ CocaCola 總裁         │   每日 1 次決策       │ PepsiCo 總裁          │    │
│  │ price / marketing /  │◄───────────────────►│ price / marketing /  │    │
│  │ recipe / slogan      │   (僅 free 模式呼叫)  │ recipe / slogan      │    │
│  └──────────┬───────────┘                     └──────────┬───────────┘    │
│             │ 動作空間 (JSON)                             │                │
│  ┌──────────┴────────────────────────────────────────────┴───────────┐    │
│  │                    Market Engine（參數化，無 LLM）                 │    │
│  │  100/200/300 消費者：效用函數 + Gumbel 噪音 + 群體決策規則          │    │
│  │  每日：定價 → 消費者選擇 → 滿意度評分 → 評論 → 帳務 → 市占/HHI      │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

- **品牌 Agent**：LLM 驅動（DeepSeek `deepseek-chat`，OpenAI-compatible，新增 backend `competeai/agent/backends/deepseek.py`）。每日 1 次呼叫，輸出「分析 + 單一 JSON」。
- **消費者 Agent**：**參數化效用模型**（非 LLM）——doc 的個體效用函數：
  `U_ijt = β_ij − α_i·P_jt + γ_q·Q_jt + γ_a·A_jt + ε_ijt`（ε ~ Gumbel，尺度 `gumbel_scale`）
  另設 opt-out 選項（效用 0 + Gumbel 噪音），每日固定消費 1 單位或選擇不購買。

## 3. 實驗設計與分組

### 3.1 兩階段（Q2=d）

| 階段 | 內容 | 組別 | 可口可樂 | 百事可樂 |
| :--- | :--- | :--- | :--- | :--- |
| **Phase A** | 單邊價格衝擊，測 XED | `CG` | 固定 $2.00（全期） | 自由（LLM） |
| | | `TG1` | 第 5 天起 **+5%**（$2.10） | 自由（LLM） |
| | | `TG2` | 第 5 天起 **+10%**（$2.20） | 自由（LLM） |
| | | `TG3` | 第 5 天起 **+20%**（$2.40） | 自由（LLM） |
| **Phase B** | 對稱競價，觀察演化 | `SYM` | 第 5 天起自由（LLM） | 第 5 天起自由（LLM） |
| **外部效度** | 2022 案例重現（Q10c） | `PEP12` | 固定 $2.00 | 第 5 天起 **+12%**（$2.24） |

> 註：`PEP12` 中百事價格固定為外生衝擊（重現 2022 年事件），可口可樂維持不變——兩者皆非 LLM，純參數化檢驗價格替代效應。

### 3.2 網格與重複次數（Q5/Q12/Q13）

- 消費者數 × 時長：**{100, 200, 300} × {2, 4, 6 週} = 9 cells**（1 週 = 7 天）
- 每 cell × 每組 × **5 seeds**（Q13=b）
- 總 runs = 9 × 6 × 5 = **270 runs**（majority_explore 規則）
- 額外：`sum` 群體規則對照組（Q11）：anchor cell（100 人 × 4 週）× 6 組 × 5 seeds = 30 runs
- 每 run：第 1–4 天為基準穩定期（兩家均 $2.00、無行銷、無配方變更、無 LLM 呼叫），第 5 天起進入處置/自由期。

### 3.3 消費者異質性（Q16 預設）

| 參數 | 值 | 說明 |
| :--- | :--- | :--- |
| 收入 | U(5000, 15000) | 每人月收入（美元） |
| 價格敏感度 | `α_i = 31000 / income_i` | 與收入成反比（標定） |
| 品牌忠誠度 | `β_ij ~ N(5.0, 3.0)` | 對兩品牌各自抽樣 |
| 品質權重 | γ_q = 3.0 | |
| 廣告權重 | γ_a = 0.8 | 曝光 `A = 1 − e^(−marketing/300)` |
| Gumbel 噪音尺度 | 2.0 | 標定 |
| 群體比例 | 30% 單人 / 70% 群體 | 群體大小 2–4 人（機率 0.3/0.4/0.3） |
| 群體探索傾向 | 0.1493 | 呼應 doc 的群體探索率 |
| 群體決策規則 | majority_explore（主）/ sum（對照） | Q11 |

### 3.4 消費者參數標定（Q14=c）

用 `calibrate_beverage.py` 在純參數化市場（無 LLM、價格固定）搜尋 `alpha_scale / beta_mean / beta_sd / gumbel_scale`，使基準市場滿足：

- **PED(可口可樂) ∈ [−4.0, −2.0]**（實證：碳酸飲料品牌 PED −2~−4）
- **XED(可樂→百事) ≈ +0.63**（實證：AIDS/歷史估計）

標定結果（多 seed 平均，seed ∈ {42, 7, 123}）：

| 指標 | 標定值 | 目標 | fit |
| :--- | :--- | :--- | :--- |
| PED（可口可樂） | −2.01 | −2.0 ~ −4.0 | ✓ 邊界內 |
| XED（可樂→百事） | +0.66 | ≈ +0.63 | 偏差 +0.03 |
| 基準市占（可樂/百事） | 0.338 / 0.365 | 近對稱雙寡頭 | opt-out 30% |

標定參數凍結於 `logs/coke_pepsi/calibrated_params.json`，全部 treatment 使用同一組消費者參數；最終 XED 偏差即可乾淨歸因於 LLM 品牌決策層。

## 4. 品牌 Agent 動作空間與決策契約

### 4.1 API 動作空間（doc 對齊，Q7=b）

| 動作 | 參數 | 機制 |
| :--- | :--- | :--- |
| `price` | float ∈ [0.5, 5.0] | 零售價，直接進效用函數價格項 |
| `marketing_budget` | float ∈ [0, 2000] | 每日行銷支出 → 廣告曝光（邊際遞減） |
| `recipe_change` | float ∈ [−0.3, +0.3] | 品質增減；每 +0.1 品質 → 每罐成本 +$0.05 |
| `slogan` | str ≤ 60 chars | 廣告標語，供對手情報與評論引用 |

每日成本：固定通路費 $200 + 行銷預算 + 品質成本；資金 $10,000 起，耗盡即破產退場。

### 4.2 LLM 決策 Prompt（Q15=c）

- **系統 prompt**（`competeai/prompt_template/beverage/brand_system.txt`）：中文人設 + 市場規則 + 動作空間 + JSON schema 說明。
- **每日 prompt**（`competeai/prompt_template/beverage/daybook.txt`）：中文情境，注入昨日經營日報、對手情報（價格/標語/估算市占）、消費者評論摘要；要求先分析再輸出**純 JSON**（英文鍵名：`price / marketing_budget / recipe_change / slogan`）。
- 解析失敗自動重試 1 次（提示僅輸出 JSON），仍失敗則沿用上一日決策。

### 4.3 消費者回饋（Q7=b）

- 滿意度分數：`s = 1 + 4·sigmoid(6·(Q − 0.7) − 3·(P − 2.0)/2.0 + N(0, 0.4))` → 1–5 星。
- 品牌讀到的評論：**結構化數字（平均評分、銷量、營收、對手價格） + 範本化文字評論 3–5 條**（依星等從正/中/負樣本池抽取）——保留「讀評論調整配方」行為鏈，成本近乎零。

## 5. 執行流程（每日時序）

```
Day t（t ≥ 5，free 品牌）:
  1. 品牌 Agent 讀昨日日報 + 對手情報 + 評論 → LLM 決策（1 call/品牌）
  2. 市場引擎計算當日價格/品質/廣告曝光
  3. 消費者（或群體）依效用 + Gumbel 噪音選擇品牌 / opt-out
  4. 計算銷量、營收、市占、HHI；更新資金與破產狀態
  5. 消費者試飲 → 滿意度星等 → 生成範本評論（供次日品牌閱讀）
  6. 每日記錄寫入 CSV
```

## 6. 分析配方（Q10=abc 全做，Q17=a）

| 分析 | 方法 | 對應 RQ |
| :--- | :--- | :--- |
| **XED / PED** | log-log 需求迴歸（含群組-cell-seed 固定效果、品質/行銷控制變數） | RQ1 |
| **弧彈性** | 弧彈性公式：CG vs TG 的 (ΔQ_pepsi/Q̄)/(ΔP_coke/P̄) | RQ1 |
| **外部效度** | PEP12 組：百事 +12% → 可樂市占變化 vs 2022 實證（~+2pp） | RQ5 |
| 市占 / HHI | 時間序列（圖）+ 均值比較 | RQ4 |
| 微觀轉移 | 消費者軌跡 → Markov 轉移矩陣（Coke/Pepsi/OptOut） | RQ3 |
| 策略演化 | 依百事價格/行銷軌跡分類：份額掠奪 vs 邊際跟進 vs 其他 | RQ2 |
| 品質演化 | 兩品牌品質時間序列 | RQ4 |
| 社交調節 | solo vs group 分組 XED（consumer-level 聚合） | RQ3 |
| 群體規則對照 | majority_explore vs sum 規則的 XED 比較 | Q11 |

產出：`logs/coke_pepsi/fig/*.png` + `logs/coke_pepsi/summary.json` + `docs/Beverage_Experiment_Report.md`（中文）。

## 7. 交付物清單與複現步驟

### 7.1 程式檔案

| 檔案 | 用途 |
| :--- | :--- |
| `competeai/agent/backends/deepseek.py` | DeepSeek backend（`DEEPSEEK_API_KEY`、base_url、`deepseek-chat`） |
| `competeai/scene/beverage.py` | 場景引擎：BrandAgent + 消費者效用 + 市場運算（繞過 Django） |
| `competeai/prompt_template/beverage/brand_system.txt` | 品牌系統 prompt（中文） |
| `competeai/prompt_template/beverage/daybook.txt` | 每日決策 prompt（中文 + 英文 JSON 鍵） |
| `competeai/examples/beverage.yaml` | 實驗設定（市場/品牌/消費者/網格） |
| `calibrate_beverage.py` | 消費者參數標定（PED/XED 目標） |
| `run_beverage.py` | 網格執行器（270 + 30 runs，並行 workers） |
| `analysis_beverage.py` | 計量分析 + 圖表 + summary.json |

### 7.2 複現步驟

```bash
# 1. 環境
python3 -m venv .venv && .venv/bin/pip install openai numpy pandas matplotlib PyYAML requests scienceplots seaborn
echo "DEEPSEEK_API_KEY=sk-..." > .env   # 不 commit

# 2. 標定消費者參數
.venv/bin/python calibrate_beverage.py          # -> logs/coke_pepsi/calibrated_params.json

# 3. 正式執行（9 cells × 6 組 × 5 seeds = 270 runs）
.venv/bin/python run_beverage.py --workers 5 --save-consumer

# 4. 群體規則對照（Q11）：sum 規則，anchor cell
.venv/bin/python run_beverage.py --consumers 100 --weeks 4 --group-rule sum --workers 3 --save-consumer

# 5. 分析
.venv/bin/python analysis_beverage.py           # -> summary.json + fig/*.png
```

### 7.3 輸出結構

```
logs/coke_pepsi/
├── calibrated_params.json      # 標定結果
├── summary.json                # 全部分析指標
├── fig/                        # HHI / 品質 / 市占圖
├── daily/{group}/n{n}_w{w}/seed{s}.csv       # 每日市場統計
└── consumer/{group}/n{n}_w{w}/seed{s}.csv.gz # 消費者逐日選擇軌跡
```

## 8. 預期結果與假設檢驗

| 假設 | 檢驗方式 |
| :--- | :--- |
| H1：TG2 (+10%) 模擬 XED ≈ +0.63（實證錨點） | log-log 迴歸 + 弧彈性，與 +0.63 比較 |
| H2：百事 Agent 分化出「份額掠奪」與「邊際跟進」 | 策略分類統計 |
| H3：群體消費者 XED > 單人消費者 XED | solo vs group 分組 XED |
| H4：SYM 組出現價格戰與品質提升（86.67% 品質提升理論） | 品質時間序列、HHI 收斂 |
| H5：PEP12（百事 +12%）可樂市占上升（2022 案例 ~+2pp） | 外部效度檢驗 |

## 9. 限制與偏誤聲明

- 消費者為參數化效用模型，非 LLM——捕捉穩定需求反應，但無 LLM 消費者的語言化決策過程。
- XED 偏差歸因：消費者層已標定到實證錨點，剩餘偏差反映 LLM 品牌策略層。
- 群體決策為多數決 + 探索傾向的簡化（非真實語言討論）。
- 品質為單一連續維度，未區分甜度/咖啡因等配方細項。
- 標定採用多 seed 平均；單 seed 標定值可能有 ±0.1 級別噪音。
