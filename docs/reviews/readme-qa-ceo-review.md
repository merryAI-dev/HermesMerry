# README QA and CEO Review

Date: 2026-05-26

Scope: `README.md` and `docs/ONBOARDING.md`

## QA Result

Pass with operating caveats.

The README now separates implemented runtime capabilities from conditional integrations. It avoids claiming that the system has completed real overnight runs or that production reliability is already proven.

Claims checked against the codebase:

- `agent_work_queue` chain exists in `src/merry_runtime/pipelines/agent_work_queue.py` and `configs/agent_work_queue.discovery.json`.
- SMINFO queue behavior is covered by `src/merry_runtime/pipelines/enrich_sminfo.py`, `src/merry_runtime/ingestion/sminfo_queue.py`, and integration tests.
- THE VC Playwright crawling is implemented in `src/merry_runtime/adapters/thevc_playwright.py`.
- Local AIOps dashboard rendering is implemented in `src/merry_runtime/loop_dashboard.py`.
- Gmail behavior is described as draft-only, matching the runtime wording and safety boundary.

Remaining risks:

- Real Google Sheets/SMINFO/THE VC behavior still requires credentialed staging verification.
- Public source pages can change without code changes.
- `uv.lock` and `tmp/` are intentionally left out of this documentation commit unless the operator decides to version them later.

## CEO-Readability Result

Pass after simplification.

The opening now explains the business purpose before internal module names. Technical details are moved into commands, module map, and onboarding sections. Non-developer readers should be able to understand:

- why the system exists,
- what it can currently do,
- what still depends on credentials or staging runs,
- where an operator should check whether a run actually completed.

Recommended executive framing:

HermesMerry is best described as an evidence-tracking discovery workflow, not as a fully autonomous decision maker. The system can reduce manual collection and monitoring work, but final candidate judgment should remain with the operating team until several real runs are verified.
