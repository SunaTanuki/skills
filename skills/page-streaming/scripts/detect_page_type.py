#!/usr/bin/env python3
"""
Page type detection: Determines content_delivery_type + behavior to decide fetching strategy.

The goal is not to guess the specific technology name, but to determine the crawler strategy (doc §10).
Judgment criteria:
  1. Does the initial HTML have the main content?
  2. How much does the DOM expand after JS execution?
  3. Is there a scroll increment? (This script determines 1 and 2)

Since the majority of modern web sites are SPAs (~80-90%), if undetectable, lean towards spa_csr (doc §3).
cf. docs/page-type-detection.md
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds (Auxiliary. Mainly rely on relative comparisons, do not rely too much on absolute values)
# ---------------------------------------------------------------------------
SHELL_TEXT_THRESHOLD = 300
RICH_TEXT_THRESHOLD = 2000
SPA_RATIO_THRESHOLD = 0.5
HYBRID_RATIO_THRESHOLD = 0.85
CHUNK_SCRIPT_THRESHOLD = 3

# ---------------------------------------------------------------------------
# Crawler Strategy Mapping (doc §6)
# ---------------------------------------------------------------------------
STRATEGY_MAP: dict[str, str] = {
    "static_or_ssr": "curl",
    "hybrid": "Playwright DOM (save after hydration)",
    "spa_csr": "Playwright wait + DOM capture",
}


# ---------------------------------------------------------------------------
# HTML Fetching
# ---------------------------------------------------------------------------
def _fetch_url_curl(url: str, timeout: int = 15) -> str:
    """Fetch HTML using curl. Succeeds on more sites than urllib."""
    result = subprocess.run(
        [
            "curl", "-sL",
            "--max-time", str(timeout),
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr[:200]}")
    return result.stdout


def _html_to_text(html: str) -> str:
    """Remove scripts and styles from HTML, and extract visible text."""
    s = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    s = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# HTML Analysis
# ---------------------------------------------------------------------------
def analyze_html(html: str) -> dict:
    """Collect clues for judgment from the initial HTML."""
    text = _html_to_text(html)

    _ROOT_ID_PATTERN = r'(?:root|app|react-root|__nuxt|__next)'

    has_empty_root = bool(re.search(
        rf'<div\s+id=["\']{ _ROOT_ID_PATTERN}["\']>\s*</div>',
        html, re.IGNORECASE,
    ))

    return {
        "body_text_len": len(text),
        "html_len": len(html),
        "has_empty_root": has_empty_root,
        "has_nuxt": bool(re.search(r'id=["\']__nuxt["\']', html)),
        "has_root_app": bool(re.search(rf'id=["\']{ _ROOT_ID_PATTERN}["\']', html)),
        "has_next_data": "__NEXT_DATA__" in html,
        "data_server_rendered": (
            'data-server-rendered="true"' in html
            or "data-server-rendered='true'" in html
        ),
        "script_chunk_count": len(re.findall(
            r'<script[^>]+src=["\'][^"\']*(?:chunk|entry|app|bundle|vendor|main)[^"\']*\.js',
            html, re.I,
        )),
        "placeholder_count": len(re.findall(
            r"該当\s*件数?\s*[：:]\s*[-–—]\s*件|[-–—]\s*件",
            text,
        )),
        "has_pagination": bool(re.search(
            r'class=["\'][^"\']*pagination[^"\']*["\']'
            r'|aria-label=["\']pagination["\']',
            html, re.I,
        )),
    }


# ---------------------------------------------------------------------------
# Judgment
# ---------------------------------------------------------------------------
def classify(
    clues: dict,
    playwright_text_len: int | None = None,
) -> tuple[str, list[str], list[str]]:
    """
    content_delivery_type と behavior (補助属性) をJudgmentする。

    Most important criterion: Can the main content be seen without JS? (doc §2.1)
    Lean towards spa_csr when indistinguishable (doc §3: SPAs are ~80-90%)

    Returns: (content_type, reasons, behaviors)
    """
    reasons: list[str] = []
    behaviors: list[str] = []
    score_static = 0
    score_spa = 0

    body_len = clues["body_text_len"]

    # --- 1) Shell detection (highest priority: doc §2.2) ---
    if clues["has_empty_root"] and body_len < SHELL_TEXT_THRESHOLD:
        reasons.append(f"Initial HTML is only a shell (empty root element + text {body_len} chars)")
        _detect_behaviors(clues, behaviors)
        return "spa_csr", reasons, behaviors

    # --- 2) curl vs Playwright text length ratio (Main: doc §2.2 / §4 step4) ---
    if playwright_text_len is not None and playwright_text_len > 0:
        ratio = body_len / playwright_text_len
        if ratio < SPA_RATIO_THRESHOLD:
            score_spa += 3
            reasons.append(
                f"curl/Playwright text ratio = {ratio:.2f}"
                f" (< {SPA_RATIO_THRESHOLD}) -> dependent on JS"
            )
        elif ratio < HYBRID_RATIO_THRESHOLD:
            score_spa += 1
            score_static += 1
            reasons.append(
                f"curl/Playwright text ratio = {ratio:.2f} -> supplemented by JS (hybrid candidate)"
            )
        else:
            score_static += 2
            reasons.append(
                f"curl/Playwright text amounts are similar (ratio {ratio:.2f}) -> leaning towards static_or_ssr"
            )

    # --- 3) Body text length ---
    if body_len >= RICH_TEXT_THRESHOLD:
        score_static += 2
        reasons.append(f"Rich body text ({body_len} chars) -> has main content")
    elif body_len >= SHELL_TEXT_THRESHOLD:
        score_static += 1
        reasons.append(f"Has body text ({body_len} chars)")
    else:
        score_spa += 2
        reasons.append(f"Little body text ({body_len} chars) -> possible shell")

    # --- 4) framework hints (Auxiliary: doc §2.2) ---
    if clues["has_nuxt"]:
        reasons.append("framework hint: Nuxt (SSR/CSR/hybrid are all possible)")
        if clues["placeholder_count"] > 0:
            score_spa += 2
            reasons.append("Nuxt + placeholders -> this page leans towards CSR")

    if clues["has_root_app"] and body_len < RICH_TEXT_THRESHOLD:
        score_spa += 1
        reasons.append("id=\"app\"/\"root\" + little text content")

    if clues["has_next_data"]:
        score_static += 1
        reasons.append("framework hint: __NEXT_DATA__ (Next.js SSR)")

    if clues["data_server_rendered"]:
        score_static += 1
        reasons.append("framework hint: data-server-rendered")

    # --- 5) JS bundle amount ---
    if clues["script_chunk_count"] >= CHUNK_SCRIPT_THRESHOLD:
        score_spa += 1
        reasons.append(f"Many JS chunks/bundles ({clues['script_chunk_count']} 本)")

    # --- 6) Placeholders ---
    if clues["placeholder_count"] > 0 and not clues["has_nuxt"]:
        score_spa += 1
        reasons.append("Has count placeholders -> list is fetched via JS")

    # --- behavior estimation (doc §1.2) ---
    _detect_behaviors(clues, behaviors)

    # --- 最終Judgment ---
    has_ssr_marker = clues["has_next_data"] or clues["data_server_rendered"]
    has_rich_body = body_len >= RICH_TEXT_THRESHOLD

    # hybrid: SSR marker present + strong SPA indications
    if has_ssr_marker and score_spa > score_static:
        return "hybrid", reasons, behaviors

    # hybrid: rich initial content + many JS chunks (SSR + hydration)
    if has_rich_body and clues["script_chunk_count"] >= CHUNK_SCRIPT_THRESHOLD:
        reasons.append("Has initial content + many JS bundles -> hybrid (SSR + hydration)")
        return "hybrid", reasons, behaviors

    if score_static > score_spa:
        return "static_or_ssr", reasons, behaviors

    # SPAs are the majority (doc §3) -> tie or less defaults to spa_csr
    return "spa_csr", reasons, behaviors


def _detect_behaviors(clues: dict, behaviors: list[str]) -> None:
    """Estimates auxiliary attributes (behavior)."""
    if clues["placeholder_count"] > 0 or clues.get("has_empty_root"):
        if "infinite_scroll" not in behaviors:
            behaviors.append("infinite_scroll")
    if clues["has_pagination"]:
        if "pagination" not in behaviors:
            behaviors.append("pagination")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Page Type Detection: content_delivery_type + behavior (for fetching strategy)",
    )
    parser.add_argument("--url", type=str, help="Judgmentしたい URL (curl で取得)")
    parser.add_argument("--curl-html", type=str, metavar="PATH",
                        help="Path to existing curl fetched HTML file")
    parser.add_argument("--playwright-json", type=str, metavar="PATH",
                        help="Path to page_001.json fetched by Playwright (improves accuracy through relative comparison if present)")
    parser.add_argument("--timeout", type=int, default=15, help="URL fetch timeout in seconds")
    args = parser.parse_args()

    # --- HTML Fetching ---
    if args.curl_html:
        path = Path(args.curl_html)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        html = path.read_text(encoding="utf-8", errors="replace")
    elif args.url:
        try:
            html = _fetch_url_curl(args.url, timeout=args.timeout)
        except Exception as e:
            print(f"Error fetching URL: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.error("Either --url or --curl-html must be specified")

    # --- Playwright comparison data (optional) ---
    # Meta-information (page_0NN.json) output by page_streamer has text_length at the root. For compatibility, also refers to text of items (snippets).
    playwright_text_len = None
    if args.playwright_json and Path(args.playwright_json).exists():
        try:
            with open(args.playwright_json) as f:
                data = json.load(f)
            if isinstance(data.get("text_length"), int):
                playwright_text_len = data["text_length"]
            else:
                items = data.get("items") or []
                if items and isinstance(items[0].get("text"), str):
                    playwright_text_len = len(items[0]["text"])
        except (json.JSONDecodeError, KeyError):
            pass

    # --- Judgment ---
    clues = analyze_html(html)
    content_type, reasons, behaviors = classify(clues, playwright_text_len)

    # --- 出力 ---
    print("## Page Type Detection Result\n")
    print(f"**content_delivery_type**: `{content_type}`")
    if behaviors:
        print(f"**behavior**: {', '.join(f'`{b}`' for b in behaviors)}")
    if playwright_text_len is not None:
        print(f"  curl: {clues['body_text_len']} chars / Playwright: {playwright_text_len} chars")
    else:
        print(f"  body テキスト: {clues['body_text_len']} chars")

    print(f"\n**crawler strategy**: {STRATEGY_MAP.get(content_type, 'Playwright')}")
    if "infinite_scroll" in behaviors:
        print("  + scroll capture (fetch scroll increments)")
    if "pagination" in behaviors:
        print("  + URL crawl (pagination)")

    print("\n**Judgment理由**:")
    for r in reasons:
        print(f"  - {r}")


if __name__ == "__main__":
    main()

