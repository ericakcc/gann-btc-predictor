# 江恩比特幣轉折點預測工具

本專案提供基於 W.D. Gann（江恩）理論的比特幣轉折時間點預測工具。

## 使用方式

### 斜線命令

```
/gann-btc 2024-11-10 high 93000, 2024-01-23 low 38500 --current 67000
```

或直接輸入 `/gann-btc` 進入互動模式。

### Python 驗算

```bash
python scripts/gann_calc.py --pivots '[{"date":"2024-11-10","type":"high","price":93000}]' --current 67000 --range 360
```

## 檔案結構

- `.claude/commands/gann-btc.md` — 斜線命令定義
- `skills/gann-theory/SKILL.md` — 核心江恩計算方法
- `references/` — 江恩週期與九宮格參考文件
- `scripts/gann_calc.py` — Python 交叉驗算腳本
- `evals/` — 測試案例
