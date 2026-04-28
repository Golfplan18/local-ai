#!/usr/bin/env python3
"""
Portability linter for the Ora codebase.

Scans the repo for known cross-platform compatibility issues so that Windows
and Linux ports don't regress. Output is human-readable and re-runnable.

Usage:
    python3 scripts/check-portability.py
    python3 scripts/check-portability.py --quiet   (only show CRITICAL+HIGH)

Exit code: 0 if no CRITICAL findings, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".claude",
    "Ora.app", "Ora Models.app", "chromadb", "logs", "models",
    "logo", "output", "data", "browser-profiles", "browser-sessions",
    "vendor",
}
SKIP_FILE_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".icns", ".ico",
                       ".db", ".sqlite", ".sqlite3", ".bin", ".gguf",
                       ".safetensors", ".log", ".bak", ".woff", ".woff2",
                       ".ttf", ".otf", ".pdf", ".zip", ".tar", ".gz"}
SKIP_FILENAMES = {"check-portability.py"}

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int
    snippet: str
    note: str


def walk_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn in SKIP_FILENAMES:
                continue
            p = Path(dirpath) / fn
            if p.suffix.lower() in SKIP_FILE_SUFFIXES:
                continue
            yield p


def read_text(p: Path) -> str | None:
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    sample = raw[:4096]
    if sample.count(b"\x00") > 0:
        return None
    nonprintable = sum(1 for b in sample if b < 9 or (13 < b < 32) or b == 127)
    if sample and nonprintable / len(sample) > 0.05:
        return None
    try:
        return raw.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return None


def is_in_module_docstring(text: str, match_start: int) -> bool:
    """Heuristic: is the match inside the first triple-quoted block (module docstring)?"""
    head = text[:match_start]
    open_marker = head.find('"""')
    if open_marker == -1:
        open_marker = head.find("'''")
    if open_marker == -1:
        return False
    close_marker = text.find('"""', open_marker + 3)
    if close_marker == -1:
        close_marker = text.find("'''", open_marker + 3)
    if close_marker == -1:
        return False
    return open_marker < match_start < close_marker


# Each rule: (severity, rule_id, regex, applies_to_extensions, note)
# "applies_to_extensions" None means all text files.
RULES = [
    ("CRITICAL", "posix-pkill",
        re.compile(r"\bpkill\b"),
        {".sh", ".bash", ".zsh"},
        "pkill is POSIX-only; Windows needs taskkill or Python psutil"),

    ("CRITICAL", "homebrew-python-hardcode",
        re.compile(r"/opt/homebrew/bin/python3?"),
        {".sh", ".bash", ".zsh", ".py"},
        "Homebrew path is macOS-only; use a fallback chain or 'python3' from PATH"),

    ("CRITICAL", "macos-osascript",
        re.compile(r"\bosascript\b"),
        None,
        "osascript is macOS-only; Windows/Linux need different notification mechanism"),

    ("CRITICAL", "macos-lsregister",
        re.compile(r"\blsregister\b"),
        None,
        "lsregister is macOS-only (CoreServices)"),

    ("CRITICAL", "macos-iconutil",
        re.compile(r"\biconutil\b"),
        {".sh", ".bash", ".zsh", ".py"},
        "iconutil is macOS-only; .icns generation should be guarded by sys.platform check"),

    ("CRITICAL", "macos-pmset",
        re.compile(r"\bpmset\b"),
        None,
        "pmset is macOS-only"),

    ("CRITICAL", "macos-launchctl",
        re.compile(r"\blaunchctl\b"),
        None,
        "launchctl is macOS-only"),

    ("CRITICAL", "macos-pbcopy-pbpaste",
        re.compile(r"\bpb(copy|paste)\b"),
        None,
        "pbcopy/pbpaste are macOS-only"),

    ("HIGH", "posix-pgrep",
        re.compile(r"\bpgrep\b"),
        None,
        "pgrep is POSIX-only; Windows needs psutil or tasklist. OK if guarded by platform check."),

    ("HIGH", "tmp-hardcode",
        re.compile(r'(["\'])(/tmp/)'),
        {".py", ".sh", ".bash", ".zsh", ".js"},
        "/tmp/ is Unix-only; use tempfile module (Python) or %TEMP% (Windows)"),

    ("HIGH", "library-app-support-hardcode",
        re.compile(r"~/Library/|/Users/[^/]+/Library/"),
        {".py", ".sh", ".bash", ".zsh", ".js"},
        "macOS-only path; needs platform branching for Windows (%APPDATA%) and Linux (~/.config)"),

    ("HIGH", "applications-hardcode",
        re.compile(r"/Applications/"),
        None,
        "macOS-only path"),

    ("MEDIUM", "users-oracle-hardcode",
        re.compile(r"/Users/oracle/"),
        {".py", ".sh", ".bash", ".zsh", ".js", ".json"},
        "Hardcoded user-specific path; should use $HOME or expanduser. JSON configs are usually regenerated by installer — verify."),

    ("MEDIUM", "macos-open-command-bare",
        re.compile(r"\bsubprocess\.(?:run|call|Popen)\(\s*\[?\s*['\"]open['\"]"),
        {".py"},
        "subprocess call to 'open' is macOS-only; Linux uses xdg-open, Windows uses os.startfile"),

    ("LOW", "darwin-platform-check",
        re.compile(r"sys\.platform\s*==\s*['\"]darwin['\"]|platform\.system\(\)\s*==\s*['\"]Darwin['\"]"),
        {".py"},
        "Platform check found — verify the non-Darwin branch is implemented (this rule reports for review, not as a bug)"),
]


