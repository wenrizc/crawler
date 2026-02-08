from __future__ import annotations

"""syosetu.org 小说正文抓取脚本。

功能概述：
- 按章节页 URL 逐页抓取 HTML
- 从页面中提取 `#honbun` 元素内的正文文本（使用 BeautifulSoup）
- 将每一章保存为 `output/<novel_id>/<page:03d>.txt`

设计要点：
- 站点可能存在 Cloudflare 防护：
  - `engine=auto` 时优先使用 cloudscraper（若已安装）
  - 若先用 requests 且检测到疑似 CF block，会自动切换到 cloudscraper 再重试
- 支持断点续跑：默认若输出文件已存在则跳过，除非指定 `--overwrite`
- 输出使用 UTF-8 BOM（utf-8-sig），便于 Windows 记事本等工具识别编码
"""

import argparse
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

try:
    import cloudscraper  # type: ignore
except Exception:  # pragma: no cover
    cloudscraper = None


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


def _looks_like_cloudflare_block(resp: requests.Response) -> bool:
    """粗略判断响应是否像 Cloudflare 的拦截页。

    说明：
    - syosetu.org 有时会被 Cloudflare 防护
    - requests 访问时可能拿到 403 + “Just a moment...” 页面
    - 这里做一个启发式判断，供 auto 模式切换引擎使用
    """
    if resp.status_code != 403:
        return False
    text = (resp.text or "").lower()
    return "just a moment" in text and "cloudflare" in text


def _best_bs4_parser() -> str:
    """选择 BeautifulSoup 的解析器。

    - 若安装了 lxml，则使用更快/更健壮的 `lxml`
    - 否则回退到 Python 内置的 `html.parser`
    """
    try:
        import lxml  # noqa: F401
    except Exception:
        return "html.parser"
    return "lxml"


def extract_honbun_text(html: str) -> str:
    """从章节 HTML 中提取正文（#honbun）。

    参数：
    - html: 章节页 HTML 源码

    返回：
    - 提取到的正文文本（末尾带一个换行）
    - 若未找到 `#honbun` 或提取结果为空，返回空字符串

    细节：
    - 使用 `get_text("\n", strip=True)` 将 HTML 中的换行/段落转换为文本换行
    - 去掉首尾空行，保证输出更干净
    """
    soup = BeautifulSoup(html, _best_bs4_parser())
    honbun = soup.select_one("#honbun")
    if honbun is None:
        return ""

    text = honbun.get_text("\n", strip=True)
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return ("\n".join(lines) + "\n") if lines else ""


@dataclass(frozen=True)
class CrawlConfig:
    """抓取配置。

    字段说明：
    - novel_id: 小说 ID（用于拼接 URL、以及默认输出目录名）
    - start/end: 起止章节页编号（闭区间）
    - out_dir: 输出目录
    - sleep_seconds: 每页请求之间的基础睡眠时间（会叠加少量随机抖动）
    - timeout_seconds: 单次请求超时
    - max_retries: 单页失败重试次数
    - engine: 请求引擎：auto / requests / cloudscraper
    - overwrite: 是否覆盖已存在章节文件（默认跳过，便于断点续跑）
    """
    novel_id: int
    start: int
    end: int
    out_dir: Path
    sleep_seconds: float
    timeout_seconds: float
    max_retries: int
    engine: str  # auto | requests | cloudscraper
    overwrite: bool


def build_url(novel_id: int, page: int) -> str:
    """根据小说 ID 与章节页编号构造章节 URL。"""
    return f"https://syosetu.org/novel/{novel_id}/{page}.html"


def iter_pages(start: int, end: int) -> Iterable[int]:
    """生成要抓取的章节页编号序列（闭区间）。"""
    if end < start:
        raise ValueError("--end must be >= --start")
    return range(start, end + 1)


def make_session(engine: str) -> requests.Session:
    """根据引擎类型创建 Session。

    - requests: 直接使用 requests.Session
    - cloudscraper: 使用 cloudscraper.create_scraper（底层仍是 requests），更易绕过部分 CF
    """
    if engine == "cloudscraper":
        if cloudscraper is None:
            raise RuntimeError(
                "engine=cloudscraper 需要安装 cloudscraper：pip install cloudscraper"
            )
        sess = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        sess.headers.update(DEFAULT_HEADERS)
        return sess

    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)
    return sess


