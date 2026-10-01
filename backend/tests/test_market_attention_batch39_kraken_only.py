from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATTENTION = ROOT / "src" / "ai_spot_trader" / "market" / "attention.py"
MAIN = ROOT / "src" / "ai_spot_trader" / "main.py"
OBSOLETE_INTEGRATION = ROOT / "src" / "ai_spot_trader" / "integrations" / "openai_market_attention.py"


def test_radar_runtime_contains_no_openai_or_web_research_path() -> None:
    attention = ATTENTION.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    forbidden = (
        "OpenAIWebAttentionResearcher",
        "PublicAttentionResearcher",
        "PublicAttentionSnapshot",
        "PublicResearchDecision",
        "web_search_count",
        "max_web_searches_per_refresh",
        "public_attention_ttl_seconds",
        "public_attention_event_cooldown_seconds",
        "public_research",
    )
    for token in forbidden:
        assert token not in attention
        assert token not in main


def test_obsolete_openai_market_attention_integration_is_deleted() -> None:
    assert not OBSOLETE_INTEGRATION.exists()


def test_modified_radar_runtime_contains_no_obvious_secret_literal() -> None:
    combined = ATTENTION.read_text(encoding="utf-8") + MAIN.read_text(encoding="utf-8")
    assert "sk-" not in combined
    assert "BEGIN PRIVATE KEY" not in combined
