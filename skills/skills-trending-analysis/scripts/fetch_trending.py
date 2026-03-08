"""
Trending ページの HTML を Playwright で取得する。

約100件のユニークなスキルを取得するため、デフォルトでビューポート高さ4000px・
スクロールを有効にし、リストの遅延読み込みをトリガーする。

仮想リストでは表示外の行は DOM から消えるため、デフォルトでは
スクロールしながらリンクを連結し、extract と同形式の JSON を
tmp/trending.json（キーワードありの場合は tmp/trending_<keyword>.json）に保存する。
以降の処理（統計分析）はスクロール有無にかかわらず同じ入力ファイルを使う。
"""
import sys
import argparse
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright
import urllib.parse

# 取得目標件数（リンク数がこの値に達したら打ち切り）。スピード重視で100にすると早く終了する
TARGET_ITEM_COUNT = 100
# スクロール最大回数（デフォルト10回）
MAX_SCROLL_ITERATIONS = 10
# 高さが変わらないと判定する連続回数で打ち切り
SCROLL_NO_CHANGE_LIMIT = 5
# ビューポート: 高さを大きくして一度に多くの要素がレンダリングされるようにする
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 4000


def _js_count_skill_links() -> str:
    """DOM 内のスキル詳細リンク（/owner/skill-name 形式）の数を返す JS。"""
    return """
    () => {
        const exclude = ['/trending', '/docs', '/audits', '/hot', '/search'];
        const links = document.querySelectorAll('a[href^="/"]');
        let count = 0;
        for (const a of links) {
            const href = a.getAttribute('href') || '';
            if (exclude.some(x => href.includes(x))) continue;
            const parts = href.split('/').filter(Boolean);
            if (parts.length >= 2) count++;
        }
        return count;
    }
    """


def _js_get_skill_links_with_text() -> str:
    """現在 DOM にあるスキルリンクの href とテキストを返す（連結モード用）。"""
    return """
    () => {
        const exclude = ['/trending', '/docs', '/audits', '/hot', '/search'];
        const links = document.querySelectorAll('a[href^="/"]');
        const out = [];
        for (const a of links) {
            const href = (a.getAttribute('href') || '').trim();
            if (exclude.some(x => href.includes(x))) continue;
            const parts = href.split('/').filter(Boolean);
            if (parts.length >= 2) {
                out.push({ href, text: a.innerText.replace(/\\s+/g, ' ').trim().slice(0, 150) });
            }
        }
        return out;
    }
    """


def _parse_install_count(text: str) -> int | None:
    """テキストから install 数をパース（extract_trending と同等）。"""
    t = re.sub(r"\s+", " ", text).strip().lower()
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*k\b", t, re.IGNORECASE)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r"\b([\d,]+)(?:\s+installs?)?\b", t, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _href_text_to_item(href: str, text: str) -> dict | None:
    """href とテキストから title, developer, installs を組み立てる。"""
    parts = [p for p in href.split("/") if p]
    if len(parts) >= 3:
        developer, title = parts[0], parts[-1]
    elif len(parts) == 2:
        developer, title = parts[0], parts[1]
    else:
        return None
    installs = _parse_install_count(text)
    if installs is None:
        return None
    return {"title": title, "developer": developer, "installs": installs}


