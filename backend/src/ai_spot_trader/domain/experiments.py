import hashlib
import json
from datetime import datetime
from decimal import Decimal

from ai_spot_trader.domain.enums import ExperimentVariable, LLMModel
from ai_spot_trader.domain.models import AggressivenessContext, ExperimentManifest

AGGRESSIVENESS_MAPPING_VERSION = "aggressiveness-map-v1"
EXPERIMENT_PROTOCOL_VERSION = "paper-experiment-v1"
MODEL_EXPERIMENT_PROTOCOL_VERSION = "paper-experiment-v2"

_MODEL_EXPERIMENT_FIELDS = {
    "comparison_variable",
    "experiment_group_digest",
    "replicate_index",
    "replicate_count",
}

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
    """Reject manifests whose protocol identity, grouping, or canonical mapping was altered."""

    if manifest.protocol_version not in {
        EXPERIMENT_PROTOCOL_VERSION,
        MODEL_EXPERIMENT_PROTOCOL_VERSION,
    }:
        raise ValueError("unsupported experiment protocol version")

    expected_context = aggressiveness_context(manifest.aggressiveness.level)
    if manifest.aggressiveness != expected_context:
        raise ValueError("experiment manifest aggressiveness mapping is not canonical")

    if manifest.protocol_version == EXPERIMENT_PROTOCOL_VERSION:
        if any(getattr(manifest, field) is not None for field in _MODEL_EXPERIMENT_FIELDS):
            raise ValueError("paper-experiment-v1 cannot carry model-comparison metadata")
    else:
        _validate_model_experiment_metadata(manifest)
        expected_group = canonical_experiment_digest(_model_comparison_payload(manifest))
        if expected_group != manifest.experiment_group_digest:
            raise ValueError("experiment group digest does not match controlled fields")

    actual = canonical_experiment_digest(_manifest_digest_payload(manifest))
    if actual != manifest.experiment_digest:
        raise ValueError("experiment manifest digest does not match its canonical fields")


def comparison_identity(manifest: ExperimentManifest) -> str:
    """Digest Batch 13 controlled fields while intentionally excluding aggressiveness."""

    validate_experiment_manifest_digest(manifest)
    if manifest.protocol_version != EXPERIMENT_PROTOCOL_VERSION:
        raise ValueError("aggressiveness comparison requires paper-experiment-v1")
    payload = manifest.model_dump(
        exclude={"experiment_digest", "aggressiveness", *_MODEL_EXPERIMENT_FIELDS}
    )
    payload["aggressiveness_mapping_version"] = manifest.aggressiveness.mapping_version
    return canonical_experiment_digest(payload)


def model_comparison_identity(manifest: ExperimentManifest) -> str:
    """Return the verified group identity for a controlled Luna/Sol experiment."""

    validate_experiment_manifest_digest(manifest)
    if manifest.protocol_version != MODEL_EXPERIMENT_PROTOCOL_VERSION:
        raise ValueError("model comparison requires paper-experiment-v2")
    assert manifest.experiment_group_digest is not None
    return manifest.experiment_group_digest


def model_comparison_group_digest(manifest: ExperimentManifest) -> str:
    """Calculate the deterministic group digest before the full manifest digest is assigned."""

    if manifest.protocol_version != MODEL_EXPERIMENT_PROTOCOL_VERSION:
        raise ValueError("model comparison group digest requires paper-experiment-v2")
    _validate_model_experiment_metadata(manifest, allow_zero_group_digest=True)
    return canonical_experiment_digest(_model_comparison_payload(manifest))


def manifest_digest_payload(manifest: ExperimentManifest) -> dict[str, object]:
    """Return the version-aware payload used for the durable experiment digest."""

    return _manifest_digest_payload(manifest)


def canonical_experiment_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_digest_payload(manifest: ExperimentManifest) -> dict[str, object]:
    exclude = {"experiment_digest"}
    if manifest.protocol_version == EXPERIMENT_PROTOCOL_VERSION:
        exclude.update(_MODEL_EXPERIMENT_FIELDS)
    return manifest.model_dump(exclude=exclude)


def _model_comparison_payload(manifest: ExperimentManifest) -> dict[str, object]:
    return manifest.model_dump(
        exclude={
            "experiment_digest",
            "experiment_group_digest",
            "llm_model",
            "replicate_index",
        }
    )


def _validate_model_experiment_metadata(
    manifest: ExperimentManifest,
    *,
    allow_zero_group_digest: bool = False,
) -> None:
    if manifest.comparison_variable is not ExperimentVariable.LLM_MODEL:
        raise ValueError("paper-experiment-v2 comparison_variable must be LLM_MODEL")
    if manifest.experiment_group_digest is None:
        raise ValueError("paper-experiment-v2 requires experiment_group_digest")
    if not allow_zero_group_digest and manifest.experiment_group_digest == "0" * 64:
        raise ValueError("paper-experiment-v2 requires a finalized group digest")
    if manifest.replicate_index is None or manifest.replicate_count is None:
        raise ValueError("paper-experiment-v2 requires replicate metadata")
    if manifest.replicate_index > manifest.replicate_count:
        raise ValueError("replicate_index cannot exceed replicate_count")
    if manifest.source_digest is None:
        raise ValueError("paper-experiment-v2 requires a frozen source_digest")


def _jsonable(value: object) -> object:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (LLMModel, ExperimentVariable)):
        return value.value
    return value
