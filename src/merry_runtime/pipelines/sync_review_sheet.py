from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst
from merry_runtime.models import CandidateCard
from merry_runtime.review_sync import ReviewValidationError, apply_review_to_card, parse_review_row


@dataclass(frozen=True, slots=True)
class ReviewSyncResult:
    run_id: str
    review_count: int
    rejected_row_count: int


def sync_review_sheet(
    *,
    structured_store: StructuredStore,
    review_queue: ReviewQueue,
    ac_id: str,
    run_id: str | None = None,
) -> ReviewSyncResult:
    started_at = _now()
    run_id = run_id or f"run_review_{ac_id}_{_short_digest(started_at)}"
    card_rows = structured_store.query_rows(sql="select * from candidate_cards where ac_id=@ac_id", parameters={"ac_id": ac_id})
    cards = {str(row["card_id"]): _card_from_row(row) for row in card_rows}
    review_rows = review_queue.read_pending_reviews(sheet_tab=ac_id)

    valid_review_rows: list[dict[str, object]] = []
    updated_card_rows: list[dict[str, object]] = []
    errors: list[str] = []
    for row in review_rows:
        try:
            review = parse_review_row(row, valid_card_ids=set(cards.keys()))
        except ReviewValidationError as exc:
            errors.append(str(exc))
            continue

        review_id = f"rev_{_short_digest(review.card_id, review.reviewer, review.decision.value, review.memo)}"
        review_row = asdict(review)
        review_row["decision"] = review.decision.value
        review_row["review_id"] = review_id
        review_row["reviewed_at"] = started_at
        valid_review_rows.append(review_row)

        updated_card = apply_review_to_card(cards[review.card_id], review)
        updated_card_row = asdict(updated_card)
        updated_card_rows.append(updated_card_row)

    if valid_review_rows:
        structured_store.upsert_rows(table="reviews", rows=valid_review_rows, key_fields=("review_id",))
    if updated_card_rows:
        structured_store.upsert_rows(table="candidate_cards", rows=updated_card_rows, key_fields=("card_id",))

    status = "success" if not errors else "partial_success"
    result = ReviewSyncResult(run_id=run_id, review_count=len(valid_review_rows), rejected_row_count=len(errors))
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "sync-review-sheet",
                "status": status,
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(review_rows),
                "output_count": len(valid_review_rows),
                "error_message": " | ".join(errors),
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _card_from_row(row: dict[str, Any]) -> CandidateCard:
    return CandidateCard(
        card_id=str(row["card_id"]),
        ac_id=str(row["ac_id"]),
        entity_id=str(row["entity_id"]),
        summary=str(row["summary"]),
        recommended_action=str(row["recommended_action"]),
        status=str(row.get("status", "new")),
        created_at=row.get("created_at"),
    )


def _short_digest(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return now_kst()
