from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr, ValidationError

from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.market.attention import (
    PublicAttentionCatalyst,
    PublicAttentionDirection,
    PublicAttentionMetric,
    PublicAttentionObservation,
    PublicAttentionSnapshot,
    PublicAttentionSource,
    RadarStatus,
)

logger = logging.getLogger(__name__)


class PublicAttentionResearchError(RuntimeError):
    """Raised by the auxiliary web-research adapter; callers must fail soft."""


class PublicAttentionTransportError(PublicAttentionResearchError):
    """OpenAI web research failed at the network/transport boundary."""


class PublicAttentionHTTPError(PublicAttentionResearchError):
    """OpenAI web research returned a non-transient HTTP contract error."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class PublicAttentionSchemaError(PublicAttentionHTTPError):
    """OpenAI rejected the Responses request/schema contract with HTTP 400."""


# Batch 34 used contract-oriented names while Batch 34.1 initially exposed the
# more general HTTP name. Keep those names as aliases rather than forcing tests
# or callers to change during a local, non-integrated batch transition.
PublicAttentionBadRequestError = PublicAttentionSchemaError
PublicAttentionRequestError = PublicAttentionSchemaError
PublicAttentionContractError = PublicAttentionSchemaError
PublicAttentionResponseError = PublicAttentionHTTPError


class PublicAttentionRateLimitError(PublicAttentionTransportError):
    """OpenAI web research remained rate-limited after bounded retries."""

    def __init__(self, message: str, *, status_code: int = 429) -> None:
        super().__init__(message)
        self.status_code = status_code


class PublicAttentionServerError(PublicAttentionTransportError):
    """OpenAI web research returned a retryable 5xx response."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class PublicAttentionIncompleteError(PublicAttentionResearchError):
    """OpenAI Responses finished with the explicit ``incomplete`` status."""

    def __init__(
        self,
        message: str = "OpenAI web research response is incomplete",
        *,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = (
            _bounded_token(reason, max_length=80, fallback="unknown")
            if reason is not None
            else None
        )


class PublicAttentionValidationError(PublicAttentionResearchError):
    """Canonical Pydantic validation failed with bounded value-free diagnostics."""

    def __init__(
        self,
        *,
        validation_path: str,
        validation_code: str,
        validation_error_count: int,
    ) -> None:
        path = _bounded_token(validation_path, max_length=160, fallback="unknown")
        code = _bounded_token(validation_code, max_length=80, fallback="unknown")
        count = min(max(int(validation_error_count), 1), 8)
        super().__init__(
            "Structured public attention data failed canonical validation "
            f"path={path} code={code} errors={count}"
        )
        self.validation_path = path
        self.validation_code = code
        self.validation_error_count = count


# Keep the wire schema inside the Structured Outputs subset accepted by Responses.
# Canonical length constraints remain enforced by the Pydantic domain models below.
PUBLIC_ATTENTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "attention_direction": {
            "type": "string",
            "enum": ["RISING", "STABLE", "FALLING", "UNKNOWN"],
        },
        "confidence_context": {"type": "string"},
        "quantitative_metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "window": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "source_url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "published_at": {
                        "anyOf": [{"type": "string"}, {"type": "null"}]
                    },
                },
                "required": ["name", "value", "unit", "window", "source_url", "published_at"],
                "additionalProperties": False,
            },
        },
        "qualitative_observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["text", "source_url"],
                "additionalProperties": False,
            },
        },
        "possible_catalysts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "source_url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["description", "source_url"],
                "additionalProperties": False,
            },
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "published_at": {
                        "anyOf": [{"type": "string"}, {"type": "null"}]
                    },
                },
                "required": ["title", "url", "published_at"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "attention_direction",
        "confidence_context",
        "quantitative_metrics",
        "qualitative_observations",
        "possible_catalysts",
        "sources",
    ],
    "additionalProperties": False,
}


