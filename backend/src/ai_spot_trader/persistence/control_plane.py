from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import unified_diff
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.agent.prompt import (
    BASE_AGENT_CONTRACT_VERSION,
    normalize_strategy_prompt,
    strategy_prompt_digest,
)
from ai_spot_trader.control_plane import (
    CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION,
    CampaignConfiguration,
    campaign_identity_digest,
)
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.persistence.models import (
    CampaignRecord,
    StrategyRecord,
    StrategyRevisionRecord,
)


class ControlPlaneError(RuntimeError):
    pass


class ControlPlaneNotFoundError(ControlPlaneError):
    pass


class ControlPlaneConflictError(ControlPlaneError):
    pass


class ControlPlaneUnavailableError(ControlPlaneError):
    pass


@dataclass(frozen=True, slots=True)
class StrategyRevisionView:
    strategy_id: UUID
    strategy_revision: int
    strategy_prompt: str
    strategy_prompt_digest: str
    base_agent_contract_version: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StrategyView:
    strategy_id: UUID
    strategy_name: str
    created_at: datetime
    archived_at: datetime | None
    latest_revision: int | None


@dataclass(frozen=True, slots=True)
class StrategyRevisionComparison:
    strategy_id: UUID
    left_revision: int
    right_revision: int
    left_digest: str
    right_digest: str
    identical: bool
    unified_diff: str


@dataclass(frozen=True, slots=True)
class CampaignView:
    campaign_id: UUID
    created_at: datetime
    strategy_id: UUID
    strategy_revision: int
    strategy_prompt_digest: str
    base_agent_contract_version: str
    configuration: CampaignConfiguration
    configuration_digest: str
    experiment_protocol_version: str
    experiment_digest: str


@dataclass(frozen=True, slots=True)
class SessionBundleView:
    """Atomic persistence result backing the user-facing Session façade."""

    strategy: StrategyView
    revision: StrategyRevisionView
    campaign: CampaignView


class ControlPlaneStore(Protocol):
    async def create_strategy(
        self, *, name: str, strategy_prompt: str
    ) -> tuple[StrategyView, StrategyRevisionView]: ...

    async def list_strategies(self) -> tuple[StrategyView, ...]: ...
    async def get_strategy(self, strategy_id: UUID) -> StrategyView | None: ...
    async def rename_strategy(self, strategy_id: UUID, *, name: str) -> StrategyView: ...
    async def archive_strategy(self, strategy_id: UUID) -> StrategyView: ...

    async def create_revision(
        self, strategy_id: UUID, *, strategy_prompt: str
    ) -> StrategyRevisionView: ...

    async def get_revision(
        self, strategy_id: UUID, revision: int
    ) -> StrategyRevisionView | None: ...

    async def compare_revisions(
        self, strategy_id: UUID, left: int, right: int
    ) -> StrategyRevisionComparison: ...

    async def create_campaign(
        self,
        *,
        strategy_id: UUID,
        strategy_revision: int,
        configuration: CampaignConfiguration,
    ) -> CampaignView: ...

    async def list_campaigns(self) -> tuple[CampaignView, ...]: ...
    async def get_campaign(self, campaign_id: UUID) -> CampaignView | None: ...

    async def latest_campaign_for_strategy(
        self, strategy_id: UUID
    ) -> CampaignView | None: ...

    async def create_session_bundle(
        self,
        *,
        name: str,
        strategy_prompt: str,
        configuration: CampaignConfiguration,
    ) -> SessionBundleView: ...

    async def update_session_bundle(
        self,
        strategy_id: UUID,
        *,
        name: str,
        strategy_prompt: str,
        configuration: CampaignConfiguration,
    ) -> SessionBundleView: ...


class SqlAlchemyControlPlaneStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
    ) -> None:
        self._sessions = sessions
        self._clock = clock or SystemClock()

    async def create_strategy(
        self,
        *,
        name: str,
        strategy_prompt: str,
    ) -> tuple[StrategyView, StrategyRevisionView]:
        normalized_name = _name(name)
        prompt = normalize_strategy_prompt(strategy_prompt)
        now = _clock_utc(self._clock)
        strategy_id = uuid4()
        revision = StrategyRevisionRecord(
            strategy_id=strategy_id,
            strategy_revision=1,
            strategy_prompt=prompt,
            strategy_prompt_digest=strategy_prompt_digest(prompt),
            base_agent_contract_version=BASE_AGENT_CONTRACT_VERSION,
            created_at=now,
        )
        record = StrategyRecord(
            strategy_id=strategy_id,
            strategy_name=normalized_name,
            created_at=now,
            archived_at=None,
        )
        try:
            async with self._sessions() as session, session.begin():
                session.add(record)
                session.add(revision)
                await session.flush()
            return _strategy_view(record, latest_revision=1), _revision_view(revision)
        except IntegrityError as exc:
            raise ControlPlaneConflictError("strategy creation conflicted") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def list_strategies(self) -> tuple[StrategyView, ...]:
        try:
            async with self._sessions() as session:
                records = (
                    await session.scalars(
                        select(StrategyRecord).order_by(
                            StrategyRecord.created_at.desc(),
                            StrategyRecord.strategy_id.desc(),
                        )
                    )
                ).all()
                result: list[StrategyView] = []
                for record in records:
                    latest = await session.scalar(
                        select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                            StrategyRevisionRecord.strategy_id == record.strategy_id
                        )
                    )
                    result.append(_strategy_view(record, latest_revision=latest))
                return tuple(result)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def get_strategy(self, strategy_id: UUID) -> StrategyView | None:
        try:
            async with self._sessions() as session:
                record = await session.get(StrategyRecord, strategy_id)
                if record is None:
                    return None
                latest = await session.scalar(
                    select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                        StrategyRevisionRecord.strategy_id == strategy_id
                    )
                )
                return _strategy_view(record, latest_revision=latest)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def rename_strategy(self, strategy_id: UUID, *, name: str) -> StrategyView:
        normalized_name = _name(name)
        try:
            async with self._sessions() as session, session.begin():
                record = await session.get(StrategyRecord, strategy_id, with_for_update=True)
                if record is None:
                    raise ControlPlaneNotFoundError("strategy not found")
                record.strategy_name = normalized_name
                latest = await session.scalar(
                    select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                        StrategyRevisionRecord.strategy_id == strategy_id
                    )
                )
                await session.flush()
                return _strategy_view(record, latest_revision=latest)
        except ControlPlaneNotFoundError:
            raise
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def archive_strategy(self, strategy_id: UUID) -> StrategyView:
        now = _clock_utc(self._clock)
        try:
            async with self._sessions() as session, session.begin():
                record = await session.get(StrategyRecord, strategy_id, with_for_update=True)
                if record is None:
                    raise ControlPlaneNotFoundError("strategy not found")
                if record.archived_at is None:
                    record.archived_at = now
                latest = await session.scalar(
                    select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                        StrategyRevisionRecord.strategy_id == strategy_id
                    )
                )
                await session.flush()
                return _strategy_view(record, latest_revision=latest)
        except ControlPlaneNotFoundError:
            raise
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def create_revision(
        self,
        strategy_id: UUID,
        *,
        strategy_prompt: str,
    ) -> StrategyRevisionView:
        prompt = normalize_strategy_prompt(strategy_prompt)
        now = _clock_utc(self._clock)
        try:
            async with self._sessions() as session, session.begin():
                strategy = await session.get(StrategyRecord, strategy_id, with_for_update=True)
                if strategy is None:
                    raise ControlPlaneNotFoundError("strategy not found")
                if strategy.archived_at is not None:
                    raise ControlPlaneConflictError("archived strategy cannot receive a revision")
                latest = await session.scalar(
                    select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                        StrategyRevisionRecord.strategy_id == strategy_id
                    )
                )
                next_revision = int(latest or 0) + 1
                record = StrategyRevisionRecord(
                    strategy_id=strategy_id,
                    strategy_revision=next_revision,
                    strategy_prompt=prompt,
                    strategy_prompt_digest=strategy_prompt_digest(prompt),
                    base_agent_contract_version=BASE_AGENT_CONTRACT_VERSION,
                    created_at=now,
                )
                session.add(record)
                await session.flush()
                return _revision_view(record)
        except (ControlPlaneNotFoundError, ControlPlaneConflictError):
            raise
        except IntegrityError as exc:
            raise ControlPlaneConflictError("strategy revision creation conflicted") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def get_revision(
        self,
        strategy_id: UUID,
        revision: int,
    ) -> StrategyRevisionView | None:
        if revision < 1:
            return None
        try:
            async with self._sessions() as session:
                record = await session.get(
                    StrategyRevisionRecord,
                    {"strategy_id": strategy_id, "strategy_revision": revision},
                )
                return None if record is None else _revision_view(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def compare_revisions(
        self,
        strategy_id: UUID,
        left: int,
        right: int,
    ) -> StrategyRevisionComparison:
        left_view = await self.get_revision(strategy_id, left)
        right_view = await self.get_revision(strategy_id, right)
        if left_view is None or right_view is None:
            raise ControlPlaneNotFoundError("strategy revision not found")
        diff = "\n".join(
            unified_diff(
                left_view.strategy_prompt.splitlines(),
                right_view.strategy_prompt.splitlines(),
                fromfile=f"revision-{left}",
                tofile=f"revision-{right}",
                lineterm="",
            )
        )
        return StrategyRevisionComparison(
            strategy_id=strategy_id,
            left_revision=left,
            right_revision=right,
            left_digest=left_view.strategy_prompt_digest,
            right_digest=right_view.strategy_prompt_digest,
            identical=left_view.strategy_prompt_digest == right_view.strategy_prompt_digest,
            unified_diff=diff,
        )

    async def create_campaign(
        self,
        *,
        strategy_id: UUID,
        strategy_revision: int,
        configuration: CampaignConfiguration,
    ) -> CampaignView:
        now = _clock_utc(self._clock)
        try:
            async with self._sessions() as session, session.begin():
                strategy = await session.get(StrategyRecord, strategy_id)
                if strategy is None:
                    raise ControlPlaneNotFoundError("strategy not found")
                if strategy.archived_at is not None:
                    raise ControlPlaneConflictError(
                        "archived strategy cannot start a new campaign"
                    )
                revision = await session.get(
                    StrategyRevisionRecord,
                    {
                        "strategy_id": strategy_id,
                        "strategy_revision": strategy_revision,
                    },
                )
                if revision is None:
                    raise ControlPlaneNotFoundError("strategy revision not found")
                record = _new_campaign_record(
                    strategy_id=strategy_id,
                    revision=revision,
                    configuration=configuration,
                    created_at=now,
                )
                session.add(record)
                await session.flush()
                return _campaign_view(record)
        except (ControlPlaneNotFoundError, ControlPlaneConflictError):
            raise
        except IntegrityError as exc:
            raise ControlPlaneConflictError("campaign creation conflicted") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def list_campaigns(self) -> tuple[CampaignView, ...]:
        try:
            async with self._sessions() as session:
                records = (
                    await session.scalars(
                        select(CampaignRecord).order_by(
                            CampaignRecord.created_at.desc(),
                            CampaignRecord.campaign_id.desc(),
                        )
                    )
                ).all()
                return tuple(_campaign_view(record) for record in records)
        except (SQLAlchemyError, OSError, TimeoutError, ValueError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def get_campaign(self, campaign_id: UUID) -> CampaignView | None:
        try:
            async with self._sessions() as session:
                record = await session.get(CampaignRecord, campaign_id)
                return None if record is None else _campaign_view(record)
        except (SQLAlchemyError, OSError, TimeoutError, ValueError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def latest_campaign_for_strategy(
        self, strategy_id: UUID
    ) -> CampaignView | None:
        try:
            async with self._sessions() as session:
                record = await session.scalar(
                    select(CampaignRecord)
                    .where(CampaignRecord.strategy_id == strategy_id)
                    .order_by(
                        CampaignRecord.created_at.desc(),
                        CampaignRecord.campaign_id.desc(),
                    )
                    .limit(1)
                )
                return None if record is None else _campaign_view(record)
        except (SQLAlchemyError, OSError, TimeoutError, ValueError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def create_session_bundle(
        self,
        *,
        name: str,
        strategy_prompt: str,
        configuration: CampaignConfiguration,
    ) -> SessionBundleView:
        """Persist Strategy + revision 1 + Campaign atomically for the Session façade."""

        normalized_name = _name(name)
        prompt = normalize_strategy_prompt(strategy_prompt)
        now = _clock_utc(self._clock)
        strategy_id = uuid4()
        strategy = StrategyRecord(
            strategy_id=strategy_id,
            strategy_name=normalized_name,
            created_at=now,
            archived_at=None,
        )
        revision = StrategyRevisionRecord(
            strategy_id=strategy_id,
            strategy_revision=1,
            strategy_prompt=prompt,
            strategy_prompt_digest=strategy_prompt_digest(prompt),
            base_agent_contract_version=BASE_AGENT_CONTRACT_VERSION,
            created_at=now,
        )
        campaign = _new_campaign_record(
            strategy_id=strategy_id,
            revision=revision,
            configuration=configuration,
            created_at=now,
        )
        try:
            async with self._sessions() as session, session.begin():
                session.add(strategy)
                session.add(revision)
                # Campaign references the composite StrategyRevision FK but has no ORM
                # relationship to it. Flush parent rows first so PostgreSQL cannot insert
                # the Campaign before its referenced revision. The outer transaction keeps
                # Strategy + Revision + Campaign creation atomic.
                await session.flush()
                session.add(campaign)
                await session.flush()
            return SessionBundleView(
                strategy=_strategy_view(strategy, latest_revision=1),
                revision=_revision_view(revision),
                campaign=_campaign_view(campaign),
            )
        except IntegrityError as exc:
            raise ControlPlaneConflictError("session creation conflicted") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc

    async def update_session_bundle(
        self,
        strategy_id: UUID,
        *,
        name: str,
        strategy_prompt: str,
        configuration: CampaignConfiguration,
    ) -> SessionBundleView:
        """Apply a Session edit without mutating historical revisions or Campaigns."""

        normalized_name = _name(name)
        prompt = normalize_strategy_prompt(strategy_prompt)
        now = _clock_utc(self._clock)
        try:
            async with self._sessions() as session, session.begin():
                strategy = await session.get(StrategyRecord, strategy_id, with_for_update=True)
                if strategy is None:
                    raise ControlPlaneNotFoundError("session not found")
                if strategy.archived_at is not None:
                    raise ControlPlaneConflictError("archived session cannot be modified")

                campaign = await session.scalar(
                    select(CampaignRecord)
                    .where(CampaignRecord.strategy_id == strategy_id)
                    .order_by(
                        CampaignRecord.created_at.desc(),
                        CampaignRecord.campaign_id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
                if campaign is None:
                    raise ControlPlaneNotFoundError("session campaign not found")
                # Keep the newest Campaign ordering deterministic even with fixed/coarse clocks.
                if now <= _utc(campaign.created_at):
                    now = _utc(campaign.created_at) + timedelta(microseconds=1)
                current_revision = await session.get(
                    StrategyRevisionRecord,
                    {
                        "strategy_id": strategy_id,
                        "strategy_revision": campaign.strategy_revision,
                    },
                )
                if current_revision is None:
                    raise ControlPlaneUnavailableError(
                        "session campaign strategy revision is unavailable"
                    )

                strategy.strategy_name = normalized_name
                requested_prompt_digest = strategy_prompt_digest(prompt)
                prompt_changed = requested_prompt_digest != current_revision.strategy_prompt_digest
                configuration_changed = configuration.digest != campaign.configuration_digest

                target_revision = current_revision
                if prompt_changed:
                    latest = await session.scalar(
                        select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                            StrategyRevisionRecord.strategy_id == strategy_id
                        )
                    )
                    target_revision = StrategyRevisionRecord(
                        strategy_id=strategy_id,
                        strategy_revision=int(latest or 0) + 1,
                        strategy_prompt=prompt,
                        strategy_prompt_digest=requested_prompt_digest,
                        base_agent_contract_version=BASE_AGENT_CONTRACT_VERSION,
                        created_at=now,
                    )
                    session.add(target_revision)
                    await session.flush()

                target_campaign = campaign
                if prompt_changed or configuration_changed:
                    target_campaign = _new_campaign_record(
                        strategy_id=strategy_id,
                        revision=target_revision,
                        configuration=configuration,
                        created_at=now,
                    )
                    session.add(target_campaign)
                    await session.flush()

                latest_revision = await session.scalar(
                    select(func.max(StrategyRevisionRecord.strategy_revision)).where(
                        StrategyRevisionRecord.strategy_id == strategy_id
                    )
                )
                await session.flush()
                return SessionBundleView(
                    strategy=_strategy_view(strategy, latest_revision=latest_revision),
                    revision=_revision_view(target_revision),
                    campaign=_campaign_view(target_campaign),
                )
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneUnavailableError):
            raise
        except IntegrityError as exc:
            raise ControlPlaneConflictError("session update conflicted") from exc
        except (SQLAlchemyError, OSError, TimeoutError, ValueError) as exc:
            raise ControlPlaneUnavailableError("control-plane store unavailable") from exc


def _new_campaign_record(
    *,
    strategy_id: UUID,
    revision: StrategyRevisionRecord,
    configuration: CampaignConfiguration,
    created_at: datetime,
) -> CampaignRecord:
    experiment_digest = campaign_identity_digest(
        strategy_id=strategy_id,
        strategy_revision=revision.strategy_revision,
        strategy_prompt_digest_value=revision.strategy_prompt_digest,
        base_agent_contract_version=revision.base_agent_contract_version,
        configuration_digest=configuration.digest,
    )
    return CampaignRecord(
        campaign_id=uuid4(),
        created_at=created_at,
        strategy_id=strategy_id,
        strategy_revision=revision.strategy_revision,
        strategy_prompt_digest=revision.strategy_prompt_digest,
        base_agent_contract_version=revision.base_agent_contract_version,
        configuration_payload=configuration.canonical_payload(),
        configuration_digest=configuration.digest,
        experiment_protocol_version=CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION,
        experiment_digest=experiment_digest,
    )


def _campaign_view(record: CampaignRecord) -> CampaignView:
    configuration = CampaignConfiguration.model_validate_json(
        json.dumps(record.configuration_payload, sort_keys=True, separators=(",", ":"))
    )
    if configuration.digest != record.configuration_digest:
        raise ValueError("campaign configuration digest mismatch")
    if record.experiment_protocol_version != CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION:
        raise ValueError("unsupported campaign experiment protocol")
    expected_experiment_digest = campaign_identity_digest(
        strategy_id=record.strategy_id,
        strategy_revision=record.strategy_revision,
        strategy_prompt_digest_value=record.strategy_prompt_digest,
        base_agent_contract_version=record.base_agent_contract_version,
        configuration_digest=record.configuration_digest,
    )
    if expected_experiment_digest != record.experiment_digest:
        raise ValueError("campaign experiment digest mismatch")
    return CampaignView(
        campaign_id=record.campaign_id,
        created_at=_utc(record.created_at),
        strategy_id=record.strategy_id,
        strategy_revision=record.strategy_revision,
        strategy_prompt_digest=record.strategy_prompt_digest,
        base_agent_contract_version=record.base_agent_contract_version,
        configuration=configuration,
        configuration_digest=record.configuration_digest,
        experiment_protocol_version=record.experiment_protocol_version,
        experiment_digest=record.experiment_digest,
    )


def _revision_view(record: StrategyRevisionRecord) -> StrategyRevisionView:
    digest = strategy_prompt_digest(record.strategy_prompt)
    if digest != record.strategy_prompt_digest:
        raise ControlPlaneUnavailableError("strategy revision digest mismatch")
    return StrategyRevisionView(
        strategy_id=record.strategy_id,
        strategy_revision=record.strategy_revision,
        strategy_prompt=record.strategy_prompt,
        strategy_prompt_digest=record.strategy_prompt_digest,
        base_agent_contract_version=record.base_agent_contract_version,
        created_at=_utc(record.created_at),
    )


def _strategy_view(record: StrategyRecord, *, latest_revision: int | None) -> StrategyView:
    return StrategyView(
        strategy_id=record.strategy_id,
        strategy_name=record.strategy_name,
        created_at=_utc(record.created_at),
        archived_at=None if record.archived_at is None else _utc(record.archived_at),
        latest_revision=None if latest_revision is None else int(latest_revision),
    )


def _name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("strategy name cannot be empty")
    if len(normalized) > 120:
        raise ValueError("strategy name is too long")
    return normalized


def _clock_utc(clock: Clock) -> datetime:
    value = clock.now()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("control-plane clock must be timezone-aware")
    return value.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
