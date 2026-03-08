# 出力フォーマット（AI 最終要約）

このファイルは、SKILL.md の「AI が行う最終要約」で生成するレポートのフォーマットと生成ルールを定義する。

統計値の根拠は **analyze_trending.py の出力 JSON** に限る。  
AI は **数値の再計算を行わない**。

---

# レポート構成

レポートは以下のセクションで構成する。

1. **Trending summary**
2. **Top skills**
3. **Keyword ranking**
4. **Developer ranking**
5. **Ecosystem analysis**

セクション順序は必ず維持する。

---

# 1. Trending summary

トレンドの概要を **3〜6項目程度の箇条書き**で説明する。

内容例:

- 主流技術
- 人気トピック
- 新しいカテゴリ
- install 数が集中している分野

ルール:

- 数値は summary / ranking から引用する
- keyword や skill 名を具体的に示す
- 推測ではなく **観測結果に基づく説明**にする

例:

- エージェント系ツールが上位を占める
- design / ui 関連の keyword が多い
- image / generator 系のスキルが人気

---

# 2. Top skills

`skill_ranking` を元に、**installs 上位 N 件**を表形式で表示する。

表形式:

| Rank | Title | Developer | Installs |
|-----|------|------|------|

件数は analyze_trending.py の出力に基づく。

ルール:

- installs 降順
- title / developer / installs をそのまま引用
- AI が順位を変更してはならない

表のあとに **1〜2文の短い説明**を付ける。

例:

- 上位スキルはエージェント関連ツールが多い
- 画像生成・動画生成スキルも人気

---

# 3. Keyword ranking

`keyword_ranking_by_installs`  
`keyword_ranking_by_skill_count`

の **両方を使用する**。

## installs ベースランキング

| Rank | Keyword | Skill count | Total installs |

件数は analyze_trending.py の出力に基づく。

## skill_count ベースランキング

| Rank | Keyword | Skill count | Total installs |

件数は analyze_trending.py の出力に基づく。

ルール:

- keyword は analyze_trending.py の出力をそのまま使用
- デフォルトはタイトルの `-` 単純分割（--suffix-merge 指定時のみ phrase 結合）
- AI が keyword を独自に再構成しない

表のあとに **2〜3文の解釈**を書く。

例:

- design / ui が多く、UI 系スキル需要が高い
- generator / image など生成系が人気

---

# 4. Developer ranking

`developer_ranking` を使用する。

表形式:

| Rank | Developer | Skill count | Total installs | Top keywords |

件数は analyze_trending.py の出力に基づく。

Top keywords は `top_keywords` をそのまま表示する。

その後、各 developer の傾向を **1行で説明**する。

説明は以下を参考にする:

- top_keywords
- top_skills_by_installs

例:

toolshell — エージェント・画像生成・UI 系スキル
trailofbits — セキュリティ・監査ツール

ルール:

- keyword の意味的グループ化は許可
- installs の数値は変更しない

---

# 5. Ecosystem analysis

全体の傾向を **4〜6文程度でまとめる**。

参照する情報:

- summary
- keyword ranking
- developer ranking
- concentration

含める観点:

### 集中と分散

`concentration` 指標を使って説明する。

例:

- top_10_skill_install_share
- top_10_developer_install_share

### 技術テーマ

例:

- agent
- design
- image-generation
- data

### エコシステム構造

例:

- 多様な developer が存在
- 特定 developer の集中
- 新しいカテゴリの出現

---

# 数値引用ルール

数値は **analyze_trending.py の出力 JSON** から引用する。

使用可能なデータ:

- summary
- skill_ranking
- keyword_ranking_by_installs
- keyword_ranking_by_skill_count
- developer_ranking
- concentration

AI は以下をしてはならない:

- installs を再計算する
- ranking を再生成する
- keyword を再分割する

---

# 事実と解釈の分離

レポートでは **事実と解釈を混同しない**。

事実:

- installs
- ranking
- keyword counts
- developer counts

解釈:

- 技術トレンド
- 人気カテゴリ
- エコシステム構造

事実を提示した後に解釈を書く。

---

# 最終注記

レポートの最後に必ず以下を記載する。

本レポートの数値・ランキングはすべて analyze_trending.py の出力に基づく。


⸻
