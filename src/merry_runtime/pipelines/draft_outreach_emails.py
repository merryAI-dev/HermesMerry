from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from merry_runtime.adapters.interfaces import ReviewQueue, StructuredStore
from merry_runtime.clock import now_kst
from merry_runtime.normalization import normalize_company_name


OUTREACH_DRAFTS_TAB = "Outreach Drafts"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BAD_EMAIL_DOMAINS = {"thevc.kr", "www.thevc.kr"}


class DraftClient(Protocol):
    def create_draft(self, *, to: str, subject: str, body_text: str) -> str: ...


@dataclass(frozen=True, slots=True)
class OutreachDraftResult:
    run_id: str
    candidate_count: int
    drafted_count: int
    skipped_count: int
    error_count: int


def draft_outreach_emails(
    *,
    review_queue: ReviewQueue,
    structured_store: StructuredStore,
    draft_client: DraftClient,
    max_items: int,
    company_names: list[str] | None = None,
    run_id: str | None = None,
) -> OutreachDraftResult:
    started_at = _now()
    run_id = run_id or f"run_outreach_{_short_digest(started_at)}"
    rows = review_queue.read_pending_reviews(sheet_tab="Candidate Detail")
    candidates = _candidate_rows(rows=rows, company_names=company_names or [])
    existing_keys = _existing_draft_keys(structured_store=structured_store)

    draft_rows: list[dict[str, object]] = []
    sheet_rows: list[dict[str, object]] = []
    skipped_count = 0
    error_count = 0
    drafted_count = 0
    attempted_count = 0
    for candidate in candidates:
        company = _candidate_company(candidate)
        email = _candidate_email(candidate)
        if not company or not _is_valid_email(email):
            skipped_count += 1
            continue
        duplicate_key = _draft_key(company=company, contact_email=email)
        if duplicate_key in existing_keys:
            skipped_count += 1
            continue
        if attempted_count >= max(max_items, 0):
            skipped_count += 1
            continue

        attempted_count += 1
        subject = _subject(company)
        body_text = _body_text(candidate)
        drafted_at = _now()
        try:
            gmail_draft_id = draft_client.create_draft(to=email, subject=subject, body_text=body_text)
            status = "draft_created"
            error_message = ""
            drafted_count += 1
            existing_keys.add(duplicate_key)
        except Exception as exc:
            gmail_draft_id = ""
            status = "error"
            error_message = f"{type(exc).__name__}: {exc}"[:1000]
            error_count += 1
        draft_row = {
            "outreach_id": _outreach_id(company=company, contact_email=email),
            "company": company,
            "contact_email": email,
            "subject": subject,
            "body_text": body_text,
            "gmail_draft_id": gmail_draft_id,
            "status": status,
            "source_url": _source_url(candidate),
            "drafted_at": drafted_at,
            "error_message": error_message,
        }
        draft_rows.append(draft_row)
        sheet_rows.append(_sheet_row(candidate=candidate, draft_row=draft_row))

    if draft_rows:
        structured_store.upsert_rows(
            table="outreach_email_drafts",
            rows=draft_rows,
            key_fields=("outreach_id",),
        )
        review_queue.upsert_cards(
            sheet_tab=OUTREACH_DRAFTS_TAB,
            rows=sheet_rows,
            key_fields=("company", "contact_email"),
        )

    result = OutreachDraftResult(
        run_id=run_id,
        candidate_count=len(candidates),
        drafted_count=drafted_count,
        skipped_count=skipped_count,
        error_count=error_count,
    )
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": run_id,
                "job_name": "draft-outreach-emails",
                "status": "success" if error_count == 0 else "partial_success",
                "started_at": started_at,
                "finished_at": _now(),
                "input_count": len(candidates),
                "output_count": drafted_count,
                "error_message": "",
            }
        ],
        key_fields=("run_id",),
    )
    return result


