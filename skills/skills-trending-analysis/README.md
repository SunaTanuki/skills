# Skills Trending Analysis

skills.sh の trending ページを取得し、スキル・開発者・キーワードの統計とトレンド要約を生成する Skill です。

## 目的

- 人気スキルのランキング取得
- キーワード・開発者別の集計
- エコシステムの集中度指標（concentration）の算出
- AI による考察・要約レポートの生成

## 前提環境

- Python 3.10+
- Playwright（Chromium）

依存はこの Skill ディレクトリ内の `.venv` にのみインストールします。

## クイックスタート

```bash
# 初回のみ: 仮想環境と Chromium のセットアップ
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# データ取得（キーワードなし）
python3 scripts/fetch_trending.py

# 統計分析
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

その後、AI は `tmp/trending_analysis.json` を参照し、`references/output-format.md` に従ってレポートを生成します。

## 出力

- **tmp/trending.json** — 取得したスキル一覧（title, developer, installs）
- **tmp/trending_analysis.json** — 統計結果（summary, skill_ranking, keyword_ranking, developer_ranking, concentration）
- レポート — Trending summary / Top skills / Keyword ranking / Developer ranking / Ecosystem analysis

## 参照

- **SKILL.md** — 実行手順・ルール・パイプラインの詳細
- **references/output-format.md** — AI が生成するレポートのフォーマット
