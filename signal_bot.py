import os
import sys

import pandas as pd
import requests
import yfinance as yf

TOKEN = os.environ["TG_TOKEN"]
CHAT = os.environ["TG_CHAT"]
TEST = os.environ.get("TEST", "").lower() in ("1", "true", "yes")

SYMBOL = "GC=F"
SL_MULT = 1.5
RR = 1.5
MAX_AGE_MIN = 10


def send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT, "text": text}, timeout=20)
    r.raise_for_status()


def calc_rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def calc_atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def main():
    df = yf.download(SYMBOL, period="5d", interval="5m", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    df = df.dropna()
    if len(df) < 250:
        print("not enough data (market may be closed)")
        return

    df = df.iloc[:-1]

    df["fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["slow"] = df["close"].ewm(span=21, adjust=False).mean()
    df["trend"] = df["close"].ewm(span=200, adjust=False).mean()
    df["rsi"] = calc_rsi(df["close"])
    df["atr"] = calc_atr(df)

    h = df["close"].resample("1h").last().dropna().iloc[:-1]
    htf_bull = h.iloc[-1] > h.ewm(span=50, adjust=False).mean().iloc[-1]

    prev, cur = df.iloc[-2], df.iloc[-1]
    bar_close_time = df.index[-1] + pd.Timedelta(minutes=5)
    age_min = (pd.Timestamp.now(tz=df.index.tz) - bar_close_time).total_seconds() / 60

    cross_up = prev["fast"] <= prev["slow"] and cur["fast"] > cur["slow"]
    cross_dn = prev["fast"] >= prev["slow"] and cur["fast"] < cur["slow"]

    buy = cross_up and cur["close"] > cur["trend"] and 50 < cur["rsi"] < 70 and htf_bull
    sell = cross_dn and cur["close"] < cur["trend"] and 30 < cur["rsi"] < 50 and not htf_bull

    price, atr = float(cur["close"]), float(cur["atr"])
    sl_d = atr * SL_MULT

    if TEST:
        send(
            "✅ บอทพร้อมทำงาน\n"
            f"ราคาทอง (GC=F): {price:.2f}\n"
            f"RSI: {cur['rsi']:.1f} | ATR: {atr:.2f}\n"
            f"เทรนด์ 5 นาที: {'ขึ้น' if price > cur['trend'] else 'ลง'} | "
            f"เทรนด์ 1 ชม.: {'ขึ้น' if htf_bull else 'ลง'}"
        )
        return

    if age_min > MAX_AGE_MIN:
        print(f"no new signal (last bar closed {age_min:.0f} min ago)")
        return

    if buy:
        sl, tp = price - sl_d, price + sl_d * RR
        send(
            "🟢 BUY ทอง\n"
            f"เข้า: {price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\n"
            "TF: M5 | ไม่ใช่คำแนะนำการลงทุน ใช้ความเสี่ยงต่อไม้ต่ำ ๆ"
        )
    elif sell:
        sl, tp = price + sl_d, price - sl_d * RR
        send(
            "🔴 SELL ทอง\n"
            f"เข้า: {price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\n"
            "TF: M5 | ไม่ใช่คำแนะนำการลงทุน ใช้ความเสี่ยงต่อไม้ต่ำ ๆ"
        )
    else:
        print("no signal")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("error:", e)
        sys.exit(1)
