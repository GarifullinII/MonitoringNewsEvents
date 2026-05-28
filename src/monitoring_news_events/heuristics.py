from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from .models import AngleIdea, Article, FeedbackEntry, GeoConfig, Headline, RawSignal, Recommendation, SignalRisk
from .utils import normalize_text, now_utc, parse_datetime, stable_id, truncate


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "экономика": [
        "inflation",
        "price",
        "salary",
        "econom",
        "pension",
        "tariff",
        "cost of living",
        "цена",
        "зарплат",
        "пенси",
        "инфляц",
        "тариф",
        "бюджет",
    ],
    "политика": [
        "election",
        "president",
        "parliament",
        "minister",
        "government",
        "policy",
        "protest",
        "закон",
        "правитель",
        "президент",
        "министр",
        "митинг",
        "выбор",
    ],
    "соцсети": [
        "viral",
        "trend",
        "tiktok",
        "twitter",
        "x.com",
        "reddit",
        "telegram",
        "instagram",
        "youtube",
        "meme",
        "вирус",
        "тренд",
    ],
    "селеба": [
        "actor",
        "singer",
        "celebrity",
        "blogger",
        "star",
        "artist",
        "умер",
        "скончал",
        "пев",
        "акт",
        "звезд",
    ],
    "скандал": [
        "scandal",
        "corruption",
        "arrest",
        "fraud",
        "lawsuit",
        "leak",
        "controversy",
        "скандал",
        "корруп",
        "арест",
        "утечк",
        "обвин",
        "мошеннич",
    ],
    "банки-налоги": [
        "bank",
        "loan",
        "credit",
        "mortgage",
        "tax",
        "vat",
        "interest rate",
        "deposit",
        "налог",
        "банк",
        "ставк",
        "ипотек",
        "кредит",
        "вклад",
    ],
    "страхи": [
        "fear",
        "panic",
        "warning",
        "risk",
        "crime",
        "shortage",
        "blackout",
        "crisis",
        "warning",
        "страх",
        "паник",
        "риск",
        "криз",
        "дефицит",
    ],
}

TRIGGER_KEYWORDS: dict[str, list[str]] = {
    "деньги": ["salary", "income", "tax", "bank", "credit", "price", "зарплат", "доход", "банк", "налог", "цена"],
    "кризис": ["crisis", "inflation", "panic", "corruption", "raid", "shutdown", "криз", "инфляц", "паник", "скандал"],
    "возможность": ["growth", "new", "opportunity", "bonus", "launch", "record", "рост", "возмож", "шанс", "нов"],
    "страх": ["risk", "warning", "arrest", "fraud", "death", "threat", "страх", "риск", "мошеннич", "умер"],
    "доверие": ["official", "bank", "expert", "minister", "doctor", "банк", "официаль", "эксперт", "министр"],
}

SOURCE_RELIABILITY = {
    "топовое СМИ": "высокая",
    "локальный таблоид": "средняя",
    "Twitter-тренд": "низкая",
    "TikTok": "низкая",
    "Telegram-канал": "средняя",
    "форум": "низкая",
}

CREATIVE_TYPES = ["новостной", "эмоциональный", "разоблачение", "личная история"]
HEADLINE_FORMATS = ["вопрос", "шок", "цифра", "цитата", "интрига"]


def _best_match(text: str, mapping: dict[str, list[str]], fallback: str) -> str:
    best_key = fallback
    best_score = -1
    for key, keywords in mapping.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_key = key
            best_score = score
    return best_key


def _best_match_with_score(text: str, mapping: dict[str, list[str]], fallback: str) -> tuple[str, int]:
    best_key = fallback
    best_score = -1
    for key, keywords in mapping.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_key = key
            best_score = score
    return best_key, best_score


def _freshness_bucket(published_at: str) -> tuple[str, int]:
    published = parse_datetime(published_at)
    if published is None:
        return ("неделя", 1)
    age = now_utc() - published
    if age <= timedelta(days=2):
        return ("срочно 24-48ч", 3)
    if age <= timedelta(days=7):
        return ("неделя", 2)
    return ("более", 1)


