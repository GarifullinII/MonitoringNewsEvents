from __future__ import annotations

import tomllib
from pathlib import Path

from .models import (
    AirtableConfig,
    AirtableTableConfig,
    GeoConfig,
    LLMConfig,
    ProjectConfig,
    SourceConfig,
)


def _resolve_path(base_dir: Path, candidate: str) -> Path:
    path = Path(candidate)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _parse_source(source_data: dict, config_dir: Path) -> SourceConfig:
    source = SourceConfig(
        kind=source_data["kind"],
        name=source_data["name"],
        source_type=source_data["source_type"],
        category=source_data["category"],
        url=source_data.get("url"),
        query=source_data.get("query"),
        language=source_data.get("language", "en-US"),
        country=source_data.get("country", "US"),
        max_items=int(source_data.get("max_items", 10)),
        path=source_data.get("path"),
    )
    if source.path:
        source.path = str(_resolve_path(config_dir, source.path))
    return source


def _parse_airtable_config(payload: dict) -> AirtableConfig:
    airtable_data = payload.get("airtable", {})
    table_names = airtable_data.get("tables", {})
    table_ids = airtable_data.get("table_ids", {})

    def make_table_config(key: str, default_name: str) -> AirtableTableConfig:
        return AirtableTableConfig(
            name=table_names.get(key, default_name),
            url_table_id=table_ids.get(key, ""),
        )

    return AirtableConfig(
        enabled=bool(airtable_data.get("enabled", False)),
        api_token_env=airtable_data.get("api_token_env", "AIRTABLE_TOKEN"),
        base_id=airtable_data.get("base_id", ""),
        api_base_url=airtable_data.get("api_base_url", "https://api.airtable.com/v0"),
        timeout_seconds=int(airtable_data.get("timeout_seconds", 30)),
        report_link_field=airtable_data.get("report_link_field", ""),
        report_link_poll_attempts=int(airtable_data.get("report_link_poll_attempts", 6)),
        report_link_poll_interval_seconds=float(
            airtable_data.get("report_link_poll_interval_seconds", 2.0)
        ),
        report_record_url_template=airtable_data.get("report_record_url_template", ""),
        reports_table=make_table_config("reports", "Reports"),
        raw_signals_table=make_table_config("raw_signals", "Inforeasons"),
        angles_table=make_table_config("angles", "Angles"),
        headlines_table=make_table_config("headlines", "Headlines"),
        recommendations_table=make_table_config("recommendations", "Recommendations"),
        risks_table=make_table_config("risks", "Risks"),
    )


def load_project_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path).resolve()
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)

    config_dir = config_path.parent
    project_data = payload.get("project", {})
    llm_data = payload.get("llm", {})
    airtable_config = _parse_airtable_config(payload)

    llm_config = LLMConfig(
        enabled=bool(llm_data.get("enabled", False)),
        provider=llm_data.get("provider", "openai_responses"),
        model=llm_data.get("model", "gpt-4.1-mini"),
        api_key_env=llm_data.get("api_key_env", "OPENAI_API_KEY"),
        api_base_url=llm_data.get("api_base_url", "https://api.openai.com/v1/responses"),
        timeout_seconds=int(llm_data.get("timeout_seconds", 45)),
    )

    report_dir = _resolve_path(config_dir, project_data.get("report_dir", "outputs"))
    data_dir = _resolve_path(config_dir, project_data.get("data_dir", "data"))

    default_coverage_days = int(project_data.get("coverage_days", 7))
    default_signal_limit = int(project_data.get("signal_limit", 15))
    default_idea_limit = int(project_data.get("idea_limit", 25))
    default_headlines_per_idea = int(project_data.get("headlines_per_idea", 4))

    geos: list[GeoConfig] = []
    for geo_data in payload.get("geo", []):
        sources = [_parse_source(item, config_dir) for item in geo_data.get("source", [])]
        geos.append(
            GeoConfig(
                id=geo_data["id"],
                name=geo_data["name"],
                owner=geo_data.get("owner", "Unknown owner"),
                offer_name=geo_data["offer_name"],
                offer_description=geo_data["offer_description"],
                audience_pains=list(geo_data.get("audience_pains", [])),
                offer_hooks=list(geo_data.get("offer_hooks", [])),
                evergreen_themes=list(geo_data.get("evergreen_themes", [])),
                previous_report_url=geo_data.get("previous_report_url", ""),
                coverage_days=int(geo_data.get("coverage_days", default_coverage_days)),
                signal_limit=int(geo_data.get("signal_limit", default_signal_limit)),
                idea_limit=int(geo_data.get("idea_limit", default_idea_limit)),
                headlines_per_idea=int(
                    geo_data.get("headlines_per_idea", default_headlines_per_idea)
                ),
                report_language=geo_data.get("report_language", "ru"),
                llm_enabled=geo_data.get("llm_enabled"),
                sources=sources,
            )
        )

    return ProjectConfig(
        report_dir=report_dir,
        data_dir=data_dir,
        llm=llm_config,
        airtable=airtable_config,
        geos=geos,
    )