async def fetch_trending_async(
    keyword: str = None,
    max_scrolls: int | None = None,
    viewport_height: int | None = None,
    collect_while_scroll: bool = True,
) -> tuple[Path, int]:
    """Trending ページを取得し、保存先パスと取得したスキルリンク数（または項目数）を返す。"""
    base_url = "https://skills.sh/trending"
    if keyword:
        url = f"{base_url}?q={urllib.parse.quote(keyword)}"
        tmp_filename = f"trending_{keyword}.json" if collect_while_scroll else f"trending_{keyword}_raw.html"
    else:
        url = base_url
        tmp_filename = "trending.json" if collect_while_scroll else "trending_raw.html"

    skill_dir = Path(__file__).parent.parent
    tmp_dir = skill_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    file_path = tmp_dir / tmp_filename

    vh = viewport_height if viewport_height is not None else VIEWPORT_HEIGHT
    limit = max_scrolls if max_scrolls is not None else MAX_SCROLL_ITERATIONS

    print(f"Fetching: {url} (viewport_height={vh}, max_scrolls={limit}, collect_while_scroll={collect_while_scroll})")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": VIEWPORT_WIDTH, "height": vh},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            count_skill_links = _js_count_skill_links()
            get_links_with_text = _js_get_skill_links_with_text()
            previous_height = await page.evaluate("document.body.scrollHeight")
            no_change_count = 0
            all_collected: dict[str, str] = {}  # href -> text（連結モード時）

            if limit > 0:
                print(f"Scrolling to load more items (target >= {TARGET_ITEM_COUNT}, max {limit} rounds)...")
            for i in range(limit):
                # 連結モード: 各位置で現在 DOM にあるリンクを収集
                if collect_while_scroll:
                    links = await page.evaluate(get_links_with_text)
                    for x in links:
                        all_collected[x["href"]] = x["text"]

                # 一度に下までスクロール
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

                # 少し上に戻してから再び下まで（Intersection Observer 系のトリガー用）
                await page.evaluate("window.scrollBy(0, -400)")
                await page.wait_for_timeout(300)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

                current_height = await page.evaluate("document.body.scrollHeight")
                if current_height == previous_height:
                    no_change_count += 1
                    if no_change_count >= SCROLL_NO_CHANGE_LIMIT:
                        print(f"  Height unchanged for {SCROLL_NO_CHANGE_LIMIT} rounds, stopping at round {i + 1}.")
                        break
                else:
                    no_change_count = 0
                previous_height = current_height

                n = await page.evaluate(count_skill_links)
                if (i + 1) % 5 == 0 or n >= TARGET_ITEM_COUNT:
                    print(f"  Round {i + 1}: {n} skill links, body height {current_height}, collected unique={len(all_collected)}" if collect_while_scroll else f"  Round {i + 1}: {n} skill links, body height {current_height}")
                if not collect_while_scroll and n >= TARGET_ITEM_COUNT:
                    print(f"  Reached target count {n} >= {TARGET_ITEM_COUNT}.")
                    break
            else:
                if limit > 0:
                    print(f"  Reached max scroll iterations ({limit}).")

            if collect_while_scroll:
                # 連結した href+text から item を組み立て（extract と同形式の JSON）
                items: list[dict] = []
                seen: set[tuple[str, str]] = set()
                for href, text in all_collected.items():
                    item = _href_text_to_item(href, text)
                    if not item:
                        continue
                    key = (item["title"], item["developer"])
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(item)
                items.sort(key=lambda x: x["installs"], reverse=True)
                out = {"ok": True, "structure_valid": True, "items": items}
                file_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Saved to {file_path} ({len(items)} unique items)")
                await browser.close()
                return (file_path, len(items))

            # 仮想リストでは描画されている行だけ DOM に存在する。保存前に先頭へスクロールし、
            # ランク上位（トレンド先頭）の行が DOM に描画されるようにする。
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(2000)

            html = await page.content()
            file_path.write_text(html, encoding="utf-8")
            final_count = await page.evaluate(count_skill_links)
            print(f"Saved HTML to: {file_path} (Size: {len(html)} bytes, ~{final_count} skill links)")

        except Exception as e:
            print(f"Failed to fetch {url}: {e}", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        await browser.close()
        return (file_path, final_count)

def fetch_trending(
    keyword: str = None,
    max_scrolls: int | None = None,
    viewport_height: int | None = None,
    collect_while_scroll: bool = True,
) -> tuple[Path, int]:
    """Trending ページを取得し、保存先パスと取得したスキルリンク数（または項目数）を返す。"""
    return asyncio.run(fetch_trending_async(keyword, max_scrolls, viewport_height, collect_while_scroll))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch trending skills from skills.sh")
    parser.add_argument("--keyword", type=str, help="Optional keyword to search for", default=None)
    parser.add_argument("--max-scrolls", type=int, default=None, help="Max scroll iterations (0=no scroll, default: %d)" % MAX_SCROLL_ITERATIONS)
    parser.add_argument("--viewport-height", type=int, default=None, help="Viewport height in px (default: %d)" % VIEWPORT_HEIGHT)
    parser.add_argument("--no-collect-while-scroll", action="store_true", help="Disable: save HTML after scrolling to top (fewer items, extract step needed)")
    args = parser.parse_args()
    collect_while_scroll = not args.no_collect_while_scroll
    path, count = fetch_trending(args.keyword, args.max_scrolls, args.viewport_height, collect_while_scroll)
    # 終了コードは従来どおり（呼び出し元が path のみを期待している場合は path で十分）
    # count は実験スクリプトなどで利用可能
