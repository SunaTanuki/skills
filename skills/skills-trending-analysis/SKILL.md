---
name: skills-trending-analysis
description: skills.sh の trending ページを取得して、スキル・開発者・キーワードの統計を生成し、トレンドの要約を作成します。skills.sh の人気スキル、トレンド分析、開発者ランキング、キーワード傾向を知りたいときに使用します。
---

# Skills Trending Analysis

`skills.sh` の trending 情報を取得し、スキルエコシステムの統計分析と要約を生成する。

この Skill は、トレンドスキルの一覧を取得し、構造チェック付き抽出と統計処理を行い、その結果をもとに全体傾向を要約する。

---

# 入力

任意でキーワードを指定できる。

- キーワードあり: `https://skills.sh/trending?q=<keyword>`
- キーワードなし: `https://skills.sh/trending`

例: `swift`, `python`, `agent`

---

# 出力

以下を含む結果を生成する。

1. Trending summary
2. Top skills
3. Keyword ranking
4. Developer ranking
5. Ecosystem analysis

統計処理は Python で行い、AI はその結果に基づいて考察と要約を行う。

---

# 実行環境

この Skill は Python と Playwright を使用して Web ページを取得する。

想定する実行環境:

- Python 3.10 以上
- skill ディレクトリ内の Python 仮想環境 `.venv`
- Playwright
- Chromium

依存ライブラリは `.venv` にのみインストールする。  
グローバル Python 環境への依存追加は禁止する。

この設計の目的:

- Skill 実行の再現性を保つ
- 利用者環境との依存衝突を避ける
- Skill 単体での独立実行を可能にする

---

# 初回セットアップ

初回実行時のみ、以下を行う。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

仮想環境ルール:

- `.venv` が存在する場合は再作成しない
- `.venv` が存在しない場合のみ作成する
- 依存ライブラリは `.venv` にのみインストールする
- グローバル環境に依存を追加してはならない
- 仮想環境が壊れている場合のみ再作成する

---

# データ取得方針

skills.sh には公式の公開 API が確認されていない。  
また、サイトは Next.js App Router + React Server Components を使用しており、通常の HTTP GET では検索結果が反映されない静的 HTML が返る場合がある。

そのため、この Skill では以下の方式を採用する。

1. Playwright でページを実際にレンダリングする
2. JavaScript 実行後の DOM を取得する
3. レンダリング済み HTML を `tmp/` に保存する
4. 抽出スクリプトで HTML を解析する

ブラウザ MCP は使用しない。この Skill では、再現可能な Python スクリプト実行を優先する。

---

# 将来の API 対応

将来的に skills.sh の公式 API が公開された場合は、取得方式を次の優先順位に切り替える。

API → HTML 解析 (Playwright)

つまり:

1. 公開 API が利用可能なら API を使用する
2. API が存在しない場合のみ HTML 解析を使用する

---

# パイプライン

この Skill の処理は次の順で進める。

```
fetch
  ↓
validate + extract
  ↓
analyze
  ↓
summary
```

役割分担:

- **Python**: fetch、構造チェック、抽出、統計分析
- **AI**: 統計結果の解釈、開発者傾向の要約、全体考察、最終レポート生成

---

# 実行手順

**デフォルト実行**: 以下「1. データ取得」→「3. 統計分析」を順に実行する。この組み合わせが標準のパイプラインであり、分析結果には **developer の top_skills_by_installs**（代表 skill 上位 3 件）と **concentration**（集中度指標）が含まれる。keyword はタイトルの `-` 単純分割（suffix phrase merge は **デフォルト off**。有効にする場合は `--suffix-merge` を指定する）。ランキングの上位件数は **デフォルト 20 件**。

---

## 1. データ取得

キーワードなし:

```bash
python3 scripts/fetch_trending.py
```

キーワードあり:

```bash
python3 scripts/fetch_trending.py --keyword swift
```

- **デフォルト（スクロール収集あり）**: スクロールしながらリンクを連結し、**`tmp/trending.json`**（キーワードありの場合は `tmp/trending_<keyword>.json`）に保存する。このとき HTML は保存しない。続けて「3. 統計分析」へ進む（2. は不要）。
- **`--no-collect-while-scroll` 指定時**: スクロール後に先頭へ戻し、`tmp/trending_raw.html` を保存する。続けて「2. 構造チェックと抽出」で HTML から `tmp/trending.json` を生成してから「3. 統計分析」へ進む。

いずれの場合も、統計分析の入力は常に **`tmp/trending.json`**（キーワードありの場合は `tmp/trending_<keyword>.json`）となる。

---

## 2. 構造チェックと抽出（`--no-collect-while-scroll` 時のみ）

fetch を `--no-collect-while-scroll` で実行した場合のみ行う。抽出スクリプトは構造チェック機能を含む。

通常の trending:

```bash
python3 scripts/extract_trending.py --html tmp/trending_raw.html --output tmp/trending.json
```

keyword 付き:

```bash
python3 scripts/extract_trending.py --html tmp/trending_swift_raw.html --output tmp/trending_swift.json
```

