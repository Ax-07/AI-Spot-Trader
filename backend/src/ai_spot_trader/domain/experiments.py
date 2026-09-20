import hashlib
import json
from datetime import datetime
from decimal import Decimal

from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.models import AggressivenessContext, ExperimentManifest

AGGRESSIVENESS_MAPPING_VERSION = "aggressiveness-map-v1"
EXPERIMENT_PROTOCOL_VERSION = "paper-experiment-v1"

_AGGRESSIVENESS_PROFILES: tuple[tuple[str, str], ...] = (
    (
        "capital_preservation",
        "Prefer HOLD unless the supplied facts make a trade unusually compelling. "
        "When trading, propose the smallest strategically meaningful quantity.",
    ),
    (
        "very_conservative",
        "Require strong evidence before trading and keep proposed quantities very small. "
        "Prefer HOLD when the trade thesis is marginal or mixed.",
    ),
    (
        "conservative",
        "Trade selectively on clear evidence and keep proposed quantities small. "
        "Use HOLD readily when conviction is limited.",
    ),
    (
        "measured",
        "Favor selective trades with measured proposed quantities. "
        "Do not force activity when the evidence is inconclusive.",
    ),
    (
        "balanced",
        "Balance opportunity and restraint. Trade when the supplied facts support a clear thesis, "
        "using a moderate strategic quantity, otherwise HOLD.",
    ),
    (
        "active",
        "Be moderately more willing to act on a supported thesis and may propose a somewhat larger "
        "strategic quantity, while preserving HOLD for weak evidence.",
    ),
    (
        "assertive",
        "Act assertively when the supplied facts support a coherent thesis and may propose "
        "a larger strategic quantity. Do not trade merely to increase activity.",
    ),
    (
        "aggressive",
        "Be willing to act on a broader set of well-reasoned opportunities and may propose large "
        "strategic quantities, subject to the unchanged deterministic Risk Engine.",
    ),
    (
        "very_aggressive",
        "Favor action when the supplied facts support a plausible and coherent opportunity, and "
        "may propose very large strategic quantities. HOLD remains valid when no thesis is "
        "supportable.",
    ),
    (
        "maximum_experimental",
        "Use the highest experimental strategic initiative: act on supported opportunities and may "
        "propose the largest quantities justified by the supplied portfolio context. Never "
        "infer that Risk limits are relaxed, and HOLD remains valid when no defensible "
        "trade exists.",
    ),
)


def aggressiveness_context(level: int) -> AggressivenessContext:
    """Return the canonical discrete strategic mapping for one level from 1 to 10."""

    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 10:
        raise ValueError("aggressiveness must be an integer between 1 and 10")
    posture, instruction = _AGGRESSIVENESS_PROFILES[level - 1]
    return AggressivenessContext(
        mapping_version=AGGRESSIVENESS_MAPPING_VERSION,
        level=level,
        posture=posture,
        strategic_instruction=instruction,
    )


def validate_experiment_manifest_digest(manifest: ExperimentManifest) -> None:
    """Reject a durable manifest whose identity or canonical mapping was altered."""

    if manifest.protocol_version != EXPERIMENT_PROTOCOL_VERSION:
        raise ValueError("unsupported experiment protocol version")
    expected_context = aggressiveness_context(manifest.aggressiveness.level)
    if manifest.aggressiveness != expected_context:
        raise ValueError("experiment manifest aggressiveness mapping is not canonical")
    payload = manifest.model_dump(exclude={"experiment_digest"})
    actual = canonical_experiment_digest(payload)
    if actual != manifest.experiment_digest:
        raise ValueError("experiment manifest digest does not match its canonical fields")


def comparison_identity(manifest: ExperimentManifest) -> str:
    """Digest fixed protocol fields while intentionally excluding aggressiveness."""

    validate_experiment_manifest_digest(manifest)
    payload = manifest.model_dump(exclude={"experiment_digest", "aggressiveness"})
    payload["aggressiveness_mapping_version"] = manifest.aggressiveness.mapping_version
    return canonical_experiment_digest(payload)


def canonical_experiment_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: object) -> object:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, LLMModel):
        return value.value
    return value
