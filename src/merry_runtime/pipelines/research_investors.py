from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from merry_runtime.adapters.interfaces import LLMClient, ReviewQueue, StructuredStore, WebSearchClient
from merry_runtime.clock import now_kst


INVESTOR_DB_TAB = "Investor DB"
INVESTOR_RESEARCH_HEADERS: tuple[str, ...] = (
    "투자사",
    "KVIC 공개 활성 펀드 수",
    "KVIC 공개 전체 펀드 수",
    "KVIC 공개 활성 운용액(억원)",
    "KVIC 공개 활성 약정액(억원)",
    "외부 공개 AUM(억원)",
    "외부 공개 운용 조합 수",
    "외부 공개 누적 투자액(억원)",
    "AUM 설명",
    "AUM 근거 제목",
    "AUM 근거 URL",
    "AUM 신뢰도",
    "AUM 상태",
    "출자 분야",
    "대표 펀드",
    "프로필 태그",
    "다음 만기일",
    "최종 만기일",
    "수집시각",
)


@dataclass(frozen=True, slots=True)
class InvestorResearchResult:
    run_id: str
    status: str
    investor_count: int
    researched_count: int
    success_count: int
    skipped_reason: str = ""


def research_investors(
    *,
    structured_store: StructuredStore,
    search_client: WebSearchClient,
    llm_client: LLMClient,
    review_queue: ReviewQueue | None = None,
    collected_at: str | None = None,
    batch_limit: int = 20,
    stale_days: int = 7,
    search_max_results: int = 5,
    run_id: str | None = None,
) -> InvestorResearchResult:
    collected_at = collected_at or now_kst()
    run_id = run_id or f"run_investor_research_{_short_digest(collected_at)}"
    investors = _query_all(structured_store, "kvic_investor_managers")
    existing = {str(row.get("manager_id") or ""): row for row in _query_all(structured_store, "investor_external_profiles")}
    selected = [
        row
        for row in sorted(investors, key=_investor_sort_key)
        if _needs_refresh(existing.get(str(row.get("manager_id") or "")), collected_at=collected_at, stale_days=stale_days)
    ][: max(0, batch_limit)]
    rows = [
        _research_one_investor(
            investor=investor,
            search_client=search_client,
            llm_client=llm_client,
            collected_at=collected_at,
            search_max_results=search_max_results,
        )
        for investor in selected
    ]
    structured_store.upsert_rows(table="investor_external_profiles", rows=rows, key_fields=("manager_id",))
    if review_queue is not None:
        publish_investor_db(structured_store=structured_store, review_queue=review_queue)
    success_count = sum(1 for row in rows if row.get("status") == "success")
    result = InvestorResearchResult(
        run_id=run_id,
        status="success",
        investor_count=len(investors),
        researched_count=len(rows),
        success_count=success_count,
    )
    _record_agent_run(structured_store=structured_store, result=result, started_at=collected_at, finished_at=now_kst())
    return result


def publish_investor_db(*, structured_store: StructuredStore, review_queue: ReviewQueue) -> None:
    investors = _query_all(structured_store, "kvic_investor_managers")
    external_profiles = _query_all(structured_store, "investor_external_profiles")
    review_queue.replace_rows(
        sheet_tab=INVESTOR_DB_TAB,
        headers=INVESTOR_RESEARCH_HEADERS,
        rows=investor_sheet_rows(investors=investors, external_profiles=external_profiles),
    )


def investor_sheet_rows(
    *,
    investors: list[dict[str, object]],
    external_profiles: list[dict[str, object]],
) -> list[dict[str, object]]:
    external_by_manager_id = {str(row.get("manager_id") or ""): row for row in external_profiles}
    rows: list[dict[str, object]] = []
    for investor in sorted(investors, key=_investor_sort_key):
        external = external_by_manager_id.get(str(investor.get("manager_id") or ""), {})
        rows.append(
            {
                "투자사": investor.get("manager_name", ""),
                "KVIC 공개 활성 펀드 수": investor.get("active_fund_count", ""),
                "KVIC 공개 전체 펀드 수": investor.get("total_fund_count", ""),
                "KVIC 공개 활성 운용액(억원)": investor.get("active_amount_eok", ""),
                "KVIC 공개 활성 약정액(억원)": investor.get("active_commitment_eok", ""),
                "외부 공개 AUM(억원)": external.get("external_aum_eok", ""),
                "외부 공개 운용 조합 수": external.get("external_fund_count", ""),
                "외부 공개 누적 투자액(억원)": external.get("external_cumulative_investment_eok", ""),
                "AUM 설명": external.get("description", ""),
                "AUM 근거 제목": external.get("evidence_title", ""),
                "AUM 근거 URL": external.get("evidence_url", ""),
                "AUM 신뢰도": external.get("confidence", ""),
                "AUM 상태": external.get("status", ""),
                "출자 분야": _join(investor.get("fund_fields")),
                "대표 펀드": _join(investor.get("representative_funds")),
                "프로필 태그": _join(investor.get("profile_tags")),
                "다음 만기일": investor.get("next_expiry_at", ""),
                "최종 만기일": investor.get("latest_expiry_at", ""),
                "수집시각": investor.get("collected_at", ""),
            }
        )
    return rows


