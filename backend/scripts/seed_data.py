"""초기 데이터 적재: 서울 최근 1년 일별 기온 → Firestore `data` 컬렉션

데이터 출처: Open-Meteo Historical Weather API (API 키 불필요, CC BY 4.0)
  - value : 일평균 기온(℃)
  - memo  : 최고/최저 기온과 강수량

실행 (backend 폴더에서):
  python scripts/seed_data.py               # 최근 365일 적재 (이미 있는 날짜는 건너뜀)
  python scripts/seed_data.py --reset       # 기존 data 컬렉션을 비우고 새로 적재
  python scripts/seed_data.py --days 200    # 기간 변경
  python scripts/seed_data.py --dry-run     # 저장하지 않고 받아오기만 확인
  python scripts/seed_data.py --json raw.json   # 브라우저로 저장한 API 응답 파일 사용
  python scripts/seed_data.py --csv my.csv --last 365 --reset   # 내 CSV 사용 (열 이름 자동 인식)
  python scripts/seed_data.py --csv my.csv --value-col "평균기온(°C)"  # 값 열 직접 지정
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend 폴더를 import 경로에 추가

from app.repositories import get_data_repo  # noqa: E402

LAT, LON = 37.5665, 126.9780  # 서울시청
API = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_DELAY_DAYS = 6       # 과거 자료 API는 최근 며칠이 아직 비어 있을 수 있다


def build_url(days: int) -> str:
    end = date.today() - timedelta(days=ARCHIVE_DELAY_DAYS)
    start = end - timedelta(days=days - 1)
    params = {"latitude": LAT, "longitude": LON, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
              "timezone": "Asia/Seoul"}
    return f"{API}?{urllib.parse.urlencode(params)}"


def rows_from_open_meteo(data: dict) -> list[dict]:
    d = data["daily"]
    rows = []
    for i, day in enumerate(d["time"]):
        mean = d["temperature_2m_mean"][i]
        if mean is None:
            continue  # 결측일은 건너뜀
        tmax, tmin, rain = d["temperature_2m_max"][i], d["temperature_2m_min"][i], d["precipitation_sum"][i]
        memo = f"최고 {tmax}℃ / 최저 {tmin}℃"
        if rain:
            memo += f" / 강수 {rain}mm"
        rows.append({"date": day, "value": round(float(mean), 1), "memo": memo})
    return rows


# CSV 열 이름 자동 인식 후보 (소문자·공백 제거 후 비교)
DATE_CANDIDATES = ["date", "날짜", "일자", "일시", "datetime", "time", "tm"]
VALUE_CANDIDATES = ["value", "값", "tmean", "평균기온(°c)", "평균기온(℃)", "평균기온", "temperature", "temp", "close", "종가"]
MEMO_CANDIDATES = ["memo", "메모", "note", "notes", "비고"]
WEATHER_MEMO_COLS = [("tmax", "최고", "℃"), ("tmin", "최저", "℃"), ("precip", "강수", "mm")]  # 이전 분석 과제 CSV 형식


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def _pick(columns: list[str], wanted: str | None, candidates: list[str], label: str) -> str | None:
    by_norm = {_norm(c): c for c in columns}
    if wanted:
        if _norm(wanted) not in by_norm:
            sys.exit(f"❌ {label} 열 '{wanted}'이(가) 없습니다. CSV 열: {columns}")
        return by_norm[_norm(wanted)]
    return next((by_norm[_norm(c)] for c in candidates if _norm(c) in by_norm), None)


def _is_zero(text: str) -> bool:
    try:
        return float(text) == 0
    except ValueError:
        return False


def _parse_date(text: str) -> str | None:
    t = text.strip()[:10].replace("/", "-").replace(".", "-")
    if len(t) == 8 and t.isdigit():                      # 20240101
        t = f"{t[:4]}-{t[4:6]}-{t[6:]}"
    try:
        return date.fromisoformat(t).isoformat()
    except ValueError:
        return None


def _read_csv(path: str) -> tuple[list[str], list[dict]]:
    for enc in ("utf-8-sig", "cp949"):                   # 엑셀·공공데이터 CSV는 cp949인 경우가 많다
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader.fieldnames or []), list(reader)
        except UnicodeDecodeError:
            continue
    sys.exit("❌ CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장해 주세요.")


def rows_from_csv(path: str, date_col: str | None = None, value_col: str | None = None,
                  memo_col: str | None = None) -> list[dict]:
    """다양한 형식의 CSV를 (date, value, memo)로 바꾼다.

    - 열 이름 자동 인식: date/날짜/일시, value/값/tmean/평균기온 등
    - 이전 분석 과제 CSV(date,tmax,tmin,tmean,precip)는 tmean을 값으로, 최고/최저/강수를 메모로 사용
    - 날짜 형식: 2024-01-01, 2024/01/01, 2024.01.01, 20240101, 2024-01-01 09:00
    - 같은 날짜가 여러 번 나오면 첫 행만 사용, 값이 비었거나 숫자가 아니면 건너뜀
    """
    columns, raw = _read_csv(path)
    dcol = _pick(columns, date_col, DATE_CANDIDATES, "날짜")
    vcol = _pick(columns, value_col, VALUE_CANDIDATES, "값")
    mcol = _pick(columns, memo_col, MEMO_CANDIDATES, "메모")
    if not dcol or not vcol:
        sys.exit(f"❌ 날짜/값 열을 찾지 못했습니다. CSV 열: {columns}\n"
                 "   --date-col, --value-col 옵션으로 열 이름을 직접 지정하세요.")
    weather = [(c, label, u) for c, label, u in WEATHER_MEMO_COLS if _pick(columns, None, [c], c)] if not mcol else []
    print(f"🔎 열 매핑: 날짜='{dcol}', 값='{vcol}', 메모='{mcol or ('자동(' + ', '.join(c for c, *_ in weather) + ')' if weather else '없음')}'")

    rows, seen, skipped = [], set(), 0
    for r in raw:
        d = _parse_date(r.get(dcol) or "")
        try:
            v = float(str(r.get(vcol, "")).replace(",", ""))
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError
        except ValueError:
            v = None
        if not d or v is None or d in seen:
            skipped += 1
            continue
        seen.add(d)
        if mcol:
            memo = (r.get(mcol) or "").strip()
        else:
            parts = []
            for c, label, u in weather:
                val = (r.get(c) or "").strip()
                if not val or (label == "강수" and _is_zero(val)):
                    continue                     # 빈 값, 강수 0mm는 메모에서 생략
                parts.append(f"{label} {val}{u}")
            memo = " / ".join(parts)
        rows.append({"date": d, "value": round(v, 2), "memo": memo[:200]})
    if skipped:
        print(f"   (날짜·값이 비었거나 형식 오류, 중복 날짜 {skipped}행 건너뜀)")
    return sorted(rows, key=lambda x: x["date"])


def filter_rows(rows: list[dict], start: str | None, end: str | None, last: int | None) -> list[dict]:
    if start:
        rows = [r for r in rows if r["date"] >= start]
    if end:
        rows = [r for r in rows if r["date"] <= end]
    if last:
        rows = rows[-last:]
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="초기 시계열 데이터 적재")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--reset", action="store_true", help="기존 data 컬렉션 삭제 후 적재")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", help="Open-Meteo 응답을 저장한 JSON 파일")
    p.add_argument("--csv", help="CSV 파일 (열 이름 자동 인식)")
    p.add_argument("--date-col", help="CSV 날짜 열 이름 (자동 인식이 안 될 때)")
    p.add_argument("--value-col", help="CSV 값 열 이름 (예: tmean, 평균기온(°C))")
    p.add_argument("--memo-col", help="CSV 메모 열 이름")
    p.add_argument("--start", help="이 날짜 이후만 사용 (YYYY-MM-DD)")
    p.add_argument("--end", help="이 날짜 이전만 사용 (YYYY-MM-DD)")
    p.add_argument("--last", type=int, help="가장 최근 N개만 사용 (예: 365)")
    a = p.parse_args()

    if a.csv:
        rows = rows_from_csv(a.csv, a.date_col, a.value_col, a.memo_col)
    elif a.json:
        rows = rows_from_open_meteo(json.loads(Path(a.json).read_text(encoding="utf-8")))
    else:
        url = build_url(a.days)
        print(f"📥 요청: {url}")
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                rows = rows_from_open_meteo(json.loads(resp.read().decode("utf-8")))
        except Exception as e:
            print(f"❌ 다운로드 실패: {e}\n   위 URL을 브라우저로 열어 raw.json으로 저장한 뒤 --json raw.json 으로 다시 실행하세요.")
            sys.exit(1)

    rows = filter_rows(rows, a.start, a.end, a.last)
    if len(rows) > 2000:
        print(f"⚠️  {len(rows)}개는 Firestore 무료 한도(일 읽기 5만 회)에 부담이 됩니다. --last 365 처럼 줄이는 것을 권장합니다.")
    if not rows:
        sys.exit("❌ 적재할 데이터가 없습니다.")
    print(f"✅ {len(rows)}개 준비: {rows[0]['date'] if rows else '-'} ~ {rows[-1]['date'] if rows else '-'}")
    if len(rows) < 100:
        print("⚠️  데이터가 100개 미만입니다. 과제 조건(100개 이상)을 확인하세요.")
    if a.dry_run:
        print("   (dry-run: 저장하지 않음)", rows[:3])
        return

    repo = get_data_repo()
    if a.reset:
        print(f"🗑  기존 데이터 {repo.delete_all()}개 삭제")
        existing = set()
    else:
        existing = {r["date"] for r in repo.list_all()}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_rows = [{**r, "created_at": now, "updated_at": now} for r in rows if r["date"] not in existing]
    n = repo.bulk_create(new_rows)
    print(f"💾 {n}개 저장 완료 (이미 있던 날짜 {len(rows) - n}개 건너뜀)")


if __name__ == "__main__":
    main()
