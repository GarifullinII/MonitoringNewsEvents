from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = False
    provider: str = "openai_responses"
    model: str = "gpt-4.1-mini"
    api_key_env: str = "OPENAI_API_KEY"
    api_base_url: str = "https://api.openai.com/v1/responses"
    timeout_seconds: int = 45


@dataclass(slots=True)
class AirtableTableConfig:
    name: str
    url_table_id: str = ""


@dataclass(slots=True)
class AirtableConfig:
    enabled: bool = False
    api_token_env: str = "AIRTABLE_TOKEN"
    base_id: str = ""
    api_base_url: str = "https://api.airtable.com/v0"
    timeout_seconds: int = 30
    report_link_field: str = ""
    report_link_poll_attempts: int = 6
    report_link_poll_interval_seconds: float = 2.0
    report_record_url_template: str = ""
    reports_table: AirtableTableConfig = field(
        default_factory=lambda: AirtableTableConfig(name="Reports")
    )
    raw_signals_table: AirtableTableConfig = field(
        default_factory=lambda: AirtableTableConfig(name="Inforeasons")
    )
    angles_table: AirtableTableConfig = field(
        default_factory=lambda: AirtableTableConfig(name="Angles")
    )
    headlines_table: AirtableTableConfig = field(
        default_factory=lambda: AirtableTableConfig(name="Headlines")
    )
    recommendations_table: AirtableTableConfig = field(
        default_factory=lambda: AirtableTableConfig(name="Recommendations")
    )
    risks_table: AirtableTableConfig = field(
        default_factory=lambda: AirtableTableConfig(name="Risks")
    )


@dataclass(slots=True)
class SourceConfig:
    kind: str
    name: str
    source_type: str
    category: str
    url: str | None = None
    query: str | None = None
    language: str = "en-US"
    country: str = "US"
    max_items: int = 10
    path: str | None = None


@dataclass(slots=True)
class GeoConfig:
    id: str
    name: str
    owner: str
    offer_name: str
    offer_description: str
    audience_pains: list[str] = field(default_factory=list)
    offer_hooks: list[str] = field(default_factory=list)
    evergreen_themes: list[str] = field(default_factory=list)
    previous_report_url: str = ""
    coverage_days: int = 7
    signal_limit: int = 15
    idea_limit: int = 25
    headlines_per_idea: int = 4
    report_language: str = "ru"
    llm_enabled: bool | None = None
    sources: list[SourceConfig] = field(default_factory=list)


@dataclass(slots=True)
class ProjectConfig:
    report_dir: Path
    data_dir: Path
    llm: LLMConfig = field(default_factory=LLMConfig)
    airtable: AirtableConfig = field(default_factory=AirtableConfig)
    geos: list[GeoConfig] = field(default_factory=list)

    def require_geo(self, geo_id: str) -> GeoConfig:
        for geo in self.geos:
            if geo.id == geo_id:
                return geo
        raise KeyError(f"GEO '{geo_id}' not found in configuration")


@dataclass(slots=True)
class Article:
    id: str
    title: str
    url: str
    source_name: str
    source_type: str
    category_hint: str
    published_at: str
    summary: str = ""


@dataclass(slots=True)
class RawSignal:
    id: str
    title: str
    source_url: str
    source_name: str
    source_type: str
    published_at: str
    category: str
    summary: str
    emotional_trigger: str
    shelf_life: str
    score: int
    reliability: str


@dataclass(slots=True)
class AngleIdea:
    id: str
    raw_signal_id: str
    raw_signal_title: str
    angle: str
    offer_link: str
    audience_pain: str
    creative_type: str
    priority: str
    rationale: str


@dataclass(slots=True)
class Headline:
    id: str
    angle_id: str
    angle_label: str
    text: str
    format: str
    length: int


@dataclass(slots=True)
class Recommendation:
    rank: int
    angle_id: str
    raw_signal_id: str
    priority: str
    why: str
    freshness_score: int
    trigger_score: int
    offer_fit_score: int


@dataclass(slots=True)
class SignalRisk:
    raw_signal_id: str
    legal_risk: str
    platform_ban_risk: str
    audience_negative_risk: str
    reputational_risk: str
    staleness_risk: str
    notes: str


@dataclass(slots=True)
class FeedbackEntry:
    report_date: str
    winners: list[str] = field(default_factory=list)
    losers: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GeoReport:
    geo_id: str
    geo_name: str
    generated_at: str
    coverage_period: str
    owner: str
    previous_report_url: str
    offer_name: str
    raw_signals: list[RawSignal] = field(default_factory=list)
    angles: list[AngleIdea] = field(default_factory=list)
    headlines: list[Headline] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    risks: list[SignalRisk] = field(default_factory=list)
    urgency_hot: list[str] = field(default_factory=list)
    urgency_later: list[str] = field(default_factory=list)
    feedback_summary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    airtable_report_id: str = ""
    airtable_report_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def dataclass_to_dict(instance: Any) -> dict[str, Any]:
    return asdict(instance)
