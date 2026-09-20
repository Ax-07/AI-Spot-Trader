from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from ai_spot_trader.chat.errors import (
    ChatContextNotFoundError,
    ChatProviderError,
    ChatSessionNotFoundError,
    ChatTransportError,
)
from ai_spot_trader.chat.models import (
    ChatExchangeResponse,
    ChatHistoryResponse,
    SendChatMessageRequest,
)
from ai_spot_trader.chat.service import OperatorChatService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def _service(request: Request) -> OperatorChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="operator chat is not configured",
        )
    return cast(OperatorChatService, service)


@router.post("/messages", response_model=ChatExchangeResponse)
async def send_message(
    payload: SendChatMessageRequest,
    request: Request,
) -> ChatExchangeResponse:
    try:
        return await _service(request).send_message(
            message=payload.message,
            session_id=payload.session_id,
            context_cycle_id=payload.context_cycle_id,
        )
    except ChatContextNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="historical cycle not found",
        ) from exc
    except ChatSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat session not found",
        ) from exc
    except ChatTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="chat provider is unavailable",
        ) from exc
    except ChatProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="chat response is unavailable",
        ) from exc


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(session_id: UUID, request: Request) -> ChatHistoryResponse:
    try:
        return await _service(request).history(session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat session not found",
        ) from exc
