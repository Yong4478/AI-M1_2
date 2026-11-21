"""Firestore 저장소 구현.

서비스 계정 키는 코드에 넣지 않고 환경 변수로 받는다.
  - FIREBASE_SERVICE_ACCOUNT_JSON : 키 JSON 내용 전체 (또는 base64로 인코딩한 문자열)  ← Render 권장
  - FIREBASE_SERVICE_ACCOUNT_PATH : 키 파일 경로 (로컬 개발용)
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ..config import Settings
from ..errors import ServiceUnavailableError

DATA_COLLECTION = "data"
CONV_COLLECTION = "conversations"
BATCH_SIZE = 400  # Firestore 배치 1회 최대 500건


def _load_credentials(settings: Settings) -> credentials.Certificate:
    raw = settings.firebase_service_account_json
    if raw:
        text = raw if raw.lstrip().startswith("{") else base64.b64decode(raw).decode("utf-8")
        try:
            info = json.loads(text)
        except json.JSONDecodeError as e:
            raise ServiceUnavailableError(
                "FIREBASE_SERVICE_ACCOUNT_JSON 형식이 올바르지 않습니다. 키 파일 내용 전체를 그대로 붙여 넣으세요.") from e
        return credentials.Certificate(info)
    if settings.firebase_service_account_path:
        return credentials.Certificate(settings.firebase_service_account_path)
    raise ServiceUnavailableError(
        "Firebase 서비스 계정 키가 설정되지 않았습니다. "
        "환경 변수 FIREBASE_SERVICE_ACCOUNT_JSON(또는 FIREBASE_SERVICE_ACCOUNT_PATH)을 설정하세요.")


def get_firestore_client(settings: Settings):
    if not firebase_admin._apps:
        firebase_admin.initialize_app(_load_credentials(settings))
    return firestore.client()


def _with_id(doc) -> dict[str, Any]:
    return {"id": doc.id, **(doc.to_dict() or {})}


class FirestoreDataRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.collection(DATA_COLLECTION)

    def list_all(self) -> list[dict[str, Any]]:
        return [_with_id(d) for d in self.col.order_by("date").stream()]

    def get(self, item_id: str) -> Optional[dict[str, Any]]:
        doc = self.col.document(item_id).get()
        return _with_id(doc) if doc.exists else None

    def find_by_date(self, date: str) -> Optional[dict[str, Any]]:
        docs = list(self.col.where(filter=FieldFilter("date", "==", date)).limit(1).stream())
        return _with_id(docs[0]) if docs else None

    def create(self, data: dict[str, Any]) -> str:
        ref = self.col.document()
        ref.set(data)
        return ref.id

    def update(self, item_id: str, fields: dict[str, Any]) -> None:
        self.col.document(item_id).update(fields)

    def delete(self, item_id: str) -> None:
        self.col.document(item_id).delete()

    def bulk_create(self, rows: list[dict[str, Any]]) -> int:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = self.db.batch()
            for row in rows[i:i + BATCH_SIZE]:
                batch.set(self.col.document(), row)
            batch.commit()
        return len(rows)

    def delete_all(self) -> int:
        n = 0
        while True:
            docs = list(self.col.limit(BATCH_SIZE).stream())
            if not docs:
                return n
            batch = self.db.batch()
            for d in docs:
                batch.delete(d.reference)
            batch.commit()
            n += len(docs)


class FirestoreConversationRepository:
    LIST_FIELDS = ["title", "message_count", "last_message", "created_at", "updated_at"]

    def __init__(self, db):
        self.col = db.collection(CONV_COLLECTION)

    def list(self, limit: int) -> list[dict[str, Any]]:
        q = (self.col.order_by("updated_at", direction=firestore.Query.DESCENDING)
             .select(self.LIST_FIELDS).limit(limit))   # select: messages 필드는 읽지 않아 전송량 절약
        return [_with_id(d) for d in q.stream()]

    def get(self, conv_id: str) -> Optional[dict[str, Any]]:
        doc = self.col.document(conv_id).get()
        return _with_id(doc) if doc.exists else None

    def create(self, data: dict[str, Any]) -> str:
        ref = self.col.document()
        ref.set(data)
        return ref.id

    def update(self, conv_id: str, fields: dict[str, Any]) -> None:
        self.col.document(conv_id).update(fields)

    def delete(self, conv_id: str) -> None:
        self.col.document(conv_id).delete()
