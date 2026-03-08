"""
Calculate statistics from the JSON output of extract_trending.py (deterministic).

Input: items[] (title, developer, installs)
Output: summary, skill_ranking, keyword_ranking, developer_ranking
Only the subsequent "interpretation" and "summary" are left to the AI.
"""
import sys
import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict

# Number of top items to output for each ranking. 0 means all items.
DEFAULT_TOP_N = 20


# Words matching these suffixes are merged with the preceding word into a 2-word phrase
# (improves semantic accuracy).
SUFFIX_PHRASE_MERGE = frozenset({
    "practices",
    "review",
    "design",
    "generation",
    "browser",
})


def normalize_keyword(keyword: str) -> str:
    return keyword.strip().lower()


def split_title_to_keywords(title: str, suffix_merge: bool = False) -> list[str]:
    """
    Split the title by '-' and return unique keywords within the same skill.
    Only when suffix_merge is True, combine specific suffixes with the preceding word into a 2-word phrase.
    """
    raw = [normalize_keyword(p) for p in title.split("-")]
    parts = [p for p in raw if p]
    if suffix_merge:
        merged: list[str] = []
        i = 0
        while i < len(parts):
            if parts[i] in SUFFIX_PHRASE_MERGE and merged:
                prev = merged.pop()
                merged.append(f"{prev}-{parts[i]}")
                i += 1
            else:
                merged.append(parts[i])
                i += 1
        parts = merged
    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def build_summary(items: list[dict], suffix_merge: bool = False) -> dict:
    all_keywords = set()
    developers = set()
    for item in items:
        developers.add(item["developer"])
        for kw in split_title_to_keywords(item["title"], suffix_merge=suffix_merge):
            all_keywords.add(kw)
    return {
        "total_skills": len(items),
        "total_installs": sum(item["installs"] for item in items),
        "unique_developers": len(developers),
        "unique_keywords": len(all_keywords),
    }


def build_skill_ranking(items: list[dict]) -> list[dict]:
    sorted_items = sorted(items, key=lambda x: x["installs"], reverse=True)
    return [
        {
            "rank": idx,
            "title": item["title"],
            "developer": item["developer"],
            "installs": item["installs"],
        }
        for idx, item in enumerate(sorted_items, start=1)
    ]


def build_keyword_rankings(
    items: list[dict], suffix_merge: bool = False
) -> tuple[list[dict], list[dict]]:
    keyword_skill_count = Counter()
    keyword_total_installs = Counter()
    for item in items:
        keywords = split_title_to_keywords(item["title"], suffix_merge=suffix_merge)
        for kw in keywords:
            keyword_skill_count[kw] += 1
            keyword_total_installs[kw] += item["installs"]

    ranking_base = [
        {
            "keyword": kw,
            "skill_count": keyword_skill_count[kw],
            "total_installs": keyword_total_installs[kw],
        }
        for kw in keyword_skill_count
    ]

    by_installs = sorted(
        ranking_base,
        key=lambda x: (-x["total_installs"], -x["skill_count"], x["keyword"]),
    )
    for idx, row in enumerate(by_installs, start=1):
        row["rank"] = idx

    by_skill_count = sorted(
        ranking_base,
        key=lambda x: (-x["skill_count"], -x["total_installs"], x["keyword"]),
    )
    by_skill_count = [dict(row) for row in by_skill_count]
    for idx, row in enumerate(by_skill_count, start=1):
        row["rank"] = idx

    return by_installs, by_skill_count


def build_developer_ranking(
    items: list[dict], suffix_merge: bool = False
) -> list[dict]:
    developer_skill_count = Counter()
    developer_total_installs = Counter()
    developer_keywords = defaultdict(Counter)
    developer_skills: dict[str, list[dict]] = defaultdict(list)

    for item in items:
        developer = item["developer"]
        developer_skill_count[developer] += 1
        developer_total_installs[developer] += item["installs"]
        for kw in split_title_to_keywords(item["title"], suffix_merge=suffix_merge):
            developer_keywords[developer][kw] += 1
        developer_skills[developer].append({
            "title": item["title"],
            "installs": item["installs"],
        })

    ranking = []
    for developer in developer_skill_count:
        keyword_counter = developer_keywords[developer]
        top_keywords = [
            kw
            for kw, _ in sorted(
                keyword_counter.items(), key=lambda x: (-x[1], x[0])
            )[:5]
        ]
        skills_sorted = sorted(
            developer_skills[developer],
            key=lambda x: (-x["installs"], x["title"]),
        )
        top_skills_by_installs = [
            {"title": s["title"], "installs": s["installs"]}
            for s in skills_sorted[:3]
        ]
        ranking.append({
            "developer": developer,
            "skill_count": developer_skill_count[developer],
            "total_installs": developer_total_installs[developer],
            "top_keywords": top_keywords,
            "top_skills_by_installs": top_skills_by_installs,
        })

    ranking.sort(
        key=lambda x: (-x["total_installs"], -x["skill_count"], x["developer"])
    )
    for idx, row in enumerate(ranking, start=1):
        row["rank"] = idx

    return ranking


