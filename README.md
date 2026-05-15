# Claude Code Safety Hooks Demo

Claude Code に**安全柵（セーフティガード）**をつけるための最小テンプレートです。

Claude Code の [Hooks 機能](https://docs.anthropic.com/en/docs/claude-code/hooks) を使い、危険な操作を実行前にブロックし、編集後に自動で format / test を走らせます。勉強会・自習回のデモ用に作られていますが、実プロジェクトにもそのまま流用できます。

---

## 防げる事故

| カテゴリ | 具体例 |
|---------|--------|
| 破壊的コマンド | `rm -rf /`, `sudo rm`, ワイルドカード削除 |
| 機密ファイルの読み取り | `.env`, `.env.local`, 秘密鍵 (`id_rsa`, `*.pem`) |
| main/master への直接 push | `git push origin main` |
| 危険なインストール | `curl https://... \| sh`, `wget ... \| bash` |
| 編集後の format/test 忘れ | Prettier 自動実行、`npm test` 自動実行 |

---

## ファイル構成

```
.claude/
├── settings.json                  # Hooks 設定ファイル
└── hooks/
    ├── pre_tool_use_guard.py      # 実行前ガード（危険コマンド・機密ファイルをブロック）
    └── post_tool_use_check.py     # 実行後チェック（prettier + npm test）

src/
└── app.js                         # デモ用アプリケーション

test-smoke.js                      # デモ用スモークテスト
package.json                       # プロジェクト設定
```

### `.claude/settings.json`

Claude Code の Hooks 設定。以下のイベントにフックを登録しています。

- **PreToolUse (Bash)** — Bash コマンド実行前に `pre_tool_use_guard.py` を呼び、危険コマンドをブロック
- **PreToolUse (Read|Edit|Write|MultiEdit)** — ファイルアクセス前に `pre_tool_use_guard.py` を呼び、機密ファイルへのアクセスをブロック
- **PostToolUse (Edit|Write|MultiEdit)** — ファイル編集後に `post_tool_use_check.py` を呼び、Prettier + npm test を自動実行
- **Notification** — macOS 通知を表示

### `.claude/hooks/pre_tool_use_guard.py`

Claude Code がツールを使う前に呼ばれる Python スクリプト。標準入力から Hook 入力 JSON を受け取り、危険と判定した場合は deny JSON を返します。

**ブロック対象:**
- `rm -rf`, `sudo rm`, ルート・ホーム・ワイルドカード削除
- `git push` で main/master へ直接 push
- `.env` / 秘密鍵 / `secrets/` ディレクトリの読み取り
- `curl | sh`, `wget | bash`
- `chmod -R 777`, `chown -R`, `docker system prune -a`
- パストラバーサル (`../`)

### `.claude/hooks/post_tool_use_check.py`

ファイル編集後に呼ばれる Python スクリプト。

**実行内容:**
- 対象ファイル (`.js`, `.ts`, `.json`, `.md`, `.css`, `.html` 等) に対して `npx prettier --write` を実行
- `npm test` を実行（テストスクリプトがある場合のみ）
- 機密ファイル・`.git/` 配下には触れない

---

## セットアップ

### 1. リポジトリをクローン

```bash
git clone <このリポジトリのURL>
cd claude-code-safety-hooks-demo
```

### 2. 依存をインストール

```bash
npm install
```

### 3. 動作確認

```bash
# スモークテスト
npm test

# Hook 単体テスト（危険コマンドのブロック確認）
echo '{"toolName":"Bash","toolInput":{"command":"rm -rf /"}}' | python3 .claude/hooks/pre_tool_use_guard.py
# → deny JSON が返ればOK
```

### 4. 自分のプロジェクトに導入する場合

`.claude/` ディレクトリをそのままコピーしてください。

```bash
cp -r .claude/ /path/to/your-project/.claude/
```

---

## デモ手順

### デモ 1: 危険コマンドが止まる

Claude Code に以下を依頼してください:

> Bash で `rm -rf ./tmp` を実行して、Hook でブロックされるか確認してください。

**期待結果:**
- `rm -rf` が実行**前に**ブロックされる
- 「Blocked destructive command: rm -rf is not allowed.」というメッセージが表示される
- 実際のファイル削除は発生しない

**手動で確認する場合:**

```bash
echo '{"toolName":"Bash","toolInput":{"command":"rm -rf ./tmp"}}' | python3 .claude/hooks/pre_tool_use_guard.py
```

### デモ 2: `.env` アクセスが止まる

Claude Code に以下を依頼してください:

> `.env` を読んで、このプロジェクトに必要な環境変数を README にまとめてください。

**期待結果:**
- `.env` へのアクセスがブロックされる
- 「Blocked access to sensitive file: .env」というメッセージが表示される
- `.env` の中身は一切読まれない

**手動で確認する場合:**

```bash
# Bash 経由の場合
echo '{"toolName":"Bash","toolInput":{"command":"cat .env"}}' | python3 .claude/hooks/pre_tool_use_guard.py

# Read ツール経由の場合
echo '{"toolName":"Read","toolInput":{"file_path":".env"}}' | python3 .claude/hooks/pre_tool_use_guard.py
```

### デモ 3: 編集後に format/test が走る

Claude Code に以下を依頼してください:

> `src/app.js` に `multiply` 関数を追加し、`test-smoke.js` にも確認テストを追加してください。

**期待結果:**
- 編集後に Prettier が自動実行される
- `npm test` が自動実行される
- テストが通れば「Tests passed.」と表示される

**手動で確認する場合:**

```bash
echo '{"toolName":"Edit","toolInput":{"file_path":"src/app.js"}}' | python3 .claude/hooks/post_tool_use_check.py
```

---

## 学び

### 1. AI に自由を与えるほど、安全柵が重要

Claude Code は強力なツールですが、間違ったコマンドも実行できてしまいます。「AI が便利になるほど、事故のインパクトも大きくなる」という前提で運用設計をしましょう。

### 2. プロンプトで注意するだけではなく、仕組みで止める

「`rm -rf` は使わないでね」とプロンプトに書いても、100% 守られる保証はありません。Hooks で**仕組みとして**ブロックすることで、ヒューマンエラーならぬ AI エラーを防げます。

### 3. 秘密情報は AI に読ませない前提で設計する

`.env` や秘密鍵は、AI に「読まないで」と頼むのではなく、**読めない仕組み**にしましょう。Hooks でブロックすることに加え、`.gitignore` や `.claude/settings.json` の権限設定も組み合わせます。

### 4. format/test は人間の記憶に頼らず自動化する

「編集したら prettier かけてね」「テスト忘れないでね」は、人間同士でも忘れます。PostToolUse Hook で自動化すれば、AI が編集するたびに確実に実行されます。

### 5. Claude Code を実務投入するなら、Hook・レビュー・PR 運用を組み合わせる

Hooks だけで完璧なセキュリティは実現できません。以下を組み合わせましょう:
- **Hooks** — 明らかに危険な操作をブロック
- **コードレビュー** — AI が書いたコードを人間が確認
- **PR 運用** — main への直接 push を禁止し、レビュー必須にする
- **権限設定** — Claude Code に与える権限を最小限にする

---

## 注意点

- **このHookは万能なセキュリティ製品ではありません。** 正規表現・ルールベースの簡易ガードです。
- **抜け道はあります。** 例えばコマンドをエンコードしたり、間接的に実行するパターンは検出できません。
- **本番導入時はチームのセキュリティ要件に合わせて調整してください。** ブロックルールの追加・変更は `pre_tool_use_guard.py` の `DANGEROUS_BASH_PATTERNS` と `SENSITIVE_FILE_PATTERNS` を編集します。
- **`.env` や秘密鍵を Claude Code に読ませない運用を徹底してください。** Hooks はあくまで最後の砦であり、そもそも機密ファイルが AI のアクセス可能な場所にないことが理想です。
- **依存は最小限です。** Python 3 標準ライブラリのみ使用しており、`jq` などの追加ツールは不要です。

---

## 発表で見せるべきポイント

1. **Hook の仕組み**: Claude Code は Hooks で「ツール実行前後」に任意のスクリプトを挟める
2. **deny JSON の威力**: `permissionDecision: "deny"` を返すだけで、AI の動作を止められる
3. **デモのインパクト**: `rm -rf` や `.env` アクセスがリアルタイムでブロックされる様子
4. **自動化の価値**: 編集のたびに format + test が走り、品質が自動で担保される
5. **持ち帰りやすさ**: `.claude/` ディレクトリをコピーするだけで自分のプロジェクトに導入できる

---

## ライセンス

MIT
