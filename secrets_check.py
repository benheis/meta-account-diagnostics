#!/usr/bin/env python3
"""
Pre-commit hook: scan staged files for secrets before they leave your machine.
Blocks the commit if it finds API tokens, access keys, or credential patterns.
"""

import re
import subprocess
import sys

PATTERNS = [
    (r"META_ACCESS_TOKEN\s*=\s*[A-Za-z0-9_\-]{20,}", "Meta access token"),
    (r"EAA[A-Za-z0-9]{30,}", "Meta / Facebook Bearer token"),
    (r"['\"]act_\d{10,}['\"]", "Meta Ad Account ID (hardcoded)"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI API key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"(?i)(password|secret|api_key|access_token)\s*=\s*['\"].{8,}['\"]", "Generic credential assignment"),
]

SKIP_FILES = {".env.example", "secrets_check.py", "SKILL.md", "README.md"}


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f not in SKIP_FILES]


def get_file_content(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f":{path}"], capture_output=True, text=True
    )
    return result.stdout


def main() -> int:
    files = get_staged_files()
    violations = []

    for path in files:
        content = get_file_content(path)
        for pattern, label in PATTERNS:
            if re.search(pattern, content):
                violations.append(f"  {path}: {label}")

    if violations:
        print("❌ Commit blocked — possible secrets detected:")
        for v in violations:
            print(v)
        print("\nReview these files and remove credentials before committing.")
        print("Add test/fixture files to SKIP_FILES in secrets_check.py if this is a false positive.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