# Files where macOS-only paths are intentional (explicitly Mac-only code paths or docs
# that describe per-platform behavior including the Mac branch)
ALLOWED_MAC_ONLY_FILES = {
    "Ora.app/Contents/MacOS/ai",
    "Ora Models.app/Contents/MacOS/ai",
    "swap-icon.sh",
    "publish.sh",
    "installer/phase2/layer11-app-bundle.md",
    "installer/phase1/layer5-commercial-ai-connections.md",
    "installer/phase2/layer7-desktop-launcher.md",
    "orchestrator/tools/bash_execute.py",
    "orchestrator/tests/test_visual_extraction.py",
    "start.sh",
    "stop.sh",
}


def is_allowed_mac_only(rel_path: str) -> bool:
    return any(rel_path == p or rel_path.startswith(p + "/") for p in ALLOWED_MAC_ONLY_FILES)


# File-level patterns that indicate platform-conditional code is present.
# When found in a file, downgrade matches of platform-specific commands within that file.
PYTHON_PLATFORM_GUARD_RE = re.compile(
    r'sys\.platform\s*==\s*[\'"](darwin|linux|win32)[\'"]'
    r'|sys\.platform\s*\.\s*startswith\s*\(\s*[\'"]linux[\'"]'
    r'|platform\.system\(\)\s*==\s*[\'"](Darwin|Linux|Windows)[\'"]'
)
SH_PYTHON_FALLBACK_RE = re.compile(r'command\s+-v\s+python3?')


def has_platform_branching(text: str, ext: str) -> bool:
    if ext == ".py":
        return bool(PYTHON_PLATFORM_GUARD_RE.search(text))
    if ext in {".sh", ".bash", ".zsh"}:
        return bool(SH_PYTHON_FALLBACK_RE.search(text))
    return False


def scan(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in walk_files(root):
        rel = path.relative_to(root).as_posix()
        text = read_text(path)
        if text is None:
            continue
        ext = path.suffix.lower()
        for severity, rule_id, regex, exts, note in RULES:
            if exts is not None and ext not in exts:
                continue
            for m in regex.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                if line_end == -1:
                    line_end = len(text)
                snippet = text[line_start:line_end].strip()[:120]

                in_docstring = ext == ".py" and is_in_module_docstring(text, m.start())

                downgraded_severity = severity
                if is_allowed_mac_only(rel):
                    downgraded_severity = "INFO"
                elif in_docstring and severity == "CRITICAL":
                    downgraded_severity = "LOW"

                findings.append(Finding(
                    severity=downgraded_severity,
                    rule=rule_id,
                    file=rel,
                    line=line_no,
                    snippet=snippet,
                    note=note + (" (inside module docstring)" if in_docstring else ""),
                ))

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.file, f.line))
    return findings


def check_missing_files(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    pairs = [
        ("start.sh", "start.bat", "CRITICAL",
         "Bash launcher exists but Windows .bat equivalent is missing — Windows users have no launcher"),
        ("stop.sh", "stop.bat", "CRITICAL",
         "Bash stop script exists but Windows .bat equivalent is missing"),
    ]
    for sh, bat, sev, note in pairs:
        if (root / sh).exists() and not (root / bat).exists():
            findings.append(Finding(
                severity=sev, rule="missing-windows-launcher",
                file=sh, line=0, snippet=f"(no {bat} found alongside)",
                note=note,
            ))
    return findings


def render(findings: list[Finding], quiet: bool) -> str:
    if not findings:
        return "No portability issues found.\n"

    by_sev: dict[str, list[Finding]] = {}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)

    lines = []
    counts = ", ".join(f"{sev}: {len(items)}" for sev, items in sorted(by_sev.items(), key=lambda kv: SEVERITY_ORDER.get(kv[0], 99)))
    lines.append(f"Portability scan: {counts}")
    lines.append("")

    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        if sev not in by_sev:
            continue
        if quiet and sev not in ("CRITICAL", "HIGH"):
            continue
        lines.append(f"--- {sev} ({len(by_sev[sev])}) ---")
        for f in by_sev[sev]:
            location = f"{f.file}:{f.line}" if f.line else f.file
            lines.append(f"[{f.rule}] {location}")
            lines.append(f"    {f.snippet}")
            lines.append(f"    why: {f.note}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Ora portability linter")
    parser.add_argument("--quiet", action="store_true", help="Only show CRITICAL and HIGH findings")
    parser.add_argument("--root", default=str(ROOT), help="Root directory to scan (default: repo root)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = scan(root) + check_missing_files(root)
    print(render(findings, quiet=args.quiet))

    critical = [f for f in findings if f.severity == "CRITICAL"]
    sys.exit(1 if critical else 0)


if __name__ == "__main__":
    main()
