# Safety Model

Hermes is treated as an orchestration runtime, not as a general local computer operator.

Production profile:

- `terminal`, `file`, `code_execution`, `computer_use`, `delegation`, and `cronjob` are disabled.
- `yolo` is false.
- `terminal.backend` remains `docker` as a defense in depth setting.
- `agent.max_turns` is capped at 20.
- `tool_loop_guardrails.hard_stop_enabled` is true.

The only production tool surface is `merry_mcp.registry.TOOL_REGISTRY`. These contracts expose domain operations for BigQuery, GCS, Google Sheets, and Slack. They do not expose arbitrary shell, filesystem, browser, or code execution capabilities.

Human review remains mandatory. The system may recommend `advance`, `watchlist`, `request_more_info`, or `archive`, but the final AC decision is stored through the review Sheet feedback loop.