抽出スクリプトのルール:

- HTML 構造が想定と一致する場合のみ抽出する
- 構造が一致しない場合は失敗として停止する
- AI が HTML を直接読んで推測で値を補うことは禁止する
- 構造変更時は、抽出スクリプトを修正または再作成する

---

## 3. 統計分析（デフォルト）

入力は常に `tmp/trending.json`（キーワードありの場合は `tmp/trending_<keyword>.json`）。  
このステップの出力には、developer の top_skills_by_installs と concentration が含まれる。keyword は `-` 単純分割（suffix phrase merge は `--suffix-merge` 指定時のみ有効）。ランキングは上位 **20 件**がデフォルト。

通常の trending:

```bash
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

keyword 付き:

```bash
python3 scripts/analyze_trending.py --input tmp/trending_swift.json --output tmp/trending_swift_analysis.json
```

上位件数指定:

```bash
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json --top 20
```

`--top 0` は全件を意味する。省略時は上位 20 件。suffix phrase merge を使う場合は `--suffix-merge` を付ける。

---

# 抽出データ仕様

抽出成功時の JSON:

- 各 item には **rank**（表の # 列、1 始まり）、title、developer、installs を含む。
- **rank_consistency**: ランクが 1 から始まっているか検証する。仮想リストで別範囲を取得していると min(rank) > 1 となり、ok が false になる。
- rank_min / rank_max で取得したランク範囲を確認できる。

```json
{
  "ok": true,
  "structure_valid": true,
  "rank_consistency": true,
  "rank_min": 1,
  "rank_max": 97,
  "items": [
    {
      "rank": 1,
      "title": "agent-tools",
      "developer": "toolshell",
      "installs": 11400
    }
  ]
}
```

抽出失敗時の JSON:

```json
{
  "ok": false,
  "structure_valid": false,
  "errors": [
    "skill card not found",
    "install count selector missing"
  ]
}
```

---

# 統計分析仕様（デフォルト）

analyze_trending.py のデフォルト実行（suffix phrase merge は off、上位 20 件）は以下を生成する。

**summary**

- total_skills
- total_installs
- unique_developers
- unique_keywords

**skill_ranking**

インストール数降順でランク付けする。項目: rank, title, developer, installs

**keyword_ranking**（デフォルト: 単純分割）

タイトルを `-` で分割して keyword 化する。`--suffix-merge` 指定時のみ、特定 suffix（practices, review, design, generation, browser）を直前語と 2 語 phrase に結合する（例: best-practices, code-review）。

ルール:

- 小文字化する
- 空文字を除外する
- 同一 skill 内の同一 keyword は 1 回だけ数える
- phrase 採用時は元の単語を別 keyword として数えない

ランキングは 2 種類: `keyword_ranking_by_installs`, `keyword_ranking_by_skill_count`。各項目: rank, keyword, skill_count, total_installs

**developer_ranking**

開発者ごとに集計する。項目: rank, developer, skill_count, total_installs, **top_keywords**, **top_skills_by_installs**。top_keywords はその開発者の skill title に頻出する keyword 上位。top_skills_by_installs は installs 上位最大 3 件の skill（title, installs）。

**concentration**

- top_10_skill_install_share: 上位 10 skill の installs 合計 / total_installs（0〜1）
- top_10_developer_install_share: 上位 10 developer の total_installs 合計 / total_installs（0〜1）

---

# AI が行う最終要約

Python の分析結果をもとに、AI は以下を生成する。

1. 主流の技術や話題
2. install 数の多いスキル群の傾向
3. keyword の集中傾向
4. 開発者ごとの得意領域の短い説明
5. 全体の要約と考察

AI は、統計値そのものを再計算しない。数値の根拠は analyze_trending.py の出力を使う。詳細は `references/output-format.md` を参照する。

---

# 失敗時の原則

スクリプト実行に失敗した場合は、以下を行う。

1. 失敗した処理名を特定する
2. 観測できたエラー内容を確認する
3. 利用者向けに簡潔に要約して伝える

報告には以下を含める。

- どの処理で失敗したか
- 何が観測されたか
- 現時点で分かる範囲の原因
- 追加対応が必要かどうか

観測事実と推定は分けて書くこと。

---

# 想定外の問題

以下のような状況は想定外の問題として扱う。

- Playwright が起動できない
- Chromium のインストールに失敗する
- HTML 構造が想定と大きく異なる
- スクリプトが未定義例外で停止する
- 必要な依存関係が不足している
- 既定の手順にない復旧が必要になる

このような場合は:

- 無理に処理を続行しない
- 応急処置を勝手に試みない
- 直ちに状況を利用者に報告する
- 次の対応方針について利用者の指示を仰ぐ

---

# 参照ファイル

必要に応じて以下を参照する。

- requirements.txt
- scripts/fetch_trending.py
- scripts/extract_trending.py
- scripts/analyze_trending.py
- evals/fetch-prompts.md
- evals/extract-prompts.md
- evals/analyze-prompts.md
- references/output-format.md
