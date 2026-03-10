"""
Synchronous fetching script for page-streaming.

Opens a URL using Playwright, executes the init script, and continuously captures from page_001 up to N pages,
saving the meta-information to sessions/{session_name}/pages/page_0NN.json. No background polling is performed.
Only handles fetching; does not perform page type detection or curl fetching.
Outputs a list of objects (JSON array) expanding the meta-information of each generated page (contents of page_0NN.json) to standard output.
"""
import argparse
import asyncio
import json
import re
import shutil
import sys
import traceback
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

# Initial load wait time (ms)
DEFAULT_LOAD_WAIT_MS = 2000
# Wait time after scroll (ms)
SCROLL_WAIT_MS = 800
# Wait time after running initialization script (ms)
INIT_SCRIPT_WAIT_MS = 1500

# incremental strategy: move largely -> sweep near the end proportional to viewport (ensures sentinel crossing)
COARSE_RATIO = 0.8       # coarse scroll amount = viewport * ratio
FINE_START_RATIO = 0.1   # sweep start offset = viewport * ratio
FINE_END_RATIO = 0.2     # sweep end offset = viewport * ratio（move amount per iteration = viewport になる）
FINE_STEP_RATIO = 0.02   # step = viewport * ratio（if 5000px it's 100px）
SWEEP_STEP_WAIT_MS = 50  # Wait after each sweep step (waits for IntersectionObserver etc. to fire)
COARSE_AFTER_WAIT_MS = 100  # Short wait immediately after coarse scroll

# Wait for DOM to settle (wait for async updates in React/Vue etc.)
DOM_SETTLE_STABLE_MS = 200  # Considered stable if the number of nodes doesn't change for this duration
DOM_SETTLE_POLL_MS = 50     # Polling interval

DEFAULT_VIEWPORT_WIDTH = 1920
DEFAULT_VIEWPORT_HEIGHT = 5000
DEFAULT_MAX_PAGES = 3

# Scroll strategy: full=all the way to the bottom at once / incremental=coarse move + sweep at the end (for Lazy/IO/Virtual list)
SCROLL_STRATEGY_FULL = "full"
SCROLL_STRATEGY_INCREMENTAL = "incremental"
DEFAULT_SCROLL_STRATEGY = SCROLL_STRATEGY_INCREMENTAL

# --help For --help: description of scroll-strategy=incremental
# See references/scroll-behavior.md for behavioral details.
HELP_EPILOG_INCREMENTAL = """
--scroll-strategy=incremental (Recommended: for virtual lists/Lazy load)
  Dynamic content (Lazy load / IntersectionObserver / virtual list) is often triggered 'when elements enter the viewport'.
  If you scroll all the way to the bottom at once, the sentinel is skipped and the trigger won't fire,
  so after a coarse move, we sweep finely near the end of the viewport to cause crossing.

  Scroll amount per iteration:
    coarse(viewport * coarse_ratio) after which advance scrollTop to base + (viewport * fine_end_ratio).
    合計 = viewport * (coarse_ratio + fine_end_ratio)。Default 0.8+0.2=1.0, advancing exactly 1 viewport.

  Implementation image (during capture of 1 page):
    1) scrollTop += viewport * coarse_ratio  (Coarse move)
    2) for y in [fine_start .. fine_end]: scrollTop = base + y  (Sweep)
    3) wait / DOM settle
    4) capture

  デフォルト: --coarse-ratio=0.8, --fine-start-ratio=0.1, --fine-end-ratio=0.2, --fine-step-ratio=0.02
  Details: references/scroll-behavior.md
"""


def _sessions_dir() -> Path:
    """Returns sessions/ at the skills root from the script's location."""
    return Path(__file__).resolve().parent.parent / "sessions"


def _resolve_session_path(session_name: str, *, continue_session: bool = False) -> Path:
    """
    Determines the save path from the session name.
    - continue_session=False: Delete if exists, then create.
    - continue_session=True: Use existing session, abort if it doesn't exist.
    Aborts if the folder cannot be created, or if the session does not exist during continue.
    """
    if not session_name or "/" in session_name or "\\" in session_name:
        print(f"Error: invalid session_name (no path separators): {session_name!r}", file=sys.stderr)
        sys.exit(1)
    base = _sessions_dir()
    session_path = base / session_name
    if session_path.exists() and not session_path.is_dir():
        print(f"Error: session path exists and is not a directory: {session_path}", file=sys.stderr)
        sys.exit(1)
    if continue_session:
        if not session_path.exists():
            print(f"Error: --continue requires existing session directory: {session_path}", file=sys.stderr)
            sys.exit(1)
        (session_path / "pages").mkdir(exist_ok=True)
        (session_path / "logs").mkdir(exist_ok=True)
        return session_path
    try:
        if session_path.exists():
            shutil.rmtree(session_path)
        session_path.mkdir(parents=True)
        (session_path / "pages").mkdir(exist_ok=True)
        (session_path / "logs").mkdir(exist_ok=True)
    except OSError as e:
        print(f"Error: cannot create session directory {session_path}: {e}", file=sys.stderr)
        sys.exit(1)
    return session_path


