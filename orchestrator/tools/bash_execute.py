"""Bash command execution with safety classification, output truncation,
working directory containment, and background process management."""

import os
import re
import shlex
import shutil
import signal
import subprocess
import time

try:
    import runtime_paths as _rp
    WORKSPACE = _rp.WORKSPACE
except ImportError:  # pragma: no cover
    WORKSPACE = os.path.expanduser("~/ora/")


def _posix_shell_path() -> str | None:
    """The POSIX shell executable commands must run under, or None.

    On POSIX platforms returns None: ``shell=True``'s default (/bin/sh)
    already IS the POSIX shell the profiler models. On Windows,
    ORA_POSIX_SHELL must name an actual shell executable (absolute path to
    an existing file, or a name resolvable on PATH — e.g. Git Bash's
    bash.exe or a WSL sh shim). A flag-style value ("1", a nonexistent
    path) is rejected: the profiler and the executed shell must be the SAME
    shell, so a declaration that can't actually be executed counts as no
    declaration at all."""
    if os.name != "nt":
        return None
    declared = (os.environ.get("ORA_POSIX_SHELL") or "").strip()
    if not declared:
        return None
    if os.path.isabs(declared):
        return declared if os.path.isfile(declared) else None
    return shutil.which(declared)


def _posix_shell_available() -> bool:
    """The shell profiler models POSIX shell grammar (shlex, cd/pushd, &&,
    redirects). It is valid only on a POSIX shell. On Windows the tool
    fails closed unless ORA_POSIX_SHELL names a real POSIX shell executable
    (WSL/git-bash) — which execute_command then also runs commands under,
    so the profiled grammar and the executing shell can never diverge.
    This is NOT full Windows shell profiling; it is a conservative gate."""
    if os.name != "nt":
        return True
    return _posix_shell_path() is not None

# ── Background process tracking ────────────────────────────────────────────
MANAGED_PROCESSES = []

# ── Command classifier (deterministic, rule-based) ─────────────────────────

BLOCKED_PATTERNS = [
    r"sudo\s+rm\s+-rf\s+/\s*$",
    r":\(\)\{\s*:\|:&\s*\};:",        # fork bomb
    r">\s*/dev/sd[a-z]",
    r"\bmkfs\b",
    r"(>|>>)\s*/(System|usr|bin|sbin|etc)/",
]

DANGEROUS_PATTERNS = [
    (r"\brm\b", "rm command detected — may delete files"),
    (r"\bchmod\b", "chmod changes file permissions"),
    (r"\bchown\b", "chown changes file ownership"),
    (r"\bsudo\b", "sudo runs with elevated privileges"),
    (r"curl\s.*\|\s*(sh|bash)", "piped download to shell — arbitrary code execution"),
    (r"wget\s.*\|\s*(sh|bash)", "piped download to shell — arbitrary code execution"),
    (r"\bdd\b", "dd writes raw data — can overwrite devices"),
    (r"\bkill\b", "kill terminates processes"),
    (r"\bpkill\b", "pkill terminates processes by pattern"),
    (r"\bsystemctl\b", "systemctl modifies system services"),
    (r"\blaunchctl\b", "launchctl modifies macOS services"),
    (r"/\s+-rf\b", "recursive force deletion with broad scope"),
    (r"\bfind\b.*-delete\b", "find with -delete removes matching files"),
]

SAFE_COMMANDS = {
    "echo", "cat", "ls", "pwd", "whoami", "date", "which", "uname",
    "head", "tail", "wc", "grep", "rg", "find", "python3", "python",
    "git", "npm", "node", "pip3", "pip", "brew",
}

SAFE_GIT_SUBCOMMANDS = {"status", "log", "diff", "branch", "show", "tag", "remote"}


def classify_command(command_string: str) -> dict:
    """Classify a command by risk level. Returns {level, reason}."""
    cmd = command_string.strip()

    # Rule 1: blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd):
            return {"level": "blocked",
                    "reason": f"This command could cause irreversible system damage: matched pattern '{pattern}'"}

    # Rule 2: dangerous patterns
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return {"level": "dangerous", "reason": reason}

    # Rule 3: check file paths for out-of-workspace references
    ws_real = os.path.realpath(WORKSPACE)
    sensitive_dirs = ["/System", "/usr", "/bin", "/sbin", "/etc",
                      "/Library", "/var", "/private"]
    # Simple path extraction: tokens starting with / or ~
    tokens = cmd.split()
    for token in tokens:
        if token.startswith("/") or token.startswith("~"):
            resolved = os.path.realpath(os.path.expanduser(token))
            for sd in sensitive_dirs:
                if resolved.startswith(sd):
                    return {"level": "dangerous",
                            "reason": f"Command references sensitive directory: {resolved}"}

    # Rule 4: safe commands
    base_cmd = cmd.split("|")[0].strip().split()[0] if cmd.strip() else ""
    # Handle path-qualified commands
    base_cmd = os.path.basename(base_cmd)

    if base_cmd in SAFE_COMMANDS:
        # Special handling for git — only read-only subcommands are safe
        if base_cmd == "git":
            parts = cmd.split("|")[0].strip().split()
            if len(parts) >= 2 and parts[1] in SAFE_GIT_SUBCOMMANDS:
                return {"level": "safe", "reason": f"Read-only git command: git {parts[1]}"}
            return {"level": "moderate", "reason": f"Git write command: {' '.join(parts[:2])}"}
        return {"level": "safe", "reason": "Read-only command within workspace"}

    # Rule 5: default to moderate
    return {"level": "moderate", "reason": "Unclassified command — treated as moderate risk"}


