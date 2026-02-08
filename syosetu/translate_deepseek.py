from __future__ import annotations

"""调用 DeepSeek 将日文 txt 批量翻译为中文，并写入新目录。

使用场景：
- 已通过 crawl_syosetu.py 抓取到章节文本（例如 output/182965/*.txt）
- 希望将每个 txt 翻译成中文，保持文件名/目录结构不变

关键特性：
- 递归遍历输入目录下的 *.txt
- 将长文本按字符数拆分为多个 chunk，逐段翻译后再拼接
- 失败自动重试（带简单退避 + 抖动），降低临时网络错误/限流影响
- 默认跳过已存在输出文件，便于断点续跑（可用 --overwrite 覆盖）

鉴权方式：
- 从环境变量读取 DEEPSEEK_API_KEY
- 若安装了 python-dotenv，会自动尝试从同目录的 .env 加载环境变量

注意：
- 本脚本使用 DeepSeek OpenAI 兼容接口：POST /v1/chat/completions
- 为了兼容 Windows 记事本，输出默认用 utf-8-sig（带 BOM）
"""

import argparse
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import requests

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None


DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class TranslateConfig:
    """翻译脚本的运行配置。"""
    in_dir: Path
    out_dir: Path
    api_base: str
    model: str
    max_chars_per_chunk: int
    sleep_seconds: float
    timeout_seconds: float
    max_retries: int
    overwrite: bool
    batch_size: int  # 并行翻译的文件数量


def _split_text_into_chunks(text: str, *, max_chars: int) -> list[str]:
    """按字符数上限将文本拆成多个 chunk。

    设计思路：
    - 以“行”为最小拼接单位（保留换行符），尽量不在一行中间硬切
    - 当缓冲区累计长度超过 max_chars 时 flush

    返回：chunk 列表（每个元素都是一个待翻译的文本片段）。
    """
    if not text.strip():
        return [text]

    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        # 将当前缓冲区内容输出为一个 chunk，并清空缓冲
        nonlocal buf, buf_len
        if buf:
            chunks.append("".join(buf))
            buf = []
            buf_len = 0

    for line in lines:
        if buf_len + len(line) > max_chars and buf:
            flush()
        buf.append(line)
        buf_len += len(line)

        if buf_len >= max_chars:
            flush()

    flush()
    return chunks


def _post_chat_completions(
    sess: requests.Session,
    api_base: str,
    api_key: str,
    *,
    model: str,
    user_text: str,
    timeout_seconds: float,
) -> str:
    """调用 DeepSeek 的 chat/completions 接口并返回模型输出文本。

    参数：
    - sess: requests.Session，复用连接减少开销
    - api_base: 例如 https://api.deepseek.com
    - api_key: 环境变量 DEEPSEEK_API_KEY
    - model: 模型名（默认 deepseek-chat）
    - user_text: 待翻译的原文（单个 chunk）
    - timeout_seconds: 请求超时

    返回：choices[0].message.content
    """
    url = api_base.rstrip("/") + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": 
"""你是专业小说文本翻译家。
任务：把用户提供的日文原文翻译为简体中文。
要求：
1) 尽量忠实原意，文风贴合原著，做到“信、达、雅”，不删减剧情信息。
2) 保留原文段落、换行、标点层级；对话行的断行也尽量保持。
3) 不要添加任何解释、注释、吐槽、设定科普；只输出译文。
4) 专有名词/人名/地名：严格按【专有名词对照表】进行统一替换（同一词在全文必须译名一致）。
   - 若原文出现片假名、汉字写法、或轻微变体（空格/中点/大小写差异），也要归并到同一个译名。
   - 对照表没有收录且明显是人名/组织名/术语时：保持原文不翻译（不要自行编译名）。
5) 色情内容描写：在不增添新设定的前提下，尽量完整、细致、具有画面感地翻译

输出格式：
- 只输出翻译后的中文正文，不要重复原文，不要输出“对照表”本身，不要输出过程说明。

【专有名词对照表（优先替换；日文/常见写法 => 简中译名）】
# 主角
ランス => 兰斯
シィル・プライン => 希露·普莱恩
# 魔王
トロス => 托洛斯
ククルククル => 克克鲁克克鲁
アベル => 阿维尔
スラル => 丝拉尔
ナイチサ => 纳伊奇萨
ジル => 姬尔
ガイ => 盖伊
来水美樹 => 来水美树
リトルプリンセス => 来水美树
ケイブリス => 凯布利斯

# 凯布利斯派相关
カミーラ => 卡米拉
ジーク => 基克
ラ・サイゼル => 拉·赛泽璐
キャサリン => 凯瑟琳
メディウサ => 美杜莎
ガルティア => 加尔提亚
ラウネア => 拉乌涅阿
タルゴ => 塔尔歌
サメザン => 沙梅赞
パイアール => 派阿尔
レッドアイ => 赤眼
レイ => 雷伊
レイ・ガットホン => 雷伊
バボラ => 巴博拉
カイト => 凯特
カクトミ・カイト => 凯特
ワーグ => 瓦古·赤
ラッシー => 拉西

# 荷妮特派相关
ホーネット => 荷妮特
ケイコ => 惠子
ラ・ハウゼル => 拉·哈泽璐
火炎書士 => 火炎术士
サテラ => 萨特拉
シーザー => 西撒
イシス => 伊西斯
アイゼル => 艾泽鲁
シルキィ => 希尔基
シルキィ・リトルレーズン => 希尔基
メガラス => 超拉斯
ノス => 诺斯
ザビエル => 查比埃尔
レキシントン => 列克星敦
アトランタ => 亚特兰大

# 无使徒魔人
ネルアポロン => 尼尔阿朴龙
ヘビーカロリー => 黑比卡洛里
ワルルポート => 瓦鲁鲁珀特
かわぞゑ => 川添
小川健太郎 => 小川健太郎
アベルト・セフティ => 阿贝鲁特·赛弗提
リズナ・ランフビット => 利兹娜·兰菲比特

# 神与系统
ルドラサウム => 路得拉萨乌姆
プランナー => 普兰纳
ローベン・パーン => 洛本·潘
ハーモニット => 哈摩尼特
光の神 => 光之神
闇の神 => 暗之神
火の神 => 火之神
水の神 => 水之神
人間管理局ALICE => 人间管理局ALICE
クェルプラン => 奎尔普兰
System => System
システム神 => System
G・O・D => G·O·D
Da Angus => Da Angus
""",
            },
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
    }

    resp = sess.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    if resp.status_code != 200:
        # 失败时截断一部分响应，避免错误信息过长
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Unexpected response: {data}") from e


