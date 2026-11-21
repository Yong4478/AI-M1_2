"""서비스 계층 예외. FastAPI에 의존하지 않으며, main.py에서 HTTP 상태 코드로 변환한다."""


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ServiceUnavailableError(AppError):
    """설정 누락(DB 키, OpenAI 키 등)으로 기능을 쓸 수 없음"""
    status_code = 503
    code = "service_unavailable"


class UpstreamError(AppError):
    """외부 서비스(OpenAI, Firestore) 호출 실패"""
    status_code = 502
    code = "upstream_error"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