# ── Shell capability profiles (Execution Review Phase 1) ───────────────────
# Allowlist-with-known-profiles per spec §7: a shell command runs un-gated
# only when EVERY segment of it matches a profile whose mutability /
# sensitivity / egress are known. Anything else is unknown → the dispatcher
# gate fails closed (blocked + queued for approval). This closes the old
# silent door where the SAFE_COMMANDS tier (including interpreters and
# package managers) executed with zero prompting in every permission mode.
#
# Matching is flag-aware and fail-closed on unrecognized shapes:
#   - compound commands are split on && || ; | and newlines (quote-aware);
#     each segment must independently match, and the whole command takes
#     the MOST severe axes across segments;
#   - command substitution ($(...), backticks), subshells, and redirections
#     to absolute paths outside the workspace make the command unknown;
#   - a profiled command with an explicitly irreversible flag (git push
#     --force et al.) classifies irreversible even though its bare form is
#     profiled.
#
# The profile seed set below is a PROVISIONAL tuning surface: seeded from
# the Phase-0 command inventory, meant to be extended from observed gate
# events, not from guesswork.

_READ_ONLY_BASES = {
    "ls", "cat", "head", "tail", "wc", "pwd", "which", "date", "whoami",
    "uname", "echo", "printf", "grep", "rg", "sort", "uniq", "cut", "tr",
    "stat", "file", "du", "df", "basename", "dirname", "realpath", "true",
    "false", "test", "[", "env", "sw_vers", "sysctl", "md5", "shasum",
    "diff", "comm", "jq", "column", "xxd", "strings", "sed", "awk",
    # Additional read-only viewers/decoders (also in _FILE_OPERAND_READERS,
    # so their operands are surfaced for secret-read escalation).
    "nl", "tac", "rev", "base64", "od", "less", "more", "readlink", "cmp",
}

# File-reading commands whose non-option operands are files to READ — every
# bare filename counts (so 'cat id_rsa' surfaces id_rsa as a read path, which
# the dispatcher resolves against the effective cwd and gates if secret).
_FILE_OPERAND_READERS = {
    "cat", "head", "tail", "wc", "od", "xxd", "strings", "md5", "shasum",
    "file", "stat", "cut", "sort", "uniq", "comm", "diff", "column", "nl",
    "base64", "less", "more", "tac", "rev", "realpath", "readlink", "cmp",
}
# Commands whose FIRST operand is a pattern/filter/program and the REST are
# files (grep pattern, jq filter, awk/sed program).
_PATTERN_THEN_FILE_READERS = {"grep", "rg", "egrep", "fgrep", "jq", "awk"}

# Archive / compress / transform commands that READ their file operands in
# full (then write to stdout or an archive). A secret operand here is an
# un-gated read unless surfaced. Distinct from _REVERSIBLE_BASES (their
# mutability stays write; this set only adds read-path surfacing).
_ARCHIVE_TRANSFORM_BASES = {
    "tar", "gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz", "zstd",
    "zip", "unzip", "ffmpeg", "pandoc", "whisper-cli", "openssl",
}

# Local write, cheaply undoable (workspace artifacts, media transforms).
_REVERSIBLE_BASES = {
    "mkdir", "touch", "cp", "mv", "ln", "tar", "gzip", "gunzip", "zip",
    "unzip", "ffmpeg", "pandoc", "whisper-cli", "yt-dlp", "tee",
}
# Of those, the ones that reach the network.
_REVERSIBLE_EGRESS_EXTERNAL = {"yt-dlp"}

_GIT_READ_SUBCOMMANDS = {
    "status", "log", "diff", "show", "tag", "remote", "rev-parse",
    "ls-files", "blame", "shortlog", "describe", "config",
}
_GIT_REVERSIBLE_SUBCOMMANDS = {
    "add", "commit", "checkout", "switch", "restore", "merge", "stash",
    "reset", "branch", "init", "rm", "mv", "cherry-pick", "revert", "worktree",
}
_GIT_EGRESS_SUBCOMMANDS = {"fetch", "pull", "clone"}
_GIT_IRREVERSIBLE_PUSH_FLAGS = {
    "--force", "-f", "--force-with-lease", "--delete", "-d", "--mirror",
    "--prune",
}

_UNKNOWN = {"mutability": "irreversible", "sensitivity": "secret",
            "egress": "external", "unknown": True}

# Utilities whose primary contract is to invoke another executable.  They are
# deliberately explicit even though most already fall through to _UNKNOWN:
# this is the audit surface that prevents a future allowlist addition from
# silently turning a launcher into a terminal read/write profile.
_COMMAND_LAUNCHING_WRAPPERS = {
    "command", "exec", "nice", "nohup", "timeout", "xargs", "parallel",
    "setsid", "stdbuf", "ionice", "taskset", "chroot", "sudo", "doas",
    "su", "runuser", "watch",
}

_FIND_EXECUTION_PREDICATES = {"-exec", "-execdir", "-ok", "-okdir"}

_VERSION_HELP_BASES = (
    _READ_ONLY_BASES | _REVERSIBLE_BASES | {
        "find", "git", "python3", "python", "pip", "pip3", "npm", "node",
        "brew", "curl", "wget", "rm",
    }
)

_REDIRECT_RE = re.compile(r"^\d*(>>|>)$")            # '>', '>>', '2>', '1>>'
_REDIRECT_PREFIX_RE = re.compile(r"^\d*(>>|>)(.+)$")  # '2>/dev/null', '>file'


