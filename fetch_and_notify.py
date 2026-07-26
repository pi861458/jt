"""
為替カレンダー通知スクリプト
Forex Factoryの週次JSONフィードから当日分の経済指標・休場情報を取得し、
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

IMPACT_EMOJI = {
    "High": "🔴",
    "Medium": "🟡",
    "Low": "⚪",
    "Holiday": "🏖️",
}


def fetch_calendar():
    """Forex Factoryの週次カレンダーJSONを取得する"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(FF_CALENDAR_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def to_jst(date_str):
    """FFの日付文字列(ISO8601)をJSTのdatetimeに変換"""
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.astimezone(JST)


def filter_today(events):
    """JSTで「今日」に該当するイベントだけ抽出"""
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
    high = [(dt_, e) for dt_, e in today_events if e.get("impact") == "High"]
    medium = [(dt_, e) for dt_, e in today_events if e.get("impact") == "Medium"]
    low = [(dt_, e) for dt_, e in today_events if e.get("impact") == "Low"]

    lines = []

    if holidays:
        lines.append("🏖️ 本日の休場")
        for e in holidays:
            lines.append(f"　・{e.get('country', '')} {e.get('title', '')}")
        lines.append("")
    else:
        lines.append("🏖️ 本日、主要市場の休場情報はありません")
        lines.append("")

    def section(title, items):
        if not items:
            return
        lines.append(title)
        for dt_, e in items:
            time_str = dt_.strftime("%H:%M")
            country = e.get("country", "")
            name = e.get("title", "")
            forecast = e.get("forecast", "")
            previous = e.get("previous", "")
            extra = ""
            if forecast or previous:
                extra = f"（予想:{forecast or '-'} / 前回:{previous or '-'}）"
            lines.append(f"　{time_str} [{country}] {name} {extra}")
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
