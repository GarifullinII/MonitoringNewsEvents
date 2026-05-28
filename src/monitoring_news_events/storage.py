from __future__ import annotations

import json
from pathlib import Path

from .models import FeedbackEntry, GeoReport, dataclass_to_dict
from .reporting import render_json, render_markdown
from .utils import slugify


class LocalArtifactStore:
    def __init__(self, report_dir: Path, data_dir: Path) -> None:
        self.report_dir = report_dir
        self.data_dir = data_dir

    def load_feedback(self, geo_id: str) -> list[FeedbackEntry]:
        feedback_dir = self.data_dir / "feedback"
        payload_path = feedback_dir / f"{geo_id}.json"
        if not payload_path.exists():
            return []
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        entries: list[FeedbackEntry] = []
        for item in payload.get("entries", []):
            entries.append(
                FeedbackEntry(
                    report_date=item["report_date"],
                    winners=list(item.get("winners", [])),
                    losers=list(item.get("losers", [])),
                    lessons=list(item.get("lessons", [])),
                )
            )
        return entries

    def persist_report(self, report: GeoReport, append_knowledge_base: bool = True) -> dict[str, Path]:
        geo_dir = self.report_dir / report.geo_id
        geo_dir.mkdir(parents=True, exist_ok=True)
        slug = slugify(report.generated_at.replace(":", "-"))
        markdown_path = geo_dir / f"{slug}.md"
        json_path = geo_dir / f"{slug}.json"
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        json_path.write_text(render_json(report), encoding="utf-8")
        if append_knowledge_base:
            self._append_knowledge_base(report)
        return {"markdown": markdown_path, "json": json_path}

    def _append_knowledge_base(self, report: GeoReport) -> None:
        base_dir = self.data_dir / "knowledge_base"
        base_dir.mkdir(parents=True, exist_ok=True)
        self._append_jsonl(base_dir / "inforeasons.jsonl", report.raw_signals, report.geo_id)
        self._append_jsonl(base_dir / "angles.jsonl", report.angles, report.geo_id)
        self._append_jsonl(base_dir / "headlines.jsonl", report.headlines, report.geo_id)
        self._append_jsonl(base_dir / "reports.jsonl", [report], report.geo_id)

    def _append_jsonl(self, path: Path, items: list, geo_id: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            for item in items:
                payload = dataclass_to_dict(item)
                payload["geo_id"] = geo_id
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
