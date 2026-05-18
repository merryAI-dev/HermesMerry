from __future__ import annotations

from dataclasses import replace

from merry_runtime.models import CandidateCard, Decision, Review


class ReviewValidationError(ValueError):
    pass


_DECISION_TO_STATUS = {
    Decision.ADVANCE: "advanced",
    Decision.WATCHLIST: "watchlist",
    Decision.REJECT: "rejected",
    Decision.REQUEST_MORE_INFO: "needs_info",
}


def parse_review_row(row: dict[str, str], *, valid_card_ids: set[str]) -> Review:
    card_id = (row.get("card_id") or "").strip()
    if card_id not in valid_card_ids:
        raise ReviewValidationError(f"Unknown card_id: {card_id}")

    reviewer = (row.get("reviewer") or "").strip()
    if not reviewer:
        raise ReviewValidationError("reviewer is required")

    decision_value = (row.get("decision") or "").strip()
    try:
        decision = Decision(decision_value)
    except ValueError as exc:
        allowed = ", ".join(decision.value for decision in Decision)
        raise ReviewValidationError(f"Invalid decision '{decision_value}'. Allowed: {allowed}") from exc

    return Review(
        card_id=card_id,
        reviewer=reviewer,
        decision=decision,
        memo=(row.get("review_memo") or "").strip(),
    )


def apply_review_to_card(card: CandidateCard, review: Review) -> CandidateCard:
    if card.card_id != review.card_id:
        raise ReviewValidationError(f"Review card_id {review.card_id} does not match card {card.card_id}")
    return replace(card, status=_DECISION_TO_STATUS[review.decision])
