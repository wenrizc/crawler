"""NowCoder scraper.

Workflow:
1) Use Playwright to browse interview list pages and collect UUIDs.
2) Use requests to fetch detail pages and parse title/content.
3) Save merged data into nowcoder_scraped_data.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Response, sync_playwright

from parser_utils import fetch_best_detail

TARGET_URL = (
    "https://www.nowcoder.com/interview/center?entranceType=%E5%AF%BC%E8%88%AA%E6%A0%8F"
)
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_JSON_FILE = SCRIPT_DIR / "nowcoder_scraped_data.json"

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


def load_existing_records() -> tuple[set[str], list[dict[str, Any]]]:
    """Load existing records from JSON file."""
    existing_uuids: set[str] = set()
    existing_data: list[dict[str, Any]] = []

    if not OUTPUT_JSON_FILE.exists():
        return existing_uuids, existing_data

    try:
        existing_data = json.loads(OUTPUT_JSON_FILE.read_text(encoding="utf-8"))
        for item in existing_data:
            uuid = item.get("uuid")
            if uuid:
                existing_uuids.add(uuid)
        print(f"[*] Loaded {len(existing_uuids)} existing UUIDs")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[!] Failed to read existing JSON: {exc}")

    return existing_uuids, existing_data


def collect_uuids(existing_uuids: set[str], max_pages: int = 20) -> tuple[list[str], dict[str, str]]:
    """Collect new UUIDs from interview list pages with Playwright."""
    collected_uuids: list[str] = []
    cookies_for_requests: dict[str, str] = {}

    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def handle_response(response: Response) -> None:
            if "api/sparta/job-experience/experience/job/list" not in response.url:
                return
            try:
                data = response.json()
                if data.get("code") != 0:
                    return
                for item in data.get("data", {}).get("records", []):
                    uuid = item.get("momentData", {}).get("uuid")
                    if not uuid:
                        continue
                    if uuid in existing_uuids:
                        print(f"[*] Skip existing UUID: {uuid}")
                        continue
                    if uuid not in collected_uuids:
                        collected_uuids.append(uuid)
                        print(f"[+] New UUID: {uuid}")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[*] Failed to parse list API response: {exc}")

        print("============= Stage 1: Collect UUIDs =============")
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        print("[*] Page opened. Close login popup manually if it appears...")
        time.sleep(5)
        page.wait_for_load_state("networkidle")

        page.on("response", handle_response)
        print("[*] List API listener started.")

        # Trigger first list load after filters are applied manually.
        time.sleep(10)
        page.mouse.wheel(0, 1000)
        page.wait_for_load_state("networkidle")

        for page_index in range(1, max_pages + 1):
            print(f"\n--- Processing list page {page_index}/{max_pages} ---")
            page.mouse.wheel(0, 10000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            if page_index == max_pages:
                break

            try:
                next_button = page.locator("button.btn-next")
                next_button.wait_for(state="visible", timeout=5000)
                next_button.click()
                page.wait_for_load_state("networkidle")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[*] Next page unavailable, stop paging: {exc}")
                break

        page.remove_listener("response", handle_response)
        print(f"\n[✓] Stage 1 done. Collected {len(collected_uuids)} new UUIDs.")

        cookies = context.cookies()
        cookies_for_requests = {cookie["name"]: cookie["value"] for cookie in cookies}
        browser.close()
        print("[*] Browser closed.")

    return collected_uuids, cookies_for_requests


def fetch_detail_records(
    uuids: list[str],
    cookies_for_requests: dict[str, str],
) -> list[dict[str, str]]:
    """Fetch and parse detail pages by UUID."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(cookies_for_requests)

    records: list[dict[str, str]] = []
    print("\n============= Stage 2: Fetch Detail Pages =============")

    for i, uuid in enumerate(uuids, 1):
        detail_url = f"https://www.nowcoder.com/feed/main/detail/{uuid}"
        print(f"[*] ({i}/{len(uuids)}) {detail_url}")
        try:
            parsed = fetch_best_detail(session, detail_url, timeout=20)
            if parsed.selected_url != detail_url:
                print(f"    [*] Fallback URL used: {parsed.selected_url}")

            records.append(
                {
                    "uuid": uuid,
                    "title": parsed.title,
                    "content": parsed.content,
                    "url": detail_url,
                }
            )
            print(f"    [+] Title: {parsed.title}")
            time.sleep(2)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"    [!] Failed: {exc}")

    return records


def scrape() -> None:
    """Run full scraping process."""
    existing_uuids, existing_data = load_existing_records()
    new_uuids, cookies_for_requests = collect_uuids(existing_uuids=existing_uuids)

    if not new_uuids:
        print("[!] No new UUIDs collected.")
        return

    new_records = fetch_detail_records(new_uuids, cookies_for_requests)
    if not new_records:
        print("[!] No new detail records fetched.")
        return

    merged_data = new_records + existing_data
    OUTPUT_JSON_FILE.write_text(
        json.dumps(merged_data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    print(
        f"\n[✓] Done. Added {len(new_records)} records, total {len(merged_data)}. "
        f"Saved to {OUTPUT_JSON_FILE}"
    )


if __name__ == "__main__":
    scrape()

