import pytest

from merry_runtime.models import CandidateCard, Decision
from merry_runtime.review_sync import ReviewValidationError, apply_review_to_card, parse_review_row


def test_parses_valid_sheet_review_row() -> None:
    row = {
        "card_id": "card_001",
        "reviewer": "boram",
        "decision": "watchlist",
        "review_memo": "Good impact signal; wait for sales proof.",
    }

    review = parse_review_row(row, valid_card_ids={"card_001"})

    assert review.card_id == "card_001"
    assert review.decision is Decision.WATCHLIST
    assert review.memo == "Good impact signal; wait for sales proof."


def test_rejects_unknown_sheet_decision() -> None:
    row = {
        "card_id": "card_001",
        "reviewer": "boram",
        "decision": "maybe",
        "review_memo": "",
    }

    with pytest.raises(ReviewValidationError):
        parse_review_row(row, valid_card_ids={"card_001"})


def test_applies_review_decision_to_candidate_card_status() -> None:
    card = CandidateCard(
        card_id="card_001",
        ac_id="ac_climate",
        entity_id="ent_climate",
        summary="Strong climate impact candidate.",
        recommended_action="advance",
        status="new",
    )
    review = parse_review_row(
        {
            "card_id": "card_001",
            "reviewer": "boram",
            "decision": "request_more_info",
            "review_memo": "Need revenue evidence.",
        },
        valid_card_ids={"card_001"},
    )

    updated = apply_review_to_card(card, review)

    assert updated.status == "needs_info"
