#!/usr/bin/env python3
"""
江恩比特幣轉折點預測 — Python 驗算腳本

用法：
  自動模式（從 Binance 抓取即時價格與歷史轉折點）：
  python gann_calc.py --auto --range 360
  python gann_calc.py --auto --lookback 14 --min-change 10.0 --history-days 730

  手動模式（指定參考點與價格）：
  python gann_calc.py --pivots '[{"date":"2024-11-10","type":"high","price":93000}]' --current 67000 --range 360
  python gann_calc.py --pivots '[{"date":"2024-11-10","type":"high","price":93000},{"date":"2024-01-23","type":"low","price":38500}]' --current 67000

輸出 JSON 格式的投射日期、匯聚點和九宮格計算結果。
"""

import argparse
import json
import math
import sys
import io
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from collections import defaultdict

# 修正 Windows 終端 Unicode 輸出問題
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# === 週期常數 ===

STANDARD_CYCLES = [30, 45, 60, 72, 90, 120, 144, 150, 180, 210, 225, 240, 270, 300, 315, 330, 360, 720]
SQUARE_CYCLES = [49, 64, 81, 100, 121, 144, 169, 196, 225, 256, 289, 324, 361, 400]
FIBONACCI_CYCLES = [21, 34, 55, 89, 144, 233, 377]

SEASONAL_DATES = [
    (3, 20, "春分"),
    (6, 21, "夏至"),
    (9, 22, "秋分"),
    (12, 21, "冬至"),
    (2, 4, "冬春中間點"),
    (5, 6, "春夏中間點"),
    (8, 6, "夏秋中間點"),
    (11, 6, "秋冬中間點"),
]

SQ9_ANGLES = [
    ("45°", 0.25),
    ("90°", 0.50),
    ("180°", 1.00),
    ("270°", 1.50),
    ("360°", 2.00),
]


def fetch_current_price():
    """從 Binance API 抓取比特幣即時價格。"""
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gann-btc/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return float(data["price"])
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as e:
        print(f"[錯誤] 無法從 Binance 取得即時價格: {e}", file=sys.stderr)
        print("請改用手動模式：--pivots '...' --current 價格", file=sys.stderr)
        sys.exit(1)


def fetch_ohlc_history(days=730):
    """從 Binance API 抓取比特幣日線 OHLC 歷史資料。"""
    limit = min(days, 1000)
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gann-btc/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"[錯誤] 無法從 Binance 取得歷史資料: {e}", file=sys.stderr)
        print("請改用手動模式：--pivots '...' --current 價格", file=sys.stderr)
        sys.exit(1)

    ohlc = []
    for candle in raw:
        # Binance kline 格式: [open_time, open, high, low, close, ...]
        open_time_ms = candle[0]
        dt = datetime.utcfromtimestamp(open_time_ms / 1000).date()
        ohlc.append({
            "date": dt.isoformat(),
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
        })
    return ohlc


def detect_pivots(ohlc_data, lookback=14, min_change_pct=10.0):
    """用滑動窗口偵測局部高低轉折點。

    Args:
        ohlc_data: fetch_ohlc_history() 的回傳值
        lookback: 前後各比較的天數
        min_change_pct: 最小波動百分比，過濾不顯著的轉折
    Returns:
        list of dict: [{"date": "YYYY-MM-DD", "type": "high"/"low", "price": float}]
    """
    n = len(ohlc_data)
    if n < lookback * 2 + 1:
        return []

    # 第一步：找出所有局部高點和低點
    raw_pivots = []

    for i in range(lookback, n - lookback):
        current = ohlc_data[i]

        # 局部高點：某日 high > 前後各 lookback 天的所有 high
        is_high = all(
            current["high"] > ohlc_data[j]["high"]
            for j in range(i - lookback, i + lookback + 1)
            if j != i
        )

        # 局部低點：某日 low < 前後各 lookback 天的所有 low
        is_low = all(
            current["low"] < ohlc_data[j]["low"]
            for j in range(i - lookback, i + lookback + 1)
            if j != i
        )

        if is_high:
            raw_pivots.append({
                "date": current["date"],
                "type": "high",
                "price": current["high"],
            })
        elif is_low:
            raw_pivots.append({
                "date": current["date"],
                "type": "low",
                "price": current["low"],
            })

    # 第二步：過濾，只保留波動幅度 >= min_change_pct% 的顯著轉折點
    if not raw_pivots:
        return []

    filtered = [raw_pivots[0]]

    for pivot in raw_pivots[1:]:
        last = filtered[-1]

        # 計算相對前一個轉折點的波動幅度
        if last["price"] != 0:
            change_pct = abs(pivot["price"] - last["price"]) / last["price"] * 100
        else:
            change_pct = 0

        # 同方向的轉折點，保留更極端的那個
        if pivot["type"] == last["type"]:
            if pivot["type"] == "high" and pivot["price"] > last["price"]:
                filtered[-1] = pivot
            elif pivot["type"] == "low" and pivot["price"] < last["price"]:
                filtered[-1] = pivot
        elif change_pct >= min_change_pct:
            filtered.append(pivot)

    return filtered


