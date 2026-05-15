#!/usr/bin/env python3
"""
Claude Code Hook: PostToolUse Check
=====================================
Claude Code がファイルを編集した後に呼ばれ、
自動で Prettier フォーマットと npm test を実行する。

stdin から Hook 入力 JSON を受け取る。
"""

import json
import os
import shutil
import subprocess
import sys


# フォーマット対象の拡張子
FORMAT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".css", ".html"}

# 機密ファイル・ディレクトリのパターン（フォーマット対象外）
SENSITIVE_PATTERNS = [".env", "secret", ".git/", "id_rsa", "id_ed25519", ".pem", ".key", "private"]


def log(msg: str) -> None:
    """Hook ログを stderr に出力する（Claude Code に表示される）"""
    print(f"[Claude Hook] {msg}", file=sys.stderr)


def is_sensitive(path: str) -> bool:
    """機密ファイルかどうかを判定する"""
    normalized = path.lower().replace("\\", "/")
    for pattern in SENSITIVE_PATTERNS:
        if pattern in normalized:
            return True
    return False


def should_format(path: str) -> bool:
    """フォーマット対象かどうかを判定する"""
    if is_sensitive(path):
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in FORMAT_EXTENSIONS


def find_project_root() -> str:
    """プロジェクトルートを探す（環境変数 or カレントディレクトリ）"""
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def run_prettier(file_path: str, project_root: str) -> None:
    """Prettier でフォーマットする"""
    npx = shutil.which("npx")
    if not npx:
        log("npx not found, skipping prettier.")
        return

    package_json = os.path.join(project_root, "package.json")
    if not os.path.isfile(package_json):
        log("No package.json found, skipping prettier.")
        return

    # ファイルが存在するか確認
    if not os.path.isfile(file_path):
        log(f"File not found: {file_path}, skipping prettier.")
        return

    log(f"Running prettier: {file_path}")
    try:
        result = subprocess.run(
            [npx, "prettier", "--write", file_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
        )
        if result.returncode != 0:
            log(f"Prettier warning: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        log("Prettier timed out (30s).")
    except Exception as e:
        log(f"Prettier error: {e}")


def run_npm_test(project_root: str) -> None:
    """npm test を実行する"""
    package_json_path = os.path.join(project_root, "package.json")
    if not os.path.isfile(package_json_path):
        log("No package.json found, skipping npm test.")
        return

    # package.json に test スクリプトがあるか確認
    try:
        with open(package_json_path, "r") as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        test_script = scripts.get("test", "")
        # デフォルトの "no test specified" はスキップ
        if not test_script or "no test specified" in test_script:
            log("No test script configured, skipping npm test.")
            return
    except Exception:
        log("Could not read package.json, skipping npm test.")
        return

    npm = shutil.which("npm")
    if not npm:
        log("npm not found, skipping test.")
        return

    log("Running npm test")
    try:
        result = subprocess.run(
            [npm, "test"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_root,
        )
        if result.returncode != 0:
            log(f"Test failed:\n{result.stdout}\n{result.stderr}")
        else:
            log("Tests passed.")
    except subprocess.TimeoutExpired:
        log("npm test timed out (60s).")
    except Exception as e:
        log(f"Test error: {e}")


def extract_file_path(tool_input: dict) -> str | None:
    """ツール入力からファイルパスを取得する"""
    for key in ("file_path", "filePath", "path"):
        if key in tool_input:
            return tool_input[key]
    return None


def main():
    log("Post-edit check started")

    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        log(f"Warning: failed to parse input: {e}")
        sys.exit(0)

    tool_name = data.get("toolName", "")
    tool_input = data.get("toolInput", {})
    project_root = find_project_root()

    # 編集されたファイルパスを収集
    edited_files = []

    file_path = extract_file_path(tool_input)
    if file_path:
        edited_files.append(file_path)

    # MultiEdit の場合は複数ファイル
    if tool_name == "MultiEdit":
        for edit in tool_input.get("edits", []):
            fp = edit.get("file_path") or edit.get("filePath") or edit.get("path")
            if fp:
                edited_files.append(fp)

    # 重複を除去
    edited_files = list(dict.fromkeys(edited_files))

    # Prettier 実行
    for fp in edited_files:
        if should_format(fp):
            run_prettier(fp, project_root)

    # npm test 実行
    run_npm_test(project_root)

    log("Post-edit check completed")
    sys.exit(0)


if __name__ == "__main__":
    main()