def _signal_score(category: str, trigger: str, shelf_bonus: int, source_type: str, text: str) -> int:
    reliability_bonus = {"высокая": 3, "средняя": 2, "низкая": 1}.get(
        SOURCE_RELIABILITY.get(source_type, "средняя"),
        2,
    )
    category_bonus = 2 if category in {"экономика", "банки-налоги", "скандал"} else 1
    trigger_bonus = 3 if trigger in {"деньги", "кризис", "страх"} else 2
    urgency_bonus = 1 if any(word in text for word in ("urgent", "breaking", "срочно", "немедленно")) else 0
    return min(10, reliability_bonus + category_bonus + trigger_bonus + shelf_bonus + urgency_bonus)


def _select_pain(geo: GeoConfig, trigger: str, index: int) -> str:
    if geo.audience_pains:
        return geo.audience_pains[index % len(geo.audience_pains)]
    default_map = {
        "деньги": "люди боятся потерять часть дохода",
        "кризис": "люди ждут нового удара по бюджету",
        "возможность": "люди ищут окно возможностей, пока тема горячая",
        "страх": "люди пытаются защититься до того, как станет хуже",
        "доверие": "люди верят знакомому источнику и хотят понятное решение",
    }
    return default_map.get(trigger, "аудитории нужен понятный и безопасный ориентир")


def _select_offer_hook(geo: GeoConfig, index: int) -> str:
    if geo.offer_hooks:
        return geo.offer_hooks[index % len(geo.offer_hooks)]
    return geo.offer_description


def build_raw_signals(articles: list[Article], geo: GeoConfig) -> list[RawSignal]:
    candidates: list[RawSignal] = []
    for article in articles:
        text = normalize_text(f"{article.title} {article.summary}")
        category_guess, category_score = _best_match_with_score(text, CATEGORY_KEYWORDS, "экономика")
        category = category_guess if category_score > 0 else article.category_hint or category_guess
        trigger = _best_match(text, TRIGGER_KEYWORDS, "деньги")
        shelf_life, freshness_bonus = _freshness_bucket(article.published_at)
        score = _signal_score(category, trigger, freshness_bonus, article.source_type, text)
        summary = truncate(article.summary or article.title, 220)
        candidates.append(
            RawSignal(
                id=stable_id("S", f"{geo.id}|{article.id}|{category}"),
                title=article.title,
                source_url=article.url,
                source_name=article.source_name,
                source_type=article.source_type,
                published_at=article.published_at,
                category=category,
                summary=summary,
                emotional_trigger=trigger,
                shelf_life=shelf_life,
                score=score,
                reliability=SOURCE_RELIABILITY.get(article.source_type, "средняя"),
            )
        )

    sorted_candidates = sorted(candidates, key=lambda signal: (signal.score, signal.published_at), reverse=True)
    return sorted_candidates[: geo.signal_limit]


def build_evergreen_signals(geo: GeoConfig) -> list[RawSignal]:
    fallback_themes = geo.evergreen_themes or [
        "рост цен и попытка сохранить семейный бюджет",
        "банковские комиссии и поиск запасного дохода",
        "маленькие зарплаты и страх не вытянуть месяц",
    ]
    signals: list[RawSignal] = []
    for index, theme in enumerate(fallback_themes[: geo.signal_limit], start=1):
        signals.append(
            RawSignal(
                id=f"S-EVER-{index:03d}",
                title=theme.capitalize(),
                source_url="",
                source_name="Банк вечных тем",
                source_type="внутренняя база",
                published_at="",
                category="страхи",
                summary=f"Evergreen-тема для {geo.name}: {theme}. Подходит, когда свежая новостная повестка слабая.",
                emotional_trigger="страх",
                shelf_life="более",
                score=6,
                reliability="высокая",
            )
        )
    return signals


