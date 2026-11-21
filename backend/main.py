"""서울 날씨 AI 비서 — FastAPI 백엔드

로컬 실행:  uvicorn main:app --reload
API 문서:   http://localhost:8000/docs (Swagger UI)
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import AppError
from app.routers import chat, conversations, data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
settings = get_settings()

app = FastAPI(
    title="서울 날씨 AI 비서 API",
    description=(
        "서울 일평균 기온 시계열을 저장·분석하고, 데이터 요약을 시스템 프롬프트에 주입해 "
        "맞춤형 답변을 하는 AI 비서 API입니다.\n\n"
        "- **데이터**: CRUD + 요약(summary) + 확장 통계(statistics)\n"
        "- **대화 기록**: 저장 · 목록 · 불러오기 · 삭제\n"
        "- **AI 채팅**: 컨텍스트 주입 + Function Calling + 자동 저장"
    ),
    version="1.0.0",
)

# 예상하지 못한 오류(500)도 JSON으로 돌려준다.
# 이 미들웨어를 CORS보다 먼저 등록해야 CORS가 바깥에서 감싸, 500 응답에도 CORS 헤더가 붙는다.
# (헤더가 없으면 브라우저는 실제 오류 대신 "연결 실패/CORS 오류"로만 보여 준다)
@app.middleware("http")
async def catch_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001
        log.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다. Render 로그를 확인하세요.",
                                                      "code": "internal_error"})


# CORS: 브라우저는 다른 도메인(Vercel)에서 오는 요청을 기본적으로 막는다.
# 허용할 프론트엔드 주소만 환경 변수 ALLOWED_ORIGINS로 지정한다. (* 전체 허용은 쓰지 않는다)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/", tags=["상태"], summary="서비스 정보")
def root():
    return {"service": "서울 날씨 AI 비서 API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["상태"], summary="헬스 체크 (콜드스타트 깨우기용)")
def health():
    """DB 연결 없이 즉시 응답한다. 프론트는 첫 화면에서 이 주소로 서버를 먼저 깨운다."""
    return {
        "status": "ok",
        "database": "memory" if settings.use_memory_db else "firestore",
        "openai_configured": bool(settings.openai_api_key),
        "model": settings.openai_model,
        "tools_enabled": settings.enable_tools,
        "allowed_origins": settings.allowed_origins,   # CORS 설정 확인용 (비밀 값 아님)
    }
