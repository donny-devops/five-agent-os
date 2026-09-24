from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_MANIFEST_DIR = REPO_ROOT / "prompts" / "agents"
POLICY_REGISTRY_PATH = REPO_ROOT / "policies" / "registry.json"
EVAL_FIXTURES_PATH = REPO_ROOT / "evals" / "fixtures.json"
SNAPSHOT_DIR = REPO_ROOT / "tests" / "snapshots" / "prompts"


@dataclass(frozen=True)
class AgentManifest:
    agent_id: str
    name: str
    version: str
    role: str
    mission: str
    owns: list[str]
    must_not: list[str]
    output_contract: str
    policies: list[str]
    prompt: str


@dataclass(frozen=True)
class PolicyRule:
    policy_id: str
    name: str
    severity: str
    patterns: list[str]
    action: str
    message: str


@dataclass
class GuardrailResult:
    allowed: bool
    triggered: list[dict[str, str]] = field(default_factory=list)

    @property
    def human_review_required(self) -> bool:
        return any(rule.get("action") == "escalate" for rule in self.triggered)


class PromptManifestError(ValueError):
    pass


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Parse the narrow YAML subset used by prompt manifests.

    This avoids a runtime PyYAML dependency while still making prompts reviewable as YAML.
    Supported forms: scalars, scalar lists, and literal block strings.
    """
    data: dict[str, Any] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw.startswith(" "):
            raise PromptManifestError(f"Unexpected indentation in {path}: {raw}")
        if ":" not in raw:
            raise PromptManifestError(f"Expected key/value line in {path}: {raw}")
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "|":
            block: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                block.append(lines[i][2:] if lines[i].startswith("  ") else "")
                i += 1
            data[key] = "\n".join(block).rstrip() + "\n"
            continue
        if value == "[]":
            data[key] = []
            i += 1
            continue
        if value == "":
            items: list[str] = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                items.append(_parse_scalar(lines[i][4:]))
                i += 1
            data[key] = items
            continue
        data[key] = _parse_scalar(value)
        i += 1
    return data


def load_manifest(path: Path) -> AgentManifest:
    raw = load_simple_yaml(path)
    required = {
        "agent_id",
        "name",
        "version",
        "role",
        "mission",
        "owns",
        "must_not",
        "output_contract",
        "policies",
        "prompt",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise PromptManifestError(f"{path} missing keys: {', '.join(missing)}")
    return AgentManifest(**{key: raw[key] for key in required})


def load_manifests(directory: Path = PROMPT_MANIFEST_DIR) -> dict[str, AgentManifest]:
    manifests = [load_manifest(path) for path in sorted(directory.glob("*.yaml"))]
    return {manifest.agent_id: manifest for manifest in manifests}


def load_policy_registry(path: Path = POLICY_REGISTRY_PATH) -> list[PolicyRule]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [PolicyRule(**rule) for rule in payload["rules"]]


def _matches_policy_pattern(pattern: str, text: str) -> bool:
    """Check if *pattern* matches *text* with word boundary awareness."""
    lead = r"\b" if re.match(r"^\w", pattern) else ""
    trail = r"\b" if re.search(r"\w$", pattern) else ""
    regex = rf"{lead}{pattern}{trail}"
    return bool(re.search(regex, text, flags=re.IGNORECASE))


def apply_guardrails(text: str, policies: list[PolicyRule] | None = None) -> GuardrailResult:
    rules = policies if policies is not None else load_policy_registry()
    triggered: list[dict[str, str]] = []
    for rule in rules:
        for pattern in rule.patterns:
            if _matches_policy_pattern(pattern, text):
                triggered.append(
                    {
                        "policy_id": rule.policy_id,
                        "name": rule.name,
                        "severity": rule.severity,
                        "action": rule.action,
                        "message": rule.message,
                    }
                )
                break
    allowed = not any(rule["action"] == "block" for rule in triggered)
    return GuardrailResult(allowed=allowed, triggered=triggered)


def _required_contract_keys(agent_name: str) -> tuple[str, ...]:
    contract_keys: dict[str, tuple[str, ...]] = {
        "data_synthesis_agent": (
            "summary",
            "key_facts",
            "entities",
            "success_criteria",
            "constraints",
            "contradictions",
            "assumptions",
            "confidence",
            "recommended_next_agent",
        ),
        "decision_making_agent": (
            "decision",
            "options",
            "recommended_option",
            "rationale",
            "risks",
            "mitigations",
            "human_approval_required",
            "next_agent",
        ),
        "content_outreach_agent": (
            "content_type",
            "audience",
            "subject_lines",
            "primary_draft",
            "alternate_drafts",
            "claims_requiring_verification",
            "placeholders",
            "next_agent",
        ),
        "compliance_quality_agent": (
            "status",
            "overall_score",
            "checks",
            "issues",
            "approved_for_delivery",
            "human_review_required",
            "revision_instructions",
        ),
    }
    return contract_keys.get(agent_name, ())


def validate_agent_contract(agent_name: str, output: dict[str, Any]) -> list[str]:
    if not isinstance(output, dict):
        return [f"{agent_name}: output must be an object"]
    return [
        f"{agent_name}: missing {key}" for key in _required_contract_keys(agent_name) if key not in output
    ]


def score_telemetry(agent_name: str, output: dict[str, Any], guardrail: GuardrailResult) -> dict[str, Any]:
    contract_errors = validate_agent_contract(agent_name, output)
    score = 100
    score -= 20 * len(contract_errors)
    score -= 15 * len(guardrail.triggered)
    return {
        "agent_name": agent_name,
        "contract_valid": not contract_errors,
        "contract_errors": contract_errors,
        "guardrail_triggers": guardrail.triggered,
        "quality_score": max(score, 0),
    }


def render_prompt_snapshot(manifest: AgentManifest) -> str:
    return "\n".join(
        [
            f"agent_id: {manifest.agent_id}",
            f"version: {manifest.version}",
            f"role: {manifest.role}",
            "prompt:",
            manifest.prompt.strip(),
            "",
        ]
    )


def load_eval_fixtures(path: Path = EVAL_FIXTURES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["fixtures"]


def evaluate_request(user_request: str) -> dict[str, Any]:
    guardrail = apply_guardrails(user_request)
    return {
        "input_allowed": guardrail.allowed,
        "human_review_required": guardrail.human_review_required,
        "triggered_policies": guardrail.triggered,
    }


SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|password|secret|token|credential|private[_-]?key)",
    re.IGNORECASE,
)


def scrub_sensitive_fields(payload: dict[str, Any]) -> dict[str, Any]:
    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if SENSITIVE_KEY_PATTERN.search(key) else walk(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return walk(payload)
