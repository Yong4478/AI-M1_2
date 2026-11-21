"""저장소(Repository) 계층: DB 접근 코드만 모아 둔다.

서비스 계층은 이 인터페이스만 사용하므로 Firestore ↔ 메모리 DB를 바꿔도 서비스 코드는 그대로다.
"""

from __future__ import annotations

import threading

from ..config import get_settings
from ..errors import ServiceUnavailableError
from .base import ConversationRepository, DataRepository

_lock = threading.Lock()
_repos: tuple[DataRepository, ConversationRepository] | None = None


def _build() -> tuple[DataRepository, ConversationRepository]:
    settings = get_settings()
    if settings.use_memory_db:
        from .memory import MemoryConversationRepository, MemoryDataRepository
        return MemoryDataRepository(), MemoryConversationRepository()

    from .firestore import FirestoreConversationRepository, FirestoreDataRepository, get_firestore_client
    db = get_firestore_client(settings)
    return FirestoreDataRepository(db), FirestoreConversationRepository(db)


def get_repositories() -> tuple[DataRepository, ConversationRepository]:
    global _repos
    if _repos is None:
        with _lock:
            if _repos is None:
                try:
                    _repos = _build()
                except ServiceUnavailableError:
                    raise
                except Exception as e:  # 키 형식 오류 등
                    raise ServiceUnavailableError(f"데이터베이스 초기화 실패: {e}") from e
    return _repos


def get_data_repo() -> DataRepository:
    return get_repositories()[0]


def get_conversation_repo() -> ConversationRepository:
    return get_repositories()[1]


def set_repositories(data: DataRepository, conv: ConversationRepository) -> None:
    """테스트용: 저장소를 직접 주입한다."""
    global _repos
    _repos = (data, conv)
