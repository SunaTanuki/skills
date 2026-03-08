import sys
import json
import re
import argparse
from pathlib import Path
from bs4 import BeautifulSoup, Tag


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_rank_from_text(text: str) -> int | None:
    """
    Parse the rank number at the beginning of the line.
    Example: "1 agent-tools toolshell/skills 11.4K" -> 1, "717 apify-trend-analysis" -> 717
    """
    t = normalize_text(text)
    m = re.match(r"^(\d+)\s", t)
    if m:
        return int(m.group(1))
    return None


def parse_install_count(text: str) -> int | None:
    """
    Parse install count from strings like:
    - '1,234 installs'
    - '123 installs'
    - '12.3k installs'  (optional support)
    - or just '12.3k' if accompanied by context
    """
    text = normalize_text(text).lower()

    # 12.3k or 12.3K
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*k\b", text, re.IGNORECASE)
    if m:
        return int(float(m.group(1)) * 1000)

    # 1,234 or 123
    m = re.search(r"\b([\d,]+)(?:\s+installs?)?\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))

    return None


def find_candidate_cards(soup: BeautifulSoup) -> list[Tag]:
    """
    Find candidate card-like elements by looking for anchors that seem to link to skill pages.
    """
    candidates: list[Tag] = []

    # Skill detail link candidates on skills.sh
    for a in soup.find_all("a", href=True):
        href = a["href"]

        # Loosely determine patterns that look like skill detail pages
        # Since it's in the format owner/repo, we can check if it starts with "/" and contains another "/",
        # but for now, we'll handle it with an exclusion list.
        if href.startswith("/"):
            if any(x in href for x in ["/trending", "/docs", "/audits", "/hot", "/search"]):
                continue

            text = normalize_text(a.get_text(" ", strip=True))
            if text:
                candidates.append(a)

    # Deduplication
    unique: list[Tag] = []
    seen = set()
    for c in candidates:
        key = id(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def extract_card_data(card: Tag) -> dict | None:
    """
    Try to extract title, developer, installs from a candidate card/link.
    Returns None if required fields cannot be recovered.
    """
    text = normalize_text(card.get_text(" ", strip=True))
    if not text:
        return None

    # The string might be a mix of title and install count
    # Common real-world example: "agent-tools toolshell/skills 12.3K"
    
    # Restore from href. Supports both 2-part (owner/repo) and 3-part (owner/collection/skill) URLs.
    developer = None
    title = None
    href = card.get("href", "")
    parts = [p for p in href.split("/") if p]
    if len(parts) >= 3:
        # Example: /toolshell/skills/agent-tools -> developer=toolshell, title=agent-tools
        developer = parts[0]
        title = parts[-1]
    elif len(parts) == 2:
        developer = parts[0]
        title = parts[1]
    elif len(parts) == 1:
        title = parts[0]

    if not title:
        title = text

    # If the developer couldn't be obtained from href, we'd give up or search from text.
    if not developer:
        return None

    # Look for the install count in the nearby text
    install_count = parse_install_count(text)
    
    # If the inside of the anchor tag is divided, check the parent
    parent_text = ""
    if card.parent and isinstance(card.parent, Tag):
        parent_text = normalize_text(card.parent.get_text(" ", strip=True))
        if install_count is None:
            install_count = parse_install_count(parent_text)

    grandparent_text = ""
    if card.parent and card.parent.parent and isinstance(card.parent.parent, Tag):
        grandparent_text = normalize_text(card.parent.parent.get_text(" ", strip=True))
        if install_count is None:
            install_count = parse_install_count(grandparent_text)

    if not title or not developer or install_count is None:
        return None

    # The rank number is the number at the beginning of the line (the # column). 
    # It might be fetched from the parent element's text.
    rank = parse_rank_from_text(text)
    if rank is None and parent_text:
        rank = parse_rank_from_text(parent_text)
    if rank is None and grandparent_text:
        rank = parse_rank_from_text(grandparent_text)

    return {
        "rank": rank,
        "title": title,
        "developer": developer,
        "installs": install_count,
    }


def validate_rank_consistency(items: list[dict]) -> dict:
    """
    Verify if the extracted data's rank starts sequentially from 1.
    If a different range is fetched in a virtual list, min(rank) will be > 1.
    Returns {"valid": bool, "errors": list, "rank_min": int|None, "rank_max": int|None}
    """
    errors: list[str] = []
    ranks = [item["rank"] for item in items if item.get("rank") is not None]
    rank_min = min(ranks) if ranks else None
    rank_max = max(ranks) if ranks else None

    if not ranks:
        return {"valid": True, "errors": [], "rank_min": None, "rank_max": None}

    if rank_min != 1:
        errors.append(
            f"rank_consistency: ranks do not start from 1 (min={rank_min}); "
            "data may be from wrong part of list (e.g. virtualized list showing different range)"
        )
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "rank_min": rank_min,
        "rank_max": rank_max,
    }


def validate_structure(html_content: str) -> dict:
    """
    Check if the HTML has an extractable structure.
    Returns {"valid": bool, "errors": list}
    """
    errors = []

    if not html_content or not html_content.strip():
        return {"valid": False, "errors": ["HTML content is empty"]}

    soup = BeautifulSoup(html_content, "html.parser")

    page_text = normalize_text(soup.get_text(" ", strip=True)).lower()
    if "skills" not in page_text:
        errors.append("page does not appear to contain skills-related text")

    candidates = find_candidate_cards(soup)
    if not candidates:
        errors.append("no candidate skill links found")

    extracted_preview = []
    for card in candidates[:50]:
        item = extract_card_data(card)
        if item:
            extracted_preview.append(item)

    if len(extracted_preview) < 3:
        errors.append("fewer than 3 extractable skill items found. DOM structure might have changed or might be a non-trending page.")

    if not errors:
        return {"valid": True, "errors": []}
    return {"valid": False, "errors": errors}


def extract_data(html_content: str) -> list:
    """
    Extract items from confirmed HTML structure.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    candidates = find_candidate_cards(soup)

    items = []
    seen = set()

    for card in candidates:
        item = extract_card_data(card)
        if not item:
            continue

        key = (item["title"], item["developer"])
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    # Sort by rank before returning (1, 2, 3, ...). If ranks are identical, sort by installs descending.
    items.sort(key=lambda x: (x.get("rank") if x.get("rank") is not None else 999999, -x["installs"]))
    return items


def main(html_file: Path, output_file: Path) -> None:
    if not html_file.exists():
        print(f"Error: HTML file {html_file} not found.", file=sys.stderr)
        sys.exit(1)

    html_content = html_file.read_text(encoding="utf-8")

    validation = validate_structure(html_content)

    output_data = {
        "ok": validation["valid"],
        "structure_valid": validation["valid"],
    }

    if validation["valid"]:
        try:
            items = extract_data(html_content)
            output_data["items"] = items
            if not items:
                output_data["ok"] = False
                output_data["errors"] = ["No items extracted despite structure validation success"]
            else:
                rank_check = validate_rank_consistency(items)
                output_data["rank_consistency"] = rank_check["valid"]
                output_data["rank_min"] = rank_check.get("rank_min")
                output_data["rank_max"] = rank_check.get("rank_max")
                if not rank_check["valid"]:
                    output_data["ok"] = False
                    output_data["errors"] = output_data.get("errors", []) + rank_check["errors"]
        except Exception as e:
            output_data["ok"] = False
            output_data["structure_valid"] = False
            output_data["errors"] = [f"Extraction failed during processing: {str(e)}"]
    else:
        output_data["errors"] = validation["errors"]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Extraction result written to {output_file}")

    if not output_data["ok"]:
        print("Warning: extraction failed. See output JSON for details.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract data from trending HTML")
    parser.add_argument("--html", required=True, type=str, help="Path to input HTML file")
    parser.add_argument("--output", required=True, type=str, help="Path to output JSON file")

    args = parser.parse_args()
    main(Path(args.html), Path(args.output))
