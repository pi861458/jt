"""
為替カレンダー通知スクリプト（ゴールド重視版）
Forex Factoryの週次JSONフィードから当日分の経済指標・休場情報を取得し、
日本語に翻訳した上で、ゴールド(XAUUSD)に影響が大きい指標を目立たせて
ntfy経由でiPhoneに通知する。
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import requests

# --- 設定 ---
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
JST = timezone(timedelta(hours=9))

# --- 指標名の日本語訳辞書 ---
# キーはFFの英語表記（小文字化・前後空白除去して比較）。
# 完全一致しないものは元の英語名のまま表示する。
TRANSLATIONS = {
    "non-farm employment change": "非農業部門雇用者数（NFP）",
    "unemployment rate": "失業率",
    "average hourly earnings m/m": "平均時給（前月比）",
    "cpi m/m": "消費者物価指数（前月比）",
    "cpi y/y": "消費者物価指数（前年比）",
    "core cpi m/m": "コアCPI（前月比）",
    "core cpi y/y": "コアCPI（前年比）",
    "ppi m/m": "生産者物価指数（前月比）",
    "core ppi m/m": "コア生産者物価指数（前月比）",
    "pce price index m/m": "PCEデフレーター（前月比）",
    "core pce price index m/m": "コアPCEデフレーター（前月比）",
    "fomc statement": "FOMC声明",
    "fomc meeting minutes": "FOMC議事録",
    "federal funds rate": "FF金利（政策金利）",
    "fed chair powell speaks": "パウエルFRB議長 発言",
    "gdp q/q": "GDP（前期比）",
    "advance gdp q/q": "GDP速報値（前期比）",
    "prelim gdp q/q": "GDP改定値（前期比）",
    "retail sales m/m": "小売売上高（前月比）",
    "core retail sales m/m": "コア小売売上高（前月比）",
    "ism manufacturing pmi": "ISM製造業景況指数",
    "ism services pmi": "ISM非製造業（サービス業）景況指数",
    "ism manufacturing prices": "ISM製造業価格指数",
    "prelim upmc consumer sentiment": "ミシガン大学消費者信頼感指数（速報）",
    "consumer confidence": "消費者信頼感指数",
    "building permits": "建設許可件数",
    "housing starts": "住宅着工件数",
    "existing home sales": "中古住宅販売件数",
    "new home sales": "新築住宅販売件数",
    "durable goods orders m/m": "耐久財受注（前月比）",
    "core durable goods orders m/m": "コア耐久財受注（前月比）",
    "trade balance": "貿易収支",
    "initial jobless claims": "新規失業保険申請件数",
    "jolts job openings": "JOLTS求人件数",
    "adp non-farm employment change": "ADP雇用統計",
    "crude oil inventories": "原油在庫",
    "german ifo business climate": "独Ifo企業景況感指数",
    "ecb press conference": "ECB記者会見",
    "ecb main refinancing rate": "ECB主要政策金利",
    "boe gov bailey speaks": "イングランド銀行総裁 発言",
    "monetary policy statement": "金融政策声明",
    "boj gov ueda speaks": "日銀総裁 発言",
    "core national cpi y/y": "全国コアCPI（前年比）",
}

# --- ゴールド(XAUUSD)への影響が大きい指標のキーワード ---
# 米国のインフレ・雇用・金利・地政学関連が中心。
GOLD_KEYWORDS = [
    "non-farm", "nfp", "unemployment", "cpi", "ppi", "pce",
    "fomc", "federal funds", "fed chair", "powell", "rate decision",
    "interest rate", "gdp", "ism manufacturing", "ism services",
    "retail sales", "jobless claims", "jolts", "adp",
    "consumer sentiment", "consumer confidence",
]
GOLD_CURRENCIES = {"USD"}  # ゴールドはドル建てのためUSD指標が最重要

IMPACT_EMOJI = {
    "High": "🔴",
    "Medium": "🟡",
    "Low": "⚪",
    "Holiday": "🏖️",
}


def translate(title):
    key = title.strip().lower()
    return TRANSLATIONS.get(key, title)


def is_gold_relevant(event):
    """ゴールド(XAUUSD)に影響が大きい指標かどうかを判定"""
    if event.get("country") not in GOLD_CURRENCIES:
        return False
    if event.get("impact") not in ("High", "Medium"):
        return False
    title_lower = event.get("title", "").lower()
    return any(kw in title_lower for kw in GOLD_KEYWORDS)


def fetch_calendar():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(FF_CALENDAR_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def to_jst(date_str):
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.astimezone(JST)


def filter_today(events):
    today = datetime.now(JST).date()
    result = []
    for e in events:
        date_str = e.get("date")
        if not date_str:
            continue
        try:
            dt_jst = to_jst(date_str)
        except (ValueError, TypeError):
            continue
        if dt_jst.date() == today:
            result.append((dt_jst, e))
    result.sort(key=lambda pair: pair[0])
    return result


def build_message(today_events):
    if not today_events:
        return "本日は主要な経済指標・イベントの登録がありません。"

    holidays = [e for dt_, e in today_events if e.get("impact") == "Holiday"]
    gold_events = [(dt_, e) for dt_, e in today_events if is_gold_relevant(e)]
    high = [(dt_, e) for dt_, e in today_events if e.get("impact") == "High"]
    medium = [(dt_, e) for dt_, e in today_events if e.get("impact") == "Medium"]
    low = [(dt_, e) for dt_, e in today_events if e.get("impact") == "Low"]

    lines = []

    # --- 休場情報 ---
    if holidays:
        lines.append("🏖️ 本日の休場")
        for e in holidays:
            lines.append(f"　・{e.get('country', '')} {translate(e.get('title', ''))}")
        lines.append("")
    else:
        lines.append("🏖️ 本日、主要市場の休場情報はありません")
        lines.append("")

    # --- ゴールド注目指標（最優先で表示） ---
    if gold_events:
        lines.append("✨ ゴールドに影響しそうなのはコレ！")
        for dt_, e in gold_events:
            time_str = dt_.strftime("%H:%M")
            name = translate(e.get("title", ""))
            forecast = e.get("forecast", "")
            previous = e.get("previous", "")
            extra = ""
            if forecast or previous:
                extra = f"（予想:{forecast or '-'} / 前回:{previous or '-'}）"
            lines.append(f"　{time_str} {name} {extra}")
        lines.append("")

    # --- 重要度別の全体一覧 ---
    def section(title, items):
        if not items:
            return
        lines.append(title)
        for dt_, e in items:
            time_str = dt_.strftime("%H:%M")
            country = e.get("country", "")
            name = translate(e.get("title", ""))
            forecast = e.get("forecast", "")
            previous = e.get("previous", "")
            extra = ""
            if forecast or previous:
                extra = f"（予想:{forecast or '-'} / 前回:{previous or '-'}）"
            star = "★ " if is_gold_relevant(e) else "　"
            lines.append(f"{star}{time_str} [{country}] {name} {extra}")
        lines.append("")

    section("🔴 重要指標（High）", high)
    section("🟡 中重要度（Medium）", medium)
    section("⚪ 低重要度（Low）", low)

    return "\n".join(lines).strip()


def send_ntfy(message, title="本日の為替カレンダー"):
    if not NTFY_TOPIC:
        print("ERROR: NTFY_TOPIC が設定されていません", file=sys.stderr)
        sys.exit(1)

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    resp = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": "default",
            "Tags": "moneybag",
        },
        timeout=10,
    )
    resp.raise_for_status()


def main():
    try:
        events = fetch_calendar()
    except Exception as e:
        send_ntfy(f"データ取得に失敗しました: {e}", title="⚠️ 為替カレンダー取得エラー")
        raise

    today_events = filter_today(events)
    message = build_message(today_events)
    send_ntfy(message)
    print("通知を送信しました。")
    print(message)


if __name__ == "__main__":
    main()
