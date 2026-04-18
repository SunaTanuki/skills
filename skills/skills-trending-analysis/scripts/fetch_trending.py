import sys
import argparse
import json
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta

"""
Fetch the trending skills directly from skills.sh via its internal JSON API.
"""

INTERNAL_API_BASE = "https://skills.sh/api/skills/all-time"
CACHE_EXPIRY_HOURS = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://skills.sh/trending",
    "Accept": "application/json",
}

def is_cache_valid(cache_file: Path) -> bool:
    if not cache_file.exists():
        return False
    mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
    if datetime.now() - mtime > timedelta(hours=CACHE_EXPIRY_HOURS):
        return False
    return True

def fetch_trending(
    output_path: Path,
    keyword: str = None,
    refresh: bool = False,
    limit: int = 1000
) -> int:
    """Fetch the trending items directly from the internal API and save to the specified output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)
    
    # Cache check
    if not refresh and is_cache_valid(output_path):
        print(f"Using cached data from {output_path}")
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return len(data.get("items", []))

    print(f"Fetching trending data directly from skills.sh API...")
    items = []
    page = 0
    
    try:
        while len(items) < limit:
            url = f"{INTERNAL_API_BASE}/{page}"
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            raw_skills = data.get("skills", [])
            if not raw_skills:
                break
                
            for s in raw_skills:
                source = s.get("source", "")
                developer = source.split("/")[0] if "/" in source else "unknown"
                
                items.append({
                    "title": s.get("name"),
                    "developer": developer,
                    "installs": s.get("installs", 0)
                })
            
            if not data.get("hasMore", False):
                break
            
            page += 1
            time.sleep(0.5)

        if keyword:
            kw = keyword.lower()
            items = [item for item in items if kw in item["title"].lower() or kw in item["developer"].lower()]

        items.sort(key=lambda x: x["installs"], reverse=True)
        items = items[:limit]

        out = {
            "ok": True,
            "structure_valid": True,
            "items": items,
            "fetched_at": datetime.now().isoformat(),
            "source": f"Direct internal API (pages 0-{page})"
        }
        
        output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved to {output_path} ({len(items)} items from {page+1} API pages)")
        return len(items)

    except Exception as e:
        print(f"Failed to fetch from internal API: {e}", file=sys.stderr)
        if output_path.exists():
            print(f"Falling back to expired cache: {output_path}")
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return len(data.get("items", []))
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch trending skills directly from skills.sh")
    parser.add_argument("--output", type=str, required=True, help="Path to save the output JSON (REQUIRED)")
    parser.add_argument("--keyword", type=str, help="Optional keyword to filter by", default=None)
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and force fetch")
    parser.add_argument("--limit", type=int, default=1000, help="Number of items to fetch (default: 1000)")
    
    args = parser.parse_args()
    
    count = fetch_trending(
        output_path=args.output,
        keyword=args.keyword,
        refresh=args.refresh,
        limit=args.limit
    )
