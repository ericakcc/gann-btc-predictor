# 江恩比特幣轉折點預測工具

基於 W.D. Gann（江恩）理論的比特幣轉折時間點預測工具。透過多重時間週期匯聚分析，找出未來最可能出現趨勢轉折的日期。

## 功能特色

- **自動模式** — 從 Binance API 即時抓取 BTC 價格與歷史 K 線，自動偵測轉折點
- **時間週期投射** — 標準江恩週期、完全平方數、費波那契數三大類別
- **匯聚偵測** — 當多個獨立週期指向同一日期時，轉折概率大幅上升
- **九宮格（Square of Nine）** — 計算價格支撐/阻力位
- **音階比率（Harmonic Ratio）** — 基於十二平均律的支撐/阻力計算
- **百分比分割** — 江恩經典回撤/反彈百分比
- **季節強化** — 春分、夏至、秋分、冬至等關鍵日期比對
- **零外部依賴** — 只使用 Python 標準庫

## 快速開始

### 自動模式（推薦）

```bash
python scripts/gann_calc.py --auto
```

自動從 Binance 抓取即時價格、歷史日線資料，偵測轉折點並執行完整分析。

### 自訂偵測參數

```bash
python scripts/gann_calc.py --auto --lookback 21 --min-change 15 --history-days 1000 --range 720
```

| 參數 | 預設 | 說明 |
|------|------|------|
| `--lookback` | 14 | 轉折偵測窗口天數，越大轉折點越少但越顯著 |
| `--min-change` | 10.0 | 最小波動百分比，過濾不顯著的小幅轉折 |
| `--history-days` | 730 | 抓取歷史天數（最大 1000） |
| `--range` | 360 | 預測未來天數 |

### 手動模式

```bash
python scripts/gann_calc.py \
  --pivots '[{"date":"2024-11-10","type":"high","price":93000},{"date":"2024-01-23","type":"low","price":38500}]' \
  --current 67000 \
  --range 360
```

## 輸出範例

```
=== 自動模式：從 Binance 抓取資料 ===

即時價格: $67,446.97
取得 730 根日線 (2024-02-24 ~ 2026-02-22)
偵測到 30 個顯著轉折點

=== 匯聚點 (15 個) ===
  2026-03-19 | 分數 13 (強) 🌟春分 (2026-03-20)
  2026-02-27 | 分數 12 (強)
  2026-03-05 | 分數 11 (強)
  ...
```

完整 JSON 結果會輸出至 `gann_output.json`。

## 專案結構

```
├── scripts/
│   └── gann_calc.py          # 主程式（支援自動/手動模式）
├── skills/
│   └── gann-theory/
│       └── SKILL.md           # 核心江恩計算方法文件
├── references/
│   ├── gann-cycles.md         # 江恩週期參考
│   ├── square-of-nine.md      # 九宮格參考
│   └── harmonic-ratio.md      # 音階比率參考
├── evals/                     # 測試案例
├── .claude/
│   └── commands/
│       └── gann-btc.md        # Claude Code 斜線命令定義
├── CLAUDE.md                  # Claude Code 專案指示
└── README.md
```

## Claude Code 整合

本專案也可在 [Claude Code](https://claude.com/claude-code) 中使用斜線命令：

```
/gann-btc --auto
/gann-btc 2024-11-10 high 93000, 2024-01-23 low 38500 --current 67000
```

或輸入 `/gann-btc` 進入互動問答模式。

## 江恩理論簡介

W.D. Gann 認為市場依循自然法則運行，**時間是最重要的因素**。核心思路：

1. 從歷史重要高低點出發，加上特定天數（週期）得到「投射日期」
2. 當多個獨立週期從不同參考點同時指向同一日期時（**匯聚**），該日期出現轉折的概率大幅上升
3. 配合九宮格、音階比率等工具判斷關鍵價位

詳細計算方法請參閱 [`skills/gann-theory/SKILL.md`](skills/gann-theory/SKILL.md)。

## 免責聲明

本工具基於江恩理論的數學模式識別，僅供教育與研究用途，不構成投資建議。加密貨幣波動劇烈，請自行評估風險。