def _redirect_write_targets(tokens: list[str]) -> list[str]:
    """Extract output-redirection target paths from a token list.

    Handles spaced ('> path') and glued ('>path', '2>/dev/null') forms.
    Any redirect makes the segment a write; the target path is fed through
    the sensitivity/protected resolver by the dispatcher.
    """
    targets = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if _REDIRECT_RE.match(t):
            if i + 1 < len(tokens):
                targets.append(tokens[i + 1])
                i += 2
                continue
        m = _REDIRECT_PREFIX_RE.match(t)
        if m and m.group(2):
            targets.append(m.group(2))
        i += 1
    return targets


_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _env_is_inspection_only(args: list[str]) -> bool:
    """Return True only when ``env`` has no utility operand.

    POSIX ``env`` prints the resulting environment when options and
    NAME=VALUE assignments exhaust its argv; otherwise it launches the first
    remaining operand.  Only the small cross-platform inspection grammar is
    admitted here.  Ambiguous or execution-bearing options (notably ``-S``)
    fail closed with the utility-bearing forms.
    """
    i = 0
    while i < len(args):
        token = args[i]
        if _ENV_ASSIGN_RE.match(token):
            i += 1
            continue
        if token in {
            "-i", "--ignore-environment", "-0", "--null", "-v", "--debug",
            "--help", "--version",
        }:
            i += 1
            continue
        if token in {"-u", "--unset"}:
            if i + 1 >= len(args) or not args[i + 1]:
                return False
            i += 2
            continue
        if token.startswith("--unset=") and token.split("=", 1)[1]:
            i += 1
            continue
        if token == "--":
            return i + 1 == len(args)
        return False
    return True


def _has_command_launching_option(base: str, args: list[str]) -> bool:
    """Recognize child-process options on otherwise profiled utilities."""
    if base == "find":
        return any(arg in _FIND_EXECUTION_PREDICATES for arg in args)
    if base == "tar":
        for arg in args:
            if arg in {
                "-I", "--use-compress-program", "--to-command",
                "--info-script", "--rsh-command",
            }:
                return True
            if arg.startswith((
                "-I", "--use-compress-program=", "--to-command=",
                "--info-script=", "--rsh-command=",
                "--checkpoint-action=exec=",
            )):
                return True
        return False
    if base == "pandoc":
        return any(
            arg in {"-F", "--filter", "-L", "--lua-filter", "--pdf-engine"}
            or arg.startswith((
                "-F", "-L", "--filter=", "--lua-filter=", "--pdf-engine=",
            ))
            for arg in args
        )
    if base == "yt-dlp":
        return any(
            arg == "--exec" or arg.startswith("--exec=")
            or arg.startswith("--exec-before-download")
            or arg.startswith("--exec-after-download")
            for arg in args
        )
    if base == "zip":
        return any(
            arg == "-TT" or arg.startswith("-TT")
            or arg == "--unzip-command"
            or arg.startswith("--unzip-command=")
            for arg in args
        )
    return False


def _strip_env_prefix(tokens: list[str]) -> list[str]:
    """Drop leading NAME=VALUE assignment tokens (env prefixes like
    'FOO=1 cmd') so the real command verb is tokens[0]."""
    while len(tokens) > 1 and _ENV_ASSIGN_RE.match(tokens[0]):
        tokens = tokens[1:]
    return tokens


def _cd_effect(segment: str):
    """If ``segment`` is a cd/pushd/popd, return ('cd'|'pushd'|'popd', arg);
    else (None, None). ``arg`` is None for bare cd/popd."""
    import shlex
    try:
        tokens = _strip_env_prefix(shlex.split(segment))
    except ValueError:
        return (None, None)
    if not tokens:
        return (None, None)
    base = os.path.basename(tokens[0])
    if base not in ("cd", "pushd", "popd"):
        return (None, None)
    rest = tokens[1:]
    # A bare '-' target means "previous directory" — unmodelable.
    if "-" in rest:
        return (base, "-")
    arg = next((t for t in rest if not t.startswith("-")), None)
    return (base, arg)


