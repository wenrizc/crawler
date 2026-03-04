"""Repair script for NowCoder scraped data and analysis markdown files.

This script does three things:
1) Re-fetch records with placeholder title/content from nowcoder_scraped_data.json.
2) Save fetched raw HTML for those records.
3) Rebuild markdown files whose filename contains "标题未找到" using repaired data
   and the same LLM call path used by process.py (ask_zhipu).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from parser_utils import CONTENT_NOT_FOUND, TITLE_NOT_FOUND, fetch_best_detail, is_placeholder
from process import ask_zhipu

SCRIPT_DIR = Path(__file__).resolve().parent
JSON_PATH = SCRIPT_DIR / "nowcoder_scraped_data.json"
HTML_SAVE_DIR = SCRIPT_DIR / "raw_html_repair"
ANALYSIS_DIR = SCRIPT_DIR / "interview_analysis"

HEADERS = {
    "Host": "www.nowcoder.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) "
        "Gecko/20100101 Firefox/146.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Referer": "https://www.nowcoder.com/",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def slugify(name: str, max_len: int = 80) -> str:
    """Return a filesystem-friendly file stem."""
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5 _-]", "_", name).strip()
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "Untitled"
    return cleaned[:max_len]


def safe_print(message: str) -> None:
    """Print text safely even when terminal encoding cannot represent some chars."""
    try:
        print(message)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((message + "\n").encode("utf-8", errors="backslashreplace"))


def load_data(json_path: Path) -> list[dict[str, Any]]:
    return json.loads(json_path.read_text(encoding="utf-8"))


def find_placeholder_records(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in data:
        title = item.get("title", "")
        content = item.get("content", "")
        if is_placeholder(title, TITLE_NOT_FOUND) or is_placeholder(content, CONTENT_NOT_FOUND):
            items.append(item)
    return items


def repair_json_data(data: list[dict[str, Any]]) -> dict[str, int]:
    """Repair placeholder records in JSON and save raw HTML for each repaired record."""
    session = requests.Session()
    session.headers.update(HEADERS)
    HTML_SAVE_DIR.mkdir(parents=True, exist_ok=True)

    placeholders = find_placeholder_records(data)
    print(f"[*] Placeholder records in JSON: {len(placeholders)}")

    repaired = 0
    unchanged = 0
    failed = 0
    fallback_url_used = 0

    for idx, item in enumerate(placeholders, 1):
        uuid = item.get("uuid", f"unknown-{idx}")
        detail_url = item.get("url") or f"https://www.nowcoder.com/feed/main/detail/{uuid}"
        print(f"[*] ({idx}/{len(placeholders)}) Repairing {uuid}")
        try:
            parsed = fetch_best_detail(
                session,
                detail_url,
                timeout=25,
                save_html_dir=HTML_SAVE_DIR,
                save_name=uuid,
            )
            if parsed.selected_url != detail_url:
                fallback_url_used += 1

            old_title = item.get("title", "")
            old_content = item.get("content", "")
            item["title"] = parsed.title
            item["content"] = parsed.content
            item["url"] = detail_url

            changed = (old_title != parsed.title) or (old_content != parsed.content)
            if changed:
                repaired += 1
                safe_print(f"    [+] Title: {parsed.title}")
            else:
                unchanged += 1
                print("    [=] No change after re-fetch")
        except Exception as exc:  # pylint: disable=broad-except
            failed += 1
            print(f"    [!] Failed: {exc}")

    return {
        "placeholder_total": len(placeholders),
        "repaired": repaired,
        "unchanged": unchanged,
        "failed": failed,
        "fallback_url_used": fallback_url_used,
    }


def save_data_with_backup(data: list[dict[str, Any]], json_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = json_path.with_suffix(f".{timestamp}.bak")
    shutil.copy2(json_path, backup_path)
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    print(f"[*] Backup created: {backup_path.name}")
    print(f"[*] JSON saved: {json_path.name}")
    return backup_path


def extract_uuid_from_markdown(md_text: str) -> str:
    match = re.search(r"nowcoder\.com/feed/main/detail/([a-f0-9]+)", md_text)
    return match.group(1) if match else ""


def call_llm_with_retry(api_key: str, base_url: str | None, content: str, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        result = ask_zhipu(api_key, base_url, content)
        if result and result.strip():
            return result.strip()
        if attempt < retries:
            sleep_seconds = 2 * attempt
            print(f"    [*] LLM retry in {sleep_seconds}s (attempt {attempt + 1}/{retries})")
            time.sleep(sleep_seconds)
    return None


def unique_target_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 1
    while True:
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def repair_markdown_files(
    data: list[dict[str, Any]],
    analysis_dir: Path,
    api_key: str,
    base_url: str | None,
) -> dict[str, int]:
    """Repair markdown files named '*_标题未找到.md' with repaired title/content."""
    data_by_uuid = {item.get("uuid"): item for item in data if item.get("uuid")}
    placeholder_files = sorted(analysis_dir.glob("*_标题未找到.md"))
    print(f"[*] Placeholder markdown files: {len(placeholder_files)}")

    repaired = 0
    skipped = 0
    failed = 0

    for idx, md_path in enumerate(placeholder_files, 1):
        print(f"[*] ({idx}/{len(placeholder_files)}) Repairing markdown: {md_path.name}")
        try:
            old_text = md_path.read_text(encoding="utf-8")
            uuid = extract_uuid_from_markdown(old_text)
            if not uuid:
                skipped += 1
                print("    [!] Skip: UUID not found in markdown")
                continue

            item = data_by_uuid.get(uuid)
            if not item:
                skipped += 1
                print(f"    [!] Skip: UUID not found in JSON ({uuid})")
                continue

            title = item.get("title", TITLE_NOT_FOUND).strip() or TITLE_NOT_FOUND
            content = item.get("content", CONTENT_NOT_FOUND).strip() or CONTENT_NOT_FOUND
            url = item.get("url", f"https://www.nowcoder.com/feed/main/detail/{uuid}")

            if is_placeholder(title, TITLE_NOT_FOUND) or is_placeholder(content, CONTENT_NOT_FOUND):
                skipped += 1
                print("    [!] Skip: record still has placeholder title/content")
                continue

            analysis = call_llm_with_retry(api_key, base_url, content)
            if not analysis:
                failed += 1
                print("    [!] Failed: LLM returned empty output")
                continue

            match = re.match(r"^(\d+)_", md_path.stem)
            prefix = match.group(1) if match else "000"
            new_name = f"{prefix}_{slugify(title)}.md"
            target_path = unique_target_path(analysis_dir / new_name)

            new_text = f"[查看原文]({url})\n\n{analysis}\n"
            target_path.write_text(new_text, encoding="utf-8")

            if target_path != md_path:
                md_path.unlink()

            repaired += 1
            print(f"    [+] Saved: {target_path.name}")
        except Exception as exc:  # pylint: disable=broad-except
            failed += 1
            print(f"    [!] Failed: {exc}")

    return {
        "placeholder_files": len(placeholder_files),
        "repaired": repaired,
        "skipped": skipped,
        "failed": failed,
    }


def main() -> None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None

    if not JSON_PATH.exists():
        raise FileNotFoundError(f"JSON file not found: {JSON_PATH}")
    if not ANALYSIS_DIR.exists():
        raise FileNotFoundError(f"Markdown directory not found: {ANALYSIS_DIR}")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to repair markdown via LLM.")

    data = load_data(JSON_PATH)
    json_stats = repair_json_data(data)
    save_data_with_backup(data, JSON_PATH)
    md_stats = repair_markdown_files(data, ANALYSIS_DIR, api_key, base_url)

    print("\n============= Repair Summary =============")
    print(f"JSON placeholder records: {json_stats['placeholder_total']}")
    print(f"JSON repaired: {json_stats['repaired']}")
    print(f"JSON unchanged: {json_stats['unchanged']}")
    print(f"JSON failed: {json_stats['failed']}")
    print(f"JSON fallback URL used: {json_stats['fallback_url_used']}")
    print(f"Markdown placeholder files: {md_stats['placeholder_files']}")
    print(f"Markdown repaired: {md_stats['repaired']}")
    print(f"Markdown skipped: {md_stats['skipped']}")
    print(f"Markdown failed: {md_stats['failed']}")


if __name__ == "__main__":
    main()
