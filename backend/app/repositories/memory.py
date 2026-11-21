"""메모리 저장소 (USE_MEMORY_DB=true).

Firebase를 설정하기 전에 로컬에서 화면·API를 먼저 확인하거나, 테스트할 때만 쓴다.
서버를 재시작하면 데이터가 사라진다. 배포 환경에서는 반드시 Firestore를 사용한다.
"""

from __future__ import annotations

import copy
import threading
import uuid
from typing import Any, Optional


class MemoryDataRepository:
    def __init__(self):
        self._rows: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(({"id": k, **copy.deepcopy(v)} for k, v in self._rows.items()), key=lambda r: r["date"])

    def get(self, item_id: str) -> Optional[dict[str, Any]]:
        row = self._rows.get(item_id)
        return {"id": item_id, **copy.deepcopy(row)} if row else None

    def find_by_date(self, date: str) -> Optional[dict[str, Any]]:
        for k, v in self._rows.items():
            if v["date"] == date:
                return {"id": k, **copy.deepcopy(v)}
        return None

    def create(self, data: dict[str, Any]) -> str:
        item_id = uuid.uuid4().hex[:20]
        with self._lock:
            self._rows[item_id] = copy.deepcopy(data)
        return item_id

    def update(self, item_id: str, fields: dict[str, Any]) -> None:
        with self._lock:
            self._rows[item_id].update(copy.deepcopy(fields))

    def delete(self, item_id: str) -> None:
        with self._lock:
            self._rows.pop(item_id, None)

    def bulk_create(self, rows: list[dict[str, Any]]) -> int:
        for r in rows:
            self.create(r)
        return len(rows)

    def delete_all(self) -> int:
        with self._lock:
            n = len(self._rows)
            self._rows.clear()
            return n


class MemoryConversationRepository:
    def __init__(self):
        self._rows: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def list(self, limit: int) -> list[dict[str, Any]]:
        rows = [{"id": k, **{f: v.get(f) for f in ("title", "message_count", "last_message", "created_at", "updated_at")}}
                for k, v in self._rows.items()]
        return sorted(rows, key=lambda r: r.get("updated_at") or "", reverse=True)[:limit]

    def get(self, conv_id: str) -> Optional[dict[str, Any]]:
        row = self._rows.get(conv_id)
        return {"id": conv_id, **copy.deepcopy(row)} if row else None

    def create(self, data: dict[str, Any]) -> str:
        conv_id = uuid.uuid4().hex[:20]
        with self._lock:
            self._rows[conv_id] = copy.deepcopy(data)
        return conv_id

    def update(self, conv_id: str, fields: dict[str, Any]) -> None:
        with self._lock:
            self._rows[conv_id].update(copy.deepcopy(fields))

    def delete(self, conv_id: str) -> None:
        with self._lock:
            self._rows.pop(conv_id, None)
