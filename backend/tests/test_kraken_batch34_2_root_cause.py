from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ai_spot_trader.integrations.kraken.errors import (
    KrakenNetworkError,
    KrakenPayloadError,
    KrakenPayloadStage,
    KrakenRateLimitError,
    KrakenServerError,
)
from ai_spot_trader.integrations.kraken.rest import (
    KrakenPublicRestClient,
    _parse_ohlcv_payload,
)
from ai_spot_trader.integrations.kraken.symbols import parse_asset_pairs_payload

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
START = NOW - timedelta(minutes=15)


def _row(offset: int = 0) -> list[object]:
    return [
        int((START + timedelta(minutes=5 * offset)).timestamp()),
        "100",
        "102",
        "99",
        "101",
        "100.5",
        "10",
        7,
    ]


def _ohlc_payload(pair_key: str = "BTC/USD") -> dict[str, object]:
    return {
        "error": [],
        "result": {
            pair_key: [_row(0), _row(1)],
            "last": int(NOW.timestamp()),
        },
    }


def test_asset_pairs_accepts_realistic_internal_rest_keys_and_preserves_aliases() -> None:
    registry = parse_asset_pairs_payload(
        {
            "error": [],
            "result": {
                "XXBTZUSD": {
                    "altname": "XBTUSD",
                    "wsname": "XBT/USD",
                    "base": "XXBT",
                    "quote": "ZUSD",
                    "status": "online",
                },
                "AAVEZUSD": {
                    "altname": "AAVEUSD",
                    "wsname": "AAVE/USD",
                    "base": "AAVE",
                    "quote": "ZUSD",
                    "status": "online",
                },
            },
        }
    )

    assert registry.normalize("BTC/USD") == "BTC/USD"
    assert registry.normalize("XBT/USD") == "BTC/USD"
    assert registry.normalize("XBTUSD") == "BTC/USD"
    assert registry.normalize("XXBTZUSD") == "BTC/USD"
    assert registry.normalize("AAVE/USD") == "AAVE/USD"
    assert registry.normalize("AAVEZUSD") == "AAVE/USD"



def test_asset_pairs_existing_display_key_contract_remains_compatible() -> None:
    registry = parse_asset_pairs_payload(
        {
            "error": [],
            "result": {
                "BTC/EUR": {
                    "altname": "XBTEUR",
                    "wsname": "XBT/EUR",
                    "status": "online",
                }
            },
        }
    )

    assert registry.normalize("BTC/EUR") == "BTC/EUR"
    assert registry.normalize("XBTEUR") == "BTC/EUR"
    assert registry.normalize("XBT/EUR") == "BTC/EUR"

def test_asset_pairs_atypical_entry_can_fall_back_to_base_quote_without_prefix_guessing() -> None:
    registry = parse_asset_pairs_payload(
        {
            "error": [],
            "result": {
                "XXBTZEUR": {
                    "altname": "XBTEUR",
                    "base": "XXBT",
                    "quote": "ZEUR",
                    "status": "online",
                },
                "ZRXUSD": {
                    "altname": "ZRXUSD",
                    "base": "ZRX",
                    "quote": "ZUSD",
                    "status": "online",
                },
            },
        }
    )

    assert registry.normalize("XXBTZEUR") == "BTC/EUR"
    assert registry.normalize("BTC/EUR") == "BTC/EUR"
    assert registry.normalize("ZRX/USD") == "ZRX/USD"


def test_asset_pairs_unusable_entry_still_fails_closed_with_bounded_stage() -> None:
    with pytest.raises(KrakenPayloadError) as exc_info:
        parse_asset_pairs_payload(
            {
                "error": [],
                "result": {
                    "OPAQUEKEY": {
                        "altname": "OPAQUE",
                        "status": "online",
                    }
                },
            }
        )

    assert exc_info.value.stage is KrakenPayloadStage.ASSET_PAIRS_SYMBOL
    assert "OPAQUEKEY" not in str(exc_info.value)
    assert "OPAQUE" not in str(exc_info.value)