def fetch_html(
    sess: requests.Session,
    url: str,
    *,
    timeout_seconds: float,
    max_retries: int,
    sleep_seconds: float,
) -> str:
    """GET 抓取 HTML，并带有重试与退避。

    行为：
    - 200 直接返回正文
    - 429/5xx 做重试（sleep * attempt + 随机抖动）
    - 其余状态码抛出异常
    - 若响应编码缺失或为 iso-8859-1，则用 apparent_encoding 纠正
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = sess.get(url, timeout=timeout_seconds)
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in {429, 500, 502, 503, 504}:
                time.sleep(sleep_seconds * attempt + random.uniform(0, 0.5))
                continue

            resp.raise_for_status()
        except (requests.RequestException, Exception) as e:
            last_error = e
            time.sleep(sleep_seconds * attempt + random.uniform(0, 0.5))
            continue

    raise RuntimeError(f"GET 失败: {url}") from last_error


def crawl(cfg: CrawlConfig) -> int:
    """按配置抓取所有章节并落盘。

    返回：
    - 0：全部成功
    - 1：存在失败章节（会在 out_dir 写出 errors.tsv）
    """
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    engine = cfg.engine
    if engine == "auto":
        engine = "cloudscraper" if cloudscraper is not None else "requests"

    sess = make_session(engine)
    errors: list[str] = []

    for page in iter_pages(cfg.start, cfg.end):
        url = build_url(cfg.novel_id, page)
        out_path = cfg.out_dir / f"{page:03d}.txt"

        if out_path.exists() and not cfg.overwrite:
            # 断点续跑：已有输出则跳过
            print(f"[SKIP] {page} -> {out_path}")
            continue

        try:
            if cfg.engine == "auto" and engine == "requests":
                resp = sess.get(url, timeout=cfg.timeout_seconds)
                if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding
                if _looks_like_cloudflare_block(resp) and cloudscraper is not None:
                    # auto 模式下：若疑似被 Cloudflare 拦截，切换到 cloudscraper 再走统一重试逻辑
                    engine = "cloudscraper"
                    sess = make_session(engine)
                    html = fetch_html(
                        sess,
                        url,
                        timeout_seconds=cfg.timeout_seconds,
                        max_retries=cfg.max_retries,
                        sleep_seconds=cfg.sleep_seconds,
                    )
                else:
                    resp.raise_for_status()
                    html = resp.text
            else:
                html = fetch_html(
                    sess,
                    url,
                    timeout_seconds=cfg.timeout_seconds,
                    max_retries=cfg.max_retries,
                    sleep_seconds=cfg.sleep_seconds,
                )

            text = extract_honbun_text(html)
            if not text:
                raise RuntimeError("未找到 #honbun 或提取到空文本")

            # 用 UTF-8 BOM 便于 Windows 记事本 / PowerShell 自动识别编码
            out_path.write_text(text, encoding="utf-8-sig")
            print(f"[OK] {page} -> {out_path}")
        except Exception as e:
            errors.append(f"{page}\t{url}\t{e}")
            print(f"[ERR] {page} {e}", file=sys.stderr)

        time.sleep(cfg.sleep_seconds + random.uniform(0, 0.3))

    if errors:
        (cfg.out_dir / "errors.tsv").write_text(
            "\n".join(errors) + "\n", encoding="utf-8"
        )
        print(f"完成，但有 {len(errors)} 个页面失败，详情见: {cfg.out_dir / 'errors.tsv'}")
        return 1

    print("全部完成。")
    return 0


def parse_args(argv: list[str]) -> CrawlConfig:
    """解析命令行参数并返回 CrawlConfig。"""
    parser = argparse.ArgumentParser(
        description=(
            "爬取 syosetu.org 指定小说章节页，并提取 #honbun 文本。"
            "注意：syosetu.org 可能有 Cloudflare 防护，auto 模式会优先使用 cloudscraper（基于 requests）。"
        )
    )
    parser.add_argument("--novel-id", type=int, default=182965)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=445)
    parser.add_argument("--out-dir", type=Path, default=Path("output") / "182965")
    parser.add_argument("--sleep", dest="sleep_seconds", type=float, default=1.0)
    parser.add_argument("--timeout", dest="timeout_seconds", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--engine",
        choices=["auto", "requests", "cloudscraper"],
        default="auto",
        help="请求引擎：auto（默认）/ requests / cloudscraper",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的 txt 文件（默认会跳过已存在文件，便于断点续跑）",
    )
    args = parser.parse_args(argv)
    out_dir = args.out_dir
    if args.out_dir == Path("output") / "182965" and args.novel_id != 182965:
        out_dir = Path("output") / str(args.novel_id)

    return CrawlConfig(
        novel_id=args.novel_id,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
        engine=args.engine,
        overwrite=args.overwrite,
    )


def main() -> int:
    """CLI 入口。"""
    cfg = parse_args(sys.argv[1:])
    return crawl(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