def _research_one_investor(
    *,
    investor: dict[str, object],
    search_client: WebSearchClient,
    llm_client: LLMClient,
    collected_at: str,
    search_max_results: int,
) -> dict[str, object]:
    query, evidence = _search_investor_evidence(
        investor=investor,
        search_client=search_client,
        search_max_results=search_max_results,
    )
    manager_id = str(investor.get("manager_id") or "")
    manager_name = str(investor.get("manager_name") or "")
    base = {
        "manager_id": manager_id,
        "manager_name": manager_name,
        "external_aum_eok": 0.0,
        "external_fund_count": 0,
        "external_cumulative_investment_eok": 0.0,
        "description": "",
        "evidence_title": "",
        "evidence_url": "",
        "evidence_snippet": "",
        "search_query": query,
        "status": "no_result",
        "confidence": 0.0,
        "raw_json": "{}",
        "error_message": "",
        "collected_at": collected_at,
        "updated_at": collected_at,
    }
    if not evidence:
        return base
    try:
        extracted = llm_client.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_user_prompt(investor=investor, evidence=evidence),
            max_tokens=800,
        )
    except Exception as exc:
        return {**base, "status": "error", "error_message": f"{type(exc).__name__}: {exc}"[:1000]}
    return _profile_row_from_extraction(base=base, extracted=extracted, evidence=evidence)


def _profile_row_from_extraction(
    *,
    base: dict[str, object],
    extracted: dict[str, object],
    evidence: list[dict[str, str]],
) -> dict[str, object]:
    evidence_url = str(extracted.get("evidence_url") or "")
    matched = next((item for item in evidence if item.get("url") == evidence_url), evidence[0])
    status = str(extracted.get("status") or "success")
    if status not in {"success", "no_result", "error"}:
        status = "success"
    return {
        **base,
        "external_aum_eok": _as_float(extracted.get("external_aum_eok")),
        "external_fund_count": _as_int(extracted.get("external_fund_count")),
        "external_cumulative_investment_eok": _as_float(extracted.get("external_cumulative_investment_eok")),
        "description": str(extracted.get("description") or ""),
        "evidence_title": str(extracted.get("evidence_title") or matched.get("title") or ""),
        "evidence_url": evidence_url or str(matched.get("url") or ""),
        "evidence_snippet": str(matched.get("snippet") or ""),
        "status": status,
        "confidence": _as_float(extracted.get("confidence")),
        "raw_json": json.dumps(extracted, ensure_ascii=False, sort_keys=True),
    }


_SYSTEM_PROMPT = """You are Hermes' evidence encoder for investor research.
Extract only facts explicitly supported by the provided search evidence.
Return one JSON object with keys:
status, external_aum_eok, external_fund_count, external_cumulative_investment_eok,
description, evidence_title, evidence_url, confidence.
Use Korean won eok units for numeric fields. If evidence is weak, set status to no_result."""


def _user_prompt(*, investor: dict[str, object], evidence: list[dict[str, str]]) -> str:
    return json.dumps(
        {
            "investor": investor,
            "evidence": evidence,
            "output_policy": "Return only source-grounded JSON. Do not estimate missing values.",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _search_investor_evidence(
    *,
    investor: dict[str, object],
    search_client: WebSearchClient,
    search_max_results: int,
) -> tuple[str, list[dict[str, str]]]:
    queries = _investor_search_queries(investor)
    last_query = queries[-1] if queries else ""
    for query in queries:
        evidence = search_client.search(query, max_results=search_max_results)
        if evidence:
            return query, evidence
        last_query = query
    return last_query, []


def _investor_search_queries(investor: dict[str, object]) -> list[str]:
    manager_name = str(investor.get("manager_name") or "").strip()
    alias = _investor_alias(manager_name)
    queries = [
        f"{alias} AUM 운용자산",
        f"{alias} 투자조합 펀드",
        f"{manager_name} 운용자산 AUM",
        f"{manager_name} 투자조합 펀드",
    ]
    return _unique(queries)


def _investor_alias(manager_name: str) -> str:
    aliases = {"엠와이소셜컴퍼니": "MYSC"}
    return aliases.get(manager_name, manager_name)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _needs_refresh(profile: dict[str, object] | None, *, collected_at: str, stale_days: int) -> bool:
    if profile is None:
        return True
    updated_at = _parse_datetime(str(profile.get("updated_at") or ""))
    current = _parse_datetime(collected_at)
    if updated_at is None or current is None:
        return True
    return (current - updated_at).days >= max(1, stale_days)


def _query_all(structured_store: StructuredStore, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in structured_store.query_rows(sql=f"select * from {table}", parameters={})]


def _record_agent_run(
    *,
    structured_store: StructuredStore,
    result: InvestorResearchResult,
    started_at: str,
    finished_at: str,
) -> None:
    structured_store.upsert_rows(
        table="agent_runs",
        rows=[
            {
                "run_id": result.run_id,
                "job_name": "research-investors",
                "status": result.status,
                "started_at": started_at,
                "finished_at": finished_at,
                "input_count": result.investor_count,
                "output_count": result.researched_count,
                "error_message": result.skipped_reason,
            }
        ],
        key_fields=("run_id",),
    )


def _investor_sort_key(row: dict[str, object]) -> tuple[float, str]:
    return (-float(row.get("active_amount_eok") or 0.0), str(row.get("manager_name") or ""))


def _as_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _join(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if str(item))
    return str(value or "")


def _short_digest(*parts: str) -> str:
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:12]