def get_unique_cycles():
    """取得所有不重複的週期天數及其類型標籤。"""
    seen = {}
    for c in STANDARD_CYCLES:
        if c not in seen:
            seen[c] = "標準"
    for c in SQUARE_CYCLES:
        if c not in seen:
            seen[c] = "平方"
    for c in FIBONACCI_CYCLES:
        if c not in seen:
            seen[c] = "費波那契"
    return seen


def generate_projections(pivots, today, end_date):
    """從參考點生成所有投射日期。"""
    cycles = get_unique_cycles()
    projections = []

    for pivot in pivots:
        pivot_date = datetime.strptime(pivot["date"], "%Y-%m-%d").date()
        pivot_label = f"{pivot['date']} {pivot['type']} ${pivot['price']:,}"

        for days, category in cycles.items():
            proj_date = pivot_date + timedelta(days=days)
            if today <= proj_date <= end_date:
                projections.append({
                    "date": proj_date.isoformat(),
                    "source": pivot_label,
                    "days": days,
                    "category": category,
                })

    projections.sort(key=lambda x: x["date"])
    return projections


def detect_confluences(projections, tolerance=3):
    """偵測匯聚點。"""
    if not projections:
        return []

    groups = []

    for proj in projections:
        proj_date = datetime.strptime(proj["date"], "%Y-%m-%d").date()
        placed = False

        for group in groups:
            center = datetime.strptime(group["center"], "%Y-%m-%d").date()
            if abs((proj_date - center).days) <= tolerance:
                group["members"].append(proj)
                # 更新中心為中位數
                all_dates = sorted(
                    datetime.strptime(m["date"], "%Y-%m-%d").date()
                    for m in group["members"]
                )
                mid_idx = len(all_dates) // 2
                if len(all_dates) % 2 == 0:
                    mid_idx -= 1
                group["center"] = all_dates[mid_idx].isoformat()
                placed = True
                break

        if not placed:
            groups.append({
                "center": proj["date"],
                "members": [proj],
            })

    # 計算匯聚分數
    results = []
    for group in groups:
        unique_pairs = set()
        for m in group["members"]:
            unique_pairs.add((m["source"], m["category"]))
        score = len(unique_pairs)
        if score >= 2:
            results.append({
                "date": group["center"],
                "score": score,
                "signal": "強" if score >= 5 else ("中等" if score >= 3 else "弱"),
                "contributions": [
                    f"{m['source']} +{m['days']}d ({m['category']})"
                    for m in group["members"]
                ],
            })

    results.sort(key=lambda x: (-x["score"], x["date"]))
    return results[:15]


def calculate_square_of_nine(price):
    """計算九宮格支撐/阻力。"""
    sqrt_price = math.sqrt(price)
    results = []

    for angle, increment in SQ9_ANGLES:
        row = {"angle": angle}
        row["resistance_1"] = round((sqrt_price + increment) ** 2)
        row["resistance_2"] = round((sqrt_price + 2 * increment) ** 2)
        row["support_1"] = round((sqrt_price - increment) ** 2)
        row["support_2"] = round((sqrt_price - 2 * increment) ** 2)
        results.append(row)

    return results


