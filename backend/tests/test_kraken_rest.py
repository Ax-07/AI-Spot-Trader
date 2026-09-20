import asyncio

import httpx
import pytest

from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, UnknownKrakenSymbolError
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient

ASSET_PAIRS_PAYLOAD = {
    "error": [],
    "result": {
        "BTC/EUR": {
            "altname": "XBTEUR",
            "wsname": "XBT/EUR",
            "status": "online",
        },
        "ETH/EUR": {
            "altname": "ETHEUR",
            "wsname": "ETH/EUR",
            "status": "online",
        },
    },
}


def test_asset_pairs_discovery_normalizes_documented_aliases() -> None:
    seen_query = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_query
        seen_query = request.url.query.decode()
        assert request.url.path == "/0/public/AssetPairs"
        return httpx.Response(200, json=ASSET_PAIRS_PAYLOAD)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            registry = await client.fetch_pair_registry()

        assert registry.normalize("btc/eur") == "BTC/EUR"
        assert registry.normalize("XBTEUR") == "BTC/EUR"
        assert registry.normalize("XBT/EUR") == "BTC/EUR"
        with pytest.raises(UnknownKrakenSymbolError):
            registry.normalize("DOGE/NOPE")

    asyncio.run(scenario())
    assert "assetVersion=1" in seen_query
    assert "aclass_base=currency" in seen_query


def test_asset_pairs_api_error_is_rejected_without_leaking_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": ["EGeneral:Temporary lockout"], "result": {}})

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenPayloadError, match="API error") as exc_info:
                await client.fetch_pair_registry()
            assert "Temporary lockout" not in str(exc_info.value)

    asyncio.run(scenario())


def test_asset_pairs_invalid_json_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenPayloadError, match="invalid JSON"):
                await client.fetch_pair_registry()

    asyncio.run(scenario())
