"""Process scraped interview data from NowCoder and generate Markdown reports.

The script cleans HTML, optionally calls Zhipu-AI for analysis, and writes
one Markdown file per interview record.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from dotenv import load_dotenv

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_MAP = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
}


# ----------------------------------------------------------------------------
# Zhipu AI integration
# ----------------------------------------------------------------------------

def ask_zhipu(api_key: str, base_url: Optional[str], content: str) -> Optional[str]:
    """Call Zhipu-AI to analyse interview *content* and return Markdown."""
    # 使用新版 openai SDK 客户端初始化
    if base_url:
        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = OpenAI(api_key=api_key)

    prompt = (
        "请分析以下面试记录，解析出所有的面试问题,不得遗漏问题。\n" "面试记录：\n" f"{content}"
    )

    messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": prompt}
    ]

    try:
        response = client.chat.completions.create(
            model="glm-4.7",
            messages=messages,
            temperature=1.0,
        )
        return response.choices[0].message.content
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[Zhipu-AI error] {exc}")
        return None


# ----------------------------------------------------------------------------
# Core logic
# ----------------------------------------------------------------------------

def _slugify(name: str, max_len: int = 50) -> str:
    """Return a filesystem-friendly version of *name*."""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5 _-]", "_", name)[:max_len]


def load_existing_uuids(out_dir: Path) -> set:
    """从已有的 Markdown 文件中提取已处理过的 UUID"""
    existing_uuids = set()
    if not out_dir.exists():
        return existing_uuids
    
    # 遍历所有 md 文件，从文件内容中提取 uuid
    for md_file in out_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            # 从 URL 中提取 uuid: https://www.nowcoder.com/feed/main/detail/{uuid}
            match = re.search(r"nowcoder\.com/feed/main/detail/([a-f0-9]+)", content)
            if match:
                existing_uuids.add(match.group(1))
        except Exception as e:
            print(f"[!] 读取文件 {md_file} 失败: {e}")
    
    return existing_uuids


def process_interviews(json_path: Path, out_dir: Path, api_key: str, base_url: Optional[str]) -> None:
    """Convert each interview record in *json_path* to a Markdown file."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 加载已处理过的 UUID
    existing_uuids = load_existing_uuids(out_dir)
    print(f"[*] 发现 {len(existing_uuids)} 个已处理的面经，将跳过这些记录")

    try:
        interviews: List[Dict[str, Any]] = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Error: File not found: {json_path}")
        print(f"Current working directory: {Path.cwd()}")
        print(f"Trying absolute path: {json_path.absolute()}")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file {json_path}: {e}")
        return

    total = len(interviews)
    skipped = 0
    processed = 0
    
    # 获取已有文件的最大序号，新文件从这个序号+1开始
    existing_files = list(out_dir.glob("*.md"))
    next_file_idx = len(existing_files) + 1
    
    for idx, item in enumerate(interviews, 1):
        title = item.get("title") or f"Interview_{idx}"
        url = item.get("url", "")
        content = item.get("content", "")
        uuid = item.get("uuid", "")

        # 检查是否已处理过
        if uuid and uuid in existing_uuids:
            print(f"({idx}/{total}) [跳过] {title} (已存在)")
            skipped += 1
            continue

        print(f"({idx}/{total}) [处理] {title}")
        analysis = ask_zhipu(api_key, base_url, content) if api_key else None

        md_parts = [
            f"[查看原文]({url})" if url else "无",
        ]
        if analysis:
            md_parts.extend([analysis])

        out_file = out_dir / f"{next_file_idx:03d}_{_slugify(title)}.md"
        out_file.write_text("\n\n".join(md_parts), encoding="utf-8")
        print(f"Saved: {out_file}")
        processed += 1
        next_file_idx += 1

    print(f"\n[√] 处理完成！新处理 {processed} 条，跳过 {skipped} 条已存在的记录")


# ----------------------------------------------------------------------------
# CLI entrypoint
# ----------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    # 使用当前脚本所在目录作为基础路径
    script_dir = Path(__file__).parent
    
    # 定义文件路径
    JSON_FILE = script_dir / "nowcoder_scraped_data.json"
    OUTPUT_DIR = script_dir / "interview_analysis"
    
    # 确保使用绝对路径
    print(f"Looking for JSON file at: {JSON_FILE.absolute()}")
    
    # 检查文件是否存在
    if not JSON_FILE.exists():
        print(f"Error: File not found: {JSON_FILE.absolute()}")
        print("Please make sure the JSON file exists in the same directory as the script.")
        return
    
    load_dotenv()
    API_KEY = os.getenv("OPENAI_API_KEY", "")
    BASE_URL = os.getenv("OPENAI_BASE_URL") or None

    process_interviews(JSON_FILE, OUTPUT_DIR, API_KEY, BASE_URL)


if __name__ == "__main__":
    main()