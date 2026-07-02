"""에이전트 실행 엔드포인트. 라우터는 얇게 — 실제 로직은 service로 위임."""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return await service.run(req)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """SSE 스트리밍. 토큰을 실시간으로 흘리고 마지막에 done으로 확정한다."""

    async def event_gen():
        try:
            async for ev in service.astream(req):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001 — 스트림 중 오류도 클라이언트에 전달
            err = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 프록시(nginx 등)의 버퍼링 방지
        },
    )
