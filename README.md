# AI Agent Skills

このリポジトリは、AIエージェント向けの **Skill（スキル）** を公開・管理するためのコレクションです。

各 Skill は特定のタスクを実行するための **再利用可能な知識・ワークフロー・ツールのパッケージ**です。

Skill はフォルダごとに独立しており、個別に利用・インストールできます。

---

# このリポジトリについて

このプロジェクトでは以下を目的としています。

- AIエージェントの実用的な Skill を公開する
- 再現性のあるワークフローとして設計する
- スクリプト・分析・データ取得などのタスクを自動化する
- Skill エコシステムの実験と共有を行う

多くの Skill は **Pythonスクリプト + 明確な処理パイプライン**として設計されています。

例:

fetch
↓
validate
↓
extract
↓
analyze
↓
report

このように処理を分離することで、

- デバッグしやすい
- 再利用しやすい
- AI の誤推論を防ぐ

設計を目指しています。

---

# Skill 一覧

このリポジトリでは、Skill をフォルダ単位で管理しています。

## skills-trending-analysis

skills.sh のトレンドスキルを取得し、

- スキルランキング
- キーワード分析
- 開発者ランキング
- エコシステム分析

を生成する Skill。

トレンド分析や Skill エコシステムの観察に使用できます。

フォルダ:

`skills/skills-trending-analysis/`

---

## page-streaming

※概要記載予定（ページ単位、ストリーミング関連の Skill）

フォルダ:

`skills/page-streaming/`

---

# Skill 構成

各 Skill は基本的に以下の構造を持ちます。

skills/<skill-name>/
├─ SKILL.md
├─ README.md
├─ requirements.txt
├─ scripts/
├─ references/
├─ evals/
└─ examples/

### SKILL.md

AIエージェント向けの実行仕様。

- 何をする Skill か
- 実行方法
- 入出力仕様
- エラー処理

を定義します。

### README.md

人間向けの説明。

### scripts/

実際の処理を行うスクリプト。

### evals/

Skill の評価・検証用ファイル。

---

# 設計思想

このリポジトリの Skill は、次の原則で設計されています。

## 1. AI とコードの責務分離

数値処理・統計処理などの **決定的処理はコードで行う**。

AI は主に

- 要約
- 解釈
- 説明

を担当します。

これにより

- 再現性
- 精度
- 安定性

を確保します。

---

## 2. 構造チェック

外部データを扱う Skill は必ず

fetch
↓
validate
↓
extract

の構造を持ちます。

HTML構造などが変わった場合は **抽出を停止**し、誤ったデータ生成を防ぎます。

---

## 3. 再現可能な実行環境

Skill は可能な限り **独立した実行環境**で動作するように設計されています。

多くの場合:

- Python
- 仮想環境 `.venv`
- requirements.txt

を使用します。

---

# 利用方法

各 Skill は `npx skills add` コマンドでインストールできます。

### 全部入れる場合

```bash
npx skills add tmiyano89/skills
```

### 個別に入れる場合（例）

```bash
npx skills add tmiyano89/skills/skills/skills-trending-analysis
```

---

# ライセンス

MIT License

---

# 作者

t.miyano

GitHub:
https://github.com/tmiyano89