def _command_target_paths(segment: str) -> tuple[list[str], list[str]]:
    """Return (read_paths, write_paths) for one command segment.

    Load-bearing for the gate: the dispatcher runs every returned path
    through resolve_path_sensitivity (so `cat ~/.ssh/id_rsa` gates as a
    secret read) and is_protected_config_path (so `echo x > config/hooks/y`
    gates as a protected write). Best-effort and conservative — an
    unparseable segment yields no paths but resolve_shell_profile has
    already marked it unknown."""
    import shlex
    try:
        tokens = _strip_env_prefix(shlex.split(segment))
    except ValueError:
        return [], []
    if not tokens:
        return [], []
    base = os.path.basename(tokens[0])
    args = tokens[1:]
    non_flags = [t for t in args if not t.startswith("-")
                 and not _REDIRECT_RE.match(t)
                 and not _REDIRECT_PREFIX_RE.match(t)]
    reads, writes = [], []
    writes.extend(_redirect_write_targets(tokens))

    def _looks_like_path(tok: str) -> bool:
        return ("/" in tok or tok.startswith("~") or tok.startswith(".")
                or os.path.sep in tok)

    # A -f/--file program/pattern file (grep/sed/awk/jq) is READ in full —
    # surface it (both '-f path' and glued '-fpath'/'--file=path') so a
    # secret passed as the program file gates. Handled here, before the flag
    # filter drops it.
    if base in ("grep", "rg", "egrep", "fgrep", "sed", "awk", "jq"):
        for i, a in enumerate(args):
            if a in ("-f", "--file", "--exclude-from", "--include-from") \
                    and i + 1 < len(args):
                reads.append(args[i + 1])
            elif a.startswith("-f") and len(a) > 2 and not a.startswith("--"):
                reads.append(a[2:])
            elif a.startswith("--file="):
                reads.append(a.split("=", 1)[1])

    # Archive / transform / compress commands read their input file operands
    # and write a named output (archive, -o file, or in-place .gz). Which
    # operand is the output cannot be told reliably across tar's combined
    # flags, zip's leading archive, pandoc's -o, ffmpeg's trailing output,
    # gzip's in-place write, etc. — so surface EVERY path operand as BOTH a
    # read AND a write. The dispatcher then gates a secret INPUT (read side)
    # and a protected-config/secret OUTPUT (write side, e.g.
    # 'tar czf ~/ora/config/hooks/x.tgz …'). Over-gating only occurs when an
    # operand is itself protected or secret — where gating is the safe call.
    if base in _ARCHIVE_TRANSFORM_BASES:
        reads.extend(non_flags)
        # flag-attached output targets (pandoc/openssl -o, ffmpeg irrelevant
        # here since its output is a positional non_flag) are also writes.
        for i, a in enumerate(args):
            if a in ("-o", "--output", "-out") and i + 1 < len(args):
                writes.append(args[i + 1])
            elif a.startswith("--output="):
                writes.append(a.split("=", 1)[1])
        writes.extend(non_flags)

    if base == "ls":
        # Directory listing is filesystem access even when its operand is a
        # bare relative name. With no operand it addresses the effective cwd.
        reads.extend(non_flags or ["."])
    elif base == "find":
        # The first positional is the traversal root; later positionals are
        # expression operands, not additional files.
        reads.append(non_flags[0] if non_flags else ".")
    elif base in ("tee", "mkdir", "touch", "mkfifo", "mknod", "rmdir", "rm"):
        # Every operand is a created/written target — surface all (bare names
        # resolve against the effective cwd) so a target in a protected path
        # gates like file_write.  ``rm`` is included even though its effect is
        # deletion: G1.22 needs the exact target in order to distinguish an
        # approvable scoped deletion from prohibited root/state destruction.
        writes.extend(non_flags)
    elif base in ("cp", "mv", "ln") and len(non_flags) >= 2:
        writes.append(non_flags[-1])
        reads.extend(non_flags[:-1])
    elif base == "dd":
        for a in args:
            if a.startswith("of="):
                writes.append(a[3:])
            elif a.startswith("if="):
                reads.append(a[3:])
    elif base == "sed" and any(f.startswith("-i") for f in args if f.startswith("-")):
        # sed -i writes its file operands in place (first operand is the
        # script); surface every operand-file as a write, bare names included.
        writes.extend(non_flags[1:])
    elif base in ("curl", "wget"):
        # Download output targets: -o/--output (file), --output-dir (dir),
        # wget -O/--output-document (file), -P/--directory-prefix (dir).
        arg_out = {"-o", "--output", "--output-dir", "-P",
                   "--directory-prefix", "--output-document"}
        for i, a in enumerate(args):
            if a in arg_out and i + 1 < len(args):
                writes.append(args[i + 1])
            elif a == "-O" and base == "wget" and i + 1 < len(args):
                writes.append(args[i + 1])
            elif a.startswith(("--output=", "--output-dir=",
                               "--output-document=", "--directory-prefix=")):
                writes.append(a.split("=", 1)[1])
            elif base == "curl" and a.startswith("-o") and len(a) > 2:
                writes.append(a[2:])
            elif base == "wget" and a.startswith("-O") and len(a) > 2:
                writes.append(a[2:])
    elif base == "yt-dlp":
        # Network download; its -o/-P output path is a write. The default
        # (cwd) write is covered by the dispatcher's cwd protected-path check.
        for i, a in enumerate(args):
            if a in ("-o", "--output", "-P", "--paths") and i + 1 < len(args):
                writes.append(args[i + 1])
    elif base == "rg":
        # ripgrep defaults to recursive traversal of cwd when no path follows
        # the pattern.
        reads.extend(non_flags[1:] or ["."])
    elif base == "sed" or base in _PATTERN_THEN_FILE_READERS:
        # grep/rg/jq: first operand is the pattern/filter, the rest are the
        # files/dirs read. Bare filenames count — 'grep k id_rsa' reads id_rsa.
        reads.extend(non_flags[1:])
    elif base in _FILE_OPERAND_READERS:
        # cat/head/tail/wc/…: EVERY non-option operand is a file read, even a
        # bare filename ('cat id_rsa'). The dispatcher resolves each against
        # the effective cwd, so a bare secret name in a secret cwd still gates.
        reads.extend(non_flags)
    elif base in _READ_ONLY_BASES or base == "find":
        reads.extend(t for t in non_flags if _looks_like_path(t))
    return reads, writes


def _arg_touches_dot_ora(args: list) -> bool:
    """True if any non-flag token names a ``.ora`` PATH SEGMENT (Phase 8 Chunk C
    §6). Segment match (not substring) so ``.orained`` is not a false hit;
    separator-agnostic + case-folded so a Windows / macOS-case-variant pathspec
    can't slip the git-route protection."""
    for a in args:
        if not a or a.startswith("-"):
            continue
        low = a.replace("\\", "/").lower()
        if ".ora" in low.split("/"):
            return True
    return False


