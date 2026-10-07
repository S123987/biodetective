"""Local-only investigation history and report export."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / "BioDetective"
    path.mkdir(parents=True, exist_ok=True)
    return path


class InvestigationStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.path = database_path or (app_data_dir() / "investigations.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, data TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def save(self, data: dict[str, Any], investigation_id: str | None = None) -> str:
        record_id = investigation_id or str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        title = str(data.get("claim", "New investigation"))[:120]
        encoded = json.dumps(data, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO investigations(id,title,created_at,data) VALUES(?,?,?,?)",
                (record_id, title, created_at, encoded),
            )
        return record_id

    def list_recent(self, limit: int = 25) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,title,created_at FROM investigations ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def load(self, investigation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM investigations WHERE id=?", (investigation_id,)).fetchone()
        return json.loads(row["data"]) if row else None


def report_markdown(data: dict[str, Any]) -> str:
    analysis = data.get("analysis", {})
    bes = data.get("bes", {})
    lines = [
        "# BioDetective AI investigation",
        "",
        f"**Claim:** {data.get('claim', '')}",
        "",
        f"**Retrieved:** {data.get('retrieved_at', 'date not recorded')} · **Search source:** Europe PMC",
        "",
        f"**Assessment:** {data.get('assessment', '')}",
        "",
        f"**Pilot BES:** {bes.get('score') if bes.get('score') is not None else 'Not scored'} / 100",
        "",
        f"_Not a truth probability. {bes.get('label', '')}_",
        "",
        "## Competing hypotheses",
    ]
    hypotheses = analysis.get("hypotheses", [])
    if hypotheses:
        for item in hypotheses:
            lines.append(f"- **{item.get('id', '')} — {item.get('label', '')}:** {item.get('description', '')}")
    else:
        lines.append("- No structured hypotheses were returned by the local model.")
    lines.extend(["", "## Evidence landscape", ""])
    evidence = data.get("evidence", [])
    for polarity in ("supporting", "contradicting", "insufficient"):
        lines.append(f"- {polarity.title()}: {sum(1 for item in evidence if item.get('polarity') == polarity)}")
    lines.extend(["", "## Proposition-level assessments", ""])
    assessments = data.get("relationship_assessments", [])
    if assessments:
        for item in assessments:
            score = item.get("pilot_bes")
            lines.append(
                f"- **{item.get('id', '')}: {item.get('source', '')} → {item.get('target', '')}** — "
                f"{item.get('supporting', 0)} support, {item.get('contradicting', 0)} contradiction, "
                f"{item.get('insufficient', 0)} insufficient; pilot BES {score if score is not None else 'unavailable'}/100."
            )
    else:
        lines.append("- No structured graph propositions were returned.")
    lines.extend(["", "## Search queries", ""])
    lines.extend(f"- {query}" for query in analysis.get("search_queries", []))
    lines.extend(["", "## Evidence records", ""])
    for index, article in enumerate(data.get("articles", []), start=1):
        item = article.get("evidence", {})
        identifier = article.get("doi") or (f"PMID:{article['pmid']}" if article.get("pmid") else "identifier unavailable")
        lines.extend(
            [
                f"### {index}. {article.get('title', 'Untitled record')}",
                f"{article.get('authors', '')} ({article.get('year', '')}). {article.get('journal', '')}.",
                f"Source: [{identifier}]({article.get('url', '')}) · retrieved from {article.get('retrieved_from', 'Europe PMC')} · {article.get('access_level', 'metadata only')}.",
                f"**Classification:** {item.get('polarity', 'unclassified')} ({item.get('review_state', 'not reviewed')}) · {item.get('study_design', 'unknown')} · {item.get('directness', 'unclear')}.",
                f"**Reported finding:** {item.get('finding_summary', 'No extracted finding.')}",
                f"**Rationale:** {item.get('rationale', '')}",
                f"**Mapped propositions:** {', '.join(item.get('relationship_ids', [])) or 'None confidently linked.'}",
                f"**Limitations:** {', '.join(item.get('limitations', [])) or 'Not assessed.'}",
                "",
            ]
        )
    lines.extend(["## Retrieval notes", ""])
    lines.extend(f"- {warning}" for warning in data.get("retrieval_warnings", []))
    if not data.get("retrieval_warnings"):
        lines.append("- Literature search is not exhaustive; retrieved records are candidates and automated classifications require review.")
    lines.extend(["", f"**Model:** {data.get('model', 'unknown')} (local Ollama runtime)", "**Search source:** Europe PMC", ""])
    return "\n".join(lines)

