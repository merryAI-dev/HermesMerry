from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class RepoEvidence:
    repo_path: Path
    path: Path
    line_number: int
    snippet: str
    term: str

    def to_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["repo_path"] = str(self.repo_path)
        row["path"] = str(self.path)
        return row


def collect_repo_evidence(
    terms: Iterable[str],
    *,
    repo_paths: Iterable[str | Path],
    limit: int = 8,
) -> list[RepoEvidence]:
    evidence: list[RepoEvidence] = []
    seen: set[tuple[Path, Path, int]] = set()

    normalized_terms = [term.strip() for term in terms if term and term.strip()]
    for repo_path in [Path(path).expanduser().resolve() for path in repo_paths]:
        if not repo_path.exists() or not repo_path.is_dir():
            continue

        for term in normalized_terms:
            for row in _rg_fixed_string(repo_path, term):
                key = (repo_path, row.path, row.line_number)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(row)
                if len(evidence) >= limit:
                    return evidence

    return evidence


def _rg_fixed_string(repo_path: Path, term: str) -> list[RepoEvidence]:
    command = [
        "rg",
        "--line-number",
        "--fixed-strings",
        "--hidden",
        "--glob",
        "!.git",
        "--glob",
        "!uv.lock",
        "--glob",
        "!*.lock",
        "--glob",
        "!tmp",
        "--",
        term,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode not in (0, 1):
        return []

    rows: list[RepoEvidence] = []
    for line in result.stdout.splitlines():
        parsed = _parse_rg_line(line)
        if parsed is None:
            continue
        path, line_number, snippet = parsed
        rows.append(
            RepoEvidence(
                repo_path=repo_path,
                path=path,
                line_number=line_number,
                snippet=snippet.strip(),
                term=term,
            )
        )
    return rows


def _parse_rg_line(line: str) -> tuple[Path, int, str] | None:
    path_text, separator, rest = line.partition(":")
    if not separator:
        return None
    line_text, separator, snippet = rest.partition(":")
    if not separator:
        return None
    try:
        line_number = int(line_text)
    except ValueError:
        return None
    return Path(path_text), line_number, snippet
