from merry_runtime.adapters.fakes import FakeReviewQueue, FakeStructuredStore
from merry_runtime.pipelines.draft_outreach_emails import draft_outreach_emails


class FakeEmailDraftClient:
    def __init__(self) -> None:
        self.drafts: list[dict[str, str]] = []

    def create_draft(self, *, to: str, subject: str, body_text: str) -> str:
        draft_id = f"draft_{len(self.drafts) + 1:06d}"
        self.drafts.append({"draft_id": draft_id, "to": to, "subject": subject, "body_text": body_text})
        return draft_id


def test_draft_outreach_emails_creates_gmail_drafts_from_candidate_detail_contact_emails() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {
                "company": "에이아이오",
                "normalized_name": "에이아이오",
                "homepage": "https://the-aio.com/",
                "contact_email": "hello@the-aio.com",
                "business_model": "낸드컨트롤러 - 낸드플래시 시스템 반도체",
                "investment_round": "Pre-IPO",
                "investor": "비엔더블유인베스트먼트",
                "status": "crawled",
            },
            {
                "company": "노메일",
                "contact_email": "",
            },
        ],
    )
    store = FakeStructuredStore()
    client = FakeEmailDraftClient()

    result = draft_outreach_emails(
        review_queue=queue,
        structured_store=store,
        draft_client=client,
        max_items=10,
        run_id="run_outreach_test",
    )

    assert result.candidate_count == 2
    assert result.drafted_count == 1
    assert result.skipped_count == 1
    assert client.drafts[0]["to"] == "hello@the-aio.com"
    assert client.drafts[0]["subject"] == "에이아이오 관련하여 인사드립니다"
    assert "MYSC Merry 리서치팀입니다" in client.drafts[0]["body_text"]
    assert "낸드컨트롤러 - 낸드플래시 시스템 반도체" in client.drafts[0]["body_text"]
    assert "비엔더블유인베스트먼트" in client.drafts[0]["body_text"]

    [draft_row] = store.tables["outreach_email_drafts"]
    assert draft_row["company"] == "에이아이오"
    assert draft_row["contact_email"] == "hello@the-aio.com"
    assert draft_row["gmail_draft_id"] == "draft_000001"
    assert draft_row["status"] == "draft_created"
    assert draft_row["drafted_at"].endswith("+09:00")

    [sheet_row] = queue.published["Outreach Drafts"]
    assert sheet_row["company"] == "에이아이오"
    assert sheet_row["contact_email"] == "hello@the-aio.com"
    assert sheet_row["gmail_draft_id"] == "draft_000001"
    assert sheet_row["status"] == "draft_created"
    assert sheet_row["drafted_at"].endswith("+09:00")

    [agent_run] = store.tables["agent_runs"]
    assert agent_run["job_name"] == "draft-outreach-emails"
    assert agent_run["output_count"] == 1


def test_draft_outreach_emails_does_not_create_duplicate_drafts_for_existing_contacts() -> None:
    queue = FakeReviewQueue()
    queue.seed_reviews(
        "Candidate Detail",
        [
            {
                "company": "에이아이오",
                "homepage": "https://the-aio.com/",
                "contact_email": "hello@the-aio.com",
            }
        ],
    )
    store = FakeStructuredStore()
    client = FakeEmailDraftClient()

    first = draft_outreach_emails(
        review_queue=queue,
        structured_store=store,
        draft_client=client,
        max_items=10,
        run_id="run_outreach_first",
    )
    second = draft_outreach_emails(
        review_queue=queue,
        structured_store=store,
        draft_client=client,
        max_items=10,
        run_id="run_outreach_second",
    )

    assert first.drafted_count == 1
    assert second.drafted_count == 0
    assert second.skipped_count == 1
    assert len(client.drafts) == 1
    assert len(store.tables["outreach_email_drafts"]) == 1