def generate_angle_ideas(raw_signals: list[RawSignal], geo: GeoConfig) -> list[AngleIdea]:
    ideas: list[AngleIdea] = []
    for signal_index, signal in enumerate(raw_signals):
        if len(ideas) >= geo.idea_limit:
            break

        pain = _select_pain(geo, signal.emotional_trigger, signal_index)
        hook = _select_offer_hook(geo, signal_index)
        topic = truncate(signal.title, 72)
        angle_texts = [
            f"Показать, что история про '{topic}' усилила тревогу людей в {geo.name}, и перевести это в разговор о защите бюджета.",
            f"Зайти через вопрос: почему после '{topic}' аудитория снова ищет понятный способ не терять деньги и держать ситуацию под контролем.",
            f"Собрать креатив как личную историю: человек увидел '{topic}' и понял, что без запасного финансового плана снова рискует остаться в минусе.",
        ]
        if signal.emotional_trigger == "возможность":
            angle_texts[1] = (
                f"Зайти через окно возможностей: пока тема '{topic}' обсуждается, люди сильнее реагируют на идеи о дополнительном доходе."
            )
            angle_texts[2] = (
                f"Сделать ход через контраст: пока одни игнорируют '{topic}', другие уже ищут спокойный и понятный способ усилить личный доход."
            )
        if signal.category in {"скандал", "политика"}:
            angle_texts[0] = (
                f"Подать '{topic}' как сигнал нестабильности системы и перекинуть внимание на личную финансовую подушку."
            )
            angle_texts[2] = (
                f"Развернуть тему '{topic}' в формат разоблачения: если система шумит и трещит, аудитория инстинктивно ищет собственный финансовый запасной выход."
            )

        for local_index, angle_text in enumerate(angle_texts, start=1):
            if len(ideas) >= geo.idea_limit:
                break
            idea_id = f"I{len(ideas) + 1:03d}"
            creative_type = CREATIVE_TYPES[(signal_index + local_index - 1) % len(CREATIVE_TYPES)]
            priority = "A" if signal.score >= 8 else "B" if signal.score >= 6 else "C"
            ideas.append(
                AngleIdea(
                    id=idea_id,
                    raw_signal_id=signal.id,
                    raw_signal_title=signal.title,
                    angle=angle_text,
                    offer_link=hook,
                    audience_pain=pain,
                    creative_type=creative_type,
                    priority=priority,
                    rationale=(
                        f"Триггер '{signal.emotional_trigger}' уже встроен в новость, а связка с оффером идет через тему: {hook}."
                    ),
                )
            )
    return ideas


def generate_headlines(angles: list[AngleIdea], geo: GeoConfig) -> list[Headline]:
    headlines: list[Headline] = []
    for index, angle in enumerate(angles, start=1):
        topic = truncate(angle.raw_signal_title, 62)
        formats = HEADLINE_FORMATS[: geo.headlines_per_idea]
        for fmt_index, fmt in enumerate(formats, start=1):
            if fmt == "вопрос":
                text = f"Почему после '{topic}' в {geo.name} снова заговорили о запасном доходе?"
            elif fmt == "шок":
                text = f"'{topic}': новость, после которой многие в {geo.name} иначе посмотрели на свои деньги"
            elif fmt == "цифра":
                text = f"3 причины, почему тема '{topic}' цепляет людей в {geo.name} сильнее обычного"
            elif fmt == "цитата":
                text = f"\"Я не хочу снова потерять деньги\": как '{topic}' бьет по доверию аудитории"
            else:
                text = f"'{topic}' обсуждают все: почему эта новость может резко поднять интерес к офферу"
            headlines.append(
                Headline(
                    id=f"H{len(headlines) + 1:03d}",
                    angle_id=angle.id,
                    angle_label=angle.angle,
                    text=text,
                    format=fmt,
                    length=len(text),
                )
            )
    return headlines