def calculate_harmonic_levels(price, layers=4):
    """計算音階比率（Harmonic Ratio）支撐/阻力。"""
    SEMITONE = 2 ** (1 / 12)  # ≈ 1.05946
    INTERVAL_NAMES = {1: "半音", 2: "全音", 3: "小三度", 4: "大三度"}
    results = []

    for n in range(1, layers + 1):
        ratio = SEMITONE ** n
        results.append({
            "layer": n,
            "interval": INTERVAL_NAMES[n],
            "ratio": round(ratio, 5),
            "resistance": round(price * ratio),
            "support": round(price / ratio),
        })

    return results


def calculate_percentage_levels(pivots, current_price):
    """計算百分比分割（Percentage Division）支撐/阻力。"""
    PERCENTAGES = [0.08, 0.125, 0.25, 0.333, 0.50]
    SEMITONE = 2 ** (1 / 12)
    results = []

    for pivot in pivots:
        price = pivot["price"]
        pivot_label = f"{pivot['date']} {pivot['type']} ${price:,}"

        if pivot["type"] == "high":
            for pct in PERCENTAGES:
                level = round(price * (1 - pct))
                results.append({
                    "source": pivot_label,
                    "method": f"回撤 {pct:.1%}",
                    "level": level,
                })
        elif pivot["type"] == "low":
            for pct in PERCENTAGES:
                level = round(price * (1 + pct))
                results.append({
                    "source": pivot_label,
                    "method": f"反彈 {pct:.1%}",
                    "level": level,
                })

    # 從目前價格的額外計算（群主做法）
    results.append({
        "source": f"目前價格 ${current_price:,.0f}",
        "method": "÷ 1.08 (8%折扣)",
        "level": round(current_price / 1.08),
    })
    results.append({
        "source": f"目前價格 ${current_price:,.0f}",
        "method": f"÷ {SEMITONE:.4f} (半音折扣)",
        "level": round(current_price / SEMITONE),
    })

    return results


def get_seasonal_dates(today, end_date):
    """取得預測範圍內的季節日期。"""
    results = []
    for year in range(today.year, end_date.year + 1):
        for month, day, name in SEASONAL_DATES:
            try:
                d = datetime(year, month, day).date()
                if today <= d <= end_date:
                    results.append({"date": d.isoformat(), "event": name})
            except ValueError:
                continue
    results.sort(key=lambda x: x["date"])
    return results


def check_seasonal_enhancement(confluences, seasonal_dates, tolerance=5):
    """檢查匯聚點是否有季節強化。"""
    for conf in confluences:
        conf_date = datetime.strptime(conf["date"], "%Y-%m-%d").date()
        conf["seasonal"] = None
        for sd in seasonal_dates:
            sd_date = datetime.strptime(sd["date"], "%Y-%m-%d").date()
            if abs((conf_date - sd_date).days) <= tolerance:
                conf["seasonal"] = f"{sd['event']} ({sd['date']})"
                break
    return confluences


