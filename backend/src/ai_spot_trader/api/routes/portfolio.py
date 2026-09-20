from collections.abc import Mapping
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ai_spot_trader.api.schemas import PortfolioResponse
from ai_spot_trader.core.runtime import AppRuntime

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def _runtime(request: Request) -> AppRuntime:
    return cast(AppRuntime, request.app.state.runtime)


@router.get("", response_model=PortfolioResponse)
async def current_portfolio(request: Request) -> PortfolioResponse:
    portfolio = _runtime(request).portfolio
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAPER portfolio is not configured",
        )

    try:
        snapshot = portfolio.snapshot()
        if isinstance(snapshot, BaseModel):
            payload = snapshot.model_dump(mode="python")
        elif isinstance(snapshot, Mapping):
            payload = dict(snapshot)
        else:
            raise TypeError("unsupported portfolio snapshot type")
        return PortfolioResponse.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PAPER portfolio state is unavailable",
        ) from exc
