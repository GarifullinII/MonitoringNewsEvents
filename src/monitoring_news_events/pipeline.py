from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .airtable import AirtablePublisher
from .heuristics import (
    build_evergreen_signals,
    build_raw_signals,
    build_recommendations,
    build_risks,
    build_urgency,
    generate_angle_ideas,
    generate_headlines,
    summarize_feedback,
)
from .models import AngleIdea, GeoReport, Headline, ProjectConfig, Recommendation, SignalRisk
from .notifications import NotificationHub
from .openai_client import OpenAIResponsesClient
from .sources import fetch_geo_articles
from .storage import LocalArtifactStore
from .utils import isoformat_utc, now_utc, parse_datetime


@dataclass(slots=True)
class PipelineArtifacts:
    report: GeoReport
    markdown_path: Path
    json_path: Path
    airtable_report_id: str = ""
    airtable_report_url: str = ""
    notifications: list[str] = field(default_factory=list)


class MonitoringPipeline:
    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.store = LocalArtifactStore(config.report_dir, config.data_dir)
        self.airtable = AirtablePublisher(config.airtable)
        self.llm_client = OpenAIResponsesClient(config.llm)
        self.notifier = NotificationHub()

    def run(
        self,
        geo_id: str,
        notify: bool = False,
        force_disable_llm: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PipelineArtifacts:
        def progress(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        geo = self.config.require_geo(geo_id)
        progress(f"Starting report generation for GEO '{geo.id}' ({geo.name})")
        progress("Fetching articles from configured sources")
        articles = fetch_geo_articles(geo)
        progress(f"Fetched {len(articles)} article candidates")
        progress("Building raw signals, angles, headlines, recommendations, and risks")
        raw_signals = build_raw_signals(articles, geo)
        notes: list[str] = []
        if not raw_signals:
            raw_signals = build_evergreen_signals(geo)
            notes.append("Свежих новостей оказалось мало, поэтому выпуск дополнен evergreen-темами.")
            progress("No fresh signals found, fallback to evergreen themes")

        feedback_entries = self.store.load_feedback(geo.id)
        feedback_summary = summarize_feedback(feedback_entries)

        angles = generate_angle_ideas(raw_signals, geo)
        headlines = generate_headlines(angles, geo)
        recommendations = build_recommendations(raw_signals, angles)
        risks = build_risks(raw_signals)
        urgency_hot, urgency_later = build_urgency(raw_signals)
        llm_used = False

        llm_is_enabled_for_geo = (geo.llm_enabled if geo.llm_enabled is not None else self.config.llm.enabled) and not force_disable_llm
        if llm_is_enabled_for_geo and self.llm_client.is_enabled():
            try:
                progress("Running LLM enrichment")
                enriched = self.llm_client.enrich_report(geo, raw_signals, feedback_entries)
                angles = self._map_angles(enriched.get("angles", []), raw_signals) or angles
                headlines = self._map_headlines(enriched.get("headlines", []), angles) or headlines
                recommendations = self._map_recommendations(enriched.get("recommendations", []), angles) or recommendations
                risks = self._map_risks(enriched.get("risks", [])) or risks
                urgency = enriched.get("urgency", {})
                urgency_hot = urgency.get("hot", urgency_hot)
                urgency_later = urgency.get("later", urgency_later)
                llm_used = True
                progress("LLM enrichment completed")
            except Exception as exc:
                notes.append(f"LLM enrichment skipped: {exc}")
                progress(f"LLM enrichment skipped: {exc}")

        generated_at = now_utc()
        coverage_start = generated_at.date().isoformat()
        if raw_signals:
            published_dates = [parse_datetime(signal.published_at) for signal in raw_signals if signal.published_at]
            published_dates = [item for item in published_dates if item is not None]
            if published_dates:
                coverage_start = min(published_dates).date().isoformat()

        report = GeoReport(
            geo_id=geo.id,
            geo_name=geo.name,
            generated_at=isoformat_utc(generated_at),
            coverage_period=f"{coverage_start} — {generated_at.date().isoformat()}",
            owner=geo.owner,
            previous_report_url=geo.previous_report_url,
            offer_name=geo.offer_name,
            raw_signals=raw_signals,
            angles=angles,
            headlines=headlines,
            recommendations=recommendations,
            risks=risks,
            urgency_hot=urgency_hot,
            urgency_later=urgency_later,
            feedback_summary=feedback_summary,
            notes=notes,
            metadata={
                "article_count": len(articles),
                "raw_signal_count": len(raw_signals),
                "angles_count": len(angles),
                "headlines_count": len(headlines),
                "llm_used": llm_used,
            },
        )

        progress("Saving local markdown and JSON artifacts")
        artifact_paths = self.store.persist_report(report)
        airtable_report_id = ""
        airtable_report_url = ""
        if self.airtable.is_enabled():
            try:
                progress("Publishing report structure to Airtable")
                airtable_result = self.airtable.publish(report, artifact_paths)
                airtable_report_id = airtable_result.report_record_id
                airtable_report_url = airtable_result.report_url
                report.airtable_report_id = airtable_report_id
                report.airtable_report_url = airtable_report_url
                report.metadata["airtable_report_id"] = airtable_report_id
                report.metadata["airtable_report_url"] = airtable_report_url
                artifact_paths = self.store.persist_report(report, append_knowledge_base=False)
                progress("Airtable publish completed")
            except Exception as exc:
                report.notes.append(f"Airtable publish skipped: {exc}")
                artifact_paths = self.store.persist_report(report, append_knowledge_base=False)
                progress(f"Airtable publish skipped: {exc}")

        notifications = (
            self.notifier.send(geo, report, artifact_paths, report_url=airtable_report_url)
            if notify
            else []
        )
        if notify:
            progress(f"Notifications sent: {', '.join(notifications) if notifications else 'none'}")
        progress("Report generation completed")
        return PipelineArtifacts(
            report=report,
            markdown_path=artifact_paths["markdown"],
            json_path=artifact_paths["json"],
            airtable_report_id=airtable_report_id,
            airtable_report_url=airtable_report_url,
            notifications=notifications,
        )

    def _map_angles(self, payload: list[dict], raw_signals) -> list[AngleIdea]:
        signal_map = {signal.id: signal for signal in raw_signals}
        result: list[AngleIdea] = []
        for item in payload:
            signal = signal_map.get(item["raw_signal_id"])
            if signal is None:
                continue
            result.append(
                AngleIdea(
                    id=item["id"],
                    raw_signal_id=item["raw_signal_id"],
                    raw_signal_title=signal.title,
                    angle=item["angle"],
                    offer_link=item["offer_link"],
                    audience_pain=item["audience_pain"],
                    creative_type=item["creative_type"],
                    priority=item["priority"],
                    rationale=item["rationale"],
                )
            )
        return result

    def _map_headlines(self, payload: list[dict], angles: list[AngleIdea]) -> list[Headline]:
        angle_map = {angle.id: angle for angle in angles}
        result: list[Headline] = []
        for item in payload:
            angle = angle_map.get(item["angle_id"])
            if angle is None:
                continue
            text = item["text"]
            result.append(
                Headline(
                    id=item["id"],
                    angle_id=item["angle_id"],
                    angle_label=angle.angle,
                    text=text,
                    format=item["format"],
                    length=len(text),
                )
            )
        return result

    def _map_recommendations(self, payload: list[dict], angles: list[AngleIdea]) -> list[Recommendation]:
        angle_ids = {angle.id for angle in angles}
        result: list[Recommendation] = []
        for item in payload:
            if item["angle_id"] not in angle_ids:
                continue
            result.append(
                Recommendation(
                    rank=int(item["rank"]),
                    angle_id=item["angle_id"],
                    raw_signal_id=item["raw_signal_id"],
                    priority=item["priority"],
                    why=item["why"],
                    freshness_score=int(item["freshness_score"]),
                    trigger_score=int(item["trigger_score"]),
                    offer_fit_score=int(item["offer_fit_score"]),
                )
            )
        return sorted(result, key=lambda item: item.rank)

    def _map_risks(self, payload: list[dict]) -> list[SignalRisk]:
        result: list[SignalRisk] = []
        for item in payload:
            result.append(
                SignalRisk(
                    raw_signal_id=item["raw_signal_id"],
                    legal_risk=item["legal_risk"],
                    platform_ban_risk=item["platform_ban_risk"],
                    audience_negative_risk=item["audience_negative_risk"],
                    reputational_risk=item["reputational_risk"],
                    staleness_risk=item["staleness_risk"],
                    notes=item["notes"],
                )
            )
        return result
