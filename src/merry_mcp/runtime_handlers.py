from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.pipelines.crawl_sources import CrawlResult, crawl_sources
from merry_runtime.pipelines.draft_outreach_emails import OutreachDraftResult, draft_outreach_emails
from merry_runtime.pipelines.enrich_sminfo import SminfoEnrichmentResult, enrich_sminfo_candidates
from merry_runtime.runtime_config import RuntimeConfig


def build_runtime_handlers(
    *,
    runtime: RuntimeAdapters,
    config: RuntimeConfig,
    crawl_sources_fn: Callable[..., CrawlResult] = crawl_sources,
    enrich_sminfo_candidates_fn: Callable[..., SminfoEnrichmentResult] = enrich_sminfo_candidates,
    draft_outreach_emails_fn: Callable[..., OutreachDraftResult] = draft_outreach_emails,
) -> dict[str, Callable[[dict[str, Any]], dict[str, object]]]:
    return {
        "crawl_public_sources": lambda payload: _crawl_public_sources(
            payload,
            runtime=runtime,
            config=config,
            crawl_sources_fn=crawl_sources_fn,
        ),
        "enrich_sminfo_candidates": lambda payload: _enrich_sminfo_candidates(
            payload,
            runtime=runtime,
            config=config,
            enrich_sminfo_candidates_fn=enrich_sminfo_candidates_fn,
        ),
        "draft_outreach_emails": lambda payload: _draft_outreach_emails(
            payload,
            runtime=runtime,
            config=config,
            draft_outreach_emails_fn=draft_outreach_emails_fn,
        ),
    }


def _crawl_public_sources(
    payload: dict[str, Any],
    *,
    runtime: RuntimeAdapters,
    config: RuntimeConfig,
    crawl_sources_fn: Callable[..., CrawlResult],
) -> dict[str, object]:
    result = crawl_sources_fn(
        targets=list(payload["targets"]),
        object_store=runtime.object_store,
        structured_store=runtime.structured_store,
        review_queue=runtime.review_queue if config.review_sheet_id else None,
        wiki_store=runtime.wiki_store,
    )
    return {"job_name": "crawl-sources", **asdict(result), "crawl_sheet_tab": config.crawl_sheet_tab}


def _enrich_sminfo_candidates(
    payload: dict[str, Any],
    *,
    runtime: RuntimeAdapters,
    config: RuntimeConfig,
    enrich_sminfo_candidates_fn: Callable[..., SminfoEnrichmentResult],
) -> dict[str, object]:
    if runtime.sminfo_client is None:
        raise RuntimeError("SMINFO client is not configured")
    result = enrich_sminfo_candidates_fn(
        review_queue=runtime.review_queue,
        structured_store=runtime.structured_store,
        client=runtime.sminfo_client,
        max_items=int(payload.get("max_items") or config.sminfo_batch_limit),
        min_interval_seconds=config.sminfo_min_interval_seconds,
        stale_days=config.sminfo_stale_days,
        company_names=[str(name) for name in payload.get("company_names", [])],
    )
    return {"job_name": "enrich-sminfo", **asdict(result)}


def _draft_outreach_emails(
    payload: dict[str, Any],
    *,
    runtime: RuntimeAdapters,
    config: RuntimeConfig,
    draft_outreach_emails_fn: Callable[..., OutreachDraftResult],
) -> dict[str, object]:
    if runtime.email_draft_client is None:
        raise RuntimeError("Email draft client is not configured")
    result = draft_outreach_emails_fn(
        review_queue=runtime.review_queue,
        structured_store=runtime.structured_store,
        draft_client=runtime.email_draft_client,
        max_items=int(payload.get("max_items") or config.outreach_draft_batch_limit),
        company_names=[str(name) for name in payload.get("company_names", [])],
    )
    return {"job_name": "draft-outreach-emails", **asdict(result)}