def _load_last_page_for_continue(session_path: Path) -> tuple[int, dict]:
    """
    Loads the last page of an existing session for resuming.
    Returns: (last page number, JSON content of that page).
    Aborts if no pages exist, or if scroll.info.currentPosition / nextPosition is missing.
    """
    pages_dir = session_path / "pages"
    if not pages_dir.is_dir():
        print("Error: --continue requires sessions/<name>/pages/ with at least one page_0NN.json", file=sys.stderr)
        sys.exit(1)
    pattern = re.compile(r"page_(\d+)\.json$")
    indices: list[int] = []
    for f in pages_dir.iterdir():
        if f.is_file():
            m = pattern.match(f.name)
            if m:
                indices.append(int(m.group(1)))
    if not indices:
        print("Error: --continue requires at least one page_0NN.json in sessions/<name>/pages/", file=sys.stderr)
        sys.exit(1)
    last_index = max(indices)
    last_file = pages_dir / f"page_{last_index:03d}.json"
    try:
        data = json.loads(last_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: failed to read {last_file}: {e}", file=sys.stderr)
        sys.exit(1)
    scroll_info = (data.get("scroll") or {}).get("info")
    if not scroll_info:
        print("Error: --continue requires last page JSON to have scroll.info (currentPosition, nextPosition)", file=sys.stderr)
        sys.exit(1)
    current = scroll_info.get("currentPosition")
    next_pos = scroll_info.get("nextPosition")
    if current is None or next_pos is None:
        print("Error: --continue requires scroll.info.currentPosition and scroll.info.nextPosition in last page JSON", file=sys.stderr)
        sys.exit(1)
    return last_index, data


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _log(session_path: Path, message: str) -> None:
    log_file = session_path / "logs" / "streamer.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{_now_iso()}] {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:50000]


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_text_snippets(text: str, snippet_len: int = 300) -> dict:
    """
    Mechanically extracts snippets (text-header, text-middle, text-footer) from the beginning, middle, and end of the full text.
    To reduce the size of the meta-information, the full text is not included; only three representative sections are kept.
    """
    if not text:
        return {"text-header": "", "text-middle": "", "text-footer": ""}

    length = len(text)
    n = max(1, min(snippet_len, length))

    header = text[:n]

    # snippet_len chars around the middle
    mid_start = max(0, (length - n) // 2)
    middle = text[mid_start : mid_start + n]

    # snippet_len chars from the end
    footer = text[-n:]

    return {
        "text-header": header,
        "text-middle": middle,
        "text-footer": footer,
    }


async def _wait_dom_settle(page, timeout_ms: int = 2000) -> None:
    """
    Wait until the number of DOM nodes remains unchanged for DOM_SETTLE_STABLE_MS.
    Used to wait for asynchronous updates in React/Vue etc. to settle.
    """
    js_get_count = "() => document.body ? document.body.childNodes.length : 0"
    last_count: int | None = None
    stable_since = time.monotonic()
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        count = await page.evaluate(js_get_count)
        if last_count is not None and count == last_count:
            if (time.monotonic() - stable_since) * 1000 >= DOM_SETTLE_STABLE_MS:
                return
        else:
            last_count = count
            stable_since = time.monotonic()
        await asyncio.sleep(DOM_SETTLE_POLL_MS / 1000.0)


async def _capture_page(page, url: str) -> tuple[str, str]:
    """Gets the main content HTML and text of the current page."""
    js = """
    () => {
        const main = document.querySelector('main') || document.querySelector('[role="main"]');
        const el = main || document.body;
        return { html: el.innerHTML, text: el.innerText };
    }
    """
    try:
        result = await page.evaluate(js)
        html = result.get("html") or ""
        text = (result.get("text") or "").strip()[:50000]
        if not html:
            html = await page.content()
            text = _html_to_text(html)
        return html, text
    except Exception:
        html = await page.content()
        return html, _html_to_text(html)


async def _scroll_full(page) -> dict:
    """
    Scrolls the page to the 'bottom-most' section.
    For sites where window scroll has no effect (internal scroll containers),
    it automatically selects the scrollable element on the JS side and scrolls it.
    """
    js = r"""
    () => {
      const isScrollable = (el) => {
        if (!el) return false;
        if ((el.scrollHeight - el.clientHeight) <= 400) return false;
        if (el.clientHeight <= 200) return false;
        // Since internal scrolling can sometimes work even when overflowY is "visible", it determines it by whether scrollTop actually changes
        const before = el.scrollTop;
        try { el.scrollTop = before + 10; } catch { return false; }
        const after = el.scrollTop;
        el.scrollTop = before;
        return after !== before;
      };

      const pickBestScroller = () => {
        const candidates = [];

        const main = document.querySelector('main') || document.querySelector('[role="main"]') || document.body;
        // Scroll container candidates under main (largest first)
        for (const el of main.querySelectorAll('*')) {
          if (isScrollable(el)) candidates.push(el);
        }

        // Also include the document's scrolling element as a candidate
        const docScroll = document.scrollingElement || document.documentElement || document.body;
        if (docScroll && (docScroll.scrollHeight - docScroll.clientHeight) > 200) {
          candidates.push(docScroll);
        }

        if (candidates.length === 0) return { kind: 'window', el: null };

        candidates.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
        return { kind: 'element', el: candidates[0] };
      };

      const scroller = pickBestScroller();
      if (scroller.kind === 'window') {
        const before = window.scrollY;
        window.scrollTo(0, document.body.scrollHeight);
        const after = window.scrollY;
        return { kind: 'window', before, after };
      }

      const el = scroller.el;
      const before = el.scrollTop;
      el.scrollTop = el.scrollHeight;
      const after = el.scrollTop;
      return { kind: 'element', before, after, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight };
    }
    """
    return await page.evaluate(js)


def _target_position_from_viewport(viewport_height: int, coarse_ratio: float, fine_end_ratio: float) -> int:
    """Target position offset amount (distance advanced in 1 incremental step) = viewport * (coarse_ratio + fine_end_ratio)."""
    return int(viewport_height * (coarse_ratio + fine_end_ratio))


async def _scroll_incremental(
    page,
    viewport_height: int,
    coarse_ratio: float,
    fine_start_ratio: float,
    fine_end_ratio: float,
    fine_step_ratio: float,
    target_position: int | None = None,
) -> dict:
    """
    incremental scroll: 1) coarse move 2) sweep 3) if target_position is specified, stop exactly at the target position.
    """
    js = r"""
    (args) => {
      const {
        viewportHeight,
        coarseRatio,
        fineStartRatio,
        fineEndRatio,
        fineStepRatio,
        targetPosition
      } = args;

      const isScrollable = (el) => {
        if (!el) return false;
        if ((el.scrollHeight - el.clientHeight) <= 400) return false;
        if (el.clientHeight <= 200) return false;
        const before = el.scrollTop;
        try { el.scrollTop = before + 10; } catch { return false; }
        const after = el.scrollTop;
        el.scrollTop = before;
        return after !== before;
      };

      const pickBestScroller = () => {
        const candidates = [];
        const main = document.querySelector('main') || document.querySelector('[role="main"]') || document.body;
        for (const el of main.querySelectorAll('*')) {
          if (isScrollable(el)) candidates.push(el);
        }
        const docScroll = document.scrollingElement || document.documentElement || document.body;
        if (docScroll && (docScroll.scrollHeight - docScroll.clientHeight) > 200) candidates.push(docScroll);
        if (candidates.length === 0) return { kind: 'window', el: null };
        candidates.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
        return { kind: 'element', el: candidates[0] };
      };

      const coarsePx = Math.floor(viewportHeight * coarseRatio);
      const fineStartPx = Math.floor(viewportHeight * fineStartRatio);
      const fineEndPx = Math.floor(viewportHeight * fineEndRatio);
      const fineStepPx = Math.max(1, Math.floor(viewportHeight * fineStepRatio));

      const cap = (el, pos) => (el ? Math.min(pos, el.scrollHeight - el.clientHeight) : pos);
      const capWin = (pos) => Math.min(pos, document.documentElement.scrollHeight - window.innerHeight);

      const scroller = pickBestScroller();
      if (scroller.kind === 'window') {
        const before = window.scrollY;
        window.scrollBy(0, coarsePx);
        const base = window.scrollY;
        const endY = (targetPosition != null) ? Math.min(fineEndPx, Math.max(0, targetPosition - base)) : fineEndPx;
        for (let y = fineStartPx; y <= endY; y += fineStepPx) {
          window.scrollTo(0, Math.min(base + y, capWin(base + y)));
        }
        let after = window.scrollY;
        if (targetPosition != null) {
          window.scrollTo(0, capWin(targetPosition));
          after = window.scrollY;
        }
        return { kind: 'window', before, base, after, coarsePx, fineStartPx, fineEndPx, fineStepPx };
      }

      const el = scroller.el;
      const before = el.scrollTop;
      el.scrollTop = before + coarsePx;
      const base = el.scrollTop;
      const maxScroll = el.scrollHeight - el.clientHeight;
      const endY = (targetPosition != null) ? Math.min(fineEndPx, Math.max(0, Math.min(targetPosition, maxScroll) - base)) : fineEndPx;
      for (let y = fineStartPx; y <= endY; y += fineStepPx) {
        el.scrollTop = Math.min(base + y, maxScroll);
      }
      let after = el.scrollTop;
      if (targetPosition != null) {
        el.scrollTop = Math.min(targetPosition, maxScroll);
        after = el.scrollTop;
      }
      return {
        kind: 'element',
        before,
        base,
        after,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
        coarsePx, fineStartPx, fineEndPx, fineStepPx
      };
    }
    """
    return await page.evaluate(
        js,
        {
            "viewportHeight": viewport_height,
            "coarseRatio": coarse_ratio,
            "fineStartRatio": fine_start_ratio,
            "fineEndRatio": fine_end_ratio,
            "fineStepRatio": fine_step_ratio,
            "targetPosition": target_position,
        },
    )


async def _sweep_to_target(
    page,
    target_position: int,
    viewport_height: int,
    fine_step_ratio: float,
) -> dict:
    """
    Only sweeps from the current position to the target position, adjusting fractions to match exactly. No coarse move is performed.
    """
    js = r"""
    (args) => {
      const { targetPosition, viewportHeight, fineStepRatio } = args;
      const fineStepPx = Math.max(1, Math.floor(viewportHeight * fineStepRatio));

      const isScrollable = (el) => {
        if (!el) return false;
        if ((el.scrollHeight - el.clientHeight) <= 400) return false;
        if (el.clientHeight <= 200) return false;
        const b = el.scrollTop;
        try { el.scrollTop = b + 10; } catch { return false; }
        const a = el.scrollTop;
        el.scrollTop = b;
        return a !== b;
      };
      const pickBestScroller = () => {
        const candidates = [];
        const main = document.querySelector('main') || document.querySelector('[role="main"]') || document.body;
        for (const el of main.querySelectorAll('*')) { if (isScrollable(el)) candidates.push(el); }
        const docScroll = document.scrollingElement || document.documentElement || document.body;
        if (docScroll && (docScroll.scrollHeight - docScroll.clientHeight) > 200) candidates.push(docScroll);
        if (candidates.length === 0) return { kind: 'window', el: null };
        candidates.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
        return { kind: 'element', el: candidates[0] };
      };

      const scroller = pickBestScroller();
      if (scroller.kind === 'window') {
        const before = window.scrollY;
        const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
        const target = Math.min(targetPosition, maxScroll);
        for (let p = before + fineStepPx; p < target; p += fineStepPx) {
          window.scrollTo(0, Math.min(p, maxScroll));
        }
        window.scrollTo(0, target);
        const after = window.scrollY;
        return { kind: 'window', before, base: before, after, scrollHeight: document.documentElement.scrollHeight, clientHeight: window.innerHeight };
      }
      const el = scroller.el;
      const before = el.scrollTop;
      const maxScroll = el.scrollHeight - el.clientHeight;
      const target = Math.min(targetPosition, maxScroll);
      for (let p = before + fineStepPx; p < target; p += fineStepPx) {
        el.scrollTop = Math.min(p, maxScroll);
      }
      el.scrollTop = target;
      const after = el.scrollTop;
      return { kind: 'element', before, base: before, after, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight };
    }
    """
    return await page.evaluate(
        js,
        {"targetPosition": target_position, "viewportHeight": viewport_height, "fineStepRatio": fine_step_ratio},
    )


async def _get_scroll_state(page) -> dict:
    """Gets the current scroll position and scrollHeight/clientHeight (does not scroll)."""
    js = r"""
    () => {
      const isScrollable = (el) => {
        if (!el) return false;
        if ((el.scrollHeight - el.clientHeight) <= 400) return false;
        if (el.clientHeight <= 200) return false;
        const b = el.scrollTop;
        try { el.scrollTop = b + 10; } catch { return false; }
        const a = el.scrollTop;
        el.scrollTop = b;
        return a !== b;
      };
      const pickBestScroller = () => {
        const candidates = [];
        const main = document.querySelector('main') || document.querySelector('[role="main"]') || document.body;
        for (const el of main.querySelectorAll('*')) { if (isScrollable(el)) candidates.push(el); }
        const docScroll = document.scrollingElement || document.documentElement || document.body;
        if (docScroll && (docScroll.scrollHeight - docScroll.clientHeight) > 200) candidates.push(docScroll);
        if (candidates.length === 0) return { kind: 'window', el: null };
        candidates.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
        return { kind: 'element', el: candidates[0] };
      };
      const s = pickBestScroller();
      if (s.kind === 'window') {
        return { scrollTop: window.scrollY, scrollHeight: document.documentElement.scrollHeight, clientHeight: window.innerHeight };
      }
      return { scrollTop: s.el.scrollTop, scrollHeight: s.el.scrollHeight, clientHeight: s.el.clientHeight };
    }
    """
    return await page.evaluate(js)


def _normalize_scroll_info(info: dict) -> dict:
    """
    Normalizes the scroll info returned from JS for output.
    before -> currentPosition (position when the page was captured), after -> nextPosition (position moved to after capture).
    strategy is included in capture_config, so it is not included in scroll.
    """
    out = {k: v for k, v in info.items() if k not in ("before", "after", "base")}
    out["currentPosition"] = info.get("before")
    out["nextPosition"] = info.get("after")
    return out


async def _get_current_scroll_info(page, viewport_height: int) -> dict:
    """
    Gets only the current scroll position (does not scroll).
    Appends as scroll information for the last page, etc., if not captured after scrolling.
    """
    js = r"""
    () => {
      const isScrollable = (el) => {
        if (!el) return false;
        if ((el.scrollHeight - el.clientHeight) <= 400) return false;
        if (el.clientHeight <= 200) return false;
        const before = el.scrollTop;
        try { el.scrollTop = before + 10; } catch { return false; }
        const after = el.scrollTop;
        el.scrollTop = before;
        return after !== before;
      };
      const pickBestScroller = () => {
        const candidates = [];
        const main = document.querySelector('main') || document.querySelector('[role="main"]') || document.body;
        for (const el of main.querySelectorAll('*')) {
          if (isScrollable(el)) candidates.push(el);
        }
        const docScroll = document.scrollingElement || document.documentElement || document.body;
        if (docScroll && (docScroll.scrollHeight - docScroll.clientHeight) > 200) candidates.push(docScroll);
        if (candidates.length === 0) return { kind: 'window', el: null };
        candidates.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
        return { kind: 'element', el: candidates[0] };
      };
      const scroller = pickBestScroller();
      if (scroller.kind === 'window') {
        const pos = window.scrollY;
        return { kind: 'window', before: pos, base: pos, after: pos };
      }
      const el = scroller.el;
      const pos = el.scrollTop;
      return {
        kind: 'element',
        before: pos,
        base: pos,
        after: pos,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
      };
    }
    """
    return await page.evaluate(js)


async def _run_init(page, init_script: str, session_path: Path, url: str) -> str:
    """Runs the init script and performs navigate/click/search if necessary. Returns the URL for capture."""
    result = await page.evaluate(init_script)
    if not isinstance(result, dict):
        await page.wait_for_timeout(INIT_SCRIPT_WAIT_MS)
        return url

    nav_url = result.get("navigateTo")
    if nav_url and isinstance(nav_url, str) and nav_url.startswith("http"):
        _log(session_path, f"Init: navigateTo {nav_url[:60]}...")
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(INIT_SCRIPT_WAIT_MS)
        return page.url

    if result.get("clickByText"):
        click_text = result["clickByText"]
        if isinstance(click_text, str) and click_text.strip():
            _log(session_path, f"Init: clickByText {click_text[:40]}...")
            await page.get_by_text(click_text, exact=False).first.click(timeout=10000)
            await page.wait_for_timeout(INIT_SCRIPT_WAIT_MS)

    if result.get("searchSelector"):
        sel = result["searchSelector"]
        if isinstance(sel, str) and sel.strip():
            _log(session_path, "Init: searchSelector, pressing Enter...")
            await page.locator(sel).first.press("Enter", timeout=10000)
            await page.wait_for_timeout(INIT_SCRIPT_WAIT_MS + 3000)

    await page.wait_for_timeout(INIT_SCRIPT_WAIT_MS)
    return page.url


async def run_fetch(
    url: str | None,
    session_name: str,
    wait_ms: int = DEFAULT_LOAD_WAIT_MS,
    viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
    viewport_height: int = DEFAULT_VIEWPORT_HEIGHT,
    init_script: str | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    scroll_strategy: str = DEFAULT_SCROLL_STRATEGY,
    coarse_ratio: float = COARSE_RATIO,
    fine_start_ratio: float = FINE_START_RATIO,
    fine_end_ratio: float = FINE_END_RATIO,
    fine_step_ratio: float = FINE_STEP_RATIO,
    continue_session: bool = False,
) -> None:
    """Opens a URL and captures up to max_pages of new pages. Save location is fixed to sessions/{session_name}."""
    session_path = _resolve_session_path(session_name, continue_session=continue_session)

    # max_pages = maximum number of new pages to capture. last_page_index = final page number to capture in this execute (1-based, inclusive)
    start_page_index = 1
    existing_last_page_index = 0
    last_page_index: int  # final page number to capture in the loop (captured up to and including this value)
    resume_next_position: int | None = None  # value to scroll to nextPosition upon continue
    if continue_session:
        existing_last_page_index, last_page_data = _load_last_page_for_continue(session_path)
        if url is None or url == "":
            url = (last_page_data.get("url") or "").strip()
            if not url:
                print("Error: --continue: last page JSON has no 'url' field.", file=sys.stderr)
                sys.exit(1)
        scroll_info = (last_page_data.get("scroll") or {}).get("info") or {}
        current_pos = scroll_info.get("currentPosition")
        next_pos = scroll_info.get("nextPosition")
        if current_pos is not None and next_pos is not None and current_pos == next_pos:
            print(
                "Error: --continue: last page has currentPosition == nextPosition (scroll limit reached). Cannot capture more pages.",
                file=sys.stderr,
            )
            sys.exit(1)
        resume_next_position = next_pos
        start_page_index = existing_last_page_index + 1
        last_page_index = start_page_index + max_pages - 1  # Capture only new max_pages items
        if max_pages <= 0:
            # If fetching 0 new items is specified, output all existing pages and exit
            pages_dir = session_path / "pages"
            result = []
            for i in range(1, existing_last_page_index + 1):
                p = pages_dir / f"page_{i:03d}.json"
                if p.exists():
                    result.append(json.loads(p.read_text(encoding="utf-8")))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
    else:
        if not url or not url.strip():
            print("Error: --url is required when not using --continue.", file=sys.stderr)
            sys.exit(1)
        url = url.strip()
        last_page_index = max_pages  # fetch 1..max_pages (new max_pages items)

    t0 = time.monotonic()
    _log(session_path, f"Starting url={url} max_pages={max_pages} scroll_strategy={scroll_strategy} continue={continue_session}")

    output_pages: list[dict] = []
    # End reason: max_pages_reached=reached page limit / no_scroll_progress=aborted due to no scroll progress
    end_reason: str = "max_pages_reached"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            _log(session_path, "Navigating...")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            wait_ms = max(0, min(wait_ms, 30000))
            await page.wait_for_timeout(wait_ms)

            if init_script:
                _log(session_path, "Running init script")
                try:
                    url = await _run_init(page, init_script, session_path, url)
                except Exception as e:
                    _log(session_path, f"Init script error: {e}")

            url = page.url
            pages_dir = session_path / "pages"
            last_saved_page_file: Path | None = None
            # Segment start time. page_001=script start ~ snippets completion, page_002=from then ~ page_002 snippets completion... so the total matches execution time
            t_segment_start = t0

            # On --continue: scroll to nextPosition of the last page. A sweep does not exceed scrollHeight, repeating while waiting for redraw. Exits with error if unreachable.
            if continue_session and resume_next_position is not None and resume_next_position > 0:
                next_position = resume_next_position
                _log(session_path, f"Continue: scrolling to nextPosition={next_position}")
                while True:
                    state = await _get_scroll_state(page)
                    max_scroll = max(0, state["scrollHeight"] - state["clientHeight"])
                    target_this_round = min(next_position, max_scroll)
                    try:
                        await _sweep_to_target(page, target_this_round, viewport_height, fine_step_ratio)
                    except Exception as e:
                        _log(session_path, f"Continue: sweep failed: {e}")
                        print(f"Error: --continue: could not scroll to nextPosition {next_position}: {e}", file=sys.stderr)
                        sys.exit(1)
                    await page.wait_for_timeout(SCROLL_WAIT_MS)
                    await _wait_dom_settle(page)
                    state_after = await _get_scroll_state(page)
                    if state_after["scrollTop"] >= next_position:
                        _log(session_path, f"Continue: reached nextPosition={next_position}")
                        break
                    # If scrolled to the bottom in this round but scrollHeight hasn't expanded, cannot proceed -> exit with error
                    max_scroll_after = max(0, state_after["scrollHeight"] - state_after["clientHeight"])
                    at_bottom = state_after["scrollTop"] >= max_scroll_after
                    if at_bottom and state_after["scrollHeight"] <= state["scrollHeight"]:
                        print(
                            f"Error: --continue: could not reach nextPosition {next_position} "
                            f"(scrollTop={state_after['scrollTop']}, scrollHeight={state_after['scrollHeight']}). "
                            "Content did not extend after waiting.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    _log(session_path, f"Continue: at {state_after['scrollTop']}, scrollHeight={state_after['scrollHeight']}, sweeping again")

            for page_index in range(start_page_index, last_page_index + 1):
                html, text = await _capture_page(page, url)

                html_length = len(html or "")
                text_length = len(text or "")

                # Raw HTML/Text are saved in separate files from JSON; meta-information (JSON) contains only snippets.
                html_file = pages_dir / f"page_{page_index:03d}.html"
                txt_file = pages_dir / f"page_{page_index:03d}.txt"
                html_file.write_text(html, encoding="utf-8", errors="replace")
                txt_file.write_text(text, encoding="utf-8", errors="replace")

                snippets = _extract_text_snippets(text)
                # elapsed_sec for this page = from previous segment end (or start) until this page's snippets are captured
                page_elapsed = round(time.monotonic() - t_segment_start, 2)

                page_file = pages_dir / f"page_{page_index:03d}.json"
                page_base = f"page_{page_index:03d}"
                page_data: dict = {
                    "page_index": page_index,
                    "url": url,
                    "captured_at": _now_iso(),
                    "html_length": html_length,
                    "text_length": text_length,
                    "elapsed_sec": page_elapsed,
                    "end_reason": "continued",  # The last page's reason will be overwritten with the actual reason after the loop
                    "output_files": {
                        "all_text": f"{page_base}.txt",
                        "raw_html": f"{page_base}.html",
                        "meta": f"{page_base}.json",
                    },
                    "capture_config": {
                        "max_pages": max_pages,
                        "wait_ms": wait_ms,
                        "viewport_width": viewport_width,
                        "viewport_height": viewport_height,
                        "scroll_strategy": scroll_strategy,
                        "coarse_ratio": coarse_ratio,
                        "fine_start_ratio": fine_start_ratio,
                        "fine_end_ratio": fine_end_ratio,
                        "fine_step_ratio": fine_step_ratio,
                    },
                    # Full html/text is not included in meta-information; only snippets are kept.
                    "items": [
                        {
                            "text-header": snippets["text-header"],
                            "text-middle": snippets["text-middle"],
                            "text-footer": snippets["text-footer"],
                        }
                    ],
                    "has_more_hint": page_index < last_page_index,
                }
                _write_json(page_file, page_data)
                last_saved_page_file = page_file
                output_pages.append(page_data)
                t_segment_start = time.monotonic()  # Start of next page's segment
                _log(session_path, f"Saved page_{page_index:03d}.json ({len(html)} chars) elapsed={page_elapsed}s")

                # Common to all pages: 1) Coarse move 2) Sweep 3) Wait. If unreached and scrollHeight expanded, repeat from 2. Max sweep per iteration is up to current scrollHeight.
                if scroll_strategy == SCROLL_STRATEGY_INCREMENTAL:
                    state0 = await _get_scroll_state(page)
                    before_scroll = state0["scrollTop"]
                    max_scroll0 = max(0, state0["scrollHeight"] - state0["clientHeight"])
                    target_position = min(
                        before_scroll + _target_position_from_viewport(
                            viewport_height, coarse_ratio, fine_end_ratio
                        ),
                        max_scroll0,
                    )
                    prev_scroll_height = 0
                    first_iter = True
                    first_write = True
                    info = None

                    while True:
                        if first_iter:
                            info = await _scroll_incremental(
                                page,
                                viewport_height=viewport_height,
                                coarse_ratio=coarse_ratio,
                                fine_start_ratio=fine_start_ratio,
                                fine_end_ratio=fine_end_ratio,
                                fine_step_ratio=fine_step_ratio,
                                target_position=target_position,
                            )
                            first_iter = False
                        else:
                            info = await _sweep_to_target(
                                page, target_position, viewport_height, fine_step_ratio
                            )
                        _log(session_path, f"Incremental: {info}")
                        if last_saved_page_file:
                            try:
                                data = json.loads(last_saved_page_file.read_text(encoding="utf-8"))
                                norm = _normalize_scroll_info(info)
                                if first_write:
                                    data["scroll"] = {"info": norm}
                                    first_write = False
                                else:
                                    data["scroll"]["info"]["nextPosition"] = norm["nextPosition"]
                                    if "scrollHeight" in norm:
                                        data["scroll"]["info"]["scrollHeight"] = norm["scrollHeight"]
                                _write_json(last_saved_page_file, data)
                            except Exception as e:
                                _log(session_path, f"ScrollMeta: failed to attach incremental info: {e}")

                        await page.wait_for_timeout(COARSE_AFTER_WAIT_MS)
                        await page.wait_for_timeout(SWEEP_STEP_WAIT_MS)
                        await page.wait_for_timeout(SCROLL_WAIT_MS)
                        await _wait_dom_settle(page)

                        state = await _get_scroll_state(page)
                        if state["scrollTop"] >= target_position:
                            break
                        if state["scrollHeight"] <= prev_scroll_height:
                            break
                        prev_scroll_height = state["scrollHeight"]
                        _log(session_path, f"Incremental: not at target {target_position}, scrollHeight grew, sweeping again")

                    state_final = await _get_scroll_state(page)
                    # If breaking loop without reaching target (scrollHeight didn't expand, cannot scroll further), abort with error (no fallback)
                    if state_final["scrollTop"] < target_position:
                        max_sf = max(0, state_final["scrollHeight"] - state_final["clientHeight"])
                        if state_final["scrollTop"] >= max_sf:
                            print(
                                f"Error: could not reach target position {target_position} "
                                f"(scrollTop={state_final['scrollTop']}, scrollHeight={state_final['scrollHeight']}). "
                                "Content did not extend after waiting.",
                                file=sys.stderr,
                            )
                            sys.exit(1)
                    scrolled = state_final["scrollTop"] > before_scroll
                    if page_index >= last_page_index:
                        break
                    try:
                        if info and info.get("kind") == "window" and not scrolled:
                            wheel_delta = int(viewport_height * 0.9)
                            for _ in range(5):
                                await page.mouse.wheel(0, wheel_delta)
                                await page.wait_for_timeout(150)
                            after_wheel = await page.evaluate("() => window.scrollY")
                            _log(session_path, f"WheelFallback: delta={wheel_delta} after_window_scrollY={after_wheel}")
                            scrolled = scrolled or (after_wheel and after_wheel > 0)
                    except Exception as e:
                        _log(session_path, f"WheelFallback error: {e}")

                    if not scrolled:
                        end_reason = "no_scroll_progress"
                        _log(session_path, "NoScrollProgress: scroll position unchanged. Stopping capture early.")
                        if last_saved_page_file:
                            try:
                                data = json.loads(last_saved_page_file.read_text(encoding="utf-8"))
                                data["has_more_hint"] = False
                                data["end_reason"] = end_reason
                                _write_json(last_saved_page_file, data)
                            except Exception as e:
                                _log(session_path, f"NoScrollProgress: failed to update has_more_hint: {e}")
                        break
                else:
                    info = await _scroll_full(page)
                    _log(session_path, f"FullScroll: {info}")
                    if last_saved_page_file:
                        try:
                            data = json.loads(last_saved_page_file.read_text(encoding="utf-8"))
                            data["scroll"] = {"info": _normalize_scroll_info(info)}
                            _write_json(last_saved_page_file, data)
                        except Exception as e:
                            _log(session_path, f"ScrollMeta: failed to attach full info: {e}")
                    if page_index >= last_page_index:
                        # Last page: Wait for dynamic content to load, then try scrolling once more; if it moves, update nextPosition
                        await page.wait_for_timeout(SCROLL_WAIT_MS)
                        await _wait_dom_settle(page)
                        try:
                            info2 = await _scroll_full(page)
                            if info2.get("after") is not None and info2.get("after") > info.get("after", 0):
                                data = json.loads(last_saved_page_file.read_text(encoding="utf-8"))
                                norm = _normalize_scroll_info(info2)
                                data["scroll"]["info"]["nextPosition"] = norm["nextPosition"]
                                if "scrollHeight" in norm:
                                    data["scroll"]["info"]["scrollHeight"] = norm["scrollHeight"]
                                _write_json(last_saved_page_file, data)
                                _log(session_path, f"Last page: nextPosition updated to {norm['nextPosition']} after dynamic load")
                        except Exception as e:
                            _log(session_path, f"Last page follow-up scroll: {e}")
                        break
                    if info.get("before") == info.get("after"):
                        end_reason = "no_scroll_progress"
                        _log(session_path, "NoScrollProgress: scroll position unchanged. Stopping capture early.")
                        if last_saved_page_file:
                            try:
                                data = json.loads(last_saved_page_file.read_text(encoding="utf-8"))
                                data["has_more_hint"] = False
                                data["end_reason"] = end_reason
                                _write_json(last_saved_page_file, data)
                            except Exception as e:
                                _log(session_path, f"NoScrollProgress: failed to update has_more_hint: {e}")
                        break
                    await page.wait_for_timeout(SCROLL_WAIT_MS)

        finally:
            await browser.close()

    elapsed = time.monotonic() - t0
    _log(session_path, f"Done. {len(output_pages)} pages in {elapsed:.2f}s (end_reason={end_reason})")
    # Overwrite the last page's end_reason with the actual reason (if finished due to max_pages_reached)
    if last_saved_page_file and last_saved_page_file.exists():
        try:
            data = json.loads(last_saved_page_file.read_text(encoding="utf-8"))
            data["end_reason"] = end_reason
            _write_json(last_saved_page_file, data)
        except Exception as e:
            _log(session_path, f"Failed to update end_reason on last page: {e}")
    # Match output with saved file contents (reflecting additions of scroll / has_more_hint / end_reason)
    pages_dir = session_path / "pages"
    total_pages = (existing_last_page_index + len(output_pages)) if continue_session else len(output_pages)
    result = []
    for i in range(1, total_pages + 1):
        p = pages_dir / f"page_{i:03d}.json"
        if p.exists():
            result.append(json.loads(p.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="page-streaming: Page fetching only via Playwright. Fetches from page_001 up to max N pages, and prints a JSON list expanding the meta-info of each page (contents of page_0NN.json) to stdout.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG_INCREMENTAL,
    )
    parser.add_argument(
        "--url",
        default=None,
        metavar="URL",
        help="URL to fetch. Can be omitted if --continue (extracted from the last page's JSON).",
    )
    parser.add_argument(
        "--session-name",
        default="example",
        metavar="NAME",
        help="Session name. Save path is fixed to sessions/NAME relative to scripts (no path separators). Aborts if folder creation fails.",
    )
    parser.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="If an existing session is present, scroll to nextPosition from the last page before resuming fetch without deleting. If currentPosition==nextPosition on the last page, treats as scroll limit and aborts.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        metavar="N",
        help="Maximum number of new pages to fetch (default: %(default)s). Indicates the number of additional pages to fetch if --continue .",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=DEFAULT_LOAD_WAIT_MS,
        metavar="MS",
        help="Wait in ms after initial load (default: %(default)s)",
    )
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=DEFAULT_VIEWPORT_WIDTH,
        metavar="PX",
        help="Viewport width (default: %(default)s)",
    )
    parser.add_argument(
        "--viewport-height",
        type=int,
        default=DEFAULT_VIEWPORT_HEIGHT,
        metavar="PX",
        help="Viewport height (default: %(default)s)",
    )
    parser.add_argument(
        "--init-script",
        type=str,
        default=None,
        metavar="JS_OR_PATH",
        help="JS to run after page load (inline string or .js file path)",
    )
    parser.add_argument(
        "--scroll-strategy",
        type=str,
        default=DEFAULT_SCROLL_STRATEGY,
        choices=[SCROLL_STRATEGY_FULL, SCROLL_STRATEGY_INCREMENTAL],
        help="full=scroll to bottom every time / incremental=coarse move + sweep at end of viewport (for Lazy/IO/virtual lists, see below)",
    )
    parser.add_argument(
        "--coarse-ratio",
        type=float,
        default=COARSE_RATIO,
        help="[incremental] coarse scroll amount = viewport_height * ratio（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--fine-start-ratio",
        type=float,
        default=FINE_START_RATIO,
        help="[incremental] sweep start offset = viewport_height * ratio（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--fine-end-ratio",
        type=float,
        default=FINE_END_RATIO,
        help="[incremental] sweep end offset = viewport_height * ratio（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--fine-step-ratio",
        type=float,
        default=FINE_STEP_RATIO,
        help="[incremental] スイープstep = viewport_height * ratio（デフォルト: %(default)s）",
    )
    args = parser.parse_args()

    if not args.continue_session and not args.url:
        parser.error("--url is required (when running without --continue)")
    if args.continue_session and not args.url:
        # URL is obtained from the last page JSON in run_fetch
        args.url = None

    init_script = None
    if args.init_script:
        path = Path(args.init_script)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists() and path.suffix.lower() == ".js":
            init_script = path.read_text(encoding="utf-8")
        else:
            init_script = args.init_script

    try:
        asyncio.run(run_fetch(
            args.url,
            args.session_name,
            args.wait_ms,
            args.viewport_width,
            args.viewport_height,
            init_script,
            args.max_pages,
            args.scroll_strategy,
            args.coarse_ratio,
            args.fine_start_ratio,
            args.fine_end_ratio,
            args.fine_step_ratio,
            getattr(args, "continue_session", False),
        ))
    except Exception as e:
        print(traceback.format_exc(), file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