def main():
    parser = argparse.ArgumentParser(description="江恩比特幣轉折點預測驗算")
    parser.add_argument("--pivots", required=False, default=None, help="JSON 格式的參考點陣列")
    parser.add_argument("--current", type=float, required=False, default=None, help="目前比特幣價格")
    parser.add_argument("--range", type=int, default=360, dest="pred_range", help="預測天數範圍")
    parser.add_argument("--today", default=None, help="指定今日日期 (YYYY-MM-DD)，預設為系統日期")
    parser.add_argument("--auto", action="store_true", help="自動模式：從 Binance 抓取即時價格與歷史轉折點")
    parser.add_argument("--lookback", type=int, default=14, help="轉折偵測窗口天數（預設 14）")
    parser.add_argument("--min-change", type=float, default=10.0, help="最小波動百分比（預設 10.0）")
    parser.add_argument("--history-days", type=int, default=730, help="抓取歷史天數（預設 730）")
    args = parser.parse_args()

    # 參數驗證
    if not args.auto and (args.pivots is None or args.current is None):
        parser.error("手動模式需要 --pivots 和 --current 參數，或使用 --auto 自動模式")

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else datetime.now().date()
    end_date = today + timedelta(days=args.pred_range)

    if args.auto:
        print("=== 自動模式：從 Binance 抓取資料 ===")
        print()

        # 抓取即時價格
        print("正在抓取即時價格...")
        current_price = fetch_current_price()
        print(f"即時價格: ${current_price:,.2f}")
        print()

        # 抓取歷史 OHLC
        print(f"正在抓取 {args.history_days} 天歷史日線資料...")
        ohlc = fetch_ohlc_history(args.history_days)
        print(f"取得 {len(ohlc)} 根日線 ({ohlc[0]['date']} ~ {ohlc[-1]['date']})")
        print()

        # 偵測轉折點
        print(f"正在偵測轉折點 (lookback={args.lookback}, min_change={args.min_change}%)...")
        pivots = detect_pivots(ohlc, args.lookback, args.min_change)
        print(f"偵測到 {len(pivots)} 個顯著轉折點：")
        for p in pivots:
            print(f"  {p['date']} {p['type']:>4} ${p['price']:>10,.2f}")
        print()
    else:
        pivots = json.loads(args.pivots)
        current_price = args.current

    print(f"分析日期: {today}")
    print(f"預測至: {end_date}")
    print(f"目前價格: ${current_price:,.0f}")
    print(f"參考點: {json.dumps(pivots, ensure_ascii=False)}")
    print()

    # 1. 投射日期
    projections = generate_projections(pivots, today, end_date)
    print(f"=== 投射日期 ({len(projections)} 個在範圍內) ===")
    for p in projections:
        print(f"  {p['date']} | {p['source']} | +{p['days']}d | {p['category']}")
    print()

    # 2. 匯聚偵測
    confluences = detect_confluences(projections)
    seasonal = get_seasonal_dates(today, end_date)
    confluences = check_seasonal_enhancement(confluences, seasonal)
    print(f"=== 匯聚點 ({len(confluences)} 個) ===")
    for c in confluences:
        seasonal_mark = f" 🌟{c['seasonal']}" if c.get("seasonal") else ""
        print(f"  {c['date']} | 分數 {c['score']} ({c['signal']}){seasonal_mark}")
        for contrib in c["contributions"]:
            print(f"    - {contrib}")
    print()

    # 3. 九宮格
    sq9 = calculate_square_of_nine(current_price)
    print(f"=== 九宮格 (價格 ${current_price:,.0f}) ===")
    print(f"  {'角度':<6} | {'支撐2':>10} | {'支撐1':>10} | {'阻力1':>10} | {'阻力2':>10}")
    for row in sq9:
        print(f"  {row['angle']:<6} | ${row['support_2']:>9,} | ${row['support_1']:>9,} | ${row['resistance_1']:>9,} | ${row['resistance_2']:>9,}")
    print()

    # 4. 季節日期
    print(f"=== 季節日期 ===")
    for sd in seasonal:
        print(f"  {sd['date']} | {sd['event']}")
    print()

    # 5. 音階比率
    harmonic = calculate_harmonic_levels(current_price)
    print(f"=== 音階比率 (價格 ${current_price:,.0f}) ===")
    print(f"  SEMITONE = 2^(1/12) ≈ {2 ** (1/12):.5f}")
    print(f"  {'層數':<4} | {'音程':<6} | {'比率':>8} | {'支撐':>10} | {'阻力':>10}")
    for h in harmonic:
        print(f"  {h['layer']:<4} | {h['interval']:<6} | {h['ratio']:>8.5f} | ${h['support']:>9,} | ${h['resistance']:>9,}")
    print()

    # 6. 百分比分割
    pct_levels = calculate_percentage_levels(pivots, current_price)
    print(f"=== 百分比分割 ===")
    for pl in pct_levels:
        print(f"  {pl['source']} | {pl['method']} | ${pl['level']:>10,}")
    print()

    # 7. JSON 輸出
    output = {
        "analysis_date": today.isoformat(),
        "end_date": end_date.isoformat(),
        "current_price": current_price,
        "pivots": pivots,
        "projections": projections,
        "confluences": confluences,
        "square_of_nine": sq9,
        "seasonal_dates": seasonal,
        "harmonic_levels": harmonic,
        "percentage_levels": pct_levels,
    }

    with open("gann_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("完整結果已輸出至 gann_output.json")


if __name__ == "__main__":
    main()