def _segment_axes(segment: str) -> dict:
    """Axes for ONE simple command segment, or _UNKNOWN."""
    import shlex
    try:
        tokens = _strip_env_prefix(shlex.split(segment))
    except ValueError:
        return dict(_UNKNOWN)
    if not tokens:
        return {"mutability": "read", "sensitivity": "public", "egress": "none"}
    base = os.path.basename(tokens[0])
    args = tokens[1:]
    flags = [t for t in args if t.startswith("-")]

    # Any output redirection makes this segment a write regardless of verb
    # (the module header promised this; the write target's sensitivity is
    # resolved by the dispatcher via _command_target_paths).
    _redir_writes = _redirect_write_targets(tokens)

    # A known profile is valid only when it describes every executable the
    # shell can launch. ``env`` is terminal only when options/assignments
    # exhaust argv; every utility-bearing or ambiguous form fails closed.
    if base == "env":
        if not _env_is_inspection_only(args):
            return dict(_UNKNOWN)
        return {"mutability": "reversible_write" if _redir_writes else "read",
                "sensitivity": "private", "egress": "none"}
    if base in _COMMAND_LAUNCHING_WRAPPERS or base == "awk":
        return dict(_UNKNOWN)
    if _has_command_launching_option(base, args):
        return dict(_UNKNOWN)

    # cd / export / pushd / popd as leading no-op prefixes: read-neutral.
    # NOTE: `source` (and its POSIX synonym `.`) are deliberately NOT here — they
    # execute the CONTENTS of a file (arbitrary, model-editable code), so they are
    # a shell side door and must fail closed like `bash x.sh` / `eval` (§7), never
    # classify as a read. `.` already falls through to _UNKNOWN; `source` must too.
    if base in ("cd", "export", "pushd", "popd", "set", "unset",
                "ps", "hostname", "uptime", "id", "sleep", "true", "false"):
        return {"mutability": "reversible_write" if _redir_writes else "read",
                "sensitivity": "private", "egress": "none"}
    # A single help/version argument is a read only for an already-known
    # utility.  Never let ``unknown-executable --help`` create a profile for
    # an arbitrary binary.
    if base in _VERSION_HELP_BASES and len(args) == 1 and args[0] in {
        "--version", "-V", "--help", "-h",
    }:
        return {"mutability": "reversible_write" if _redir_writes else "read",
                "sensitivity": "private", "egress": "none"}

    if base in _READ_ONLY_BASES:
        # sed/awk can write via -i / redirection; -i makes it a write.
        if base == "sed" and any(f.startswith("-i") for f in flags):
            return {"mutability": "reversible_write", "sensitivity": "private",
                    "egress": "none"}
        if base == "find" and (
            "-delete" in args or _has_command_launching_option(base, args)
        ):
            return dict(_UNKNOWN)
        return {"mutability": "reversible_write" if _redir_writes else "read",
                "sensitivity": "private", "egress": "none"}
    if base == "find":
        if "-delete" in args or _has_command_launching_option(base, args):
            return dict(_UNKNOWN)
        return {"mutability": "read", "sensitivity": "private", "egress": "none"}

    if base in _REVERSIBLE_BASES:
        egress = "external" if base in _REVERSIBLE_EGRESS_EXTERNAL else "none"
        return {"mutability": "reversible_write", "sensitivity": "private",
                "egress": egress}

    if base == "git":
        sub = next((t for t in args if not t.startswith("-")), "")
        # Execution Review Phase 8 Chunk C (§6): a git WRITE subcommand whose
        # pathspec touches a `.ora/` directory (checkout/restore/mv/add/rm/…
        # <ref> -- .ora/tools/x.py) surfaces NO write_path to
        # is_protected_config_path, so it would run ungated and the Chunk-B
        # delta commit would then materialize the tampered check for that turn's
        # OWN review. Escalate to irreversible so the gate fires (the write-gate
        # raises the bar; the §12 verify stage is the architectural closure).
        # `git apply <patch>` naming `.ora` inside the patch is NOT arg-visible —
        # a disclosed residual, not a claim of complete closure.
        if sub not in _GIT_READ_SUBCOMMANDS and _arg_touches_dot_ora(args):
            egress = "external" if (sub in _GIT_EGRESS_SUBCOMMANDS
                                    or sub == "push") else "none"
            return {"mutability": "irreversible", "sensitivity": "private",
                    "egress": egress, "protected_config": True}
        if sub == "push":
            if any(f in _GIT_IRREVERSIBLE_PUSH_FLAGS for f in flags):
                return {"mutability": "irreversible", "sensitivity": "private",
                        "egress": "external"}
            return {"mutability": "external_write", "sensitivity": "private",
                    "egress": "external"}
        if sub in _GIT_READ_SUBCOMMANDS:
            return {"mutability": "read", "sensitivity": "private",
                    "egress": "none"}
        if sub in _GIT_REVERSIBLE_SUBCOMMANDS:
            return {"mutability": "reversible_write", "sensitivity": "private",
                    "egress": "none"}
        if sub in _GIT_EGRESS_SUBCOMMANDS:
            return {"mutability": "reversible_write", "sensitivity": "private",
                    "egress": "external"}
        return dict(_UNKNOWN)

    if base in ("python3", "python"):
        # Every form runs code Ora cannot see inside — an inline snippet
        # (-c), a repo script (x.py the model may have edited), or a module
        # (-m unittest discovers and runs repo test files). Classifying any
        # of these as a mere "write" is the shell side door: they launder
        # arbitrary execution through a profiled command. Fail closed until
        # the Phase-5 evidence runner can run them under real constraints.
        # (The sanctioned path for inline Python is the sandboxed
        # code_execute tool.)
        return dict(_UNKNOWN)

    if base in ("pip", "pip3"):
        sub = next((t for t in args if not t.startswith("-")), "")
        if sub in ("list", "show", "freeze", "check"):
            return {"mutability": "read", "sensitivity": "private",
                    "egress": "none"}
        # install/download run arbitrary setup.py from fetched packages →
        # fail closed (same opaque-execution class as the script runners).
        return dict(_UNKNOWN)

    if base == "npm":
        sub = next((t for t in args if not t.startswith("-")), "")
        if sub in ("ls", "view", "outdated"):
            return {"mutability": "read", "sensitivity": "private",
                    "egress": "external"}
        # test/run/run-script run package.json scripts the model can edit;
        # install/ci/update run arbitrary package lifecycle scripts. All
        # execute opaque code → fail closed until Phase 5.
        return dict(_UNKNOWN)

    if base == "node":
        # Runs run.js / any .js the model may have edited → fail closed.
        return dict(_UNKNOWN)

    if base == "brew":
        sub = next((t for t in args if not t.startswith("-")), "")
        if sub in ("list", "info", "search", "--version"):
            return {"mutability": "read", "sensitivity": "private",
                    "egress": "external"}
        # install/upgrade/tap run arbitrary formula code → fail closed.
        return dict(_UNKNOWN)

    if base in ("curl", "wget"):
        write_flags = {"-X", "-d", "--data", "--data-binary", "--data-raw",
                       "-F", "--form", "--upload-file", "-T", "--json"}
        if any(f in write_flags for f in args) or \
                any(f.startswith("--data") for f in args):
            return {"mutability": "external_write", "sensitivity": "private",
                    "egress": "external"}
        # A download that SAVES a file is a reversible local write (the event
        # must not claim a write-producing command is read-only). wget saves
        # by default; curl saves only with an output flag. '-O -' / output '-'
        # writes to stdout → still a read.
        download_flags = ("-o", "--output", "-O", "--remote-name",
                          "--output-dir", "-J", "--remote-header-name",
                          "-P", "--directory-prefix", "--output-document")
        stdout_out = "-" in args and any(
            f in ("-o", "-O", "--output", "--output-document") for f in args)
        saves_file = base == "wget" or any(
            f in download_flags or f.startswith(("-o", "-O", "--output"))
            for f in flags)
        if saves_file and not stdout_out:
            return {"mutability": "reversible_write", "sensitivity": "private",
                    "egress": "external"}
        return {"mutability": "read", "sensitivity": "private",
                "egress": "external"}

    if base == "rm":
        # Deleting an untracked file is not cheaply undoable. The DANGEROUS
        # prompt still fires first; a live approval satisfies the gate too.
        return {"mutability": "irreversible", "sensitivity": "private",
                "egress": "none"}

    return dict(_UNKNOWN)


