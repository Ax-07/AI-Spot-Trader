from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

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


class PublicAttentionResearchError(RuntimeError):
    """Raised by the auxiliary web-research adapter; callers must fail soft."""


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
        return _snapshot_from_payload(
            payload,
            asset=clean_asset,
            observed_at=observed_at,
            provider_sources=provider_sources,
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
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                response = await client.post(
                    f"{self._base_url}/responses",
                    headers=headers,
                    json=request,
                    timeout=self._timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise PublicAttentionResearchError("OpenAI web research transport failed") from exc
            if response.status_code == 429 or response.status_code >= 500:
                last_error = PublicAttentionResearchError(
                    f"OpenAI web research transient HTTP {response.status_code}"
                )
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
            if response.status_code >= 400:
                raise PublicAttentionResearchError(
                    f"OpenAI web research returned HTTP {response.status_code}"
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
        raise PublicAttentionResearchError("OpenAI web research failed") from last_error


def _extract_structured_payload(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("status") != "completed":
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


def _add_source(sources: dict[str, str], raw: object) -> None:
    if not isinstance(raw, dict):
        return
    candidate = raw.get("url_citation") if isinstance(raw.get("url_citation"), dict) else raw
    if not isinstance(candidate, dict):
        return
    url = candidate.get("url")
    title = candidate.get("title")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return
    clean_title = title.strip() if isinstance(title, str) and title.strip() else _domain(url)
    sources.setdefault(url, clean_title)


def _snapshot_from_payload(
    payload: dict[str, Any],
    *,
    asset: str,
    observed_at: datetime,
    provider_sources: dict[str, str],
) -> PublicAttentionSnapshot:
    try:
        direction = PublicAttentionDirection(str(payload["attention_direction"]))
        confidence_context = str(payload["confidence_context"]).strip()
    except (KeyError, ValueError) as exc:
        raise PublicAttentionResearchError(
            "Structured public attention contract is invalid"
        ) from exc
    if not confidence_context:
        raise PublicAttentionResearchError(
            "Structured public attention confidence_context is empty"
        )

    structured_sources: dict[str, tuple[str, datetime | None]] = {}
    for raw in _list_of_dicts(payload.get("sources")):
        url = _http_url(raw.get("url"))
        if url is None:
            continue
        structured_sources[url] = (
            _text(raw.get("title")) or provider_sources.get(url) or _domain(url),
            _optional_datetime(raw.get("published_at")),
        )

    # Trust only URLs surfaced by the Responses web-search metadata. Structured output may
    # describe them, but cannot create a canonical source URL on its own.
    accepted_urls = set(provider_sources)
    sources: list[PublicAttentionSource] = []
    for url in sorted(accepted_urls):
        title, published_at = structured_sources.get(
            url,
            (provider_sources.get(url) or _domain(url), None),
        )
        sources.append(
            PublicAttentionSource(
                title=title,
                url=url,
                source_domain=_domain(url),
                observed_at=observed_at,
                published_at=published_at,
            )
        )

    metrics: list[PublicAttentionMetric] = []
    for raw in _list_of_dicts(payload.get("quantitative_metrics")):
        source_url = _accepted_source_url(raw.get("source_url"), accepted_urls)
        name = _text(raw.get("name"))
        value = _text(raw.get("value"))
        if not name or not value:
            continue
        metrics.append(
            PublicAttentionMetric(
                name=name,
                value=value,
                unit=_text(raw.get("unit")),
                window=_text(raw.get("window")),
                source_url=source_url,
                observed_at=observed_at,
                published_at=_optional_datetime(raw.get("published_at")),
            )
        )

    observations = tuple(
        PublicAttentionObservation(
            text=text,
            source_url=_accepted_source_url(raw.get("source_url"), accepted_urls),
        )
        for raw in _list_of_dicts(payload.get("qualitative_observations"))
        if (text := _text(raw.get("text")))
    )
    catalysts = tuple(
        PublicAttentionCatalyst(
            description=description,
            source_url=_accepted_source_url(raw.get("source_url"), accepted_urls),
        )
        for raw in _list_of_dicts(payload.get("possible_catalysts"))
        if (description := _text(raw.get("description")))
    )
    status = RadarStatus.AVAILABLE if sources else RadarStatus.PARTIAL
    if not sources:
        confidence_context = (
            confidence_context
            + " No provider citation/source URL was returned; public attention is partial."
        )
    return PublicAttentionSnapshot(
        asset=asset,
        observed_at=observed_at,
        research_status=status,
        attention_direction=direction,
        quantitative_metrics=tuple(metrics),
        qualitative_observations=observations,
        possible_catalysts=catalysts,
        sources=tuple(sources),
        confidence_context=confidence_context,
    )


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
    if not value.startswith(("https://", "http://")):
        return None
    return value


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


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
