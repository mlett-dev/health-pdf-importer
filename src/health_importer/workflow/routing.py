from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from health_importer.state_db import StateDb
from health_importer.workflow.text_verification import TextVerificationResult
from health_importer.workflow.validation import ValidationResult


class RouteAction(StrEnum):
    AUTO_CREATE = "AUTO_CREATE"
    CREATE_WITH_REVIEW_STATUS = "CREATE_WITH_REVIEW_STATUS"
    REVIEW_ONLY = "REVIEW_ONLY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RoutingDecision:
    action: RouteAction
    review_reasons: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "review_reasons": self.review_reasons,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
        }


def decide_next_action(
    validation: ValidationResult,
    *,
    text_verification: TextVerificationResult | None = None,
    technical_error: str | None = None,
) -> RoutingDecision:
    if technical_error:
        return RoutingDecision(
            action=RouteAction.ERROR,
            blocking_reasons=[technical_error],
        )

    blocking_reasons = list(validation.errors)
    warnings = list(validation.warnings)

    if text_verification:
        warnings.extend(text_verification.warnings)
        blocking_reasons.extend(
            warning
            for warning in text_verification.warnings
            if warning in _TEXT_VERIFICATION_BLOCKERS
        )

    if blocking_reasons:
        return RoutingDecision(
            action=RouteAction.REVIEW_ONLY,
            review_reasons=_dedupe(blocking_reasons + warnings),
            blocking_reasons=_dedupe(blocking_reasons),
            warnings=_dedupe(warnings),
        )

    review_reasons = _dedupe(warnings)
    if review_reasons:
        return RoutingDecision(
            action=RouteAction.CREATE_WITH_REVIEW_STATUS,
            review_reasons=review_reasons,
            warnings=review_reasons,
        )

    return RoutingDecision(action=RouteAction.AUTO_CREATE)


def store_routing_decision(
    state_db: StateDb,
    *,
    file_id: int,
    decision: RoutingDecision,
) -> None:
    state_db.add_event(file_id, "routing_decision", decision.to_dict())


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


_TEXT_VERIFICATION_BLOCKERS = {
    "amount_not_found_in_text",
    "amount_not_found_in_vision",
    "date_not_found_in_text",
    "date_not_found_in_vision",
}
