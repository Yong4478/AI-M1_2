"""시계열 분석 → 요약 정보 생성 (순수 함수, DB·HTTP에 의존하지 않음).

요약은 두 곳에서 쓰인다.
  1) GET /api/data/summary 응답 (프론트 요약 카드)
  2) POST /api/chat 시스템 프롬프트 주입 (컨텍스트 주입)
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

TREND_WINDOW = 7          # 최근 7일 vs 직전 7일 비교
MONTHLY_LIMIT = 12        # 프롬프트에 넣을 최근 월 수


STALE_DAYS = 7           # 데이터가 오늘보다 이만큼 넘게 오래되면 '과거 데이터'로 본다


def reference_info(end: str | None, mode: str = "auto", today: date | None = None) -> dict[str, Any]:
    """분석 기준일을 정한다.

    과거 데이터(예: 2024년)로 서비스할 때 '이번 달', '최근 일주일'을 오늘(2026년)로 해석하면 답할 수 없으므로,
    데이터의 마지막 날짜를 기준일로 삼아 상대적인 기간을 해석하게 한다.
    """
    today = today or date.today()
    if mode not in ("auto", "today"):
        ref = date.fromisoformat(mode)                       # 직접 지정
        return {"reference_date": ref.isoformat(), "is_historical": ref < today - timedelta(days=STALE_DAYS)}
    if mode == "today" or not end:
        return {"reference_date": today.isoformat(), "is_historical": False}
    last = date.fromisoformat(end)
    if (today - last).days > STALE_DAYS:
        return {"reference_date": last.isoformat(), "is_historical": True}
    return {"reference_date": today.isoformat(), "is_historical": False}


def _r(v: float, d: int = 2) -> float:
    return round(float(v), d)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def monthly_stats(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in records:
        groups[r["date"][:7]].append(float(r["value"]))
    return [{"month": m, "count": len(v), "average": _r(statistics.fmean(v)), "max": _r(max(v)), "min": _r(min(v))}
            for m, v in sorted(groups.items())]


def trend_of(values: list[float], window: int = TREND_WINDOW, threshold: float | None = None) -> dict[str, Any]:
    """최근 window개 평균과 그 직전 window개 평균을 비교해 상승/하락/유지를 판단한다.

    threshold(변화 판정 기준)를 주지 않으면 전체 표준편차의 10%를 쓴다.
    → 데이터 단위(℃, 원, 분 등)가 달라도 같은 규칙으로 판단할 수 있다.
    """
    if len(values) < window * 2:
        return {"direction": "판단 불가", "window_days": window}
    recent = statistics.fmean(values[-window:])
    previous = statistics.fmean(values[-2 * window:-window])
    change = recent - previous
    if threshold is None:
        threshold = (statistics.pstdev(values) * 0.1) if len(values) > 1 else 0.0
    direction = "유지" if abs(change) <= threshold else ("상승" if change > 0 else "하락")
    pct = (change / abs(previous) * 100) if previous not in (0, 0.0) else None
    return {"direction": direction, "window_days": window, "recent_average": _r(recent),
            "previous_average": _r(previous), "change": _r(change),
            "change_pct": None if pct is None else _r(pct, 1)}


def compute_summary(records: list[dict[str, Any]], title: str, unit: str) -> dict[str, Any]:
    """records: date 오름차순 정렬된 [{date, value, memo}, ...]"""
    if not records:
        return {"title": title, "unit": unit, "period": "데이터 없음", "start": None, "end": None, "count": 0,
                "metrics": None, "trend": "데이터 없음", "trend_detail": {"direction": "판단 불가", "window_days": TREND_WINDOW},
                "monthly": [], "generated_at": _now()}

    records = sorted(records, key=lambda r: r["date"])
    values = [float(r["value"]) for r in records]
    i_max = max(range(len(values)), key=values.__getitem__)
    i_min = min(range(len(values)), key=values.__getitem__)
    td = trend_of(values)

    if td["direction"] == "판단 불가":
        trend_text = f"판단 불가 (데이터가 {TREND_WINDOW * 2}개 미만)"
    else:
        trend_text = (f"{td['direction']} (최근 {TREND_WINDOW}일 평균 {td['recent_average']}{unit}, "
                      f"직전 {TREND_WINDOW}일 대비 {td['change']:+}{unit})")

    return {
        "title": title,
        "unit": unit,
        "period": f"{records[0]['date']} ~ {records[-1]['date']}",
        "start": records[0]["date"],
        "end": records[-1]["date"],
        "count": len(records),
        "metrics": {
            "average": _r(statistics.fmean(values)),
            "median": _r(statistics.median(values)),
            "max": {"value": _r(values[i_max]), "date": records[i_max]["date"]},
            "min": {"value": _r(values[i_min]), "date": records[i_min]["date"]},
            "std": _r(statistics.pstdev(values)) if len(values) > 1 else 0.0,
            "total": _r(sum(values)),
            "latest": {"value": _r(values[-1]), "date": records[-1]["date"]},
        },
        "trend": trend_text,
        "trend_detail": td,
        "monthly": monthly_stats(records)[-MONTHLY_LIMIT:],
        "generated_at": _now(),
    }


def compute_statistics(records: list[dict[str, Any]], unit: str, ma_window: int = 7) -> dict[str, Any]:
    """(보너스) 확장 통계: 이동평균 시계열, 전일 대비 변화량(변동성), 요일별 평균, 월별 통계"""
    records = sorted(records, key=lambda r: r["date"])
    values = [float(r["value"]) for r in records]
    series = []
    for i, r in enumerate(records):
        window = values[max(0, i - ma_window + 1): i + 1]
        series.append({"date": r["date"], "value": values[i],
                       "moving_average": _r(statistics.fmean(window)) if len(window) == ma_window else None})

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    by_wd: dict[int, list[float]] = defaultdict(list)
    for r in records:
        by_wd[date.fromisoformat(r["date"]).weekday()].append(float(r["value"]))

    biggest_rise = max(range(len(changes)), key=changes.__getitem__) if changes else None
    biggest_drop = min(range(len(changes)), key=changes.__getitem__) if changes else None
    return {
        "unit": unit,
        "count": len(records),
        "moving_average_window": ma_window,
        "series": series,
        "volatility": {
            "daily_change_std": _r(statistics.pstdev(changes)) if len(changes) > 1 else None,
            "mean_abs_change": _r(statistics.fmean(abs(c) for c in changes)) if changes else None,
            "biggest_rise": None if biggest_rise is None else
            {"date": records[biggest_rise + 1]["date"], "change": _r(changes[biggest_rise])},
            "biggest_drop": None if biggest_drop is None else
            {"date": records[biggest_drop + 1]["date"], "change": _r(changes[biggest_drop])},
        },
        "weekday_average": [{"weekday": weekday_names[k], "average": _r(statistics.fmean(v)), "count": len(v)}
                            for k, v in sorted(by_wd.items())],
        "monthly": monthly_stats(records),
        "generated_at": _now(),
    }


def filter_range(records: list[dict[str, Any]], start: str | None, end: str | None) -> list[dict[str, Any]]:
    return [r for r in records if (not start or r["date"] >= start) and (not end or r["date"] <= end)]
