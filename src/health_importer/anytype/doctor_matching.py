from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz import fuzz

from health_importer.anytype.client import AnytypeClient, AnytypeObjectRef


class DoctorMatchStatus(StrEnum):
    MATCHED = "matched"
    REVIEW = "review"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class DoctorMatch:
    status: DoctorMatchStatus
    doctor: AnytypeObjectRef | None
    score: float
    review_reason: str | None = None

    @property
    def should_set_relation(self) -> bool:
        return self.status is DoctorMatchStatus.MATCHED and self.doctor is not None


def load_doctor_candidates(client: AnytypeClient) -> list[AnytypeObjectRef]:
    return client.search_object_by_type("arzt", "")


def match_doctor(
    raw_name: str | None,
    candidates: list[AnytypeObjectRef],
    *,
    match_threshold: float = 92.0,
    review_threshold: float = 80.0,
    ambiguity_margin: float = 3.0,
) -> DoctorMatch:
    normalized_query = normalize_doctor_name(raw_name or "")
    if not normalized_query:
        return DoctorMatch(
            status=DoctorMatchStatus.NO_MATCH,
            doctor=None,
            score=0.0,
            review_reason="doctor_name_missing",
        )
    if not candidates:
        return DoctorMatch(
            status=DoctorMatchStatus.REVIEW,
            doctor=None,
            score=0.0,
            review_reason="doctor_candidates_missing",
        )

    normalized_candidates = [
        (candidate, normalize_doctor_name(candidate.name)) for candidate in candidates
    ]
    exact_matches = [
        candidate
        for candidate, normalized_name in normalized_candidates
        if normalized_name == normalized_query
    ]
    if len(exact_matches) == 1:
        return DoctorMatch(status=DoctorMatchStatus.MATCHED, doctor=exact_matches[0], score=100.0)
    if len(exact_matches) > 1:
        return DoctorMatch(
            status=DoctorMatchStatus.REVIEW,
            doctor=None,
            score=100.0,
            review_reason="doctor_match_ambiguous",
        )

    scored = sorted(
        (
            (candidate, float(fuzz.WRatio(normalized_query, normalized_name)))
            for candidate, normalized_name in normalized_candidates
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    best_candidate, best_score = scored[0]
    if best_score < review_threshold:
        return DoctorMatch(
            status=DoctorMatchStatus.NO_MATCH,
            doctor=None,
            score=best_score,
            review_reason="doctor_match_not_found",
        )

    close_matches = [
        candidate for candidate, score in scored if best_score - score <= ambiguity_margin
    ]
    if len(close_matches) > 1:
        return DoctorMatch(
            status=DoctorMatchStatus.REVIEW,
            doctor=None,
            score=best_score,
            review_reason="doctor_match_ambiguous",
        )
    if best_score < match_threshold:
        return DoctorMatch(
            status=DoctorMatchStatus.REVIEW,
            doctor=None,
            score=best_score,
            review_reason="doctor_match_below_confidence_threshold",
        )
    return DoctorMatch(status=DoctorMatchStatus.MATCHED, doctor=best_candidate, score=best_score)


def normalize_doctor_name(value: str) -> str:
    normalized = _replace_german_umlauts(value).casefold()
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = _PAREN_RE.sub(" ", normalized)
    normalized = _TITLE_RE.sub(" ", normalized)
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized


def _replace_german_umlauts(value: str) -> str:
    replacements = {
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


_PAREN_RE = re.compile(r"\([^)]*\)")
_TITLE_RE = re.compile(
    r"\b(?:dr|med|univ|prof|prim|oa|ordination|praxis|frau|herr|mag|mr|mrs|ms)\b"
)
_PUNCTUATION_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")
