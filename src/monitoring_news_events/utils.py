from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        parsed = parsedate_to_datetime(candidate)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass

    normalized = candidate.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_text(value: str) -> str:
    return compact_whitespace(value).lower()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "item"


def stable_id(prefix: str, value: str, width: int = 6) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:width].upper()
    return f"{prefix}{digest}"


def isoformat_utc(value: datetime | None) -> str:
    target = value or now_utc()
    return target.astimezone(UTC).replace(microsecond=0).isoformat()


def truncate(value: str, limit: int) -> str:
    compacted = compact_whitespace(value)
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: limit - 1].rstrip()}…"
