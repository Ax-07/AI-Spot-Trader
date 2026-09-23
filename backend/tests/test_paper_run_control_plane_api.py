from datetime import UTC, datetime
from uuid import UUID

from ai_spot_trader.api.routes.paper_runs import _response
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.persistence.campaign_runs import CampaignPaperRunView


def test_paper_run_response_exposes_campaign_and_recovery_lineage() -> None:
    run_id = UUID("189a0000-0000-0000-0000-000000000401")
    parent_id = UUID("189a0000-0000-0000-0000-000000000402")
    campaign_id = UUID("189a0000-0000-0000-0000-000000000403")
    view = CampaignPaperRunView(
        paper_run_id=run_id,
        started_at=datetime(2026, 9, 23, 18, 0, tzinfo=UTC),
        ended_at=None,
        market_type="SPOT",
        symbol="BTC/USD",
        execution_universe=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        resumed_from_paper_run_id=parent_id,
        recovery_version="paper-ledger-recovery-v1",
        campaign_id=campaign_id,
    )

    response = _response(view, current_run_id=run_id)

    assert response.campaign_id == campaign_id
    assert response.resumed_from_paper_run_id == parent_id
    assert response.recovery_version == "paper-ledger-recovery-v1"
    assert response.is_current is True
