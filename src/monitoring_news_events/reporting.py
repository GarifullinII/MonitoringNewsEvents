from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict

from .models import GeoReport


def _escape_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", "<br>")


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_row, separator, *body]) if body else "\n".join([header_row, separator])


def render_markdown(report: GeoReport) -> str:
    signal_by_id = {signal.id: signal for signal in report.raw_signals}
    angle_by_id = {angle.id: angle for angle in report.angles}
    headlines_grouped: dict[str, list] = defaultdict(list)
    for headline in report.headlines:
        headlines_grouped[headline.angle_id].append(headline)

    signal_rows = [
        [
            signal.id,
            signal.title,
            signal.source_name,
            signal.source_type,
            signal.published_at or "n/a",
            signal.category,
            signal.summary,
            signal.emotional_trigger,
            signal.shelf_life,
        ]
        for signal in report.raw_signals
    ]

    angle_rows = [
        [
            angle.id,
            angle.raw_signal_id,
            angle.angle,
            angle.offer_link,
            angle.audience_pain,
            angle.creative_type,
            angle.priority,
        ]
        for angle in report.angles
    ]

    headline_rows = [
        [
            headline.id,
            headline.angle_id,
            headline.text,
            headline.format,
            str(headline.length),
        ]
        for headline in report.headlines
    ]

    recommendation_lines: list[str] = []
    for recommendation in report.recommendations:
        angle = angle_by_id.get(recommendation.angle_id)
        signal = signal_by_id.get(recommendation.raw_signal_id)
        recommendation_lines.append(
            f"### #{recommendation.rank} {angle.id if angle else recommendation.angle_id} / {recommendation.priority}"
        )
        recommendation_lines.append(f"- Инфоповод: {signal.title if signal else recommendation.raw_signal_id}")
        recommendation_lines.append(f"- Почему в топе: {recommendation.why}")
        recommendation_lines.append(
            f"- Оценки: свежесть {recommendation.freshness_score}/5, триггер {recommendation.trigger_score}/5, fit {recommendation.offer_fit_score}/5"
        )
        if angle:
            recommendation_lines.append(f"- Угол: {angle.angle}")
            best_headlines = headlines_grouped.get(angle.id, [])[:3]
            if best_headlines:
                recommendation_lines.append("- Топ-3 заголовка:")
                for headline in best_headlines:
                    recommendation_lines.append(f"  - {headline.text}")

    risk_rows = [
        [
            risk.raw_signal_id,
            risk.legal_risk,
            risk.platform_ban_risk,
            risk.audience_negative_risk,
            risk.reputational_risk,
            risk.staleness_risk,
            risk.notes,
        ]
        for risk in report.risks
    ]

    feedback_lines = "\n".join(f"- {line}" for line in report.feedback_summary) if report.feedback_summary else "- Нет данных"
    notes_lines = "\n".join(f"- {line}" for line in report.notes) if report.notes else "- Без дополнительных заметок"
    recommendations_block = "\n".join(recommendation_lines) if recommendation_lines else "Нет рекомендаций"

    return f"""# Выпуск по GEO: {report.geo_name}

- GEO: {report.geo_name} (`{report.geo_id}`)
- Дата генерации: {report.generated_at}
- Покрытие новостей: {report.coverage_period}
- Ответственный тимлид: {report.owner}
- Оффер: {report.offer_name}
- Предыдущий выпуск: {report.previous_report_url or "не указан"}

## Что зашло раньше
{feedback_lines}

## Блок 1. Сырые инфоповоды
{_markdown_table(
    ["ID", "Заголовок", "Источник", "Тип источника", "Дата", "Категория", "Описание", "Триггер", "Срок"],
    signal_rows,
)}

## Блок 2. Углы и идеи
{_markdown_table(
    ["ID идеи", "Инфоповод", "Угол", "Связка с оффером", "Боль", "Креатив", "Приоритет"],
    angle_rows,
)}

## Блок 3. Заголовки
{_markdown_table(
    ["ID", "Идея", "Текст", "Формат", "Длина"],
    headline_rows,
)}

## Блок 4. Рекомендации к тесту
{recommendations_block}

## Блок 5. Риски
{_markdown_table(
    ["Инфоповод", "Юридический", "Бан платформой", "Негатив аудитории", "Репутация", "Протухание", "Комментарий"],
    risk_rows,
)}

## Блок 6. Срочность
### 🔥 Срочно
{chr(10).join(f"- {item}" for item in report.urgency_hot) if report.urgency_hot else "- Нет критичных тем"}

### ⏳ Можно позже
{chr(10).join(f"- {item}" for item in report.urgency_later) if report.urgency_later else "- Нет вечных тем"}

## Технические заметки
{notes_lines}
"""


def render_json(report: GeoReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)
