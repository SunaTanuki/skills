import os
import subprocess
import time
import json
import argparse
from pathlib import Path
from datetime import datetime

def run_command(cmd, cwd):
    start = time.time()
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    duration = time.time() - start
    return duration, result

def main():
    parser = argparse.ArgumentParser(description="Compare API-based skill vs Playwright-based test.")
    parser.add_argument("--limit", type=int, default=100, help="Number of items to fetch for API version")
    args = parser.parse_args()

    # Paths
    base_dir = Path(__file__).parent.parent.parent
    prod_dir = base_dir / "skills" / "skills-trending-analysis"
    test_dir = base_dir / "tests" / "skills-trending-analysis"
    
    # Virtualenv path (assuming it exists in prod_dir)
    venv_python = prod_dir / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = "python3" # Fallback

    print("="*60)
    print(f"🚀 SKILLS TRENDING ANALYSIS BENCHMARK")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # 1. API Version (Production)
    print(f"\n[1] Running API Version (Production) limit={args.limit}...")
    api_fetch_cmd = f"{venv_python} scripts/fetch_trending.py --refresh --limit {args.limit}"
    api_analyze_cmd = f"{venv_python} scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json"
    
    t1_fetch, r1_fetch = run_command(api_fetch_cmd, prod_dir)
    t1_analyze, r1_analyze = run_command(api_analyze_cmd, prod_dir)
    
    if r1_analyze.returncode == 0:
        print(f"  ✅ Success")
        print(f"  ⏱️  Fetch: {t1_fetch:.2f}s | Analyze: {t1_analyze:.2f}s | Total: {t1_fetch+t1_analyze:.2f}s")
        with open(prod_dir / "tmp" / "trending_analysis.json", "r") as f:
            api_data = json.load(f)
    else:
        print(f"  ❌ Failed: {r1_analyze.stderr}")
        return

    # 2. Playwright Version (Test/Validation)
    print(f"\n[2] Running Playwright Version (Validation)...")
    pw_fetch_cmd = f"{venv_python} scripts/fetch_trending_playwright.py"
    pw_analyze_cmd = f"{venv_python} scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json"
    
    t2_fetch, r2_fetch = run_command(pw_fetch_cmd, test_dir)
    t2_analyze, r2_analyze = run_command(pw_analyze_cmd, test_dir)
    
    if r2_analyze.returncode == 0:
        print(f"  ✅ Success")
        print(f"  ⏱️  Fetch: {t2_fetch:.2f}s | Analyze: {t2_analyze:.2f}s | Total: {t2_fetch+t2_analyze:.2f}s")
        with open(test_dir / "tmp" / "trending_analysis.json", "r") as f:
            pw_data = json.load(f)
    else:
        print(f"  ❌ Failed: {r2_analyze.stderr}")
        return

    # Comparison Results
    print("\n" + "="*60)
    print("📊 COMPARISON SUMMARY")
    print("="*60)
    
    api_count = len(api_data.get("skill_ranking", []))
    pw_count = len(pw_data.get("skill_ranking", []))
    
    print(f"{'Metric':<20} | {'API (Prod)':<15} | {'Playwright (Test)':<15}")
    print("-" * 60)
    print(f"{'Items Analyzed':<20} | {api_count:<15} | {pw_count:<15}")
    print(f"{'Total Time':<20} | {t1_fetch+t1_analyze:13.2f}s | {t2_fetch+t2_analyze:13.2f}s")
    
    speedup = (t2_fetch+t2_analyze) / (t1_fetch+t1_analyze) if (t1_fetch+t1_analyze) > 0 else 0
    print(f"\n🚀 Efficiency: API version is {speedup:.1f}x faster")

    # Data Consistency Check (Compare Top 5)
    print("\n🔍 Consistency Check (Top 5 Skills):")
    api_top5 = [s["title"] for s in api_data.get("skill_ranking", [])[:5]]
    pw_top5 = [s["title"] for s in pw_data.get("skill_ranking", [])[:5]]
    
    match = "✅ MATCH" if api_top5 == pw_top5 else "⚠️ MISMATCH"
    print(f"  API Top 5: {api_top5}")
    print(f"  PW  Top 5: {pw_top5}")
    print(f"  Result:    {match}")

if __name__ == "__main__":
    main()
