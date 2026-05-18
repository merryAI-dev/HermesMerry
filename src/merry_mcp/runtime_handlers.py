from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from merry_runtime.job_runner import RuntimeAdapters
from merry_runtime.pipelines.crawl_sources import CrawlResult, crawl_sources
from merry_runtime.runtime_config import RuntimeConfig


def build_runtime_handlers(
    *,
    runtime: RuntimeAdapters,
    config: RuntimeConfig,
    crawl_sources_fn: Callable[..., CrawlResult] = crawl_sources,
) -> dict[str, Callable[[dict[str, Any]], dict[str, object]]]:
    return {
        "crawl_public_sources": lambda payload: _crawl_public_sources(
            payload,
            runtime=runtime,
            config=config,
            crawl_sources_fn=crawl_sources_fn,
        )
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
        wiki_store=runtime.wiki_store,
    )
    return {"job_name": "crawl-sources", **asdict(result), "crawl_sheet_tab": config.crawl_sheet_tab}