def test_asset_pairs_inconsistent_wsname_and_base_quote_fails_closed() -> None:
    with pytest.raises(KrakenPayloadError) as exc_info:
        parse_asset_pairs_payload(
            {
                "error": [],
                "result": {
                    "PRIVATE-PROVIDER-VALUE": {
                        "altname": "XBTUSD",
                        "wsname": "XBT/USD",
                        "base": "XETH",
                        "quote": "ZUSD",
                        "status": "online",
                    }
                },
            }
        )

    assert exc_info.value.stage is KrakenPayloadStage.ASSET_PAIRS_SYMBOL
    assert "PRIVATE-PROVIDER-VALUE" not in str(exc_info.value)

def test_asset_pairs_bad_entry_and_bad_envelope_have_distinct_safe_stages() -> None:
    with pytest.raises(KrakenPayloadError) as entry_exc:
        parse_asset_pairs_payload({"error": [], "result": {"SECRET": "raw-body"}})
    with pytest.raises(KrakenPayloadError) as payload_exc:
        parse_asset_pairs_payload({"error": "SECRET", "result": {}})

    assert entry_exc.value.stage is KrakenPayloadStage.ASSET_PAIRS_ENTRY
    assert payload_exc.value.stage is KrakenPayloadStage.ASSET_PAIRS_PAYLOAD
    assert "raw-body" not in str(entry_exc.value)
    assert "SECRET" not in str(payload_exc.value)


def test_ohlc_normal_canonical_key_is_accepted() -> None:
    rows = _parse_ohlcv_payload(
        _ohlc_payload("BTC/USD"),
        interval_minutes=5,
        expected_symbol="BTC/USD",
        received_at=NOW,
    )

    assert len(rows) == 2
    assert rows[0].close_price.as_tuple().digits


@pytest.mark.parametrize("pair_key", ["BTC/USD", "XBT/USD", "XBTUSD", "XXBTZUSD"])
def test_ohlc_accepts_canonical_display_altname_and_legacy_internal_keys(pair_key: str) -> None:
    rows = _parse_ohlcv_payload(
        _ohlc_payload(pair_key),
        interval_minutes=5,
        expected_symbol="BTC/USD",
        received_at=NOW,
    )

    assert len(rows) == 2


def test_ohlc_runtime_721_row_response_is_accepted_but_722_is_rejected() -> None:
    start = NOW - timedelta(minutes=5 * 720)

    def rows(count: int) -> list[list[object]]:
        return [
            [
                int((start + timedelta(minutes=5 * index)).timestamp()),
                "100",
                "102",
                "99",
                "101",
                "100.5",
                "10",
                7,
            ]
            for index in range(count)
        ]

    accepted = _parse_ohlcv_payload(
        {"error": [], "result": {"BTC/USD": rows(721), "last": int(NOW.timestamp())}},
        interval_minutes=5,
        expected_symbol="BTC/USD",
        received_at=NOW,
    )
    assert len(accepted) == 721
    assert accepted[-2].is_final is True
    assert accepted[-1].is_final is False

    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            {"error": [], "result": {"BTC/USD": rows(722), "last": int(NOW.timestamp())}},
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW + timedelta(minutes=5),
        )

    assert exc_info.value.stage is KrakenPayloadStage.OHLC_SERIES


def test_ohlc_wrong_pair_key_is_rejected_at_pair_key_stage() -> None:
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            _ohlc_payload("ETH/USD"),
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )

    assert exc_info.value.stage is KrakenPayloadStage.OHLC_PAIR_KEY
    assert "ETH/USD" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "expected_stage"),
    [
        ({"error": [], "result": None}, KrakenPayloadStage.OHLC_RESULT),
        ({"error": [], "result": {"last": 1}}, KrakenPayloadStage.OHLC_SERIES),
        (
            {"error": [], "result": {"BTC/USD": ["bad-row"], "last": 1}},
            KrakenPayloadStage.OHLC_ROW,
        ),
        (
            {
                "error": [],
                "result": {
                    "BTC/USD": [["bad-ts", "1", "1", "1", "1", "1", "1"]],
                    "last": 1,
                },
            },
            KrakenPayloadStage.OHLC_TIMESTAMP,
        ),
        (
            {
                "error": [],
                "result": {
                    "BTC/USD": [
                        [int(START.timestamp()), "bad", "1", "1", "1", "1", "1"]
                    ],
                    "last": 1,
                },
            },
            KrakenPayloadStage.OHLC_NUMERIC,
        ),
    ],
)
def test_ohlc_structural_failures_report_only_allowlisted_stage(
    payload: object,
    expected_stage: KrakenPayloadStage,
) -> None:
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            payload,
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )

    assert exc_info.value.stage is expected_stage


