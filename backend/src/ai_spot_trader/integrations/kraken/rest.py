import json

import httpx

from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError
from ai_spot_trader.integrations.kraken.symbols import KrakenPairRegistry, parse_asset_pairs_payload


class KrakenPublicRestClient:
    """Small unauthenticated REST client used only for Kraken Spot pair discovery."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self._owns_client = client is None

    async def fetch_pair_registry(self) -> KrakenPairRegistry:
        try:
            response = await self._client.get(
                "/0/public/AssetPairs",
                params={"assetVersion": 1, "aclass_base": "currency"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KrakenConnectionError("Kraken AssetPairs request failed") from exc

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise KrakenPayloadError("Kraken AssetPairs returned invalid JSON") from exc
        return parse_asset_pairs_payload(payload)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
