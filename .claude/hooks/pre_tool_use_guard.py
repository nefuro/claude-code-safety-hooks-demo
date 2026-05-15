#!/usr/bin/env python3
"""
Claude Code Hook: PreToolUse Guard
===================================
Claude Code がツールを実行する前に呼ばれ、
危険なコマンドや機密ファイルへのアクセスをブロックする。

stdin から Hook 入力 JSON を受け取り、
ブロック時は deny JSON を stdout に返す。
"""

import json
import re
import sys
import os


# =============================================================================
# ブロックルール定義
# =============================================================================

# Bash コマンドのブロックパターン（正規表現）
DANGEROUS_BASH_PATTERNS = [
    # rm -rf 系の危険な削除
    (r'\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f', "Blocked destructive command: rm -rf is not allowed."),
    (r'\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*r', "Blocked destructive command: rm -rf is not allowed."),
    (r'\bsudo\s+rm\b', "Blocked destructive command: sudo rm is not allowed."),
    # ルート・ホーム・カレントディレクトリ等を対象にした rm
    (r'\brm\s+.*\s+[/~][\s;|&]', "Blocked destructive command: rm on / or ~ is not allowed."),
    (r'\brm\s+.*\s+[/~]$', "Blocked destructive command: rm on / or ~ is not allowed."),
    (r'\brm\s+.*\s+\.\.\s', "Blocked destructive command: rm on parent directory is not allowed."),
    (r'\brm\s+.*\s+\.\.$', "Blocked destructive command: rm on parent directory is not allowed."),
    (r'\brm\s+.*\s+\*', "Blocked destructive command: rm with wildcard is not allowed."),

    # main/master への直接 push
    (r'\bgit\s+push\b.*\b(main|master)\b', "Blocked direct push to main/master. Use a feature branch and PR instead."),

    # .env ファイルを読もうとする操作
    (r'\b(cat|less|more|head|tail|grep|sed|awk|sort|bat|view)\b.*\.env\b',
     "Blocked access to .env file. Do not read environment files."),

    # 秘密鍵・機密ファイルを読もうとする操作
    (r'\b(cat|less|more|head|tail|grep|sed|awk|sort|bat|view)\b.*(id_rsa|id_ed25519|id_ecdsa|\.pem|\.key|private.?key|secret)',
     "Blocked access to sensitive file. Do not read private keys or secrets."),

    # curl/wget パイプで sh/bash 実行
    (r'\bcurl\b.*\|\s*(sh|bash)\b', "Blocked dangerous command: curl | sh is not allowed. Review scripts before executing."),
    (r'\bwget\b.*\|\s*(sh|bash)\b', "Blocked dangerous command: wget | sh is not allowed. Review scripts before executing."),
    (r'\bcurl\b.*\|\s*sudo\s*(sh|bash)\b', "Blocked dangerous command: curl | sudo sh is not allowed."),
    (r'\bwget\b.*\|\s*sudo\s*(sh|bash)\b', "Blocked dangerous command: wget | sudo sh is not allowed."),

    # chmod -R 777
    (r'\bchmod\s+(-R\s+)?777\b', "Blocked dangerous command: chmod 777 is not allowed."),
    (r'\bchmod\s+777\s+-R\b', "Blocked dangerous command: chmod 777 -R is not allowed."),

    # chown -R
    (r'\bchown\s+-R\b', "Blocked dangerous command: chown -R is not allowed without review."),

    # docker system prune -a
    (r'\bdocker\s+system\s+prune\s+-a', "Blocked dangerous command: docker system prune -a is not allowed."),
]

# ファイルアクセスのブロックパターン
SENSITIVE_FILE_PATTERNS = [
    # .env ファイル（完全一致 or ディレクトリ区切り後）
    (r'(^|/)\.env$', "Blocked access to sensitive file: .env"),
    (r'(^|/)\.env\.', "Blocked access to sensitive file: .env.*"),

    # secrets / secret ディレクトリ
    (r'(^|/)secrets/', "Blocked access to secrets/ directory."),
    (r'(^|/)secret/', "Blocked access to secret/ directory."),

    # .git 配下
    (r'(^|/)\.git/', "Blocked access to .git/ directory."),

    # SSH 秘密鍵
    (r'(^|/)id_rsa', "Blocked access to sensitive file: SSH private key."),
    (r'(^|/)id_ed25519', "Blocked access to sensitive file: SSH private key."),
    (r'(^|/)id_ecdsa', "Blocked access to sensitive file: SSH private key."),

    # 証明書・鍵ファイル
    (r'\.pem$', "Blocked access to sensitive file: .pem certificate/key."),
    (r'\.key$', "Blocked access to sensitive file: .key file."),

    # private key を含むパス
    (r'private.*key', "Blocked access to sensitive file: private key."),

    # パストラバーサル
    (r'\.\./', "Blocked path traversal: paths containing ../ are not allowed."),
    (r'/\.\.', "Blocked path traversal: paths containing /.. are not allowed."),
]


def deny(reason: str) -> None:
    """ブロック結果を JSON で stdout に出力して終了する"""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


def check_bash_command(command: str) -> None:
    """Bash コマンドを危険パターンと照合する"""
    for pattern, reason in DANGEROUS_BASH_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            deny(reason)


def check_file_access(file_path: str) -> None:
    """ファイルパスを機密パターンと照合する"""
    # パスを正規化（ただし実際にファイルシステムにはアクセスしない）
    normalized = file_path.replace("\\", "/")
    for pattern, reason in SENSITIVE_FILE_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            deny(reason)


def extract_file_path(tool_input: dict) -> str | None:
    """ツール入力からファイルパスを取得する"""
    # Read, Edit, Write, MultiEdit で使われるパラメータ名
    for key in ("file_path", "filePath", "path"):
        if key in tool_input:
            return tool_input[key]
    return None


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        # JSON パース失敗時はブロックせず通過させる（Hook 自体が壊れて作業停止しないように）
        print(f"[Claude Hook] Warning: failed to parse input: {e}", file=sys.stderr)
        sys.exit(0)

    tool_name = data.get("toolName", "")
    tool_input = data.get("toolInput", {})

    # --- Bash コマンドのチェック ---
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        check_bash_command(command)

    # --- ファイルアクセスのチェック ---
    if tool_name in ("Read", "Edit", "Write", "MultiEdit"):
        file_path = extract_file_path(tool_input)
        if file_path:
            check_file_access(file_path)

        # MultiEdit は複数ファイルを含む場合がある
        if tool_name == "MultiEdit":
            edits = tool_input.get("edits", [])
            for edit in edits:
                fp = edit.get("file_path") or edit.get("filePath") or edit.get("path")
                if fp:
                    check_file_access(fp)

    # ブロック対象でなければ正常終了（何も出力しない）
    sys.exit(0)


if __name__ == "__main__":
    main()
