"""Match every row of a Pkv Sammelbrief to its own invoice object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from health_importer.anytype.pkv_matching import PkvMatchCandidate, score_pkv_candidates

if TYPE_CHECKING:
    from health_importer.anytype.client import AnytypeObjectRef
    from health_importer.config import AnytypeConfig
    from health_importer.workflow.pkv_sammelbrief import ValidatedPkvPosition

# A Sammelbrief is written to several invoices without anyone looking, so a
# row only counts as matched when amount AND treatment date both agree: the
# same doctor often bills the same amount for recurring visits.
_REQUIRED_REASON_PREFIXES = ("aufwendungsbetrag_exact:", "termin_close:")


@dataclass
class PositionMatch:
    position: "ValidatedPkvPosition"
    selected: PkvMatchCandidate | None
    review_reason: str | None
    candidates: list[PkvMatchCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "object_id": self.selected.object_ref.id if self.selected else None,
            "name": self.selected.object_ref.name if self.selected else None,
            "score": self.selected.score if self.selected else None,
            "reasons": self.selected.match_reasons if self.selected else [],
            "review_reason": self.review_reason,
            "candidates": [
                {
                    "object_id": c.object_ref.id,
                    "name": c.object_ref.name,
                    "score": c.score,
                    "reasons": c.match_reasons,
                }
                for c in self.candidates[:3]
            ],
        }


def match_sammelbrief_positions(
    positionen: list["ValidatedPkvPosition"],
    candidates_by_patient: dict[str, list["AnytypeObjectRef"]],
    object_properties: dict[str, dict],
    config: "AnytypeConfig",
    *,
    auto_min: float,
) -> list[PositionMatch]:
    """Pick one invoice per row; a row without a clear, unshared winner gets a review reason."""
    matches: list[PositionMatch] = []
    for position in positionen:
        scored = score_pkv_candidates(
            candidates_by_patient.get(position.patient_first_name, []),
            position.patient_first_name,
            position.aufwendungsbetrag_eur,
            position.betreffender_termin,
            None,
            object_properties,
            config,
        )
        matches.append(_decide(position, scored, auto_min))

    # One invoice cannot absorb two rows: that would overwrite the first
    # Erstattung with the second.
    by_object: dict[str, list[PositionMatch]] = {}
    for match in matches:
        if match.selected is not None:
            by_object.setdefault(match.selected.object_ref.id, []).append(match)
    for shared in by_object.values():
        if len(shared) > 1:
            for match in shared:
                match.review_reason = "invoice_matched_by_several_positionen"
                match.selected = None
    return matches


def _decide(
    position: "ValidatedPkvPosition",
    scored: list[PkvMatchCandidate],
    auto_min: float,
) -> PositionMatch:
    if not scored:
        return PositionMatch(position, None, "no_invoice_candidates", scored)
    top = scored[0]
    missing = [
        prefix.rstrip(":")
        for prefix in _REQUIRED_REASON_PREFIXES
        if not any(reason.startswith(prefix) for reason in top.match_reasons)
    ]
    if missing:
        return PositionMatch(position, None, f"top_candidate_lacks:{','.join(missing)}", scored)
    if top.score < auto_min:
        return PositionMatch(position, None, f"top_score_below_auto_min:{top.score:.2f}", scored)
    if len(scored) > 1 and scored[1].score >= auto_min:
        return PositionMatch(position, None, "ambiguous_runner_up", scored)
    return PositionMatch(position, top, None, scored)