def test_transport_classes_429_5xx_and_network_are_unchanged() -> None:
    async def status_error(status: int) -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text="PRIVATE RESPONSE BODY", request=request)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(Exception) as exc_info:
                await client.fetch_pair_registry()
            return exc_info.value

    async def network_error() -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("PRIVATE NETWORK DETAIL", request=request)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(Exception) as exc_info:
                await client.fetch_pair_registry()
            return exc_info.value

    rate = asyncio.run(status_error(429))
    server = asyncio.run(status_error(503))
    network = asyncio.run(network_error())

    assert isinstance(rate, KrakenRateLimitError)
    assert isinstance(server, KrakenServerError)
    assert isinstance(network, KrakenNetworkError)
    assert "PRIVATE" not in str(rate)
    assert "PRIVATE" not in str(server)
    assert "PRIVATE" not in str(network)


@pytest.mark.parametrize(
    ("mutator", "expected_stage"),
    [
        (lambda rows: rows.__setitem__(0, [1, 2]), KrakenPayloadStage.OHLC_ROW),
        (lambda rows: rows[0].__setitem__(0, "not-a-timestamp"), KrakenPayloadStage.OHLC_TIMESTAMP),
        (lambda rows: rows[0].__setitem__(4, "not-a-number"), KrakenPayloadStage.OHLC_NUMERIC),
    ],
)
def test_legacy_internal_pair_key_preserves_deeper_failure_stage(mutator, expected_stage) -> None:
    rows = [_row(0), _row(1)]
    mutator(rows)
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            {"error": [], "result": {"XXBTZUSD": rows, "last": 1}},
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )

    assert exc_info.value.stage is expected_stage


def test_asset_pairs_payload_log_contains_only_operation_and_stage(caplog) -> None:
    secret = "PRIVATE-PROVIDER-VALUE"

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "error": [],
                    "result": {
                        secret: {
                            "altname": "XBTUSD",
                            "wsname": "XBT/USD",
                            "base": "XETH",
                            "quote": "ZUSD",
                            "status": "online",
                        }
                    },
                },
                request=request,
            )

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenPayloadError):
                await client.fetch_pair_registry()

    with caplog.at_level("WARNING"):
        asyncio.run(scenario())

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "operation=AssetPairs" in messages
    assert "stage=ASSET_PAIRS_SYMBOL" in messages
    assert secret not in messages
    assert "XETH" not in messages


def test_client_spot_flow_accepts_legacy_internal_ohlc_key() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/AssetPairs"):
                return httpx.Response(
                    200,
                    json={
                        "error": [],
                        "result": {
                            "XXBTZUSD": {
                                "altname": "XBTUSD",
                                "wsname": "XBT/USD",
                                "base": "XXBT",
                                "quote": "ZUSD",
                                "status": "online",
                            }
                        },
                    },
                    request=request,
                )
            if request.url.path.endswith("/OHLC"):
                return httpx.Response(
                    200,
                    json={
                        "error": [],
                        "result": {"XXBTZUSD": [_row(0), _row(1)], "last": 1},
                    },
                    request=request,
                )
            raise AssertionError(request.url.path)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            registry = await client.fetch_pair_registry()
            symbol = registry.normalize("BTC/USD")
            candles = await client.fetch_ohlcv_history(
                symbol,
                interval_minutes=5,
                since=START - timedelta(minutes=5),
            )

        assert symbol == "BTC/USD"
        assert len(candles) == 2

    asyncio.run(scenario())
