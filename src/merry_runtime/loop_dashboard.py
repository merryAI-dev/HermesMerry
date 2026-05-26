from __future__ import annotations

import html
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentRunEvent:
    run_id: str
    job_name: str
    status: str
    started_at: str
    finished_at: str
    input_count: int
    output_count: int
    error_message: str


def render_loop_dashboard(*, db_path: Path, output_path: Path, limit: int = 100) -> Path:
    events = _load_agent_run_events(db_path=db_path, limit=limit)
    queue_counts = _load_status_counts(db_path=db_path, table="sminfo_enrichment_queue")
    work_queue_counts = _load_status_counts(db_path=db_path, table="agent_work_queue")
    table_counts = _load_table_counts(db_path=db_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _render_html(
            events=events,
            queue_counts=queue_counts,
            work_queue_counts=work_queue_counts,
            table_counts=table_counts,
            db_path=db_path,
        ),
        encoding="utf-8",
    )
    return output_path


def _load_agent_run_events(*, db_path: Path, limit: int) -> list[AgentRunEvent]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if not _table_exists(connection, "agent_runs"):
            return []
        rows = connection.execute(
            """
            select run_id, job_name, status, started_at, finished_at, input_count, output_count, error_message
            from agent_runs
            order by started_at desc, finished_at desc, run_id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return [
        AgentRunEvent(
            run_id=str(row["run_id"] or ""),
            job_name=str(row["job_name"] or ""),
            status=str(row["status"] or ""),
            started_at=str(row["started_at"] or ""),
            finished_at=str(row["finished_at"] or ""),
            input_count=_int(row["input_count"]),
            output_count=_int(row["output_count"]),
            error_message=str(row["error_message"] or ""),
        )
        for row in rows
    ]


def _load_status_counts(*, db_path: Path, table: str) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        if not _table_exists(connection, table):
            return {}
        rows = connection.execute(f"select status, count(*) from {table} group by status order by status").fetchall()
    return {str(status or "unknown"): int(count or 0) for status, count in rows}


def _load_table_counts(*, db_path: Path) -> dict[str, int]:
    watched_tables = (
        "raw_sources",
        "mother_entities",
        "signals",
        "candidate_cards",
        "ac_scores",
        "sminfo_company_profiles",
        "agent_work_queue",
        "agent_runs",
    )
    counts: dict[str, int] = {}
    with sqlite3.connect(db_path) as connection:
        for table in watched_tables:
            if _table_exists(connection, table):
                counts[table] = int(connection.execute(f"select count(*) from {table}").fetchone()[0])
    return counts


def _render_html(
    *,
    events: list[AgentRunEvent],
    queue_counts: dict[str, int],
    work_queue_counts: dict[str, int],
    table_counts: dict[str, int],
    db_path: Path,
) -> str:
    status_counts = Counter(event.status or "unknown" for event in events)
    job_names = sorted({event.job_name for event in events if event.job_name})
    latest = events[0].started_at if events else "실행 기록 없음"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes 루프 콘솔</title>
  <link rel="icon" href="data:,">
  <style>
    :root {{
      --bg: #111111;
      --canvas: #201f1b;
      --canvas-2: #2d2b23;
      --ink: #f4efe2;
      --muted: #aaa395;
      --line: rgba(244, 239, 226, .22);
      --panel: #171717;
      --good: #69c56b;
      --bad: #ff4f87;
      --warn: #f4a22f;
      --accent: #8a5cf6;
      --blue: #4f79ff;
      --pink: #e9347c;
      --green: #53a33b;
      --orange: #f18a00;
      --purple: #8a5cf6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 24px 28px 48px; }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr);
      gap: 32px;
      align-items: end;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: clamp(30px, 4vw, 48px); line-height: 1; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }}
    .subtle {{ color: var(--muted); font-size: 14px; line-height: 1.55; }}

    /* AIOps 상태 색상: 정상/주의/장애를 상단 요약, 노드 링, 이벤트 로그에 같은 의미로 연결한다. */
    .aiops-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 20px 0 0; }}
    .aiops-item {{
      min-height: 92px;
      padding: 14px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      background: rgba(23, 23, 23, .9);
    }}
    .aiops-item.ok {{ border-left-color: var(--good); }}
    .aiops-item.warn {{ border-left-color: var(--warn); }}
    .aiops-item.fail {{ border-left-color: var(--bad); }}
    .aiops-label {{ color: var(--muted); font-size: 12px; font-weight: 800; }}
    .aiops-value {{ margin-top: 9px; font-size: 17px; font-weight: 850; line-height: 1.25; overflow-wrap: anywhere; }}
    .aiops-detail {{ margin-top: 7px; color: var(--muted); font-size: 12px; line-height: 1.4; overflow-wrap: anywhere; }}

    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 20px 0; }}
    .metric {{ border-top: 1px solid var(--line); padding-top: 10px; min-height: 58px; }}
    .metric strong {{ display: block; font-size: 26px; line-height: 1; }}
    .metric span {{ display: block; margin-top: 8px; color: var(--muted); font-size: 13px; }}
    .workspace {{ display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 28px; align-items: start; }}
    section {{ margin-top: 28px; }}

    /* 토폴로지 캔버스: Kafka/Dify처럼 수집->정리->판단->시트/저장소 흐름을 좌우 서비스 노드로 보여준다. */
    .topology {{
      position: relative;
      min-height: 620px;
      overflow: auto;
      background:
        linear-gradient(90deg, transparent 0 16.6%, rgba(244, 162, 47, .55) 16.7%, transparent 16.9%),
        linear-gradient(90deg, transparent 0 50%, rgba(244, 239, 226, .5) 50.1%, transparent 50.3%),
        linear-gradient(90deg, transparent 0 70%, rgba(170, 48, 210, .65) 70.1%, transparent 70.3%),
        linear-gradient(90deg, transparent 0 87%, rgba(244, 162, 47, .55) 87.1%, transparent 87.3%),
        radial-gradient(circle at 48% 42%, rgba(138, 92, 246, .18), transparent 30%),
        linear-gradient(135deg, var(--canvas), var(--canvas-2));
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.03);
    }}
    .topology-inner {{
      position: relative;
      width: 1120px;
      height: 620px;
    }}
    .plane-label {{
      position: absolute;
      top: 18px;
      color: rgba(244, 239, 226, .62);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .plane-label.source {{ left: 28px; }}
    .plane-label.runtime {{ left: 245px; }}
    .plane-label.decision {{ left: 590px; }}
    .plane-label.storage {{ left: 885px; }}
    .wires {{
      position: absolute;
      inset: 0;
      width: 1120px;
      height: 620px;
      pointer-events: none;
    }}
    .wire {{
      fill: none;
      stroke: rgba(245, 245, 245, .82);
      stroke-width: 2.1;
      filter: drop-shadow(0 0 4px rgba(255,255,255,.18));
    }}
    .wire.dim {{ stroke: rgba(245, 245, 245, .46); }}
    .node {{
      position: absolute;
      width: 152px;
      min-height: 108px;
      padding: 13px 13px 12px;
      border: 2px solid var(--node);
      border-radius: 12px;
      background: rgba(31, 23, 35, .9);
      box-shadow: 0 14px 28px rgba(0,0,0,.34), 0 0 18px color-mix(in srgb, var(--node), transparent 64%);
      transition: transform .16s ease, box-shadow .16s ease;
    }}
    .node:hover {{ transform: translateY(-2px); box-shadow: 0 18px 34px rgba(0,0,0,.42), 0 0 24px color-mix(in srgb, var(--node), transparent 46%); }}
    .node.success {{ border-color: var(--good); --node: var(--good); }}
    .node.failed {{ border-color: var(--bad); --node: var(--bad); }}
    .node.partial_success {{ border-color: var(--warn); --node: var(--warn); }}
    .node.idle {{ opacity: .68; }}
    .node-icon {{
      display: grid;
      place-items: center;
      width: 40px;
      height: 40px;
      margin-bottom: 10px;
      border-radius: 6px;
      background: var(--node);
      color: #fff;
      font-weight: 900;
      font-size: 18px;
    }}
    .node-title {{ font-weight: 800; font-size: 15px; line-height: 1.1; }}
    .node-job {{ margin-top: 5px; color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }}
    .node-meta {{ margin-top: 8px; font-size: 12px; color: var(--ink); }}
    .node-error {{ margin-top: 8px; max-height: 42px; overflow: hidden; color: var(--bad); font-size: 11px; line-height: 1.28; overflow-wrap: anywhere; }}

    /* 이벤트 레인: 잡별 최근 실행 이력을 모아 어떤 루프에서 실패/부분성공이 발생했는지 추적한다. */
    .lane-board {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .lane {{
      display: grid;
      grid-template-columns: 180px minmax(0, 1fr);
      min-height: 64px;
      border-bottom: 1px solid var(--line);
    }}
    .lane:last-child {{ border-bottom: 0; }}
    .lane-label {{ padding: 16px; font-weight: 700; border-right: 1px solid var(--line); }}
    .lane-events {{ display: flex; gap: 10px; align-items: center; padding: 12px 16px; overflow-x: auto; }}
    .event {{
      min-width: 176px;
      border-left: 4px solid var(--accent);
      padding: 8px 10px;
      background: #202020;
      transition: transform .16s ease, background .16s ease;
    }}
    .event:hover {{ transform: translateY(-2px); background: #282828; }}
    .event.success {{ border-left-color: var(--good); }}
    .event.failed {{ border-left-color: var(--bad); }}
    .event.partial_success {{ border-left-color: var(--warn); }}
    .event-time {{ color: var(--muted); font-size: 11px; white-space: nowrap; }}
    .event-title {{ margin-top: 4px; font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }}
    .event-counts {{ margin-top: 6px; color: var(--muted); font-size: 12px; }}
    .event-error {{ margin-top: 6px; color: var(--bad); font-size: 12px; line-height: 1.35; overflow-wrap: anywhere; }}
    .side {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      position: sticky;
      top: 18px;
    }}
    .kv {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--line); }}
    .kv:last-child {{ border-bottom: 0; }}
    .kv span:first-child {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; font-size: 13px; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 700; background: #202020; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ font-weight: 700; }}
    .status.success {{ color: var(--good); }}
    .status.failed {{ color: var(--bad); }}
    .status.partial_success {{ color: var(--warn); }}

    /* 모바일 운영 화면: 토폴로지는 가로 스크롤, 로그와 요약은 세로 스택으로 유지한다. */
    @media (max-width: 900px) {{
      main {{ padding: 24px 18px 36px; }}
      header, .workspace, .metrics, .aiops-strip {{ grid-template-columns: 1fr; }}
      .side {{ position: static; }}
      .lane {{ grid-template-columns: 1fr; }}
      .lane-label {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .topology {{ min-height: 520px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Hermes 루프 콘솔</h1>
      </div>
      <div class="subtle">
        운영 이벤트 DB <strong>{_h(str(db_path))}</strong><br>
        최근 실행: {_h(latest)}
      </div>
    </header>
    {_render_aiops_summary(events=events, status_counts=status_counts, queue_counts=queue_counts)}
    <div class="metrics">
      {_metric("이벤트", len(events))}
      {_metric("성공", status_counts.get("success", 0))}
      {_metric("실패", status_counts.get("failed", 0))}
      {_metric("잡", len(job_names))}
    </div>
    <section>
      <h2>파이프라인 토폴로지</h2>
      {_render_topology(events=events, queue_counts=queue_counts, table_counts=table_counts)}
    </section>
    <div class="workspace">
      <div>
        <section>
          <h2>잡 실행 레인</h2>
          <div class="lane-board">
            {_render_lanes(events, job_names)}
          </div>
        </section>
        <section>
          <h2>이벤트 로그</h2>
          {_render_event_table(events)}
        </section>
      </div>
      <aside class="side">
        <h2>Agent Work 큐</h2>
        {_render_key_values(work_queue_counts or {"none": 0})}
        <section>
        <h2>SMINFO 큐</h2>
        {_render_key_values(queue_counts or {"none": 0})}
        </section>
        <section>
          <h2>저장소 카운트</h2>
          {_render_key_values(table_counts or {"none": 0})}
        </section>
      </aside>
    </div>
  </main>
</body>
</html>
"""


def _render_aiops_summary(
    *,
    events: list[AgentRunEvent],
    status_counts: Counter[str],
    queue_counts: dict[str, int],
) -> str:
    health_label, health_detail, health_class = _aiops_health(status_counts=status_counts)
    latest = events[0] if events else None
    latest_success = _latest_event_with_status(events, "success")
    latest_failed = _latest_event_with_status(events, "failed")
    pending_queue = queue_counts.get("pending", 0)
    queue_detail = f"SMINFO pending {pending_queue}" if queue_counts else "SMINFO 큐 테이블 없음"
    return f"""
    <div class="aiops-strip" aria-label="AIOps runtime summary">
      {_aiops_item("AIOps 상태", health_label, health_detail, health_class)}
      {_aiops_item("최근 실행", latest.started_at if latest else "없음", latest.job_name if latest else "기록 없음", "ok" if latest else "warn")}
      {_aiops_item("최근 성공", latest_success.started_at if latest_success else "없음", latest_success.job_name if latest_success else "성공 이벤트 없음", "ok" if latest_success else "warn")}
      {_aiops_item("최근 실패", latest_failed.started_at if latest_failed else "없음", latest_failed.job_name if latest_failed else queue_detail, "fail" if latest_failed else "ok")}
    </div>
    """


def _aiops_health(*, status_counts: Counter[str]) -> tuple[str, str, str]:
    if status_counts.get("failed", 0):
        return ("장애", f"최근 렌더링 범위 안에 실패 {status_counts['failed']}건", "fail")
    if status_counts.get("partial_success", 0):
        return ("주의", f"부분성공 {status_counts['partial_success']}건 확인", "warn")
    if sum(status_counts.values()):
        return ("정상", "최근 루프가 성공 또는 대기 상태로 기록됨", "ok")
    return ("대기", "아직 실행 이벤트가 없음", "warn")


def _latest_event_with_status(events: list[AgentRunEvent], status: str) -> AgentRunEvent | None:
    return next((event for event in events if event.status == status), None)


def _aiops_item(label: str, value: str, detail: str, state: str) -> str:
    return f"""
    <div class="aiops-item {_status_class(state)}">
      <div class="aiops-label">{_h(label)}</div>
      <div class="aiops-value">{_h(value)}</div>
      <div class="aiops-detail">{_h(detail)}</div>
    </div>
    """


def _render_topology(
    *,
    events: list[AgentRunEvent],
    queue_counts: dict[str, int],
    table_counts: dict[str, int],
) -> str:
    latest_by_job = _latest_event_by_job(events)
    queue_total = sum(queue_counts.values())
    db_total = sum(table_counts.values())
    return f"""
    <div class="topology">
      <div class="topology-inner">
        <div class="plane-label source">수집 계층</div>
        <div class="plane-label runtime">Hermes 실행 계층</div>
        <div class="plane-label decision">판단 계층</div>
        <div class="plane-label storage">상태/관측 계층</div>
        <svg class="wires" viewBox="0 0 1120 620" aria-hidden="true">
          <defs>
            <marker id="arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L8,3 z" fill="rgba(245,245,245,.82)"></path>
            </marker>
          </defs>
          <path class="wire" d="M148 166 C214 166 220 170 286 170" marker-end="url(#arrow)"></path>
          <path class="wire" d="M438 170 C496 170 496 224 554 224" marker-end="url(#arrow)"></path>
          <path class="wire" d="M706 224 C744 224 722 136 760 136" marker-end="url(#arrow)"></path>
          <path class="wire" d="M706 224 C748 224 718 352 760 352" marker-end="url(#arrow)"></path>
          <path class="wire dim" d="M706 224 C818 224 738 486 800 486" marker-end="url(#arrow)"></path>
          <path class="wire dim" d="M438 170 C508 170 466 358 536 358" marker-end="url(#arrow)"></path>
          <path class="wire" d="M688 358 C724 358 724 352 760 352" marker-end="url(#arrow)"></path>
          <path class="wire dim" d="M160 364 C238 364 228 254 306 254" marker-end="url(#arrow)"></path>
          <path class="wire dim" d="M458 254 C512 254 500 224 554 224" marker-end="url(#arrow)"></path>
        </svg>
        {_topology_node(label="수집기", job_name="crawl-sources", event=latest_by_job.get("crawl-sources"), x=28, y=112, icon="C", color="var(--purple)")}
        {_topology_node(label="원천 적재", job_name="ingest-sources", event=latest_by_job.get("ingest-sources"), x=286, y=116, icon="I", color="var(--orange)")}
        {_topology_node(label="엔티티 정리", job_name="resolve-entities", event=latest_by_job.get("resolve-entities"), x=306, y=292, icon="R", color="var(--blue)")}
        {_topology_node(label="후보 점수화", job_name="score-candidates", event=latest_by_job.get("score-candidates"), x=554, y=170, icon="S", color="var(--pink)")}
        {_topology_node(label="회귀 보정", job_name="calibrate-scores", event=latest_by_job.get("calibrate-scores"), x=536, y=344, icon="K", color="var(--purple)")}
        {_topology_node(label="리뷰 시트", job_name="sync-review-sheet", event=latest_by_job.get("sync-review-sheet"), x=760, y=82, icon="G", color="var(--green)")}
        {_topology_node(label="SMINFO 큐", job_name="", event=None, x=760, y=298, icon="Q", color="var(--blue)", meta=f"{queue_total} tasks")}
        {_topology_node(label="Mother DB", job_name="", event=None, x=800, y=430, icon="D", color="var(--green)", meta=f"{db_total} rows")}
        {_topology_node(label="백업", job_name="backup-export", event=latest_by_job.get("backup-export"), x=946, y=252, icon="B", color="var(--orange)")}
      </div>
    </div>
    """


def _latest_event_by_job(events: list[AgentRunEvent]) -> dict[str, AgentRunEvent]:
    latest: dict[str, AgentRunEvent] = {}
    for event in events:
        latest.setdefault(event.job_name, event)
    return latest


def _topology_node(
    *,
    label: str,
    job_name: str,
    event: AgentRunEvent | None,
    x: int,
    y: int,
    icon: str,
    color: str,
    meta: str = "",
) -> str:
    status = event.status if event is not None else "idle"
    node_meta = meta
    if event is not None:
        node_meta = f"입력 {event.input_count} / 출력 {event.output_count}"
    error = f'<div class="node-error">{_h(event.error_message)}</div>' if event and event.error_message else ""
    job = f'<div class="node-job">{_h(job_name)}</div>' if job_name else ""
    return f"""
    <div class="node {_status_class(status)}" style="left:{x}px; top:{y}px; --node:{color};">
      <div class="node-icon">{_h(icon)}</div>
      <div class="node-title">{_h(label)}</div>
      {job}
      <div class="node-meta">{_h(status)} · {_h(node_meta)}</div>
      {error}
    </div>
    """


def _render_lanes(events: list[AgentRunEvent], job_names: list[str]) -> str:
    if not events:
        return '<div class="lane"><div class="lane-label">이벤트 없음</div><div class="lane-events"></div></div>'
    lanes: list[str] = []
    for job_name in job_names:
        job_events = [event for event in events if event.job_name == job_name]
        event_html = "\n".join(_render_event_chip(event) for event in job_events)
        lanes.append(
            f"""
            <div class="lane">
              <div class="lane-label">{_h(job_name)}</div>
              <div class="lane-events">{event_html}</div>
            </div>
            """
        )
    return "\n".join(lanes)


def _render_event_chip(event: AgentRunEvent) -> str:
    error = f'<div class="event-error">{_h(event.error_message)}</div>' if event.error_message else ""
    return f"""
    <div class="event {_status_class(event.status)}">
      <div class="event-time">{_h(event.started_at)}</div>
      <div class="event-title">{_h(_status_label(event.status))}</div>
      <div class="event-counts">입력 {_h(event.input_count)} · 출력 {_h(event.output_count)}</div>
      {error}
    </div>
    """


def _render_event_table(events: list[AgentRunEvent]) -> str:
    rows = "\n".join(
        f"""
        <tr>
          <td>{_h(event.started_at)}</td>
          <td>{_h(event.job_name)}</td>
          <td class="status {_status_class(event.status)}">{_h(_status_label(event.status))}</td>
          <td>{_h(event.input_count)}</td>
          <td>{_h(event.output_count)}</td>
          <td>{_h(event.error_message)}</td>
        </tr>
        """
        for event in events
    )
    return f"""
    <table>
      <thead>
        <tr>
          <th>시작</th>
          <th>잡</th>
          <th>상태</th>
          <th>입력</th>
          <th>출력</th>
          <th>오류</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """


def _render_key_values(values: dict[str, int]) -> str:
    return "\n".join(
        f'<div class="kv"><span>{_h(key)}</span><strong>{_h(value)}</strong></div>'
        for key, value in sorted(values.items())
    )


def _metric(label: str, value: int) -> str:
    return f'<div class="metric"><strong>{_h(value)}</strong><span>{_h(label)}</span></div>'


def _status_label(status: str) -> str:
    labels = {
        "success": "성공",
        "failed": "실패",
        "partial_success": "부분성공",
        "pending": "대기",
        "idle": "대기",
    }
    if not status:
        return "알 수 없음"
    return f"{labels.get(status, status)} ({status})"


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _status_class(status: str) -> str:
    return "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in status)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _h(value: object) -> str:
    return html.escape(str(value), quote=True)