_PUBLIC_ATTENTION_INSTRUCTIONS = """
Tu effectues une recherche publique observationnelle sur l'attention recente autour
d'un actif crypto.

Objectif : mesurer l'evolution de l'attention publique et identifier les faits ou evenements
recents susceptibles d'expliquer une activite inhabituelle. Priorise les faits recents et sources.
Examine, lorsque disponible, mentions, engagement, contributeurs, dominance sociale, actualites,
annonces officielles et presence simultanee sur plusieurs sources publiques.

Contraintes absolues :
- ne produis jamais BUY, SELL ou HOLD ;
- ne recommande aucune position, direction LONG/SHORT ou taille ;
- ne donne aucune probabilite de hausse ou baisse ;
- n'invente aucune metrique absente ;
- distingue les metriques quantitatives directement observees des observations qualitatives ;
- une metrique glissante 24h reste une metrique glissante 24h et ne doit jamais etre presentee
  comme de nouveaux posts dans la derniere heure ;
- ne suppose jamais un acces exhaustif a X/Twitter, Reddit, LunarCrush ou une autre plateforme ;
- conserve les URL des sources publiques utilisees.

Le resultat sert uniquement au Market Attention Radar informatif et n'influence pas le trading.
"""


class OpenAIWebAttentionResearcher:
    """Auxiliary Responses API + hosted web_search adapter, isolated from strategy calls."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: LLMModel,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
        max_attempts: int = 2,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("OpenAI API key cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client
        self._owns_client = http_client is None
        self._max_attempts = max_attempts

    async def research(
        self,
        *,
        asset: str,
        symbols: tuple[str, ...],
        observed_at: datetime,
    ) -> PublicAttentionSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        observed_at = observed_at.astimezone(UTC)
        clean_asset = asset.strip().upper()
        if not clean_asset:
            raise ValueError("asset cannot be empty")
        input_text = (
            f"Actif: {clean_asset}\n"
            f"Marches Kraken observes: {', '.join(symbols)}\n"
            f"Instant d'observation UTC: {observed_at.isoformat()}\n"
            "Recherche l'activite publique recente, son evolution et les catalyseurs eventuels. "
            "Utilise uniquement des informations publiques et cite les sources."
        )
        request = {
            "model": self._model.value,
            "instructions": _PUBLIC_ATTENTION_INSTRUCTIONS,
            "input": input_text,
            "store": False,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "include": ["web_search_call.action.sources"],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "public_attention_v1",
                    "strict": True,
                    "schema": PUBLIC_ATTENTION_SCHEMA,
                }
            },
        }
        response = await self._responses(request)
        payload = _extract_structured_payload(response)
        provider_sources = _extract_provider_sources(response)
        provider_citations = _extract_provider_citations(response)
        return _snapshot_from_payload(
            payload,
            asset=clean_asset,
            observed_at=observed_at,
            provider_sources=provider_sources,
            provider_citations=provider_citations,
        )

    async def aclose(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _responses(self, request: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        client = self._http_client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            self._http_client = client
        for attempt in range(self._max_attempts):
            try:
                response = await client.post(
                    f"{self._base_url}/responses",
                    headers=headers,
                    json=request,
                    timeout=self._timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise PublicAttentionTransportError(
                    "OpenAI web research transport failed"
                ) from exc

            if response.status_code == 429:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise PublicAttentionRateLimitError(
                    "OpenAI web research remained rate limited",
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise PublicAttentionServerError(
                    "OpenAI web research returned a server error",
                    status_code=response.status_code,
                )
            if response.status_code == 400:
                raise PublicAttentionSchemaError(
                    "OpenAI web research rejected the request/schema contract",
                    status_code=response.status_code,
                )
            if response.status_code >= 400:
                raise PublicAttentionHTTPError(
                    "OpenAI web research returned an HTTP contract error",
                    status_code=response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise PublicAttentionResearchError(
                    "OpenAI web research returned invalid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise PublicAttentionResearchError("OpenAI web research response must be an object")
            return payload
        raise PublicAttentionResearchError("OpenAI web research failed")


def _extract_structured_payload(response: dict[str, Any]) -> dict[str, Any]:
    status = response.get("status")
    if status == "incomplete":
        details = response.get("incomplete_details")
        raw_reason = details.get("reason") if isinstance(details, dict) else None
        reason = raw_reason if isinstance(raw_reason, str) else None
        raise PublicAttentionIncompleteError(reason=reason)
    if status != "completed":
        raise PublicAttentionResearchError("OpenAI web research did not complete")
    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise PublicAttentionResearchError("OpenAI refused public attention research")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if len(texts) != 1:
        raise PublicAttentionResearchError("OpenAI web research must contain one output_text")
    try:
        payload = json.loads(texts[0])
    except json.JSONDecodeError as exc:
        raise PublicAttentionResearchError(
            "Structured public attention output is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise PublicAttentionResearchError("Structured public attention output must be an object")
    return payload


def _extract_provider_sources(response: dict[str, Any]) -> dict[str, str]:
    sources: dict[str, str] = {}
    output = response.get("output")
    if not isinstance(output, list):
        return sources
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "web_search_call":
            action = item.get("action")
            if isinstance(action, dict):
                for source in action.get("sources", []):
                    _add_source(sources, source)
        if item.get("type") == "message":
            for part in item.get("content", []):
                if not isinstance(part, dict):
                    continue
                for annotation in part.get("annotations", []):
                    _add_source(sources, annotation)
    return sources


def _extract_provider_citations(response: dict[str, Any]) -> set[str]:
    citations: set[str] = set()
    output = response.get("output")
    if not isinstance(output, list):
        return citations
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if not isinstance(part, dict):
                continue
            for annotation in part.get("annotations", []):
                url = _source_url(annotation)
                if url is not None:
                    citations.add(url)
    return citations


def _source_url(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    candidate = raw.get("url_citation") if isinstance(raw.get("url_citation"), dict) else raw
    if not isinstance(candidate, dict):
        return None
    return _http_url(candidate.get("url"))


def _add_source(sources: dict[str, str], raw: object) -> None:
    if not isinstance(raw, dict):
        return
    candidate = raw.get("url_citation") if isinstance(raw.get("url_citation"), dict) else raw
    if not isinstance(candidate, dict):
        return
    url = _http_url(candidate.get("url"))
    if url is None:
        return
    title = candidate.get("title")
    clean_title = _provider_title(title, fallback=_domain(url))
    sources.setdefault(url, clean_title)


def _snapshot_from_payload(
    payload: dict[str, Any],
    *,
    asset: str,
    observed_at: datetime,
    provider_sources: dict[str, str],
    provider_citations: set[str] | None = None,
) -> PublicAttentionSnapshot:
    raw_direction = payload.get("attention_direction")
    raw_confidence_context = payload.get("confidence_context")
    if not isinstance(raw_direction, str):
        _raise_manual_validation(path="attention_direction", code="string_type")
    try:
        direction = PublicAttentionDirection(raw_direction)
    except ValueError:
        _raise_manual_validation(path="attention_direction", code="enum")
    if not isinstance(raw_confidence_context, str):
        _raise_manual_validation(path="confidence_context", code="string_type")
    confidence_context = raw_confidence_context.strip()
    if not confidence_context:
        _raise_manual_validation(path="confidence_context", code="string_too_short")

    structured_sources: dict[str, tuple[str, datetime | None]] = {}
    for raw in _list_of_dicts(payload.get("sources")):
        url = _http_url(raw.get("url"))
        if url is None:
            continue
        structured_sources[url] = (
            _text(raw.get("title")) or provider_sources.get(url) or _domain(url),
            _optional_datetime(raw.get("published_at")),
        )

    # Canonical URLs always come from Responses provider metadata. Structured output can
    # reference/enrich such URLs, but it cannot create a trusted source on its own.
    provider_urls = set(provider_sources)
    direct_references: set[str] = set()

    metrics: list[PublicAttentionMetric] = []
    for index, raw in enumerate(_list_of_dicts(payload.get("quantitative_metrics"))):
        source_url = _accepted_source_url(raw.get("source_url"), provider_urls)
        if source_url is not None:
            direct_references.add(source_url)
        name = _text(raw.get("name"))
        value = _text(raw.get("value"))
        if not name or not value:
            continue
        try:
            metric = PublicAttentionMetric(
                name=name,
                value=value,
                unit=_text(raw.get("unit")),
                window=_text(raw.get("window")),
                source_url=source_url,
                observed_at=observed_at,
                published_at=_optional_datetime(raw.get("published_at")),
            )
        except ValidationError as exc:
            _raise_pydantic_validation(exc, prefix=f"quantitative_metrics[{index}]")
        metrics.append(metric)

    observations_list: list[PublicAttentionObservation] = []
    for index, raw in enumerate(_list_of_dicts(payload.get("qualitative_observations"))):
        text = _text(raw.get("text"))
        if not text:
            continue
        source_url = _accepted_source_url(raw.get("source_url"), provider_urls)
        if source_url is not None:
            direct_references.add(source_url)
        try:
            observation = PublicAttentionObservation(text=text, source_url=source_url)
        except ValidationError as exc:
            _raise_pydantic_validation(exc, prefix=f"qualitative_observations[{index}]")
        observations_list.append(observation)

    catalysts_list: list[PublicAttentionCatalyst] = []
    for index, raw in enumerate(_list_of_dicts(payload.get("possible_catalysts"))):
        description = _text(raw.get("description"))
        if not description:
            continue
        source_url = _accepted_source_url(raw.get("source_url"), provider_urls)
        if source_url is not None:
            direct_references.add(source_url)
        try:
            catalyst = PublicAttentionCatalyst(description=description, source_url=source_url)
        except ValidationError as exc:
            _raise_pydantic_validation(exc, prefix=f"possible_catalysts[{index}]")
        catalysts_list.append(catalyst)

    citation_urls = (provider_citations or set()) & provider_urls
    structured_provider_urls = set(structured_sources) & provider_urls
    exposed_urls = direct_references | citation_urls
    if not exposed_urls:
        exposed_urls = structured_provider_urls
    if not exposed_urls:
        # No reliable linkage exists. Preserve provider metadata rather than applying
        # a relevance heuristic that could hide the only verifiable citations.
        exposed_urls = provider_urls

    sources: list[PublicAttentionSource] = []
    for index, url in enumerate(sorted(exposed_urls)):
        title, published_at = structured_sources.get(
            url,
            (provider_sources.get(url) or _domain(url), None),
        )
        try:
            source = PublicAttentionSource(
                title=title,
                url=url,
                source_domain=_domain(url),
                observed_at=observed_at,
                published_at=published_at,
            )
        except ValidationError as exc:
            _raise_pydantic_validation(exc, prefix=f"sources[{index}]")
        sources.append(source)

    status = RadarStatus.AVAILABLE if sources else RadarStatus.PARTIAL
    if not sources:
        confidence_context = _append_context(
            confidence_context,
            " No provider citation/source URL was returned; public attention is partial.",
            max_length=2000,
        )
    try:
        return PublicAttentionSnapshot(
            asset=asset,
            observed_at=observed_at,
            research_status=status,
            attention_direction=direction,
            quantitative_metrics=tuple(metrics),
            qualitative_observations=tuple(observations_list),
            possible_catalysts=tuple(catalysts_list),
            sources=tuple(sources),
            confidence_context=confidence_context,
        )
    except ValidationError as exc:
        _raise_pydantic_validation(exc, prefix="snapshot")


def _raise_manual_validation(*, path: str, code: str) -> None:
    error = PublicAttentionValidationError(
        validation_path=path,
        validation_code=code,
        validation_error_count=1,
    )
    _log_validation_error(error)
    raise error from None


def _raise_pydantic_validation(exc: ValidationError, *, prefix: str) -> None:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    first = errors[0] if errors else {}
    location = _validation_location(first.get("loc"))
    path = prefix if not location else f"{prefix}.{location}"
    code = first.get("type") if isinstance(first.get("type"), str) else "unknown"
    error = PublicAttentionValidationError(
        validation_path=path,
        validation_code=code,
        validation_error_count=len(errors) or 1,
    )
    _log_validation_error(error)
    raise error from None


def _log_validation_error(exc: PublicAttentionValidationError) -> None:
    logger.warning(
        "Public attention canonical validation failed path=%s code=%s errors=%d",
        exc.validation_path,
        exc.validation_code,
        exc.validation_error_count,
    )


def _validation_location(value: object) -> str:
    if not isinstance(value, tuple):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
        elif isinstance(item, str):
            parts.append(_bounded_token(item, max_length=64, fallback="field"))
    return ".".join(parts)


def _bounded_token(value: str, *, max_length: int, fallback: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.[]"
    cleaned = "".join(character if character in allowed else "_" for character in value)
    cleaned = cleaned.strip("._")
    return (cleaned or fallback)[:max_length]


def _list_of_dicts(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _accepted_source_url(value: object, accepted_urls: set[str]) -> str | None:
    url = _http_url(value)
    if url is None or url not in accepted_urls:
        return None
    return url


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.startswith(("https://", "http://")) or len(value) > 2048:
        return None
    return value


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _provider_title(value: object, *, fallback: str) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned and len(cleaned) <= 1000:
            return cleaned
    return fallback


def _append_context(value: str, suffix: str, *, max_length: int) -> str:
    room = max_length - len(suffix)
    if room <= 0:
        return suffix[:max_length]
    return value[:room].rstrip() + suffix


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _domain(url: str) -> str:
    domain = urlparse(url).netloc.lower().strip()
    return domain or "unknown"
