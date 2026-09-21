import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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

OHLC_START = datetime(2026, 9, 20, 11, 57, tzinfo=UTC)
OHLC_PAYLOAD = {
    "error": [],
    "result": {
        "BTC/EUR": [
            [int(OHLC_START.timestamp()), "99", "101", "98", "100", "100", "1", 10],
            [
                int((OHLC_START + timedelta(minutes=1)).timestamp()),
                "100",
                "102",
                "99",
                "101",
                "101",
                "1",
                11,
            ],
            [
                int((OHLC_START + timedelta(minutes=2)).timestamp()),
                "101",
                "103",
                "100",
                "102",
                "102",
                "1",
                12,
            ],
        ],
        "last": int((OHLC_START + timedelta(minutes=3)).timestamp()),
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


def test_ohlc_history_uses_display_symbol_and_excludes_uncommitted_tail() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_params
        assert request.url.path == "/0/public/OHLC"
        seen_params = dict(request.url.params)
        return httpx.Response(200, json=OHLC_PAYLOAD)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            candles = await client.fetch_ohlc_history(
                "BTC/EUR",
                interval_minutes=1,
                since=OHLC_START - timedelta(minutes=1),
            )

        assert len(candles) == 2
        assert candles[0].started_at == OHLC_START
        assert candles[0].closed_at == OHLC_START + timedelta(minutes=1)
        assert candles[0].close_price == Decimal("100")
        assert candles[1].closed_at == OHLC_START + timedelta(minutes=2)
        assert candles[1].close_price == Decimal("101")

    asyncio.run(scenario())
    assert seen_params["pair"] == "BTC/EUR"
    assert seen_params["assetVersion"] == "1"
    assert seen_params["interval"] == "1"
    assert seen_params["since"] == str(int((OHLC_START - timedelta(minutes=1)).timestamp()))


def test_ohlc_api_error_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/0/public/OHLC"
        return httpx.Response(
            200,
            json={"error": ["EGeneral:sensitive provider detail"], "result": {}},
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenPayloadError, match="API error") as exc_info:
                await client.fetch_ohlc_history(
                    "BTC/EUR",
                    interval_minutes=1,
                    since=OHLC_START,
                )
            assert "sensitive provider detail" not in str(exc_info.value)

    asyncio.run(scenario())


def test_ohlc_rejects_non_chronological_committed_rows() -> None:
    payload = {
        "error": [],
        "result": {
            "BTC/EUR": [
                [int((OHLC_START + timedelta(minutes=1)).timestamp()), "1", "1", "1", "1"],
                [int(OHLC_START.timestamp()), "1", "1", "1", "1"],
                [int((OHLC_START + timedelta(minutes=2)).timestamp()), "1", "1", "1", "1"],
            ],
            "last": int((OHLC_START + timedelta(minutes=3)).timestamp()),
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenPayloadError, match="chronological"):
                await client.fetch_ohlc_history(
                    "BTC/EUR",
                    interval_minutes=1,
                    since=OHLC_START,
                )

    asyncio.run(scenario())


def test_ohlc_since_must_be_timezone_aware() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient() as http_client:
            client = KrakenPublicRestClient(
                "https://api.kraken.test",
                client=http_client,
            )
            with pytest.raises(ValueError, match="timezone-aware"):
                await client.fetch_ohlc_history(
                    "BTC/EUR",
                    interval_minutes=1,
                    since=datetime(2026, 9, 20, 12, 0),
                )

    asyncio.run(scenario())
