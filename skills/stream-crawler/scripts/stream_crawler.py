#!/usr/bin/env python3
"""stream-crawler: List page fetching prioritizing success rate."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from detect_page_type import analyze_html, classify

DEFAULT_LOAD_WAIT_MS = 2500
DEFAULT_VIEWPORT_WIDTH = 1440
DEFAULT_VIEWPORT_HEIGHT = 5000
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_STEPS_PER_PAGE = 3
DEFAULT_COARSE_MARGIN_PX = 300
DEFAULT_FINE_STEP_PX = 100
DEFAULT_STEP_WAIT_MS = 300
DEFAULT_SETTLE_TIMEOUT_MS = 2400
DEFAULT_CURL_TIMEOUT_SEC = 15
TEXT_GROWTH_THRESHOLD = 120
NODE_GROWTH_THRESHOLD = 5
SCROLL_GROWTH_THRESHOLD = 80
TAIL_SAMPLE_CHARS = 1500

PICK_SCROLLER_JS = r"""
() => {
  const vw = Math.max(1, window.innerWidth || 1);
  const vh = Math.max(1, window.innerHeight || 1);
  const doc = document.scrollingElement || document.documentElement || document.body;
  const main = document.querySelector("main") || document.querySelector('[role="main"]') || document.body;

  const isScrollable = (el) => {
    if (!el) return false;
    const range = (el.scrollHeight || 0) - (el.clientHeight || 0);
    if (range <= 200) return false;
    if ((el.clientHeight || 0) <= 120) return false;
    const before = el.scrollTop || 0;
    try { el.scrollTop = before + 1; } catch { return false; }
    const after = el.scrollTop || 0;
    el.scrollTop = before;
    return after !== before;
  };

  const windowScrollable = () => {
    const maxScroll = Math.max(0, (doc.scrollHeight || 0) - (window.innerHeight || doc.clientHeight || 0));
    if (maxScroll <= 0) return false;
    const before = window.scrollY || doc.scrollTop || 0;
    window.scrollTo(0, Math.min(before + 1, maxScroll));
    const after = window.scrollY || doc.scrollTop || 0;
    window.scrollTo(0, before);
    return after !== before;
  };

  const viewportCoverage = (el) => {
    try {
      const r = el.getBoundingClientRect();
      const w = Math.max(0, Math.min(r.width, vw));
      const h = Math.max(0, Math.min(r.height, vh));
      return (w * h) / (vw * vh);
    } catch {
      return 0;
    }
  };

  const score = (el, canWindowScroll) => {
    const range = Math.max(0, (el.scrollHeight || 0) - (el.clientHeight || 0));
    const coverage = viewportCoverage(el);
    const isDoc = el === doc;
    let s = Math.log1p(range);
    s += coverage * 6;
    s += Math.min(1, (el.clientHeight || 0) / vh) * 3;
    if (isDoc) s += canWindowScroll ? 5 : 1;
    if (!isDoc && coverage < 0.45) s -= 2.5;
    return { score: s, isDoc };
  };

  const canWindowScroll = windowScrollable();
  const candidates = [];
  for (const el of main.querySelectorAll("*")) {
    if (isScrollable(el)) candidates.push(el);
  }
  if (doc) candidates.push(doc);

  const uniq = [];
  const seen = new Set();
  for (const el of candidates) {
    if (el && !seen.has(el)) {
      seen.add(el);
      uniq.push(el);
    }
  }

  if (uniq.length === 0) {
    return { kind: "window", canWindowScroll };
  }

  const scored = uniq.map((el) => ({ el, ...score(el, canWindowScroll) })).sort((a, b) => b.score - a.score);
  if (scored[0].isDoc) return { kind: "window", canWindowScroll };
  return { kind: "element", canWindowScroll };
}
"""


def _session_path(session_dir: str) -> Path:
    return Path(session_dir).resolve()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _log(session_path: Path, message: str) -> None:
    log_file = session_path / "logs" / "crawler.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as handle:
        handle.write(f"[{_now_iso()}] {message}\n")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:50000]


def _fetch_url_curl(url: str, timeout_sec: int = DEFAULT_CURL_TIMEOUT_SEC, ignore_https_errors: bool = False) -> str:
    cmd = [
        "curl",
        "-sL",
        "--max-time",
        str(timeout_sec),
        "-H",
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    ]
    if ignore_https_errors:
        cmd.append("-k")
    cmd.append(url)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec + 5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr[:200]}")
    return result.stdout


async def _inspect_view(page) -> dict:
    js = f"""
    () => {{
      const pickScroller = __PICK_SCROLLER__;
      const doc = document.scrollingElement || document.documentElement || document.body;
      const main = document.querySelector("main") || document.querySelector('[role="main"]') || document.body;
      const kind = pickScroller().kind;
      const scrollEl = kind === "window" ? doc : (() => {{
        const candidates = [];
        const isScrollable = (el) => {{
          if (!el) return false;
          if (((el.scrollHeight || 0) - (el.clientHeight || 0)) <= 200) return false;
          if ((el.clientHeight || 0) <= 120) return false;
          const before = el.scrollTop || 0;
          try {{ el.scrollTop = before + 1; }} catch {{ return false; }}
          const after = el.scrollTop || 0;
          el.scrollTop = before;
          return after !== before;
        }};
        for (const el of main.querySelectorAll("*")) {{
          if (isScrollable(el)) candidates.push(el);
        }}
        candidates.sort((a, b) => ((b.scrollHeight || 0) - (b.clientHeight || 0)) - ((a.scrollHeight || 0) - (a.clientHeight || 0)));
        return candidates[0] || doc;
      }})();
      const text = main ? (main.innerText || "") : "";
      const tail = text.slice(-{TAIL_SAMPLE_CHARS});
      const scroll = kind === "window"
        ? {{
            kind,
            position: window.scrollY || doc.scrollTop || 0,
            max_position: Math.max(0, (doc.scrollHeight || 0) - (window.innerHeight || doc.clientHeight || 0)),
            client_height: window.innerHeight || doc.clientHeight || 0,
            scroll_height: doc.scrollHeight || 0,
          }}
        : {{
            kind,
            position: scrollEl.scrollTop || 0,
            max_position: Math.max(0, (scrollEl.scrollHeight || 0) - (scrollEl.clientHeight || 0)),
            client_height: scrollEl.clientHeight || 0,
            scroll_height: scrollEl.scrollHeight || 0,
          }};
      return {{
        scroll,
        observation: {{
          text_len: text.length,
          node_count: main ? main.querySelectorAll("*").length : document.querySelectorAll("*").length,
          tail_text: tail,
        }},
      }};
    }}
    """
    payload = await page.evaluate(js.replace("__PICK_SCROLLER__", PICK_SCROLLER_JS))
    tail_text = payload["observation"].pop("tail_text", "") or ""
    payload["observation"]["tail_hash"] = _sha1(tail_text)
    payload["observation"]["tail_text_sample"] = tail_text[-300:]
    return payload


def _state_signature(state: dict) -> tuple[int, int, int, str]:
    return (
        int(state["scroll"]["scroll_height"]),
        int(state["observation"]["text_len"]),
        int(state["observation"]["node_count"]),
        str(state["observation"].get("tail_hash") or ""),
    )


async def _wait_until_growth_stops(page, poll_ms: int, timeout_ms: int) -> tuple[dict, int]:
    state = await _inspect_view(page)
    signature = _state_signature(state)
    polls = 0
    deadline = time.monotonic() + (timeout_ms / 1000.0)

    while time.monotonic() < deadline:
        await page.wait_for_timeout(poll_ms)
        current = await _inspect_view(page)
        polls += 1
        current_signature = _state_signature(current)
        if current_signature == signature:
            return current, polls
        state = current
        signature = current_signature

    return state, polls


async def _scroll(page, *, coarse_margin_px: int | None = None, fine_step_px: int | None = None) -> dict:
    mode = "coarse" if coarse_margin_px is not None else "fine"
    amount = coarse_margin_px if coarse_margin_px is not None else fine_step_px
    assert amount is not None
    js = """
    ({ mode, amount }) => {
      const pickScroller = __PICK_SCROLLER__;
      const pick = pickScroller();
      const doc = document.scrollingElement || document.documentElement || document.body;
      const main = document.querySelector("main") || document.querySelector('[role="main"]') || document.body;
      const pickElement = () => {
        const candidates = [];
        const isScrollable = (el) => {
          if (!el) return false;
          if (((el.scrollHeight || 0) - (el.clientHeight || 0)) <= 200) return false;
          if ((el.clientHeight || 0) <= 120) return false;
          const before = el.scrollTop || 0;
          try { el.scrollTop = before + 1; } catch { return false; }
          const after = el.scrollTop || 0;
          el.scrollTop = before;
          return after !== before;
        };
        for (const el of main.querySelectorAll("*")) {
          if (isScrollable(el)) candidates.push(el);
        }
        candidates.sort((a, b) => ((b.scrollHeight || 0) - (b.clientHeight || 0)) - ((a.scrollHeight || 0) - (a.clientHeight || 0)));
        return candidates[0] || doc;
      };
      const useWindow = pick.kind === "window";
      const el = useWindow ? doc : pickElement();
      const before = useWindow ? (window.scrollY || doc.scrollTop || 0) : (el.scrollTop || 0);
      const maxScroll = useWindow
        ? Math.max(0, (doc.scrollHeight || 0) - (window.innerHeight || doc.clientHeight || 0))
        : Math.max(0, (el.scrollHeight || 0) - (el.clientHeight || 0));
      let target = before;
      if (mode === "coarse") {
        target = Math.max(before, Math.max(0, maxScroll - amount));
      } else {
        target = Math.min(maxScroll, before + amount);
      }
      if (useWindow) {
        window.scrollTo(0, target);
      } else {
        el.scrollTop = target;
      }
      const after = useWindow ? (window.scrollY || doc.scrollTop || 0) : (el.scrollTop || 0);
      return { kind: useWindow ? "window" : "element", before, after, moved: after > before, max_scroll: maxScroll };
    }
    """
    result = await page.evaluate(js.replace("__PICK_SCROLLER__", PICK_SCROLLER_JS), {"mode": mode, "amount": amount})
    if mode == "fine" and result.get("kind") == "window":
        try:
            await page.mouse.wheel(0, amount)
        except Exception:
            pass
    return result


def _has_new_content(previous: dict, current: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    scroll_growth = current["scroll"]["scroll_height"] - previous["scroll"]["scroll_height"]
    if scroll_growth >= SCROLL_GROWTH_THRESHOLD:
        reasons.append(f"scroll_height +{scroll_growth}")

    text_growth = current["observation"]["text_len"] - previous["observation"]["text_len"]
    if text_growth >= TEXT_GROWTH_THRESHOLD:
        reasons.append(f"text_len +{text_growth}")

    node_growth = current["observation"]["node_count"] - previous["observation"]["node_count"]
    if node_growth >= NODE_GROWTH_THRESHOLD:
        reasons.append(f"node_count +{node_growth}")

    prev_tail = previous["observation"].get("tail_hash")
    curr_tail = current["observation"].get("tail_hash")
    position_growth = current["scroll"]["position"] - previous["scroll"]["position"]
    if curr_tail and prev_tail and curr_tail != prev_tail and position_growth > 0:
        reasons.append("tail_hash changed")

    return bool(reasons), reasons


async def _capture_main(page) -> tuple[str, str]:
    html = await page.content()
    js = """
    () => {
      const main = document.querySelector("main") || document.querySelector('[role="main"]') || document.body;
      return {
        text: main ? (main.innerText || "") : "",
      };
    }
    """
    try:
        result = await page.evaluate(js)
        text = (result.get("text") or "").strip()[:50000]
        if text:
            return html, text
    except Exception:
        pass
    return html, _html_to_text(html)


async def _save_snapshot(page, session_path: Path, page_index: int, page_url: str, state: dict, trigger: dict) -> Path:
    html, text = await _capture_main(page)
    pages_dir = session_path / "pages"
    stem = f"page_{page_index:04d}"
    html_path = pages_dir / f"{stem}.html"
    text_path = pages_dir / f"{stem}.txt"
    json_path = pages_dir / f"{stem}.json"

    html_path.write_text(html, encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    _write_json(
        json_path,
        {
            "page_index": page_index,
            "url": page_url,
            "captured_at": _now_iso(),
            "scroll": state["scroll"],
            "observation": state["observation"],
            "trigger": trigger,
            "snippets": [line for line in text.splitlines()[:5] if line.strip()][:5],
            "output_files": {"raw_html": str(html_path), "all_text": str(text_path)},
            "has_more_hint": True,
        },
    )
    return json_path


def _mark_terminal(json_path: Path) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["has_more_hint"] = False
    _write_json(json_path, payload)


async def _run_init(page, init_script: str, session_path: Path, url: str) -> str:
    result = await page.evaluate(init_script)
    if not isinstance(result, dict):
        await page.wait_for_timeout(1500)
        return url

    nav_url = result.get("navigateTo")
    if isinstance(nav_url, str) and nav_url.startswith("http"):
        _log(session_path, f"Init navigateTo={nav_url[:80]}")
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        return page.url

    click_text = result.get("clickByText")
    if isinstance(click_text, str) and click_text.strip():
        _log(session_path, f"Init clickByText={click_text[:80]}")
        await page.get_by_text(click_text, exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(1500)

    selector = result.get("searchSelector")
    if isinstance(selector, str) and selector.strip():
        _log(session_path, f"Init searchSelector={selector}")
        await page.locator(selector).first.press("Enter", timeout=10000)
        await page.wait_for_timeout(3000)

    return page.url


async def _find_growth(page, previous_state: dict, *, coarse_margin_px: int, fine_step_px: int, poll_ms: int, timeout_ms: int, max_steps: int, session_path: Path | None = None, page_index: int | None = None) -> tuple[dict | None, dict | None]:
    for step_index in range(1, max_steps + 1):
        coarse = await _scroll(page, coarse_margin_px=coarse_margin_px)
        coarse_state, coarse_polls = await _wait_until_growth_stops(page, poll_ms, timeout_ms)
        coarse_changed, coarse_reasons = _has_new_content(previous_state, coarse_state)
        if session_path is not None and page_index is not None:
            _log(session_path, f"Coarse page={page_index} step={step_index} moved={coarse['moved']} polls={coarse_polls} reasons={coarse_reasons}")
        if coarse_changed:
            return coarse_state, {"mode": "coarse", "step_index": step_index, "reasons": coarse_reasons, "polls": coarse_polls}

        fine = await _scroll(page, fine_step_px=fine_step_px)
        fine_state, fine_polls = await _wait_until_growth_stops(page, poll_ms, timeout_ms)
        fine_changed, fine_reasons = _has_new_content(previous_state, fine_state)
        if session_path is not None and page_index is not None:
            _log(session_path, f"Fine page={page_index} step={step_index} moved={fine['moved']} polls={fine_polls} reasons={fine_reasons}")
        if fine_changed:
            return fine_state, {"mode": "fine", "step_index": step_index, "reasons": fine_reasons, "polls": fine_polls}

        reached_end = fine_state["scroll"]["position"] >= fine_state["scroll"]["max_position"]
        if (not coarse.get("moved") and not fine.get("moved")) or reached_end:
            if session_path is not None and page_index is not None:
                _log(session_path, f"ReachedEnd page={page_index} step={step_index}")
            break

    return None, None


async def run_crawler(
    url: str,
    session_dir: str,
    wait_ms: int,
    viewport_width: int,
    viewport_height: int,
    max_pages: int,
    max_steps_per_page: int,
    coarse_margin_px: int,
    fine_step_px: int,
    step_wait_ms: int,
    settle_timeout_ms: int,
    init_script: str | None,
    fast: bool = False,
    wait_selector: str | None = None,
    wait_selector_timeout_ms: int = 10000,
    ignore_https_errors: bool = False,
) -> None:
    session_path = _session_path(session_dir)
    (session_path / "pages").mkdir(parents=True, exist_ok=True)
    (session_path / "logs").mkdir(parents=True, exist_ok=True)
    _log(
        session_path,
        "Starting "
        f"url={url} viewport={viewport_width}x{viewport_height} max_pages={max_pages} "
        f"max_steps_per_page={max_steps_per_page} coarse_margin_px={coarse_margin_px} "
        f"fine_step_px={fine_step_px} step_wait_ms={step_wait_ms}",
    )

    curl_html: str | None = None
    curl_clues: dict | None = None
    curl_error: str | None = None
    if not fast:
        try:
            curl_html = _fetch_url_curl(url, ignore_https_errors=ignore_https_errors)
            (session_path / "curl.html").write_text(curl_html, encoding="utf-8", errors="replace")
            curl_clues = analyze_html(curl_html, url=url)
        except Exception as exc:
            curl_error = str(exc)
            _log(session_path, f"DetectPrepFailed: {exc}")
    else:
        curl_error = "skipped in fast mode"

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=ignore_https_errors,
        )
        page = await context.new_page()
        last_json_path: Path | None = None

        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as goto_exc:
                _log(session_path, f"GotoFailed: {goto_exc}")
                _write_json(
                    session_path / "page_type.json",
                    {
                        "url": url,
                        "content_delivery_type": "unknown",
                        "behaviors": [],
                        "reasons": [curl_error or "curl_clues missing", "playwright_goto_failed"],
                        "curl": {"error": curl_error or "unknown error"},
                        "playwright": {"error": str(goto_exc).splitlines()[0]},
                    },
                )
                if curl_error and "skipped" not in curl_error:
                    raise RuntimeError(f"URL Unreachable (curl: {curl_error.splitlines()[0]}, playwright: {str(goto_exc).splitlines()[0]})") from None
                raise RuntimeError(f"GotoFailed: {str(goto_exc).splitlines()[0]}") from None

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, state="attached", timeout=wait_selector_timeout_ms)
                except Exception as exc:
                    _log(session_path, f"WaitSelectorTimeout: {exc}")
            else:
                await page.wait_for_timeout(wait_ms)
                
            if init_script:
                url = await _run_init(page, init_script, session_path, url)

            initial_state = await _inspect_view(page)
            last_json_path = await _save_snapshot(
                page,
                session_path,
                1,
                page.url,
                initial_state,
                {"mode": "initial", "step_index": 0, "reasons": ["initial capture"], "polls": 0},
            )

            previous_state = initial_state
            if curl_clues is not None:
                content_type, reasons, behaviors = classify(curl_clues, initial_state["observation"]["text_len"])
                _write_json(
                    session_path / "page_type.json",
                    {
                        "url": page.url,
                        "content_delivery_type": content_type,
                        "behaviors": behaviors,
                        "reasons": reasons,
                        "curl": {
                            "body_text_len": curl_clues.get("body_text_len"),
                            "html_len": curl_clues.get("html_len"),
                            "script_chunk_count": curl_clues.get("script_chunk_count"),
                        },
                        "playwright": {"page_index": 1, "text_len": initial_state["observation"]["text_len"]},
                    },
                )
                _log(session_path, f"TypeDetected type={content_type} behaviors={behaviors}")
            else:
                _write_json(
                    session_path / "page_type.json",
                    {
                        "url": page.url,
                        "content_delivery_type": "unknown",
                        "behaviors": [],
                        "reasons": [curl_error or "curl_clues missing"],
                        "curl": {"error": curl_error or "unknown error"},
                        "playwright": {"page_index": 1, "text_len": initial_state["observation"]["text_len"]},
                    },
                )
                _log(session_path, "TypeDetected type=unknown (curl skipped or failed)")

            for page_index in range(2, max_pages + 1):
                growth_state, trigger = await _find_growth(
                    page,
                    previous_state,
                    coarse_margin_px=coarse_margin_px,
                    fine_step_px=fine_step_px,
                    poll_ms=step_wait_ms,
                    timeout_ms=settle_timeout_ms,
                    max_steps=max_steps_per_page,
                    session_path=session_path,
                    page_index=page_index,
                )
                if growth_state is None:
                    if last_json_path is not None:
                        _mark_terminal(last_json_path)
                    _log(session_path, f"Stop: no additional content before page_{page_index:04d}")
                    break

                last_json_path = await _save_snapshot(page, session_path, page_index, page.url, growth_state, trigger)
                previous_state = growth_state
                _log(session_path, f"Captured page_{page_index:04d} mode={trigger['mode']} reasons={trigger['reasons']}")
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="stream-crawler: Fetch list pages in stages prioritizing success rate")
    parser.add_argument("--url", required=True, help="URL to fetch")
    parser.add_argument("--session-dir", default="session", help="Output directory")
    parser.add_argument("--wait-ms", type=int, default=DEFAULT_LOAD_WAIT_MS, help="Wait ms after initial load")
    parser.add_argument("--viewport-width", type=int, default=DEFAULT_VIEWPORT_WIDTH)
    parser.add_argument("--viewport-height", type=int, default=DEFAULT_VIEWPORT_HEIGHT)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--max-steps-per-page", type=int, default=DEFAULT_MAX_STEPS_PER_PAGE)
    parser.add_argument("--coarse-margin-px", type=int, default=DEFAULT_COARSE_MARGIN_PX)
    parser.add_argument("--fine-step-px", type=int, default=DEFAULT_FINE_STEP_PX)
    parser.add_argument(
        "--step-wait-ms",
        type=int,
        default=DEFAULT_STEP_WAIT_MS,
        help="Polling interval ms to check growth after scroll",
    )
    parser.add_argument(
        "--settle-timeout-ms",
        type=int,
        default=DEFAULT_SETTLE_TIMEOUT_MS,
        help="Max ms to wait for growth to stop",
    )
    parser.add_argument("--fast", action="store_true", help="Fast mode: skip curl detection and only fetch page 1")
    parser.add_argument("--wait-selector", type=str, default=None, help="Selector to wait for before capturing (e.g. 'meta[property=\"og:image\"]')")
    parser.add_argument("--wait-selector-timeout-ms", type=int, default=10000, help="Timeout in ms for wait-selector")
    parser.add_argument("--ignore-https-errors", action="store_true", help="Ignore HTTPS certificate errors")
    parser.add_argument("--quiet-errors", action="store_true", help="Print only a concise 1-line error trace when failed")
    parser.add_argument("--init-script", type=str, default=None, metavar="JS_OR_PATH")
    args = parser.parse_args()

    if args.fast:
        args.max_pages = 1

    init_script = None
    if args.init_script:
        init_path = Path(args.init_script)
        if not init_path.is_absolute():
            init_path = Path.cwd() / init_path
        init_script = init_path.read_text(encoding="utf-8") if init_path.exists() and init_path.suffix.lower() == ".js" else args.init_script

    try:
        asyncio.run(
            run_crawler(
                url=args.url,
                session_dir=args.session_dir,
                wait_ms=args.wait_ms,
                viewport_width=args.viewport_width,
                viewport_height=args.viewport_height,
                max_pages=args.max_pages,
                max_steps_per_page=args.max_steps_per_page,
                coarse_margin_px=args.coarse_margin_px,
                fine_step_px=args.fine_step_px,
                step_wait_ms=args.step_wait_ms,
                settle_timeout_ms=args.settle_timeout_ms,
                init_script=init_script,
                fast=args.fast,
                wait_selector=args.wait_selector,
                wait_selector_timeout_ms=args.wait_selector_timeout_ms,
                ignore_https_errors=args.ignore_https_errors,
            )
        )
    except Exception as exc:
        if args.quiet_errors:
            import sys
            print(f"Error: {str(exc).splitlines()[0]}", file=sys.stderr)
            sys.exit(1)
        else:
            raise


if __name__ == "__main__":
    main()
