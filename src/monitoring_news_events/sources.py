from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import Article, GeoConfig, SourceConfig
from .utils import compact_whitespace, normalize_text, parse_datetime, stable_id


USER_AGENT = "MonitoringNewsEvents/0.1 (+https://local.run)"


def build_google_news_rss_url(query: str, language: str, country: str) -> str:
    language_short = language.split("-")[0]
    encoded_query = urllib.parse.quote_plus(query)
    return (
        "https://news.google.com/rss/search"
        f"?q={encoded_query}&hl={language}&gl={country}&ceid={country}:{language_short}"
    )


def _extract_text(element: ET.Element | None, tag_names: tuple[str, ...]) -> str:
    if element is None:
        return ""
    for candidate in tag_names:
        found = element.find(candidate)
        if found is not None and found.text:
            return compact_whitespace(found.text)
    return ""


def _extract_link_from_entry(entry: ET.Element) -> str:
    link_node = entry.find("{http://www.w3.org/2005/Atom}link")
    if link_node is None:
        link_node = entry.find("link")
    if link_node is None:
        return ""
    return link_node.attrib.get("href", "") or compact_whitespace(link_node.text or "")


def parse_rss_items(source: SourceConfig, xml_payload: bytes) -> list[Article]:
    root = ET.fromstring(xml_payload)
    articles: list[Article] = []

    if root.tag.endswith("rss"):
        channel = root.find("channel")
        items = [] if channel is None else channel.findall("item")
        for index, item in enumerate(items[: source.max_items]):
            title = _extract_text(item, ("title",))
            link = _extract_text(item, ("link",))
            summary = _extract_text(item, ("description",))
            published = _extract_text(item, ("pubDate", "published", "updated"))
            if not title or not link:
                continue
            parsed_date = parse_datetime(published)
            articles.append(
                Article(
                    id=stable_id("A", f"{title}|{link}|{index}"),
                    title=title,
                    url=link,
                    source_name=source.name,
                    source_type=source.source_type,
                    category_hint=source.category,
                    published_at=parsed_date.isoformat() if parsed_date else "",
                    summary=summary,
                )
            )
        return articles

    atom_namespace = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(f"{atom_namespace}entry") or root.findall("entry")
    for index, entry in enumerate(entries[: source.max_items]):
        title = _extract_text(entry, (f"{atom_namespace}title", "title"))
        summary = _extract_text(entry, (f"{atom_namespace}summary", f"{atom_namespace}content", "summary"))
        published = _extract_text(
            entry,
            (f"{atom_namespace}published", f"{atom_namespace}updated", "published", "updated"),
        )
        link = _extract_link_from_entry(entry)
        if not title or not link:
            continue
        parsed_date = parse_datetime(published)
        articles.append(
            Article(
                id=stable_id("A", f"{title}|{link}|{index}"),
                title=title,
                url=link,
                source_name=source.name,
                source_type=source.source_type,
                category_hint=source.category,
                published_at=parsed_date.isoformat() if parsed_date else "",
                summary=summary,
            )
        )
    return articles


def _fetch_remote_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def fetch_source_articles(source: SourceConfig) -> list[Article]:
    if source.kind == "local_rss":
        if not source.path:
            raise ValueError(f"Source '{source.name}' requires 'path'")
        return parse_rss_items(source, Path(source.path).read_bytes())

    if source.kind == "google_news_rss":
        if not source.query:
            raise ValueError(f"Source '{source.name}' requires 'query'")
        url = build_google_news_rss_url(source.query, source.language, source.country)
        return parse_rss_items(source, _fetch_remote_bytes(url))

    if source.kind == "rss":
        if not source.url:
            raise ValueError(f"Source '{source.name}' requires 'url'")
        return parse_rss_items(source, _fetch_remote_bytes(source.url))

    raise ValueError(f"Unsupported source kind: {source.kind}")


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    unique: list[Article] = []
    seen: set[str] = set()
    for article in articles:
        key = normalize_text(f"{article.title}|{article.url}")
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def fetch_geo_articles(geo: GeoConfig) -> list[Article]:
    collected: list[Article] = []
    for source in geo.sources:
        try:
            collected.extend(fetch_source_articles(source))
        except Exception:
            continue

    unique = deduplicate_articles(collected)
    return sorted(unique, key=lambda item: item.published_at, reverse=True)
