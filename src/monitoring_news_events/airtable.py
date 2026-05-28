from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AirtableConfig, AirtableTableConfig, GeoReport


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


@dataclass(slots=True)
class AirtablePublishResult:
    report_record_id: str
    report_url: str = ""


class AirtableClient:
    def __init__(self, config: AirtableConfig) -> None:
        self.config = config

    def is_enabled(self) -> bool:
        return (
            self.config.enabled
            and bool(self.config.base_id)
            and bool(os.getenv(self.config.api_token_env))
        )

    def create_record(self, table_name: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = self.create_records(table_name, [fields])
        return payload[0]

    def create_records(self, table_name: str, fields_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not fields_list:
            return []
        created_records: list[dict[str, Any]] = []
        for batch in _chunked(fields_list, 10):
            payload = {
                "records": [{"fields": fields} for fields in batch],
                "typecast": True,
            }
            response = self._request_json("POST", table_name, payload)
            created_records.extend(response.get("records", []))
        return created_records

    def get_record(self, table_name: str, record_id: str) -> dict[str, Any]:
        path = f"{table_name}/{record_id}"
        return self._request_json("GET", path)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        token = os.getenv(self.config.api_token_env)
        if not token:
            raise RuntimeError(f"Environment variable {self.config.api_token_env} is not set")

        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        base = self.config.api_base_url.rstrip("/")
        url = f"{base}/{self.config.base_id}/{encoded_path}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class AirtablePublisher:
    def __init__(self, config: AirtableConfig, client: AirtableClient | None = None) -> None:
        self.config = config
        self.client = client or AirtableClient(config)

    def is_enabled(self) -> bool:
        return self.client.is_enabled()

    def publish(self, report: GeoReport, artifact_paths: dict[str, Path]) -> AirtablePublishResult:
        report_markdown = artifact_paths["markdown"].read_text(encoding="utf-8")
        report_json = artifact_paths["json"].read_text(encoding="utf-8")

        report_record = self.client.create_record(
            self.config.reports_table.name,
            self._build_report_fields(report, artifact_paths, report_markdown, report_json),
        )
        report_record_id = report_record["id"]

        signal_record_ids = self._publish_raw_signals(report, report_record_id)
        angle_record_ids = self._publish_angles(report, report_record_id, signal_record_ids)
        self._publish_headlines(report, report_record_id, angle_record_ids)
        self._publish_recommendations(report, report_record_id, signal_record_ids, angle_record_ids)
        self._publish_risks(report, report_record_id, signal_record_ids)

        report_url = self._resolve_report_url(report_record_id)
        return AirtablePublishResult(report_record_id=report_record_id, report_url=report_url)

    def _publish_raw_signals(self, report: GeoReport, report_record_id: str) -> dict[str, str]:
        records = []
        for signal in report.raw_signals:
            records.append(
                {
                    "Signal ID": signal.id,
                    "Name": signal.title,
                    "Report": [report_record_id],
                    "Source URL": signal.source_url,
                    "Source Name": signal.source_name,
                    "Source Type": signal.source_type,
                    "Published At": signal.published_at,
                    "Category": signal.category,
                    "Summary": signal.summary,
                    "Emotional Trigger": signal.emotional_trigger,
                    "Shelf Life": signal.shelf_life,
                    "Score": signal.score,
                    "Reliability": signal.reliability,
                }
            )

        created = self.client.create_records(self.config.raw_signals_table.name, records)
        return {
            signal.id: record["id"]
            for signal, record in zip(report.raw_signals, created, strict=False)
        }

    def _publish_angles(
        self,
        report: GeoReport,
        report_record_id: str,
        signal_record_ids: dict[str, str],
    ) -> dict[str, str]:
        records = []
        for angle in report.angles:
            fields: dict[str, Any] = {
                "Angle ID": angle.id,
                "Name": angle.angle[:120],
                "Report": [report_record_id],
                "Raw Signal ID": angle.raw_signal_id,
                "Raw Signal Title": angle.raw_signal_title,
                "Angle": angle.angle,
                "Offer Link": angle.offer_link,
                "Audience Pain": angle.audience_pain,
                "Creative Type": angle.creative_type,
                "Priority": angle.priority,
                "Rationale": angle.rationale,
            }
            signal_record_id = signal_record_ids.get(angle.raw_signal_id)
            if signal_record_id:
                fields["Raw Signal"] = [signal_record_id]
            records.append(fields)

        created = self.client.create_records(self.config.angles_table.name, records)
        return {
            angle.id: record["id"]
            for angle, record in zip(report.angles, created, strict=False)
        }

    def _publish_headlines(
        self,
        report: GeoReport,
        report_record_id: str,
        angle_record_ids: dict[str, str],
    ) -> None:
        records = []
        for headline in report.headlines:
            fields: dict[str, Any] = {
                "Headline ID": headline.id,
                "Name": headline.text[:120],
                "Report": [report_record_id],
                "Angle ID": headline.angle_id,
                "Angle Label": headline.angle_label,
                "Text": headline.text,
                "Format": headline.format,
                "Length": headline.length,
            }
            angle_record_id = angle_record_ids.get(headline.angle_id)
            if angle_record_id:
                fields["Angle"] = [angle_record_id]
            records.append(fields)
        if records:
            self.client.create_records(self.config.headlines_table.name, records)

    def _publish_recommendations(
        self,
        report: GeoReport,
        report_record_id: str,
        signal_record_ids: dict[str, str],
        angle_record_ids: dict[str, str],
    ) -> None:
        records = []
        for recommendation in report.recommendations:
            fields: dict[str, Any] = {
                "Name": f"Top {recommendation.rank}",
                "Report": [report_record_id],
                "Rank": recommendation.rank,
                "Angle ID": recommendation.angle_id,
                "Raw Signal ID": recommendation.raw_signal_id,
                "Priority": recommendation.priority,
                "Why": recommendation.why,
                "Freshness Score": recommendation.freshness_score,
                "Trigger Score": recommendation.trigger_score,
                "Offer Fit Score": recommendation.offer_fit_score,
            }
            angle_record_id = angle_record_ids.get(recommendation.angle_id)
            signal_record_id = signal_record_ids.get(recommendation.raw_signal_id)
            if angle_record_id:
                fields["Angle"] = [angle_record_id]
            if signal_record_id:
                fields["Raw Signal"] = [signal_record_id]
            records.append(fields)
        if records:
            self.client.create_records(self.config.recommendations_table.name, records)

    def _publish_risks(
        self,
        report: GeoReport,
        report_record_id: str,
        signal_record_ids: dict[str, str],
    ) -> None:
        records = []
        for risk in report.risks:
            fields: dict[str, Any] = {
                "Name": risk.raw_signal_id,
                "Report": [report_record_id],
                "Raw Signal ID": risk.raw_signal_id,
                "Legal Risk": risk.legal_risk,
                "Platform Ban Risk": risk.platform_ban_risk,
                "Audience Negative Risk": risk.audience_negative_risk,
                "Reputational Risk": risk.reputational_risk,
                "Staleness Risk": risk.staleness_risk,
                "Notes": risk.notes,
            }
            signal_record_id = signal_record_ids.get(risk.raw_signal_id)
            if signal_record_id:
                fields["Raw Signal"] = [signal_record_id]
            records.append(fields)
        if records:
            self.client.create_records(self.config.risks_table.name, records)

    def _build_report_fields(
        self,
        report: GeoReport,
        artifact_paths: dict[str, Path],
        report_markdown: str,
        report_json: str,
    ) -> dict[str, Any]:
        shortlist_lines = []
        for recommendation in report.recommendations:
            shortlist_lines.append(
                f"#{recommendation.rank} {recommendation.angle_id} [{recommendation.priority}] - {recommendation.why}"
            )

        return {
            "Report ID": f"{report.geo_id}:{report.generated_at}",
            "Name": f"{report.geo_name} {report.generated_at[:10]}",
            "GEO ID": report.geo_id,
            "GEO Name": report.geo_name,
            "Generated At": report.generated_at,
            "Coverage Period": report.coverage_period,
            "Owner": report.owner,
            "Offer Name": report.offer_name,
            "Previous Report URL": report.previous_report_url,
            "Feedback Summary": "\n".join(report.feedback_summary),
            "Urgency Hot": "\n".join(report.urgency_hot),
            "Urgency Later": "\n".join(report.urgency_later),
            "Notes": "\n".join(report.notes),
            "Shortlist Summary": "\n".join(shortlist_lines),
            "Report Markdown": report_markdown,
            "Report JSON": report_json,
            "Local Markdown Path": str(artifact_paths["markdown"]),
            "Local JSON Path": str(artifact_paths["json"]),
            "Raw Signal Count": len(report.raw_signals),
            "Angle Count": len(report.angles),
            "Headline Count": len(report.headlines),
            "LLM Used": bool(report.metadata.get("llm_used", False)),
        }

    def _resolve_report_url(self, report_record_id: str) -> str:
        link_field = self.config.report_link_field.strip()
        if link_field:
            resolved = self._poll_report_link_field(report_record_id, link_field)
            if resolved:
                return resolved

        if self.config.report_record_url_template:
            return self.config.report_record_url_template.format(
                base_id=self.config.base_id,
                table_id=self.config.reports_table.url_table_id,
                record_id=report_record_id,
            )

        return self._build_direct_record_url(self.config.reports_table, report_record_id)

    def _poll_report_link_field(self, report_record_id: str, link_field: str) -> str:
        attempts = max(1, self.config.report_link_poll_attempts)
        for attempt in range(attempts):
            record = self.client.get_record(self.config.reports_table.name, report_record_id)
            value = record.get("fields", {}).get(link_field)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if attempt < attempts - 1:
                time.sleep(max(0.0, self.config.report_link_poll_interval_seconds))
        return ""

    def _build_direct_record_url(self, table: AirtableTableConfig, record_id: str) -> str:
        if not table.url_table_id or not self.config.base_id:
            return ""
        return f"https://airtable.com/{self.config.base_id}/{table.url_table_id}/{record_id}"
