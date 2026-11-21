"""데이터 API: CRUD 4개 + summary 1개 (+ 보너스 statistics)

라우터는 HTTP 입출력(경로, 쿼리, 상태 코드, 응답 모델)만 담당하고 실제 로직은 서비스 계층에 맡긴다.
"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Path, Query

from ..schemas import DataCreate, DataItem, DataUpdate, MessageResponse, SummaryResponse
from ..services import data_service

router = APIRouter(prefix="/api/data", tags=["데이터"])


@router.get("/summary", response_model=SummaryResponse, summary="데이터 요약 (프롬프트 주입용)")
def get_summary():
    """기간, 개수, 평균/최대/최소, 최근 7일 추세, 월별 평균. 채팅 시스템 프롬프트에 그대로 주입된다."""
    return data_service.get_summary()


@router.get("/statistics", summary="(보너스) 확장 통계")
def get_statistics(ma_window: int = Query(7, ge=2, le=60, description="이동평균 창 크기(일)")):
    """이동평균 시계열, 전일 대비 변화량(변동성), 최대 상승/하락일, 요일별·월별 통계."""
    return data_service.get_statistics(ma_window)


@router.get("", response_model=list[DataItem], summary="데이터 목록 조회")
def list_data(
    start: Optional[date] = Query(None, description="시작일 (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="종료일 (YYYY-MM-DD)"),
    order: Literal["asc", "desc"] = Query("asc", description="날짜 정렬"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="최대 개수"),
):
    return data_service.list_data(start.isoformat() if start else None, end.isoformat() if end else None, order, limit)


@router.post("", response_model=DataItem, status_code=201, summary="새 데이터 추가")
def create_data(payload: DataCreate):
    """같은 날짜가 이미 있으면 409를 반환한다."""
    return data_service.create_data(payload)


@router.put("/{item_id}", response_model=DataItem, summary="데이터 수정")
def update_data(payload: DataUpdate, item_id: str = Path(..., min_length=1, max_length=128, description="데이터 문서 ID")):
    """date / value / memo 중 바꿀 필드만 보내면 된다."""
    return data_service.update_data(item_id, payload)


@router.delete("/{item_id}", response_model=MessageResponse, summary="데이터 삭제")
def delete_data(item_id: str = Path(..., min_length=1, max_length=128, description="데이터 문서 ID")):
    data_service.delete_data(item_id)
    return {"message": "삭제되었습니다.", "id": item_id}
