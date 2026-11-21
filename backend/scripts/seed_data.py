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
  python scripts/seed_data.py --csv my.csv      # date,value,memo 형식 CSV 사용 (다른 주제 데이터)
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


def rows_from_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return [{"date": r["date"], "value": float(r["value"]), "memo": r.get("memo", "")}
                for r in csv.DictReader(f) if r.get("date") and r.get("value") not in (None, "")]


def main() -> None:
    p = argparse.ArgumentParser(description="초기 시계열 데이터 적재")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--reset", action="store_true", help="기존 data 컬렉션 삭제 후 적재")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", help="Open-Meteo 응답을 저장한 JSON 파일")
    p.add_argument("--csv", help="date,value,memo 형식의 CSV 파일")
    a = p.parse_args()

    if a.csv:
        rows = rows_from_csv(a.csv)
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
