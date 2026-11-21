"""환경 변수 설정. 키·비밀 값은 코드에 쓰지 않고 모두 환경 변수(.env)에서 읽는다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # 로컬 개발용 .env (배포 환경에서는 Render 환경 변수가 사용됨)


def _split(value: str) -> list[str]:
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_max_tokens: int = 1500          # 비용 보호: 응답 최대 토큰
    enable_tools: bool = True              # 보너스: Function Calling 사용 여부
    chat_history_limit: int = 10           # 프롬프트에 넣을 이전 메시지 수 (토큰 절약)

    # Firebase
    firebase_service_account_json: str = ""
    firebase_service_account_path: str = ""
    use_memory_db: bool = False            # Firebase 없이 로컬 테스트할 때만 true

    # 서비스
    allowed_origins: list[str] = field(default_factory=list)
    allowed_origin_regex: str | None = None
    data_title: str = "서울 일평균 기온"
    data_unit: str = "℃"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip(),
        openai_max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "1500")),
        enable_tools=_bool(os.getenv("ENABLE_TOOLS"), True),
        chat_history_limit=int(os.getenv("CHAT_HISTORY_LIMIT", "10")),
        firebase_service_account_json=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip(),
        firebase_service_account_path=os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip(),
        use_memory_db=_bool(os.getenv("USE_MEMORY_DB"), False),
        allowed_origins=_split(os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")),
        allowed_origin_regex=os.getenv("ALLOWED_ORIGIN_REGEX") or None,
        data_title=os.getenv("DATA_TITLE", "서울 일평균 기온"),
        data_unit=os.getenv("DATA_UNIT", "℃"),
    )