def _split_segments(command_string: str) -> list[str] | None:
    """Quote-aware split on && || ; | and newlines. Returns None when the
    command contains substitution/subshell constructs (→ unknown)."""
    cmd = command_string.strip()
    if "$(" in cmd or "`" in cmd or "<(" in cmd or ">(" in cmd:
        return None
    segments, buf, i, n = [], [], 0, len(cmd)
    quote = None
    while i < n:
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        two = cmd[i:i + 2]
        if two in ("&&", "||"):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in (";", "|", "\n"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if quote:
        return None  # unbalanced quote → unknown
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def _looks_relative(p: str) -> bool:
    e = os.path.expanduser(p)
    return not os.path.isabs(e)


def resolve_shell_profile(command_string: str, cwd: str = None) -> dict:
    """Resolve a whole shell command to capability axes.

    Returns {"mutability", "sensitivity", "egress", "unknown": bool,
    "profile": str, "read_paths": [...], "write_paths": [...]}. Target paths
    are returned ABSOLUTE, resolved against the EFFECTIVE cwd — which tracks
    in-command ``cd``/``pushd``/``popd`` so ``cd ~/.aws && cat config`` gates
    ``config`` as ``~/.aws/config`` (secret), not against the original cwd.
    An un-modelable cwd change (``cd $VAR``, ``cd -``, ``popd`` with an empty
    stack) followed by a relative operand fails closed (whole command
    unknown). Any unknown segment makes the whole command unknown.
    """
    # Windows (or any non-POSIX shell): the POSIX grammar this profiler
    # models does not apply → fail closed (every command gates) rather than
    # mis-classify a cmd/PowerShell command.
    if not _posix_shell_available():
        return {**_UNKNOWN, "profile": "non-posix-shell",
                "read_paths": [], "write_paths": []}

    cmd = command_string.strip()
    if cmd.endswith("&"):
        cmd = cmd.rstrip("&").rstrip()
    segments = _split_segments(cmd)
    _first_profile = "unknown"
    if segments:
        _f = segments[0].split()
        if _f:
            _first_profile = os.path.basename(_f[0])
    if segments is None:
        return {**_UNKNOWN, "profile": _first_profile,
                "read_paths": [], "write_paths": []}

    base_cwd = os.path.realpath(os.path.expanduser(cwd)) if cwd \
        else os.path.realpath(WORKSPACE)
    eff_cwd = base_cwd
    cwd_stack = []
    cwd_known = True
    forced_unknown = False

    def _abs(p: str) -> str:
        e = str(p).replace("${WORKSPACE}", WORKSPACE).replace(
            "$WORKSPACE", WORKSPACE,
        )
        e = os.path.expanduser(os.path.expandvars(e))
        return e if os.path.isabs(e) else os.path.join(eff_cwd, e)

    # Collect read/write target paths (absolute, effective-cwd-resolved)
    # across all segments so the dispatcher can escalate sensitivity (secret
    # reads) and protected-config writes.
    read_paths, write_paths, authority_scopes = [], [], []
    for seg in segments:
        r, w = _command_target_paths(seg)
        if any(re.search(r"(?:\$[A-Za-z_{]|%[A-Za-z_][A-Za-z0-9_]*%)", p)
               for p in (r + w)):
            forced_unknown = True
        # A relative operand under an unknown cwd cannot be classified → the
        # whole command fails closed.
        if not cwd_known and any(_looks_relative(p) for p in (r + w)):
            forced_unknown = True
        abs_reads = [_abs(p) for p in r]
        abs_writes = [_abs(p) for p in w]
        read_paths.extend(abs_reads)
        write_paths.extend(abs_writes)
        try:
            scope_tokens = _strip_env_prefix(shlex.split(seg))
        except (ValueError, NameError):
            scope_tokens = []
        scope_base = os.path.basename(scope_tokens[0]) if scope_tokens else ""
        scope_flags = set(
            token for token in scope_tokens[1:] if token.startswith("-")
        )
        recursive_flag = bool(
            scope_flags & {"-r", "-R", "--recursive"}
        ) or any(
            token.startswith("-") and not token.startswith("--")
            and "r" in token[1:].lower()
            for token in scope_flags
        )
        recursive_read = (
            scope_base in {"find", "rg"}
            or scope_base in _ARCHIVE_TRANSFORM_BASES
            or (
                scope_base in {"grep", "egrep", "fgrep"}
                and recursive_flag
            )
            or (scope_base == "ls" and recursive_flag)
        )
        children_read = scope_base == "ls" and not recursive_read
        recursive_write = (
            scope_base in {"rm", "cp", "mv"}
            and recursive_flag
        )
        authority_scopes.extend({
            "path": path, "recursive": recursive_read,
            "children": children_read, "patterns": True,
        } for path in abs_reads)
        authority_scopes.extend({
            "path": path, "recursive": recursive_write,
            "children": False, "patterns": True,
        } for path in abs_writes)
        # Apply this segment's cd/pushd/popd effect to the effective cwd for
        # the NEXT segments (the shell evaluates left to right).
        kind, arg = _cd_effect(seg)
        if kind == "cd":
            if arg is None:
                eff_cwd, cwd_known = os.path.realpath(
                    os.path.expanduser("~")), True
            elif arg in ("-",) or any(c in arg for c in "$`*?"):
                cwd_known = False
            else:
                eff_cwd = _abs(arg)
                cwd_known = True
        elif kind == "pushd":
            cwd_stack.append((eff_cwd, cwd_known))
            if arg is None or arg == "-" or any(c in arg for c in "$`*?"):
                cwd_known = False
            else:
                eff_cwd = _abs(arg)
                cwd_known = True
        elif kind == "popd":
            if cwd_stack:
                eff_cwd, cwd_known = cwd_stack.pop()
            else:
                cwd_known = False

    mut, sens, egr = "read", "public", "none"
    for seg in segments:
        axes = _segment_axes(seg)
        if axes.get("unknown"):
            forced_unknown = True
            break
        order_m = ("read", "reversible_write", "external_write", "irreversible")
        order_s = ("public", "private", "sensitive", "secret")
        order_e = ("none", "local", "external")
        mut = max(mut, axes["mutability"], key=order_m.index)
        sens = max(sens, axes["sensitivity"], key=order_s.index)
        egr = max(egr, axes["egress"], key=order_e.index)
    if forced_unknown:
        return {**_UNKNOWN, "profile": _first_profile,
                "read_paths": read_paths, "write_paths": write_paths}
    # Presence of any write target forces at least reversible_write.
    if write_paths and mut == "read":
        mut = "reversible_write"
    return {"mutability": mut, "sensitivity": sens, "egress": egr,
            "unknown": False, "profile": _first_profile,
            "read_paths": read_paths, "write_paths": write_paths,
            "authority_scopes": authority_scopes}


# ── Command execution ──────────────────────────────────────────────────────

def _clean_env() -> dict:
    """Construct a clean subprocess environment."""
    parent = os.environ
    env = {}
    for key in ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL",
                "TMPDIR", "SSH_AUTH_SOCK"):
        if key in parent:
            env[key] = parent[key]
    # On Windows, spawning ANY process (even a declared Git Bash / WSL sh via
    # ORA_POSIX_SHELL) needs the core system variables — most critically
    # %SystemRoot%, without which winsock/crypto DLLs fail to load and
    # CreateProcess errors out. COMSPEC/PATHEXT/SystemDrive/windir + the temp
    # and profile roots are required for realistic command resolution. Adding
    # them only under os.name=='nt' leaves the POSIX environment byte-identical.
    if os.name == "nt":
        for key in ("SystemRoot", "SystemDrive", "windir", "COMSPEC", "PATHEXT",
                    "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
                    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"):
            if key in parent:
                env[key] = parent[key]
    env["WORKSPACE"] = WORKSPACE
    return env


def execute_command(command_string: str, timeout: int = 60,
                    cwd: str = None, background: bool = False,
                    max_output_chars: int = 10000) -> dict:
    """Execute a shell command with safety controls.

    Args:
        command_string: The command to run.
        timeout: Max seconds before killing (ignored for background).
        cwd: Working directory (defaults to WORKSPACE).
        background: If True, run via Popen and return immediately.
        max_output_chars: Truncate stdout/stderr beyond this limit.
    """
    if cwd is None:
        cwd = WORKSPACE

    # Detect background intent from trailing &
    if command_string.rstrip().endswith("&") and not background:
        background = True
        command_string = command_string.rstrip().rstrip("&").rstrip()

    # Direct-call backstop: dispatcher performs the same check before its
    # generic approval gate, but this execution boundary must not become an
    # alias/pattern or command-wrapper escape hatch for internal callers.
    unclassified = True
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        profile = resolve_shell_profile(command_string, cwd=cwd)
        # Preserve the dedicated Windows/no-POSIX-shell refusal below.  That
        # state is represented as an unknown profile but is a platform
        # availability failure, not a command-shape classification result.
        unclassified = bool(profile.get("unknown")) and \
            _posix_shell_available()
        scopes = list(profile.get("authority_scopes") or [])
        if not scopes:
            scopes = [{
                "path": path, "recursive": False,
                "children": False, "patterns": True,
            } for path in (
                list(profile.get("read_paths") or [])
                + list(profile.get("write_paths") or [])
            )]
        conflicts = any(
            system_protection.approval_authority_conflict(
                scope.get("path") or "",
                recursive=bool(scope.get("recursive")),
                patterns=bool(scope.get("patterns")),
                children=bool(scope.get("children")),
            )
            for scope in scopes
        )
    except Exception:
        conflicts = True
    if unclassified or conflicts:
        refusal = (
            "SYSTEM PROTECTION: shell command contains unclassified "
            "execution; command was not executed"
            if unclassified else
            "SYSTEM PROTECTION: shell target could include approval "
            "authority state; command was not executed"
        )
        if background:
            return {"pid": None, "status": refusal}
        return {
            "stdout": "", "stderr": refusal, "returncode": -1,
            "timed_out": False, "truncated": False,
        }

    env = _clean_env()

    # The profiler models POSIX shell grammar, so execution must run under a
    # POSIX shell too. On POSIX, shell=True (/bin/sh) already is one. On
    # Windows, run the declared ORA_POSIX_SHELL via ["-c", ...] — NEVER
    # shell=True, which would hand the command to cmd.exe: a shell the
    # profiler did not (and cannot) model. No valid declared shell → refuse
    # to execute (fail closed), for background and foreground alike.
    if os.name == "nt":
        _shell = _posix_shell_path()
        if _shell is None:
            refusal = (
                "Execution unavailable on Windows without a declared POSIX "
                "shell: set ORA_POSIX_SHELL to a real sh/bash executable "
                "(e.g. Git Bash or WSL). The command was NOT run — running "
                "it under cmd.exe would not match the POSIX profile the "
                "gate classified it with."
            )
            if background:
                return {"pid": None, "status": refusal}
            return {"stdout": "", "stderr": refusal, "returncode": -1,
                    "timed_out": False, "truncated": False}
        popen_args = [_shell, "-c", command_string]
        use_shell = False
    else:
        popen_args = command_string
        use_shell = True

    if background:
        try:
            proc = subprocess.Popen(
                popen_args, shell=use_shell, cwd=cwd, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            MANAGED_PROCESSES.append(proc)
            return {
                "pid": proc.pid,
                "status": "started in background",
                "managed_pids": [p.pid for p in MANAGED_PROCESSES if p.poll() is None],
            }
        except Exception as e:
            return {"pid": None, "status": f"failed to start: {e}"}

    # Foreground execution
    try:
        result = subprocess.run(
            popen_args, shell=use_shell, capture_output=True,
            text=True, timeout=timeout, cwd=cwd, env=env,
        )
        stdout = result.stdout
        stderr = result.stderr

        # Output truncation
        truncated = False
        if len(stdout) > max_output_chars:
            total = len(stdout)
            stdout = stdout[:max_output_chars] + (
                f"\n\n[OUTPUT TRUNCATED — showing first {max_output_chars} of "
                f"{total} characters. Pipe through head/tail/grep to narrow results.]"
            )
            truncated = True
        if len(stderr) > max_output_chars:
            total = len(stderr)
            stderr = stderr[:max_output_chars] + (
                f"\n\n[STDERR TRUNCATED — showing first {max_output_chars} of {total} characters.]"
            )
            truncated = True

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "timed_out": False,
            "truncated": truncated,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
            "timed_out": True,
            "truncated": False,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "timed_out": False,
            "truncated": False,
        }


# ── Background process management ─────────────────────────────────────────

def stop_process(pid: int) -> str:
    """Stop a managed background process by PID."""
    target = None
    for proc in MANAGED_PROCESSES:
        if proc.pid == pid:
            target = proc
            break
    if target is None:
        return f"PID {pid} is not a managed process."

    try:
        target.send_signal(signal.SIGTERM)
        try:
            target.wait(timeout=5)
        except subprocess.TimeoutExpired:
            target.kill()
            target.wait(timeout=2)
        # The owner of a foreground-managed worker may reap and unregister it
        # while stop_process() is waiting for termination.  That is a
        # successful stop, not an error or a second lifecycle effect.
        if target in MANAGED_PROCESSES:
            MANAGED_PROCESSES.remove(target)
        return f"Process {pid} stopped."
    except Exception as e:
        return f"Error stopping PID {pid}: {e}"


def cleanup_all() -> str:
    """Stop all managed background processes. Called at session end."""
    stopped = []
    for proc in list(MANAGED_PROCESSES):
        try:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stopped.append(proc.pid)
        except Exception:
            pass
    MANAGED_PROCESSES.clear()
    if stopped:
        return f"Stopped {len(stopped)} background processes: {stopped}"
    return "No background processes to stop."
