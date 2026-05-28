from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from .models import FeedbackEntry, GeoConfig, LLMConfig, RawSignal


REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "angles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "raw_signal_id": {"type": "string"},
                    "angle": {"type": "string"},
                    "offer_link": {"type": "string"},
                    "audience_pain": {"type": "string"},
                    "creative_type": {"type": "string"},
                    "priority": {"type": "string", "enum": ["A", "B", "C"]},
                    "rationale": {"type": "string"},
                },
                "required": [
                    "id",
                    "raw_signal_id",
                    "angle",
                    "offer_link",
                    "audience_pain",
                    "creative_type",
                    "priority",
                    "rationale",
                ],
            },
        },
        "headlines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "angle_id": {"type": "string"},
                    "text": {"type": "string"},
                    "format": {"type": "string"},
                },
                "required": ["id", "angle_id", "text", "format"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rank": {"type": "integer"},
                    "angle_id": {"type": "string"},
                    "raw_signal_id": {"type": "string"},
                    "priority": {"type": "string", "enum": ["A", "B", "C"]},
                    "why": {"type": "string"},
                    "freshness_score": {"type": "integer"},
                    "trigger_score": {"type": "integer"},
                    "offer_fit_score": {"type": "integer"},
                },
                "required": [
                    "rank",
                    "angle_id",
                    "raw_signal_id",
                    "priority",
                    "why",
                    "freshness_score",
                    "trigger_score",
                    "offer_fit_score",
                ],
            },
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "raw_signal_id": {"type": "string"},
                    "legal_risk": {"type": "string"},
                    "platform_ban_risk": {"type": "string"},
                    "audience_negative_risk": {"type": "string"},
                    "reputational_risk": {"type": "string"},
                    "staleness_risk": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": [
                    "raw_signal_id",
                    "legal_risk",
                    "platform_ban_risk",
                    "audience_negative_risk",
                    "reputational_risk",
                    "staleness_risk",
                    "notes",
                ],
            },
        },
        "urgency": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "hot": {"type": "array", "items": {"type": "string"}},
                "later": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["hot", "later"],
        },
    },
    "required": ["angles", "headlines", "recommendations", "risks", "urgency"],
}


class OpenAIResponsesClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def is_enabled(self) -> bool:
        return self.config.enabled and bool(os.getenv(self.config.api_key_env))

    def enrich_report(
        self,
        geo: GeoConfig,
        raw_signals: list[RawSignal],
        feedback_entries: list[FeedbackEntry],
    ) -> dict[str, Any]:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Environment variable {self.config.api_key_env} is not set")

        signals_payload = [
            {
                "id": signal.id,
                "title": signal.title,
                "category": signal.category,
                "summary": signal.summary,
                "trigger": signal.emotional_trigger,
                "shelf_life": signal.shelf_life,
                "source_type": signal.source_type,
                "published_at": signal.published_at,
            }
            for signal in raw_signals
        ]
        feedback_payload = [
            {
                "report_date": entry.report_date,
                "winners": entry.winners,
                "losers": entry.losers,
                "lessons": entry.lessons,
            }
            for entry in feedback_entries[:3]
        ]

        system_prompt = (
            "Ты редактор мониторинга инфоповодов для lawful performance-маркетинга. "
            "Нужно предложить углы, заголовки, рекомендации и риски по готовому списку новостей. "
            "Не обещай гарантированный доход, не имитируй редакционные новости, не используй клевету, "
            "не подталкивай к нарушению правил платформ."
        )

        user_prompt = {
            "geo": {
                "id": geo.id,
                "name": geo.name,
                "owner": geo.owner,
                "offer_name": geo.offer_name,
                "offer_description": geo.offer_description,
                "audience_pains": geo.audience_pains,
                "offer_hooks": geo.offer_hooks,
                "idea_limit": geo.idea_limit,
                "headlines_per_idea": geo.headlines_per_idea,
            },
            "feedback": feedback_payload,
            "raw_signals": signals_payload,
            "instructions": [
                "Верни только JSON по схеме.",
                "Используй ссылки на существующие raw_signal_id.",
                "Сделай рекомендации как shortlist из топ-5 идей.",
                "Заголовки делай цепляющими, но без ложных фактов и без финансовых гарантий.",
            ],
        }

        payload = {
            "model": self.config.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(user_prompt, ensure_ascii=False)}],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "geo_report_enrichment",
                    "schema": REPORT_SCHEMA,
                    "strict": True,
                }
            },
            "max_output_tokens": 5000,
        }

        request = urllib.request.Request(
            self.config.api_base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return self._extract_structured_output(body)

    def _extract_structured_output(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(response_payload.get("output_text"), str):
            return json.loads(response_payload["output_text"])

        for item in response_payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return json.loads(content["text"])
        raise RuntimeError("OpenAI response does not contain structured output text")