def translate_text(
    sess: requests.Session,
    cfg: TranslateConfig,
    api_key: str,
    text: str,
) -> str:
    """将整段文本翻译为中文（内部会分 chunk 调用）。

    流程：
    1) 拆分 chunks
    2) 每个 chunk 调用接口翻译；失败会按 max_retries 重试
    3) 将翻译结果按顺序拼接

    注意：
    - 为了最大程度保持原文段落结构，本脚本在 chunk 拆分时保留换行符
    - 若原文以换行结尾，则尽量保持译文也以换行结尾
    """
    chunks = _split_text_into_chunks(text, max_chars=cfg.max_chars_per_chunk)
    out_parts: list[str] = []

    for idx, chunk in enumerate(chunks, start=1):
        last_error: Exception | None = None
        for attempt in range(1, cfg.max_retries + 1):
            try:
                translated = _post_chat_completions(
                    sess,
                    cfg.api_base,
                    api_key,
                    model=cfg.model,
                    user_text=chunk,
                    timeout_seconds=cfg.timeout_seconds,
                )
                out_parts.append(translated)
                break
            except Exception as e:  # noqa: BLE001
                last_error = e
                # 简单退避：sleep_seconds * attempt + 随机抖动
                sleep = cfg.sleep_seconds * attempt + random.uniform(0, 0.5)
                print(
                    f"[RETRY] chunk {idx}/{len(chunks)} attempt {attempt}/{cfg.max_retries}: {e}",
                    file=sys.stderr,
                )
                time.sleep(sleep)
        else:
            raise RuntimeError(
                f"chunk {idx}/{len(chunks)} failed after {cfg.max_retries} retries"
            ) from last_error

        time.sleep(cfg.sleep_seconds + random.uniform(0, 0.2))

    merged = "".join(out_parts)
    # 尽量保持“末尾是否有换行”这一细节，避免章节文件最后一行粘连
    if text.endswith("\n") and not merged.endswith("\n"):
        merged += "\n"
    return merged


def iter_txt_files(root: Path) -> list[Path]:
    """递归枚举 root 下所有 .txt 文件（排序后返回，便于稳定输出）。"""
    return sorted([p for p in root.rglob("*.txt") if p.is_file()])


def ensure_parent(path: Path) -> None:
    """确保目标文件的父目录存在。"""
    path.parent.mkdir(parents=True, exist_ok=True)


def translate_single_file(
    sess: requests.Session,
    cfg: TranslateConfig,
    api_key: str,
    in_path: Path,
    out_path: Path,
    file_idx: int,
    total_files: int,
    print_lock: Lock,
) -> tuple[Path, str] | None:
    """翻译单个文件。

    返回：
    - 成功：None
    - 失败：(in_path, error_message)
    """
    rel = in_path.relative_to(cfg.in_dir)

    try:
        # 优先以 utf-8-sig 读取，兼容你前面抓取脚本写的 BOM
        text = in_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # 若没有 BOM 或编码不匹配，回退到普通 utf-8
        text = in_path.read_text(encoding="utf-8")

    try:
        translated = translate_text(sess, cfg, api_key, text)
        ensure_parent(out_path)
        # 用 UTF-8 BOM 便于 Windows 记事本 / PowerShell 自动识别编码
        out_path.write_text(translated, encoding="utf-8-sig")

        with print_lock:
            print(f"[OK] {file_idx}/{total_files} {rel} -> {out_path}")
        return None
    except Exception as e:  # noqa: BLE001
        with print_lock:
            print(f"[ERR] {file_idx}/{total_files} {rel} {e}", file=sys.stderr)
        return (in_path, str(e))


