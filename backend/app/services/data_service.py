"""데이터 CRUD + 요약 비즈니스 로직."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import get_settings
from ..errors import ConflictError, NotFoundError
from ..repositories import get_data_repo
from ..schemas import DataCreate, DataUpdate
from . import summary_service

# 요약 캐시: 채팅 요청마다 전체 데이터를 다시 읽지 않도록(Firestore 읽기 비용 절약) 메모리에 보관하고,
# 데이터가 추가·수정·삭제되면 즉시 비운다. (시드 스크립트 등 외부 변경을 위해 TTL도 둔다)
CACHE_TTL_SECONDS = 120
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _expired() -> bool:
    return time.monotonic() - _cache.get("loaded_at", 0) > CACHE_TTL_SECONDS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _all_records() -> list[dict[str, Any]]:
    with _cache_lock:
        if "records" in _cache and not _expired():
            return _cache["records"]
    records = get_data_repo().list_all()
    with _cache_lock:
        _cache.clear()
        _cache["records"] = records
        _cache["loaded_at"] = time.monotonic()
    return records


def list_data(start: Optional[str] = None, end: Optional[str] = None,
              order: str = "asc", limit: Optional[int] = None) -> list[dict[str, Any]]:
    rows = summary_service.filter_range(_all_records(), start, end)
    if order == "desc":
        rows = list(reversed(rows))
    return rows[:limit] if limit else rows


def create_data(payload: DataCreate) -> dict[str, Any]:
    repo = get_data_repo()
    d = payload.date.isoformat()
    if repo.find_by_date(d):
        raise ConflictError(f"{d} 날짜의 데이터가 이미 있습니다. 수정(PUT)을 사용하세요.")
    now = _now()
    doc = {"date": d, "value": payload.value, "memo": payload.memo, "created_at": now, "updated_at": now}
    item_id = repo.create(doc)
    invalidate_cache()
    return {"id": item_id, **doc}


def update_data(item_id: str, payload: DataUpdate) -> dict[str, Any]:
    repo = get_data_repo()
    current = repo.get(item_id)
    if not current:
        raise NotFoundError(f"ID '{item_id}' 데이터를 찾을 수 없습니다.")
    fields: dict[str, Any] = {}
    if payload.date is not None:
        d = payload.date.isoformat()
        other = repo.find_by_date(d)
        if other and other["id"] != item_id:
            raise ConflictError(f"{d} 날짜의 데이터가 이미 있습니다.")
        fields["date"] = d
    if payload.value is not None:
        fields["value"] = payload.value
    if payload.memo is not None:
        fields["memo"] = payload.memo
    fields["updated_at"] = _now()
    repo.update(item_id, fields)
    invalidate_cache()
    return {**current, **fields}


def delete_data(item_id: str) -> None:
    repo = get_data_repo()
    if not repo.get(item_id):
        raise NotFoundError(f"ID '{item_id}' 데이터를 찾을 수 없습니다.")
    repo.delete(item_id)
    invalidate_cache()


def get_summary() -> dict[str, Any]:
    records = _all_records()  # 만료되었으면 여기서 캐시 전체가 새로 고쳐진다
    with _cache_lock:
        if "summary" in _cache:
            return _cache["summary"]
    s = get_settings()
    summary = summary_service.compute_summary(records, s.data_title, s.data_unit)
    with _cache_lock:
        _cache["summary"] = summary
    return summary


def get_statistics(ma_window: int = 7) -> dict[str, Any]:
    return summary_service.compute_statistics(_all_records(), get_settings().data_unit, ma_window)


def range_report(start: Optional[str], end: Optional[str], limit: int = 62) -> dict[str, Any]:
    """특정 기간의 레코드와 기간 요약 (AI 도구 query_data_range에서 사용)"""
    rows = summary_service.filter_range(_all_records(), start, end)
    s = get_settings()
    summ = summary_service.compute_summary(rows, s.data_title, s.data_unit)
    return {"start": start, "end": end, "count": len(rows), "metrics": summ["metrics"],
            "records": [{"date": r["date"], "value": r["value"], "memo": r.get("memo", "")} for r in rows[:limit]],
            "truncated": len(rows) > limit}


def extremes(kind: str = "max", n: int = 5) -> list[dict[str, Any]]:
    rows = sorted(_all_records(), key=lambda r: float(r["value"]), reverse=(kind == "max"))
    return [{"date": r["date"], "value": r["value"], "memo": r.get("memo", "")} for r in rows[:n]]
