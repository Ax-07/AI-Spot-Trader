from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, ValidationError

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.market.candles import (
    Candle,
    CandleCapacityError,
    CandleError,
    CandleKey,
    CandleStreamService,
    CandleStreamStatus,
    CandleTimeframe,
    CandleValidationError,
)

router = APIRouter(prefix="/api/v1/markets/candles", tags=["market-candles"])


class CandleServiceLike(Protocol):
    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]: ...

    async def subscribe(
        self,
        key: CandleKey,
        *,
        history_limit: int = 1000,
    ): ...

    def status(self, key: CandleKey) -> CandleStreamStatus: ...


class CandleHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: CandleKey
    candles: tuple[Candle, ...]
    status: CandleStreamStatus


@router.get("", response_model=CandleHistoryResponse)
async def candle_history(
    request: Request,
    symbol: str = Query(min_length=3, max_length=64),
    market_type: MarketType = Query(),
    timeframe: CandleTimeframe = Query(),
    limit: int = Query(default=1000, ge=1, le=1000),
) -> CandleHistoryResponse:
    service = _service(request.app.state.candle_service)
    key = _key(symbol=symbol, market_type=market_type, timeframe=timeframe)
    try:
        candles = await service.history(key, limit=limit)
    except CandleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except CandleError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return CandleHistoryResponse(key=key, candles=candles, status=service.status(key))


@router.get("/status", response_model=CandleStreamStatus)
async def candle_status(
    request: Request,
    symbol: str = Query(min_length=3, max_length=64),
    market_type: MarketType = Query(),
    timeframe: CandleTimeframe = Query(),
) -> CandleStreamStatus:
    service = _service(request.app.state.candle_service)
    key = _key(symbol=symbol, market_type=market_type, timeframe=timeframe)
    return service.status(key)


@router.websocket("/stream")
async def candle_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    service = _service(websocket.app.state.candle_service)
    try:
        raw_symbol = websocket.query_params.get("symbol")
        raw_market_type = websocket.query_params.get("market_type")
        raw_timeframe = websocket.query_params.get("timeframe")
        raw_limit = websocket.query_params.get("limit", "1000")
        if raw_symbol is None or raw_market_type is None or raw_timeframe is None:
            raise CandleValidationError("symbol, market_type and timeframe are required")
        try:
            market_type = MarketType(raw_market_type.upper())
            timeframe = CandleTimeframe(raw_timeframe)
            history_limit = int(raw_limit)
        except (ValueError, TypeError) as exc:
            raise CandleValidationError("invalid candle stream query parameters") from exc
        key = _key(symbol=raw_symbol, market_type=market_type, timeframe=timeframe)
        history = await service.history(key, limit=history_limit)
        await websocket.send_json(
            {
                "type": "snapshot",
                "key": key.model_dump(mode="json"),
                "candles": [item.model_dump(mode="json") for item in history],
                "status": service.status(key).model_dump(mode="json"),
            }
        )
        async for candle in service.subscribe(key, history_limit=history_limit):
            await websocket.send_json(
                {
                    "type": "candle",
                    "candle": candle.model_dump(mode="json"),
                    "status": service.status(key).model_dump(mode="json"),
                }
            )
    except WebSocketDisconnect:
        return
    except (CandleValidationError, ValidationError, CandleCapacityError) as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close(code=1008)
    except CandleError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close(code=1011)


def _key(*, symbol: str, market_type: MarketType, timeframe: CandleTimeframe) -> CandleKey:
    try:
        return CandleKey(
            symbol=symbol.strip().upper(),
            market_type=market_type,
            timeframe=timeframe,
        )
    except ValidationError as exc:
        raise CandleValidationError("invalid canonical candle key") from exc


def _service(value: object) -> CandleStreamService:
    if not isinstance(value, CandleStreamService):
        raise RuntimeError("candle service is not configured")
    return value