def _candidate_rows(*, rows: list[dict[str, str]], company_names: list[str]) -> list[dict[str, str]]:
    allowed = {normalize_company_name(name) for name in company_names if name.strip()}
    candidates: list[dict[str, str]] = []
    for row in rows:
        candidate = {str(key): str(value) for key, value in row.items()}
        if allowed and normalize_company_name(_candidate_company(candidate)) not in allowed:
            continue
        candidates.append(candidate)
    return candidates


def _existing_draft_keys(*, structured_store: StructuredStore) -> set[tuple[str, str]]:
    rows = structured_store.query_rows(sql="select * from outreach_email_drafts", parameters={})
    return {
        _draft_key(company=str(row.get("company") or ""), contact_email=str(row.get("contact_email") or ""))
        for row in rows
        if str(row.get("status") or "") == "draft_created"
    }


def _candidate_company(candidate: dict[str, str]) -> str:
    return str(candidate.get("company") or candidate.get("normalized_name") or "").strip()


def _candidate_email(candidate: dict[str, str]) -> str:
    return str(candidate.get("contact_email") or candidate.get("email") or "").strip()


def _is_valid_email(value: str) -> bool:
    if not _EMAIL.fullmatch(value):
        return False
    domain = value.rsplit("@", 1)[-1].casefold()
    return domain not in _BAD_EMAIL_DOMAINS


def _subject(company: str) -> str:
    return f"{company} 관련하여 인사드립니다"


def _body_text(candidate: dict[str, str]) -> str:
    company = _candidate_company(candidate)
    lines = [
        f"안녕하세요, {company} 담당자님.",
        "",
        "MYSC Merry 리서치팀입니다.",
        f"공개 자료를 통해 {company} 관련 내용을 확인했고, 향후 액셀러레이팅/투자 연계 검토를 위해 간단히 인사드립니다.",
    ]
    business_model = str(candidate.get("business_model") or "").strip()
    investment_round = str(candidate.get("investment_round") or "").strip()
    investor = str(candidate.get("investor") or "").strip()
    detail_lines = []
    if business_model:
        detail_lines.append(f"- 비즈니스모델: {business_model}")
    if investment_round:
        detail_lines.append(f"- 투자 단계: {investment_round}")
    if investor:
        detail_lines.append(f"- 투자자: {investor}")
    if detail_lines:
        lines.extend(["", "확인한 공개 정보는 아래와 같습니다.", *detail_lines])
    lines.extend(
        [
            "",
            "가능하시면 회사소개서나 최근 업데이트를 회신으로 공유해 주실 수 있을까요?",
            "",
            "감사합니다.",
            "MYSC Merry 드림",
        ]
    )
    return "\n".join(lines)


def _source_url(candidate: dict[str, str]) -> str:
    return str(candidate.get("source_url") or candidate.get("url") or candidate.get("homepage") or "").strip()


def _sheet_row(*, candidate: dict[str, str], draft_row: dict[str, object]) -> dict[str, object]:
    return {
        "drafted_at": draft_row["drafted_at"],
        "company": draft_row["company"],
        "contact_email": draft_row["contact_email"],
        "subject": draft_row["subject"],
        "gmail_draft_id": draft_row["gmail_draft_id"],
        "status": draft_row["status"],
        "source_url": draft_row["source_url"],
        "business_model": str(candidate.get("business_model") or ""),
        "investment_round": str(candidate.get("investment_round") or ""),
        "error_message": draft_row["error_message"],
    }


def _draft_key(*, company: str, contact_email: str) -> tuple[str, str]:
    return (normalize_company_name(company), contact_email.strip().casefold())


def _outreach_id(*, company: str, contact_email: str) -> str:
    normalized_company, normalized_email = _draft_key(company=company, contact_email=contact_email)
    digest = hashlib.sha1(f"{normalized_company}|{normalized_email}".encode("utf-8")).hexdigest()[:16]
    return f"outreach_{digest}"


def _short_digest(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return now_kst()
