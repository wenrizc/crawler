from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from threading import Lock

import requests

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

import translate_deepseek as td


def parse_args(argv: list[str]) -> tuple[td.TranslateConfig, list[str]]:
    parser = argparse.ArgumentParser(description="重试翻译指定的 txt 文件（默认：287.txt、313.txt）。")
    parser.add_argument(
        "--in-dir",
        type=Path,
        default=Path("output") / "182965",
        help="输入目录（默认：output/182965）",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("output_zh") / "182965",
        help="输出目录（默认：output_zh/182965）",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default=td.DEFAULT_API_BASE,
    )
    parser.add_argument(
        "--model",
        type=str,
        default=td.DEFAULT_MODEL,
    )
    parser.add_argument(
        "--max-chars",
        dest="max_chars_per_chunk",
        type=int,
        default=30000,
    )
    parser.add_argument(
        "--sleep",
        dest="sleep_seconds",
        type=float,
        default=0.8,
    )
    parser.add_argument(
        "--timeout",
        dest="timeout_seconds",
        type=float,
        default=60.0,
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
    )
    parser.add_argument(
        "files",
        nargs="*",
        default=["287.txt", "313.txt"],
        help="要重试的文件名（相对于 in-dir），例如：287.txt 313.txt",
    )

    args = parser.parse_args(argv)

    cfg = td.TranslateConfig(
        in_dir=args.in_dir,
        out_dir=args.out_dir,
        api_base=args.api_base,
        model=args.model,
        max_chars_per_chunk=args.max_chars_per_chunk,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
        overwrite=True,
        batch_size=1,
    )
    return cfg, list(args.files)


def main(argv: list[str]) -> int:
    cfg, files = parse_args(argv)

    if load_dotenv is not None:
        load_dotenv()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(
            "DEEPSEEK_API_KEY 未设置。请先设置环境变量，例如：\n"
            "  PowerShell:  $env:DEEPSEEK_API_KEY=\"你的key\"\n"
            "  CMD:        set DEEPSEEK_API_KEY=你的key\n",
            file=sys.stderr,
        )
        return 2

    if not files:
        print("未指定任何文件。", file=sys.stderr)
        return 1

    print_lock = Lock()
    errors: list[str] = []

    total_files = len(files)
    for idx, rel_str in enumerate(files, start=1):
        rel = Path(rel_str)
        in_path = cfg.in_dir / rel
        out_path = cfg.out_dir / rel

        if not in_path.exists():
            msg = f"输入文件不存在: {in_path}"
            with print_lock:
                print(f"[ERR] {idx}/{total_files} {rel} {msg}", file=sys.stderr)
            errors.append(f"{rel}\t{msg}")
            continue

        sess = requests.Session()
        result = td.translate_single_file(
            sess,
            cfg,
            api_key,
            in_path,
            out_path,
            idx,
            total_files,
            print_lock,
        )
        if result is not None:
            errors.append(f"{rel}\t{result[1]}")

    if errors:
        err_path = cfg.out_dir / "errors_retry.tsv"
        td.ensure_parent(err_path)
        err_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
        print(f"\n完成，但有 {len(errors)} 个文件失败，详情见: {err_path}")
        return 1

    print("\n全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
