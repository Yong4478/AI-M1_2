"""대화 기록 저장·조회 로직."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..errors import NotFoundError
from ..repositories import get_conversation_repo

MAX_MESSAGES = 200      # Firestore 문서 1MB 제한 대비
TITLE_LEN = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _title_from(messages: list[dict[str, Any]]) -> str:
    first = next((m["content"] for m in messages if m["role"] == "user"), "새 대화")
    first = " ".join(first.split())
    return first if len(first) <= TITLE_LEN else first[:TITLE_LEN] + "…"


def _meta(messages: list[dict[str, Any]]) -> dict[str, Any]:
    last = messages[-1]["content"] if messages else ""
    return {"message_count": len(messages), "last_message": last[:80]}


def _normalize(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = _now()
    return [{"role": m["role"], "content": m["content"], "timestamp": m.get("timestamp") or now,
             "tool_calls": m.get("tool_calls") or []} for m in messages][-MAX_MESSAGES:]


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    rows = get_conversation_repo().list(limit)
    return [{"id": r["id"], "title": r.get("title") or "제목 없음", "message_count": r.get("message_count") or 0,
             "last_message": r.get("last_message") or "", "created_at": r.get("created_at"),
             "updated_at": r.get("updated_at")} for r in rows]


def get_conversation(conv_id: str) -> dict[str, Any]:
    conv = get_conversation_repo().get(conv_id)
    if not conv:
        raise NotFoundError(f"대화 '{conv_id}'를 찾을 수 없습니다.")
    conv.setdefault("messages", [])
    conv.setdefault("title", "제목 없음")
    conv.setdefault("message_count", len(conv["messages"]))
    conv.setdefault("last_message", "")
    return conv


def create_conversation(messages: list[dict[str, Any]], title: Optional[str] = None) -> dict[str, Any]:
    msgs = _normalize(messages)
    now = _now()
    doc = {"title": title or _title_from(msgs), "messages": msgs, **_meta(msgs), "created_at": now, "updated_at": now}
    conv_id = get_conversation_repo().create(doc)
    return {"id": conv_id, **doc}


def append_messages(conv_id: str, new_messages: list[dict[str, Any]]) -> dict[str, Any]:
    conv = get_conversation(conv_id)
    msgs = _normalize(conv["messages"] + new_messages)
    fields = {"messages": msgs, **_meta(msgs), "updated_at": _now()}
    get_conversation_repo().update(conv_id, fields)
    return {**conv, **fields}


def delete_conversation(conv_id: str) -> None:
    get_conversation(conv_id)  # 없으면 404
    get_conversation_repo().delete(conv_id)