def build_concentration(
    items: list[dict],
    total_installs: int,
    suffix_merge: bool = False,
) -> dict[str, float]:
    """
    Calculate the concentration metrics of the ecosystem.
    share = sum of top N installs / total installs (0 to 1).
    """
    if total_installs <= 0:
        return {
            "top_10_skill_install_share": 0.0,
            "top_10_developer_install_share": 0.0,
        }
    skill_ranking = build_skill_ranking(items)
    developer_ranking = build_developer_ranking(items, suffix_merge=suffix_merge)
    top_10_skill_sum = sum(
        row["installs"] for row in skill_ranking[:10]
    )
    top_10_developer_sum = sum(
        row["total_installs"] for row in developer_ranking[:10]
    )
    return {
        "top_10_skill_install_share": round(
            top_10_skill_sum / total_installs, 4
        ),
        "top_10_developer_install_share": round(
            top_10_developer_sum / total_installs, 4
        ),
    }


def validate_input(data: dict) -> tuple[bool, list[str]]:
    errors = []
    if not isinstance(data, dict):
        errors.append("input JSON must be an object")
        return False, errors

    if not data.get("ok", False):
        errors.append("input JSON has ok=false")

    if "items" not in data:
        errors.append("input JSON does not contain items")
        return False, errors

    if not isinstance(data["items"], list):
        errors.append("items must be a list")
        return False, errors

    for idx, item in enumerate(data["items"]):
        if not isinstance(item, dict):
            errors.append(f"item[{idx}] is not an object")
            continue
        for field in ["title", "developer", "installs"]:
            if field not in item:
                errors.append(f"item[{idx}] missing field: {field}")
        if "installs" in item and not isinstance(item["installs"], int):
            errors.append(f"item[{idx}].installs must be int")

    return len(errors) == 0, errors


def main(
    input_file: Path,
    output_file: Path,
    top_n: int = DEFAULT_TOP_N,
    suffix_merge: bool = False,
) -> None:
    if not input_file.exists():
        print(f"Error: input file {input_file} not found.", file=sys.stderr)
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    valid, errors = validate_input(data)
    if not valid:
        output = {"ok": False, "errors": errors}
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Analysis result written to {output_file}")
        sys.exit(1)

    items = data["items"]

    if not items:
        output = {
            "ok": False,
            "errors": ["items is empty"],
            "summary": {
                "total_skills": 0,
                "total_installs": 0,
                "unique_developers": 0,
                "unique_keywords": 0,
            },
            "skill_ranking": [],
            "keyword_ranking_by_installs": [],
            "keyword_ranking_by_skill_count": [],
            "developer_ranking": [],
            "concentration": {
                "top_10_skill_install_share": 0.0,
                "top_10_developer_install_share": 0.0,
            },
        }
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Analysis result written to {output_file}")
        sys.exit(1)

    summary = build_summary(items, suffix_merge=suffix_merge)
    skill_ranking = build_skill_ranking(items)
    keyword_ranking_by_installs, keyword_ranking_by_skill_count = (
        build_keyword_rankings(items, suffix_merge=suffix_merge)
    )
    developer_ranking = build_developer_ranking(items, suffix_merge=suffix_merge)

    total_installs = summary["total_installs"]
    concentration = build_concentration(items, total_installs, suffix_merge=suffix_merge)

    if top_n > 0:
        skill_ranking = skill_ranking[:top_n]
        keyword_ranking_by_installs = keyword_ranking_by_installs[:top_n]
        keyword_ranking_by_skill_count = keyword_ranking_by_skill_count[:top_n]
        developer_ranking = developer_ranking[:top_n]

    output = {
        "ok": True,
        "summary": summary,
        "skill_ranking": skill_ranking,
        "keyword_ranking_by_installs": keyword_ranking_by_installs,
        "keyword_ranking_by_skill_count": keyword_ranking_by_skill_count,
        "developer_ranking": developer_ranking,
        "concentration": concentration,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Analysis result written to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze extracted trending JSON"
    )
    parser.add_argument(
        "--input", required=True, type=str, help="Path to extracted JSON file"
    )
    parser.add_argument(
        "--output", required=True, type=str, help="Path to output analysis JSON"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_N,
        help="Number of top items to output for each ranking (0=all, default=%d)" % DEFAULT_TOP_N,
    )
    parser.add_argument(
        "--suffix-merge",
        action="store_true",
        help="Enable suffix phrase merge for keywords (default: off)",
    )
    args = parser.parse_args()
    main(
        Path(args.input),
        Path(args.output),
        top_n=args.top,
        suffix_merge=args.suffix_merge,
    )
