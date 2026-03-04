"""Utilities for parsing NowCoder detail pages robustly."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

TITLE_NOT_FOUND = "\u6807\u9898\u672a\u627e\u5230"
CONTENT_NOT_FOUND = "\u5185\u5bb9\u672a\u627e\u5230"
_TITLE_SUFFIX = "_\u725b\u5ba2\u7f51"
_DESC_SUFFIX = "_\u725b\u5ba2\u7f51_\u725b\u5ba2\u5728\u624b,offer\u4e0d\u6101"


def is_placeholder(value: str, placeholder: str) -> bool:
    """Return True if *value* is empty or equals *placeholder*."""
    return not value or value.strip() == placeholder


def _trim_known_suffix(text: str, suffix: str) -> str:
    text = (text or "").strip()
    if text.endswith(suffix):
        return text[: -len(suffix)].strip()
    return text


def _clean_title(title: str) -> str:
    return _trim_known_suffix((title or "").strip(), _TITLE_SUFFIX)


def _clean_description(description: str) -> str:
    text = (description or "").replace("\xa0", " ").strip()
    text = _trim_known_suffix(text, _DESC_SUFFIX)
    text = _trim_known_suffix(text, _TITLE_SUFFIX)
    return text.strip()


def _set_query(url: str, **query_updates: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(query_updates)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def detail_url_candidates(detail_url: str) -> list[str]:
    """Return candidate URLs for the same detail page."""
    clean_url = urlunsplit((*urlsplit(detail_url)[:3], "", ""))
    return [
        clean_url,
        _set_query(clean_url, sourceSSR="dynamic"),
        _set_query(clean_url, sourceSSR="detail"),
    ]


@dataclass
class ParseResult:
    title: str
    content: str
    selected_url: str
    html: str

    def score(self) -> int:
        score = 0
        if not is_placeholder(self.title, TITLE_NOT_FOUND):
            score += 1
        if not is_placeholder(self.content, CONTENT_NOT_FOUND):
            score += 2
        if self.content.startswith("<div"):
            score += 3
        return score

    @property
    def has_structured_content(self) -> bool:
        return self.content.startswith("<div") and not is_placeholder(
            self.content, CONTENT_NOT_FOUND
        )


def parse_detail_html(html: str) -> ParseResult:
    """Parse title/content from detail page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    content = ""

    title_tag = soup.select_one(
        "h1.tw-mb-5.tw-font-medium.tw-text-size-title-lg-pure.tw-text-gray-800"
    )
    if not title_tag:
        title_tag = soup.select_one("h1[class*='text-size-title']")
    if title_tag:
        title = title_tag.get_text(" ", strip=True)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = _clean_title(og_title["content"])
    if not title and soup.title:
        title = _clean_title(soup.title.get_text(" ", strip=True))
    if not title:
        title = TITLE_NOT_FOUND

    content_tag = soup.select_one(
        "div.feed-content-text.tw-text-gray-800.tw-mb-4.tw-break-all"
    )
    if not content_tag:
        content_tag = soup.select_one("div.feed-content-text")
    if content_tag:
        content = str(content_tag)
    else:
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = ""
        if og_desc and og_desc.get("content"):
            description = og_desc["content"]
        elif meta_desc and meta_desc.get("content"):
            description = meta_desc["content"]
        if description:
            content = _clean_description(description)
    if not content:
        content = CONTENT_NOT_FOUND

    return ParseResult(
        title=title.strip() or TITLE_NOT_FOUND,
        content=content.strip() or CONTENT_NOT_FOUND,
        selected_url="",
        html=html,
    )


def fetch_best_detail(
    session: requests.Session,
    detail_url: str,
    *,
    timeout: int = 20,
    save_html_dir: Optional[Path] = None,
    save_name: Optional[str] = None,
) -> ParseResult:
    """Fetch a detail page via fallback URLs and return the best parse result."""
    best = ParseResult(
        title=TITLE_NOT_FOUND,
        content=CONTENT_NOT_FOUND,
        selected_url=detail_url,
        html="",
    )

    for candidate_url in detail_url_candidates(detail_url):
        response = session.get(candidate_url, timeout=timeout)
        response.raise_for_status()

        parsed = parse_detail_html(response.text)
        parsed.selected_url = candidate_url
        parsed.html = response.text

        if parsed.score() > best.score():
            best = parsed

        if parsed.has_structured_content and not is_placeholder(
            parsed.title, TITLE_NOT_FOUND
        ):
            break

    if save_html_dir:
        save_html_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{save_name or 'detail'}.html"
        (save_html_dir / filename).write_text(best.html, encoding="utf-8")

    return best