def build_recommendations(raw_signals: list[RawSignal], angles: list[AngleIdea], limit: int = 5) -> list[Recommendation]:
    signal_map = {signal.id: signal for signal in raw_signals}
    scored_angles = sorted(
        angles,
        key=lambda angle: (
            {"A": 3, "B": 2, "C": 1}.get(angle.priority, 1),
            signal_map.get(angle.raw_signal_id, RawSignal("", "", "", "", "", "", "", "", "", "", 0, "")).score,
        ),
        reverse=True,
    )

    recommendations: list[Recommendation] = []
    for rank, angle in enumerate(scored_angles[:limit], start=1):
        signal = signal_map[angle.raw_signal_id]
        freshness_score = 5 if signal.shelf_life == "срочно 24-48ч" else 4 if signal.shelf_life == "неделя" else 2
        trigger_score = 5 if signal.emotional_trigger in {"деньги", "кризис", "страх"} else 4
        offer_fit_score = 5 if angle.priority == "A" else 4 if angle.priority == "B" else 3
        why = (
            f"Свежесть: {signal.shelf_life}. Триггер: {signal.emotional_trigger}. "
            f"Связка с оффером читается прямо через боль аудитории '{angle.audience_pain}'."
        )
        recommendations.append(
            Recommendation(
                rank=rank,
                angle_id=angle.id,
                raw_signal_id=signal.id,
                priority=angle.priority,
                why=why,
                freshness_score=freshness_score,
                trigger_score=trigger_score,
                offer_fit_score=offer_fit_score,
            )
        )
    return recommendations


def build_risks(raw_signals: list[RawSignal]) -> list[SignalRisk]:
    risks: list[SignalRisk] = []
    for signal in raw_signals:
        title_text = normalize_text(signal.title)
        legal = "средний"
        platform = "средний"
        audience = "низкий"
        reputational = "средний"
        if signal.category in {"политика", "скандал", "селеба"}:
            legal = "высокий"
            platform = "высокий"
            reputational = "высокий"
        if any(token in title_text for token in ("умер", "death", "dead", "arrest", "арест")):
            audience = "высокий"
            reputational = "высокий"
        if signal.category in {"экономика", "банки-налоги"}:
            platform = "средний"
            legal = "средний"
        if signal.shelf_life == "срочно 24-48ч":
            staleness = "высокий после 48 часов"
        elif signal.shelf_life == "неделя":
            staleness = "средний через 5-7 дней"
        else:
            staleness = "низкий"
        notes = (
            "Нужна ручная редактура: не обещать доход, не выдавать рекламу за новость, "
            "избегать клеветы и недоказуемых обвинений."
        )
        risks.append(
            SignalRisk(
                raw_signal_id=signal.id,
                legal_risk=legal,
                platform_ban_risk=platform,
                audience_negative_risk=audience,
                reputational_risk=reputational,
                staleness_risk=staleness,
                notes=notes,
            )
        )
    return risks


def build_urgency(raw_signals: list[RawSignal]) -> tuple[list[str], list[str]]:
    hot: list[str] = []
    later: list[str] = []
    for signal in raw_signals:
        label = f"{signal.title} [{signal.id}]"
        if signal.shelf_life == "срочно 24-48ч":
            hot.append(label)
        else:
            later.append(label)
    return hot, later


def summarize_feedback(entries: list[FeedbackEntry], limit: int = 3) -> list[str]:
    if not entries:
        return ["История тестов пока не заполнена. После первых запусков сюда можно подтягивать победителей и провалы."]

    summary: list[str] = []
    for entry in entries[:limit]:
        winners = ", ".join(entry.winners) if entry.winners else "нет явных победителей"
        losers = ", ".join(entry.losers) if entry.losers else "без явных провалов"
        lessons = "; ".join(entry.lessons) if entry.lessons else "уроки не зафиксированы"
        summary.append(
            f"{entry.report_date}: зашло — {winners}. Не зашло — {losers}. Что учесть дальше — {lessons}."
        )
    return summary


def index_headlines_by_angle(headlines: list[Headline]) -> dict[str, list[Headline]]:
    grouped: dict[str, list[Headline]] = defaultdict(list)
    for headline in headlines:
        grouped[headline.angle_id].append(headline)
    return grouped
