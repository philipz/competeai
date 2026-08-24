# BeverageTown 重放檢視器（beverage-ui）

**插畫風小鎮重放**：以 `beverage_town.jpg` 為畫布背景（粉彩暖色小鎮插畫），上層疊加 **truman 風格的程式化 pixel man**（16×16 單位格 fillRect 組合畫出小人，含走路動畫、面向、地面陰影）。直接讀取 `logs/coke_pepsi/` 的模擬資料（經 `prepare_ui_data.py` 預處理），完全離線運作。

## 功能

- 🖼️ 以 `beverage_town.jpg` 為背景，pixel man 疊加其上
- 🧍 **pixel man 消費者**：單人（隨機髮色/衣色）與群體（同群同色），每天依模擬資料走動到所選品牌（可樂店/百事店/廣場），有走路動畫與面向
- 🏷️ 叠在圖片上的商店招牌：🥤 可口可樂、🧃 百事可樂、廣場（不購買）
- ⏯️ 播放 / 暫停 / 第一天 / 時間軸拖曳（Day 1–N）
- 🎛️ 選擇實驗組（CG/TG1/TG2/TG3/SYM/PEP12/BF*）、情境（n100_w2 … n300_w6）、seed（0–4）
- 📊 右側資訊面板：每日價格、品質、行銷、銷量、市占、HHI
- 📢 每日動態：多少人轉投可樂/百事/不買

## 啟動

```bash
# 1.（資料有變動時才需要）把 logs/coke_pepsi 的 CSV 預處理成前端 JSON
cd .. && .venv/bin/python prepare_ui_data.py

# 2. 啟動 dev server
cd beverage-ui
npm install          # 首次
npm run dev          # http://localhost:5178
```

## 資料流

```
logs/coke_pepsi/
  daily/{group}/{cell}/seed{s}.csv        ← 每日市場統計
  consumer/{group}/{cell}/seed{s}.csv.gz  ← 消費者逐日選擇
        │ prepare_ui_data.py
        ▼
beverage-ui/public/data/
  index.json                              ← 480 runs 清單
  {group}/{cell}/seed{s}.json             ← 每 run 的 daily + choices
        │ fetch('/data/...')
        ▼
  BeverageTown.jsx（背景圖片 + 原生 canvas 2D 疊加 pixel man）
  + App.jsx（控制面板）
```

## 技術棧

- Vite + React 18（純前端，無後端）
- 背景：`public/beverage_town.jpg`（由原始圖縮放優化的 Web 版，css cover 顯示）
- 前景：**原生 Canvas 2D** 渲染 pixel man（fillRect 組合，同 truman 手法；無 WebGL 依賴，輕量快速）
- 資料全部為靜態 JSON（public/data）

> 想換背景圖：把新圖存成 `public/beverage_town.jpg`，並調整 `src/BeverageTown.jsx` 中的
> `COKE_POS` / `PEPSI_POS` / `PLAZA_POS` 三個虛擬座標，讓商店招牌對齊圖片上的位置。

## 視覺來源

| 來源 | 用途 |
| :--- | :--- |
| `beverage_town.jpg` | 畫布背景（粉彩暖色小鎮插畫） |
| truman（`drawFigure`） | pixel man 畫法：頭/瀏海/眼/身/腰帶/腳 + 走路 4-frame 動畫 |
| 圖片萃取色票 | UI：天藍 `#8ac8e1`、米杏 `#c1ab94`、奶油 `#f9e9d0`、酒紅 `#60232b` |

## 已知限制

- 角色「家」位置為前端依 cid 產生的固定布局（模擬本身無空間維度）
- 商店位置為前端設定的虛擬座標（疊在圖片上的合理位置），非圖片內真實建物
- 消費者的滿意度評論在前端未重現（原始資料未存評論文字，只有選擇軌跡）