def translate_dir(cfg: TranslateConfig) -> int:
    """遍历输入目录并分批并行翻译，返回进程退出码。

    返回码约定：
    - 0：全部成功
    - 1：部分失败（会输出 errors.tsv）
    - 2：未设置 DEEPSEEK_API_KEY
    """
    if load_dotenv is not None:
        # 可选：从 .env 加载环境变量（例如 DEEPSEEK_API_KEY=...）
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

    files = iter_txt_files(cfg.in_dir)
    if not files:
        print(f"未找到 txt 文件: {cfg.in_dir}", file=sys.stderr)
        return 1

    # 过滤掉已存在的文件（断点续跑）
    pending_files = []
    for i, in_path in enumerate(files, start=1):
        rel = in_path.relative_to(cfg.in_dir)
        out_path = cfg.out_dir / rel

        if out_path.exists() and not cfg.overwrite:
            print(f"[SKIP] {i}/{len(files)} {rel}")
            continue

        pending_files.append((i, in_path, out_path))

    if not pending_files:
        print("所有文件已存在，无需翻译。")
        return 0

    print(f"共 {len(pending_files)} 个文件待翻译，每批 {cfg.batch_size} 个并行处理")

    # 将文件列表分成批次
    batches = [
        pending_files[i : i + cfg.batch_size]
        for i in range(0, len(pending_files), cfg.batch_size)
    ]

    print_lock = Lock()
    errors: list[str] = []
    total_files = len(files)

    # 逐批处理
    for batch_idx, batch in enumerate(batches, start=1):
        total_batches = len(batches)
        print(f"\n开始处理第 {batch_idx}/{total_batches} 批（{len(batch)} 个文件）...")

        # 为每个线程创建独立的 Session
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {}
            for file_idx, in_path, out_path in batch:
                sess = requests.Session()
                future = executor.submit(
                    translate_single_file,
                    sess,
                    cfg,
                    api_key,
                    in_path,
                    out_path,
                    file_idx,
                    total_files,
                    print_lock,
                )
                futures[future] = (in_path, file_idx)

            # 等待本批所有任务完成
            for future in as_completed(futures):
                in_path, file_idx = futures[future]
                result = future.result()
                if result is not None:
                    rel = in_path.relative_to(cfg.in_dir)
                    errors.append(f"{rel}\t{result[1]}")

        print(f"第 {batch_idx}/{total_batches} 批完成")

    if errors:
        err_path = cfg.out_dir / "errors.tsv"
        ensure_parent(err_path)
        err_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
        print(f"\n完成，但有 {len(errors)} 个文件失败，详情见: {err_path}")
        return 1

    print("\n全部完成。")
    return 0


def parse_args(argv: list[str]) -> TranslateConfig:
    """解析命令行参数并返回 TranslateConfig。"""
    parser = argparse.ArgumentParser(
        description="遍历目录下 txt 文件，调用 DeepSeek 将日文翻译为中文，并输出到新目录。"
    )
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
        default=DEFAULT_API_BASE,
        help=f"API Base（默认：{DEFAULT_API_BASE}）",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"模型名（默认：{DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--max-chars",
        dest="max_chars_per_chunk",
        type=int,
        default=30000,
        help="单次请求的最大字符数（默认：3000）",
    )
    parser.add_argument(
        "--sleep",
        dest="sleep_seconds",
        type=float,
        default=0.8,
        help="每次请求的基础间隔秒数（默认：0.8）",
    )
    parser.add_argument(
        "--timeout",
        dest="timeout_seconds",
        type=float,
        default=60.0,
        help="单次请求超时秒数（默认：60）",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="失败重试次数（默认：3）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的输出文件（默认会跳过已存在文件，便于断点续跑）",
    )
    parser.add_argument(
        "--batch-size",
        dest="batch_size",
        type=int,
        default=5,
        help="并行翻译的文件数量（默认：5）",
    )
    args = parser.parse_args(argv)

    return TranslateConfig(
        in_dir=args.in_dir,
        out_dir=args.out_dir,
        api_base=args.api_base,
        model=args.model,
        max_chars_per_chunk=args.max_chars_per_chunk,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
        overwrite=args.overwrite,
        batch_size=args.batch_size,
    )


def main(argv: list[str]) -> int:
    """CLI 入口。"""
    cfg = parse_args(argv)
    return translate_dir(cfg)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
