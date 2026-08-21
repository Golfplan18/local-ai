"""Single-command execution with immutable preparation and identity binding.

``bash_execute.command`` remains a string at the model boundary, but it is
never handed to a shell.  The dispatcher prepares it once into an immutable
``PreparedCommand`` and threads that same object through classification,
approval binding, and ``shell=False`` execution.  Direct callers use the same
preparation as a backstop.

The executable is resolved with the exact clean PATH used for execution and
rechecked before spawn.  Stat/digest rechecks materially narrow executable
replacement attacks; they cannot atomically eliminate the residual same-user
race between the last check and ``exec`` on macOS.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import tempfile
from types import MappingProxyType
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

try:
    import network_policy
except ImportError:  # pragma: no cover
    from orchestrator import network_policy


WORKSPACE = _rp.WORKSPACE
MANAGED_PROCESSES: list[subprocess.Popen] = []


def _posix_shell_path() -> str | None:
    """Return the declared POSIX shell on Windows, or ``None`` otherwise."""

    if os.name != "nt":
        return None
    declared = (os.environ.get("ORA_POSIX_SHELL") or "").strip()
    if not declared:
        return None
    if os.path.isabs(declared):
        return declared if os.path.isfile(declared) else None
    return shutil.which(declared)


def _posix_shell_available() -> bool:
    """Whether the command grammar has a matching POSIX shell backend."""

    return os.name != "nt" or _posix_shell_path() is not None


class CommandPreparationError(ValueError):
    """The string cannot be represented and authorized as one exact argv."""


@dataclass(frozen=True)
class FileIdentity:
    path: str
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    digest: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class PreparedCommand:
    argv: tuple[str, ...]
    cwd: str
    env_items: tuple[tuple[str, str], ...]
    env_digest: str
    executable: FileIdentity
    dependencies: tuple[FileIdentity, ...]
    profile_name: str
    mutability: str
    sensitivity: str
    egress: str
    read_paths: tuple[str, ...]
    write_paths: tuple[str, ...]
    authority_scopes: tuple[tuple[str, bool, bool, bool], ...]
    semantic_selectors: tuple[str, ...]
    network_urls: tuple[str, ...]
    unknown_reason: str | None
    audit_command: str

    @property
    def env(self) -> dict[str, str]:
        return dict(self.env_items)

    @property
    def unknown(self) -> bool:
        return self.unknown_reason is not None

    def profile(self) -> dict[str, Any]:
        return {
            "mutability": self.mutability,
            "sensitivity": self.sensitivity,
            "egress": self.egress,
            "unknown": self.unknown,
            "reason": self.unknown_reason,
            "profile": self.profile_name,
            "read_paths": list(self.read_paths),
            "write_paths": list(self.write_paths),
            "authority_scopes": [
                {
                    "path": path,
                    "recursive": recursive,
                    "patterns": patterns,
                    "children": children,
                }
                for path, recursive, patterns, children in self.authority_scopes
            ],
            "semantic_selectors": list(self.semantic_selectors),
            "network_urls": list(self.network_urls),
            "prepared_binding": self.binding(),
        }

    def binding(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "env_digest": self.env_digest,
            "executable": self.executable.as_dict(),
            "dependencies": [item.as_dict() for item in self.dependencies],
            "profile": self.profile_name,
            "mutability": self.mutability,
            "sensitivity": self.sensitivity,
            "egress": self.egress,
            "read_paths": list(self.read_paths),
            "write_paths": list(self.write_paths),
            "authority_scopes": [
                {
                    "path": path,
                    "recursive": recursive,
                    "patterns": patterns,
                    "children": children,
                }
                for path, recursive, patterns, children in self.authority_scopes
            ],
            "semantic_selectors": list(self.semantic_selectors),
            "network_urls": list(self.network_urls),
        }


_UNKNOWN_AXES = {
    "mutability": "irreversible",
    "sensitivity": "secret",
    "egress": "external",
}

_READ_ONLY_BASES = frozenset({
    "ls", "cat", "head", "tail", "wc", "pwd", "which", "date",
    "whoami", "uname", "echo", "printf", "grep", "rg", "sort", "uniq",
    "cut", "tr", "stat", "file", "du", "df", "basename", "dirname",
    "realpath", "true", "false", "test", "sw_vers", "sysctl", "md5",
    "shasum", "diff", "comm", "jq", "column", "xxd", "strings", "sed",
    "nl", "tac", "rev", "base64", "od", "less", "more", "readlink",
    "cmp", "ps", "hostname", "uptime", "id", "sleep", "find",
})
_FILE_READERS = frozenset({
    "cat", "head", "tail", "wc", "od", "xxd", "strings", "md5",
    "shasum", "file", "stat", "cut", "sort", "uniq", "comm", "diff",
    "column", "nl", "base64", "less", "more", "tac", "rev", "realpath",
    "readlink", "cmp",
})
_PATTERN_READERS = frozenset({"grep", "rg", "jq", "sed"})
_LOCAL_WRITE_BASES = frozenset({
    "mkdir", "touch", "cp", "mv", "ln", "tar", "gzip", "gunzip", "zip",
    "unzip", "ffmpeg", "pandoc", "whisper-cli", "tee",
})
_COMMAND_LAUNCHERS = frozenset({
    "command", "exec", "nice", "nohup", "timeout", "xargs", "parallel",
    "setsid", "stdbuf", "ionice", "taskset", "chroot", "sudo", "doas",
    "su", "runuser", "watch", "env", "awk", "source", ".", "bash", "sh",
    "zsh", "fish",
})
_STATE_BUILTINS = frozenset({"export", "set", "unset", "cd", "pushd", "popd"})
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

_GIT_HARDENING = (
    "--no-pager",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "core.pager=cat",
    "-c", "pager.status=false",
    "-c", "pager.log=false",
    "-c", "pager.diff=false",
    "-c", "diff.external=",
    "-c", "credential.helper=",
    "-c", "core.askPass=",
    "-c", "sequence.editor=false",
    "-c", "core.editor=false",
    "-c", "commit.gpgSign=false",
    "-c", "tag.gpgSign=false",
    "-c", "protocol.ext.allow=never",
)
_GIT_READ_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "rev-parse", "ls-files", "blame",
    "shortlog", "describe",
})
_GIT_LOCAL_WRITE_SUBCOMMANDS = frozenset({
    "add", "commit", "checkout", "switch", "restore", "merge", "stash",
    "reset", "rm", "mv", "cherry-pick", "revert", "worktree", "init",
})
_GIT_EXECUTION_OPTIONS = (
    "--exec-path", "--config-env", "--upload-pack", "--receive-pack",
    "--exec", "--ext-diff", "--textconv", "--no-verify",
)

_GIT_OUTPUT_OPTIONS = frozenset({"--output", "--output="})
_GIT_SIGNATURE_OPTIONS = frozenset({
    "--gpg-sign", "--no-gpg-sign", "--show-signature", "--verify-signatures",
})
_GIT_STRATEGY_SUBCOMMANDS = frozenset({
    "am", "apply", "checkout", "cherry-pick", "merge", "rebase",
    "restore", "revert", "stash", "switch",
})

_GIT_HELPER_CONFIG_KEYS = (
    re.compile(r"^alias\."),
    re.compile(r"^credential(?:\..+)?\.helper$"),
    re.compile(r"^diff\..+\.(?:command|textconv)$"),
    re.compile(r"^filter\..+\.(?:clean|smudge|process)$"),
    re.compile(r"^gpg(?:\..+)?\.program$"),
    re.compile(r"^merge\..+\.driver$"),
    re.compile(r"^pager\."),
    re.compile(r"^protocol\..+\.allow$"),
    re.compile(r"^remote\..+\.(?:proxy|receivepack|uploadpack)$"),
    re.compile(r"^submodule\..+\.update$"),
    re.compile(r"^url\..+\.(?:insteadof|pushinsteadof)$"),
)
_GIT_HELPER_CONFIG_EXACT = frozenset({
    "core.attributesfile", "core.editor", "core.fsmonitor",
    "core.hookspath", "core.pager", "core.sshcommand", "diff.external",
    "help.format", "init.templatedir", "sequence.editor",
})

_UTILITY_EXECUTION_OPTIONS: dict[str, tuple[str, ...]] = {
    "rg": (
        "--pre", "--pre=", "--hostname-bin", "--hostname-bin=",
        "--search-zip", "-z",
    ),
    "sort": ("--compress-program", "--compress-program="),
    "tar": (
        "-I", "--use-compress-program", "--use-compress-program=",
        "--to-command", "--to-command=", "--info-script",
        "--info-script=", "--rsh-command", "--rsh-command=",
        "--new-volume-script", "--new-volume-script=",
        "--checkpoint-action=exec", "--checkpoint-action=exec=",
    ),
    "pandoc": (
        "-F", "--filter", "--filter=", "-L", "--lua-filter",
        "--lua-filter=", "--pdf-engine", "--pdf-engine=",
    ),
    "zip": ("-TT", "--unzip-command", "--unzip-command="),
}

_CURL_VALUE_OPTIONS = {
    "-o": "output", "--output": "output", "--url": "url",
    "-X": "method", "--request": "method", "--max-time": "number",
    "--connect-timeout": "number", "--retry": "number",
    "--retry-delay": "number", "--retry-max-time": "number",
}
_CURL_FLAG_OPTIONS = frozenset({
    "-q", "--disable", "-s", "--silent", "-S", "--show-error", "-f",
    "--fail", "--fail-with-body", "-I", "--head", "-i", "--include",
    "--compressed", "--http1.1", "--http2", "--ipv4", "--ipv6",
})
_WGET_VALUE_OPTIONS = {
    "-O": "output", "--output-document": "output", "--timeout": "number",
    "--connect-timeout": "number", "--read-timeout": "number",
    "--tries": "number",
}
_WGET_FLAG_OPTIONS = frozenset({
    "-q", "--quiet", "-nv", "--no-verbose", "--server-response",
    "--spider", "--https-only", "--no-check-certificate",
})
_FFMPEG_VALUE_OPTIONS = frozenset({
    "-f", "-ss", "-t", "-to", "-itsoffset", "-r", "-s", "-aspect",
    "-pix_fmt", "-profile", "-profile:v", "-b", "-b:v", "-b:a",
    "-crf", "-preset", "-filter", "-filter:v", "-filter:a", "-vf", "-af",
    "-filter_complex", "-map", "-metadata", "-metadata:s",
    "-c", "-c:v", "-c:a", "-ac", "-ar", "-channel_layout", "-threads",
    "-loglevel", "-stream_loop", "-protocol_whitelist",
})
_FFMPEG_IMPLICIT_WRITE_OPTIONS = frozenset({"-report", "-vstats"})


def _immutable_executable_roots() -> tuple[str, ...]:
    roots = ["/bin", "/usr/bin", "/usr/sbin", "/sbin", "/System/Library"]
    if os.name == "nt":
        for key in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(key)
            if value:
                roots.append(value)
    return tuple(os.path.normcase(os.path.realpath(item)) for item in roots)


def _known_executable_roots() -> tuple[str, ...]:
    roots = list(_immutable_executable_roots())
    roots.extend(os.path.normcase(os.path.realpath(item)) for item in (
        "/opt/homebrew/bin", "/opt/homebrew/Cellar", "/usr/local/bin",
        "/Applications/ChatGPT.app/Contents/Resources", "/Library/Apple/usr/bin",
        "/Library/Frameworks", os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.hermes/node"),
    ))
    return tuple(dict.fromkeys(roots))


def _within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(path), root)) == root
    except ValueError:
        return False


def _digest_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _identity(path: str, *, force_digest: bool = False) -> FileIdentity:
    canonical = os.path.realpath(path)
    current = os.stat(canonical)
    if not stat.S_ISREG(current.st_mode):
        raise CommandPreparationError("executable or bound dependency is not a regular file")
    immutable = any(
        _within(os.path.normcase(canonical), root)
        for root in _immutable_executable_roots()
    )
    digest = _digest_file(canonical) if force_digest or not immutable else None
    return FileIdentity(
        path=canonical,
        device=int(current.st_dev),
        inode=int(current.st_ino),
        mode=int(current.st_mode),
        size=int(current.st_size),
        mtime_ns=int(current.st_mtime_ns),
        digest=digest,
    )


def _identity_matches(expected: FileIdentity) -> bool:
    try:
        return _identity(
            expected.path,
            force_digest=expected.digest is not None,
        ) == expected
    except (OSError, CommandPreparationError):
        return False


def _scan_windows_direct_grammar(command: str) -> None:
    """Reject shell-looking grammar while preserving Windows argv quoting.

    Direct execution does not involve ``cmd.exe`` or PowerShell. Double
    quotes therefore delimit argv values, while single quotes and backslashes
    are ordinary characters under the native command-line grammar.
    """

    quoted = False
    backslashes = 0
    for char in command:
        if char == "\\":
            backslashes += 1
            continue
        if char == '"' and backslashes % 2 == 0:
            quoted = not quoted
        elif not quoted and char in ";|&<>\n\r":
            raise CommandPreparationError(
                "shell operators, pipes, redirects, and ampersands are not allowed",
            )
        elif not quoted and char in "$`()":
            raise CommandPreparationError(
                "shell expansion and subshell grammar are not allowed",
            )
        elif not quoted and char in "*?[]{}":
            raise CommandPreparationError(
                "shell glob and brace expansion are not allowed; pass exact operands",
            )
        backslashes = 0
    if quoted:
        raise CommandPreparationError("command has incomplete quoting or escaping")


def _scan_shell_grammar(command: str) -> None:
    if not isinstance(command, str) or not command.strip():
        raise CommandPreparationError("command is required")
    if os.name == "nt":
        _scan_windows_direct_grammar(command)
        return
    quote: str | None = None
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if quote == "'":
            if char == "'":
                quote = None
            continue
        if quote == '"':
            if char == '"':
                quote = None
            elif char == "\\":
                escaped = True
            elif char in {"$", "`"}:
                raise CommandPreparationError("command substitution and expansion are not allowed")
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "\\":
            escaped = True
        elif char in ";|&<>\n\r":
            raise CommandPreparationError("shell operators, pipes, redirects, and ampersands are not allowed")
        elif char in "$`()":
            raise CommandPreparationError("shell expansion and subshell grammar are not allowed")
        elif char in "*?[]{}":
            raise CommandPreparationError("shell glob and brace expansion are not allowed; pass exact operands")
    if quote or escaped:
        raise CommandPreparationError("command has incomplete quoting or escaping")


def _split_windows_command_line_fallback(command: str) -> list[str]:
    """Parse the narrow Windows CreateProcess command-line quoting grammar.

    This is the inverse of the quoting rules used by the MS C runtime and
    ``subprocess.list2cmdline``: whitespace separates arguments outside
    double quotes, and backslashes are special only when immediately followed
    by a double quote.  It is deliberately not a cmd.exe/PowerShell parser.
    """

    argv: list[str] = []
    length = len(command)
    index = 0
    while index < length:
        while index < length and command[index] in " \t":
            index += 1
        if index >= length:
            break
        chars: list[str] = []
        quoted = False
        while index < length:
            if command[index] in " \t" and not quoted:
                break
            if command[index] == "\\":
                start = index
                while index < length and command[index] == "\\":
                    index += 1
                slash_count = index - start
                if index < length and command[index] == '"':
                    chars.extend("\\" for _ in range(slash_count // 2))
                    if slash_count % 2:
                        chars.append('"')
                        index += 1
                    else:
                        # Two consecutive quotes inside a quoted argument
                        # encode one literal quote under the CRT grammar.
                        if quoted and index + 1 < length and command[index + 1] == '"':
                            chars.append('"')
                            index += 2
                        else:
                            quoted = not quoted
                            index += 1
                else:
                    chars.extend("\\" for _ in range(slash_count))
                continue
            if command[index] == '"':
                if quoted and index + 1 < length and command[index + 1] == '"':
                    chars.append('"')
                    index += 2
                else:
                    quoted = not quoted
                    index += 1
                continue
            chars.append(command[index])
            index += 1
        if quoted:
            raise CommandPreparationError("command quoting is malformed")
        argv.append("".join(chars))
        while index < length and command[index] in " \t":
            index += 1
    return argv


def _split_command_line(command: str) -> list[str]:
    """Return the native direct-execution argv without invoking a shell."""

    if os.name != "nt":
        try:
            return shlex.split(command, posix=True)
        except ValueError as exc:
            raise CommandPreparationError("command quoting is malformed") from exc

    # Prefer the operating-system parser on a real Windows host.  The local
    # implementation keeps unit tests and restricted Python builds faithful
    # without introducing a shell or a third-party dependency.
    try:  # pragma: no cover - exercised by the native-Windows suite
        import ctypes
        from ctypes import wintypes

        argc = ctypes.c_int()
        parser = ctypes.windll.shell32.CommandLineToArgvW
        parser.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        parser.restype = ctypes.POINTER(wintypes.LPWSTR)
        pointer = parser(command, ctypes.byref(argc))
        if not pointer:
            raise CommandPreparationError("Windows command line could not be parsed")
        try:
            return [pointer[item] for item in range(argc.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(pointer)
    except CommandPreparationError:
        raise
    except Exception:
        return _split_windows_command_line_fallback(command)


def _clean_env(*, git_push: bool = False) -> dict[str, str]:
    """Build the exact environment used for both lookup and execution."""

    parent = os.environ
    env: dict[str, str] = {"PATH": parent.get("PATH") or os.defpath}
    for key in ("LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "TZ"):
        if key in parent:
            env[key] = parent[key]
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        if key in parent:
            env[key] = parent[key]
    if os.name == "nt":
        for key in (
            "SystemRoot", "SystemDrive", "windir", "COMSPEC", "PATHEXT",
            "TEMP", "TMP", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
        ):
            if key in parent:
                env[key] = parent[key]
    env["WORKSPACE"] = WORKSPACE
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_EDITOR": "false",
        "GIT_SEQUENCE_EDITOR": "false",
        "GIT_ASKPASS": "false",
        "SSH_ASKPASS": "false",
        "GIT_EXTERNAL_DIFF": "",
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    })
    if git_push and parent.get("SSH_AUTH_SOCK"):
        env["SSH_AUTH_SOCK"] = parent["SSH_AUTH_SOCK"]
    return env


def _env_digest(env: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(env.items())), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _resolve_executable(token: str, cwd: str, env: Mapping[str, str]) -> str:
    expanded = os.path.expanduser(token)
    if os.path.dirname(expanded):
        candidate = expanded if os.path.isabs(expanded) else os.path.join(cwd, expanded)
        resolved = os.path.realpath(candidate)
        if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            raise CommandPreparationError("command executable is unavailable")
        return resolved
    resolved = shutil.which(expanded, path=env.get("PATH"))
    if not resolved:
        raise CommandPreparationError("command executable is unavailable")
    return os.path.realpath(resolved)


def _basename(path: str) -> str:
    name = os.path.basename(path).casefold()
    return name[:-4] if name.endswith(".exe") else name


def _known_executable(path: str) -> bool:
    normalized = os.path.normcase(os.path.realpath(path))
    temp_root = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    admitted = [
        WORKSPACE, _rp.VAULT_STR, _rp.CONVERSATIONS_STR, temp_root,
    ]
    if any(_within(normalized, os.path.normcase(os.path.realpath(root))) for root in admitted):
        return False
    return any(_within(normalized, root) for root in _known_executable_roots())


def _is_canonical_profile_executable(
    base: str,
    executable: str,
    cwd: str,
    env: Mapping[str, str],
) -> bool:
    """Bind a semantic profile to the clean resolver's canonical utility.

    Real-path comparison intentionally admits platform aliases/symlinks that
    resolve to the selected system/Homebrew executable, while rejecting a
    different path-qualified binary that merely reuses a trusted basename.
    """

    try:
        selected = _resolve_executable(base, cwd, env)
    except CommandPreparationError:
        return False
    return os.path.normcase(os.path.realpath(executable)) == os.path.normcase(
        os.path.realpath(selected),
    )


def _abs_operand(value: str, cwd: str) -> str:
    expanded = os.path.expanduser(value)
    return os.path.realpath(expanded if os.path.isabs(expanded) else os.path.join(cwd, expanded))


def _non_flags(args: Iterable[str]) -> list[str]:
    return [item for item in args if item and not item.startswith("-")]


def _matches_option(token: str, option: str) -> bool:
    """Match one exact/attached option without substring ambiguity."""

    if option.endswith("="):
        return token.startswith(option)
    if len(option) == 2 and option.startswith("-") and not option.startswith("--"):
        return token == option or (
            token.startswith("-") and not token.startswith("--")
            and option[1] in token[1:]
        )
    return token == option


def _has_any_option(args: Iterable[str], options: Iterable[str]) -> bool:
    return any(
        _matches_option(token, option)
        for token in args
        for option in options
    )


def _option_value(
    args: list[str], long_names: Iterable[str], *, short_name: str | None = None,
) -> str | None:
    """Return the last exact, equals, or short-attached option value."""

    names = tuple(long_names)
    result: str | None = None
    index = 0
    while index < len(args):
        token = args[index]
        if token in names or (short_name is not None and token == short_name):
            if index + 1 < len(args):
                result = args[index + 1]
                index += 2
                continue
            return None
        matched = False
        for name in names:
            prefix = name + "="
            if token.startswith(prefix):
                result = token[len(prefix):]
                matched = True
                break
        if matched:
            index += 1
            continue
        if (
            short_name is not None and token.startswith(short_name)
            and token != short_name and not token.startswith("--")
        ):
            result = token[len(short_name):]
        index += 1
    return result


def _recursive_option(base: str, args: list[str]) -> bool:
    if base == "du":
        return True
    if base in {"find", "rg"}:
        return True
    if base == "grep":
        return _has_any_option(args, ("-r", "-R", "--recursive"))
    if base == "ls":
        return _has_any_option(args, ("-R", "--recursive"))
    if base in {"cp", "rm"}:
        return _has_any_option(
            args, ("-r", "-R", "-a", "--recursive", "--archive"),
        )
    if base in {"gzip", "gunzip", "zip"}:
        return _has_any_option(args, ("-r", "--recursive"))
    if base == "diff":
        return _has_any_option(args, ("-r", "--recursive"))
    return False


def _tar_paths(
    args: list[str], cwd: str,
) -> tuple[list[str], list[str], list[tuple[str, bool, bool, bool]]] | None:
    """Resolve the small local tar grammar and its true traversal scopes."""

    # A files-from operand derives the traversal set from mutable file state.
    # Binding only the list file would understate authority; parsing and
    # snapshotting tar's complete list grammar here would create a second
    # state-binding system.  Keep the admitted grammar exact and fail closed.
    if _has_any_option(args, ("-T", "--files-from", "--files-from=")):
        return None
    # Absolute-name extraction permits archive members to escape the bound
    # destination (including through ``..`` and symlinked paths).
    if _has_any_option(args, ("-P", "--absolute-names")):
        return None
    if (
        args
        and not args[0].startswith("-")
        and re.fullmatch(r"[A-Za-z]+", args[0] or "")
        and "T" in args[0]
    ):
        return None

    mode: str | None = None
    archive: str | None = None
    directory = cwd
    operands: list[str] = []
    to_stdout = False
    index = 0
    old_style_consumed = False
    while index < len(args):
        token = args[index]
        if token == "--":
            operands.extend(args[index + 1:])
            break
        if token in {"-c", "--create"}:
            mode = "create"
        elif token in {"-x", "--extract", "--get"}:
            mode = "extract"
        elif token in {"-t", "--list"}:
            mode = "list"
        elif token in {"-r", "--append", "-u", "--update", "--delete", "-A", "--catenate", "--concatenate"}:
            mode = "update"
        elif token in {"-O", "--to-stdout"}:
            to_stdout = True
        elif token in {"-f", "--file"}:
            if index + 1 >= len(args):
                return None
            index += 1
            archive = args[index]
        elif token.startswith("--file="):
            archive = token.split("=", 1)[1]
        elif token in {"-C", "--directory"}:
            if index + 1 >= len(args):
                return None
            index += 1
            directory = _abs_operand(args[index], directory)
        elif token.startswith("--directory="):
            directory = _abs_operand(token.split("=", 1)[1], directory)
        elif token.startswith("-"):
            short = token[1:]
            for char_index, char in enumerate(short):
                if char == "c":
                    mode = "create"
                elif char == "x":
                    mode = "extract"
                elif char == "t":
                    mode = "list"
                elif char in {"r", "u", "A"}:
                    mode = "update"
                elif char == "O":
                    to_stdout = True
                elif char == "P":
                    return None
                elif char == "f":
                    attached = short[char_index + 1:]
                    if attached:
                        archive = attached
                    elif index + 1 < len(args):
                        index += 1
                        archive = args[index]
                    else:
                        return None
                    break
        elif index == 0 and re.fullmatch(r"[A-Za-z]+", token or ""):
            # POSIX old-style tar permits ``tar czf archive paths...``.
            old_style_consumed = True
            for char in token:
                if char == "c":
                    mode = "create"
                elif char == "x":
                    mode = "extract"
                elif char == "t":
                    mode = "list"
                elif char in {"r", "u", "A"}:
                    mode = "update"
            if "f" in token:
                if index + 1 >= len(args):
                    return None
                index += 1
                archive = args[index]
        else:
            operands.append(token)
        index += 1
    if mode is None or archive in {None, ""}:
        return None
    archive_path = archive if archive == "-" else _abs_operand(archive, cwd)
    reads: list[str] = []
    writes: list[str] = []
    scopes: list[tuple[str, bool, bool, bool]] = []
    if archive_path != "-" and mode in {"extract", "list", "update"}:
        reads.append(archive_path)
        scopes.append((archive_path, False, True, False))
    if mode in {"create", "update"}:
        if archive_path != "-":
            writes.append(archive_path)
            scopes.append((archive_path, False, True, False))
        for operand in operands:
            path = _abs_operand(operand, directory)
            reads.append(path)
            scopes.append((path, True, True, False))
    elif mode == "extract" and not to_stdout:
        writes.append(directory)
        scopes.append((directory, True, True, True))
    # ``old_style_consumed`` is intentionally retained as an explicit parse
    # branch; assigning it prevents future cleanup from folding old-style flags
    # into operands and silently losing the recursive scope.
    _ = old_style_consumed
    return reads, writes, scopes


def _pattern_reader_paths(base: str, args: list[str], cwd: str) -> list[str]:
    """Return grep/rg file operands, including attached pattern options."""

    remaining: list[str] = []
    pattern_files: list[str] = []
    explicit_pattern = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            remaining.extend(args[index + 1:])
            break
        if token in {"-e", "--regexp"}:
            if index + 1 >= len(args):
                return []
            explicit_pattern = True
            index += 2
            continue
        if token.startswith("--regexp=") or (
            token.startswith("-e") and token != "-e" and not token.startswith("--")
        ):
            explicit_pattern = True
            index += 1
            continue
        if token in {"-f", "--file"}:
            if index + 1 >= len(args):
                return []
            explicit_pattern = True
            pattern_files.append(args[index + 1])
            index += 2
            continue
        if token.startswith("--file=") or (
            token.startswith("-f") and token != "-f" and not token.startswith("--")
        ):
            explicit_pattern = True
            pattern_files.append(
                token.split("=", 1)[1]
                if token.startswith("--file=") else token[2:]
            )
            index += 1
            continue
        if not token.startswith("-"):
            remaining.append(token)
        index += 1
    files = remaining if explicit_pattern else remaining[1:]
    resolved = [
        _abs_operand(item, cwd) for item in [*pattern_files, *files] if item
    ]
    # Ripgrep searches the working tree recursively when no path operand is
    # supplied.  Pattern files do not replace that implicit search root.
    if base == "rg" and not files:
        resolved.append(_abs_operand(".", cwd))
    return list(dict.fromkeys(resolved))


def _rg_file_roots(args: list[str], cwd: str) -> list[str] | None:
    """Return the recursive roots of ripgrep's pattern-free ``--files`` mode."""

    separator = args.index("--") if "--" in args else len(args)
    if "--files" not in args[:separator]:
        return None
    value_options = {
        "-g", "--glob", "--iglob", "-t", "--type", "-T", "--type-not",
        "--ignore-file", "--max-depth", "--max-filesize", "--sort", "--sortr",
        "--path-separator", "--encoding", "--engine", "--color", "--colors",
    }
    roots: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            roots.extend(args[index + 1:])
            break
        if token == "--files":
            index += 1
            continue
        # The ignore-file is an additional model-selected read. Parsing its
        # contents is outside this exact-root grammar; refuse the shape rather
        # than letting an unbound file disappear from the authority record.
        if token == "--ignore-file" or token.startswith("--ignore-file="):
            return None
        if token in value_options:
            if index + 1 >= len(args):
                return None
            index += 2
            continue
        if any(
            token.startswith(option + "=")
            for option in value_options if option.startswith("--")
        ) or any(
            token.startswith(option) and token != option
            for option in {"-g", "-t", "-T"}
        ):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        roots.append(token)
        index += 1
    return [_abs_operand(item, cwd) for item in (roots or ["."])]


def _find_roots(args: list[str], cwd: str) -> list[str]:
    roots: list[str] = []
    after_separator = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--" and not after_separator:
            after_separator = True
            index += 1
            continue
        if not after_separator and token in {"-H", "-L", "-P"}:
            index += 1
            continue
        if not after_separator and token in {"-D", "-O"}:
            index += 2
            continue
        if token in {"!", "(", ")"} or (
            token.startswith("-") and not after_separator
        ):
            break
        roots.append(token)
        index += 1
    return [_abs_operand(item, cwd) for item in (roots or ["."])]


def _sed_expressions_and_files(
    args: list[str],
) -> tuple[list[str], list[str], list[str]] | None:
    """Return (expressions, program_files, input_files) for local sed."""

    expressions: list[str] = []
    program_files: list[str] = []
    positionals: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            positionals.extend(args[index + 1:])
            break
        if token == "--in-place":
            index += 1
            continue
        if token == "-i" and index + 1 < len(args) and args[index + 1] == "":
            index += 2
            continue
        if token in {"-e", "--expression"}:
            if index + 1 >= len(args):
                return None
            expressions.append(args[index + 1])
            index += 2
            continue
        if token.startswith("--expression="):
            expressions.append(token.split("=", 1)[1])
            index += 1
            continue
        if token.startswith("-e") and token != "-e" and not token.startswith("--"):
            expressions.append(token[2:])
            index += 1
            continue
        if token in {"-f", "--file"}:
            if index + 1 >= len(args):
                return None
            program_files.append(args[index + 1])
            index += 2
            continue
        if token.startswith("--file="):
            program_files.append(token.split("=", 1)[1])
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        positionals.append(token)
        index += 1
    if not expressions and not program_files:
        if not positionals:
            return None
        expressions.append(positionals.pop(0))
    return expressions, program_files, positionals


def _sed_write_targets(expression: str) -> list[str] | None:
    """Extract exact sed ``w file`` targets or refuse an ambiguous shape."""

    targets: list[str] = []
    simple_address = r"(?:[0-9]+(?:~[0-9]+)?|\$|/(?:\\.|[^/\n])*/)"
    range_address = (
        simple_address
        + r"(?:,(?:" + simple_address + r"|\+[0-9]+|~[0-9]+))?"
    )
    command_prefix = (
        r"(?:(?:" + range_address + r")?[ \t]*!?[ \t]*\{[ \t]*)*"
        r"(?:" + range_address + r")?[ \t]*!?[ \t]*"
    )
    # Standalone write commands, including address prefixes such as ``1w x``.
    for command in re.split(r"[;\n]", expression):
        stripped = command.strip()
        # sed's ``r`` command reads a second model-selected file.  It is not
        # an ordinary positional input, so refuse both spaced and attached
        # spellings instead of allowing that read to disappear from the
        # authority record.
        if re.match(r"^" + command_prefix + r"[rR](?:\s|/|$)", stripped):
            return None
        # GNU sed's ``e`` command and the ``s///e`` flag execute a helper
        # process.  Its filesystem/network effects cannot be represented by
        # this exact-path profile, so refuse the complete program.
        if re.match(r"^" + command_prefix + r"e(?:[ \t]|$)", stripped):
            return None
        match = re.match(
            r"^" + command_prefix + r"w[ \t]+([^ \t]+)[ \t]*$",
            stripped,
        )
        if match:
            targets.append(match.group(1))
            continue
        # Parse a single substitution command far enough to isolate its flag
        # tail.  The delimiter may be any non-alphanumeric character.
        sub = re.match(
            r"^" + command_prefix + r"s([^A-Za-z0-9\\\s])",
            stripped,
        )
        if not sub:
            if re.search(r"(?:^|[^A-Za-z0-9_])w(?:[ \t]|$)", stripped):
                return None
            continue
        delimiter = sub.group(1)
        cursor = sub.end()
        for _part in range(2):
            escaped = False
            while cursor < len(stripped):
                char = stripped[cursor]
                cursor += 1
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == delimiter:
                    break
            else:
                return None
        flags = stripped[cursor:].strip()
        # Only the substitution flag segment can request GNU ``e``.  Do not
        # scan the write target itself: an ordinary path such as
        # ``/var/folders/output`` legitimately contains the letter ``e``.
        flag_head = flags.split(None, 1)[0] if flags else ""
        if "e" in flag_head.casefold():
            return None
        write = re.search(r"(?:^|[0-9gpIimM]*)w[ \t]+([^ \t]+)[ \t]*$", flags)
        if write:
            targets.append(write.group(1))
        elif re.search(r"(?:^|[^A-Za-z0-9_])w(?:[ \t]|$)", flags):
            return None
    return targets


def _sed_paths(
    args: list[str], cwd: str,
) -> tuple[list[str], list[str]] | None:
    # A backup suffix creates an extra sidecar, and a mutable script file may
    # contain GNU sed's process-launching ``e`` command.  The admitted
    # in-place spellings are therefore only GNU ``--in-place`` and BSD
    # ``-i ''`` (no backup); both bind every input as an exact write.
    if any(
        (item.startswith("-i") and item != "-i" and not item.startswith("--"))
        or item.startswith("--in-place=")
        or item in {"-f", "--file"}
        or (item.startswith("-f") and not item.startswith("--"))
        or item.startswith("--file=")
        for item in args
    ):
        return None
    for index, item in enumerate(args):
        if item == "-i" and (index + 1 >= len(args) or args[index + 1] != ""):
            return None
    parsed = _sed_expressions_and_files(args)
    if parsed is None:
        return None
    expressions, program_files, input_files = parsed
    if program_files:
        return None
    writes: list[str] = []
    for expression in expressions:
        found = _sed_write_targets(expression)
        if found is None:
            return None
        writes.extend(found)
    reads = [*program_files, *input_files]
    if "--in-place" in args or "-i" in args:
        writes.extend(input_files)
    return (
        [_abs_operand(item, cwd) for item in reads],
        [_abs_operand(item, cwd) for item in writes],
    )


def _zip_paths(
    args: list[str], cwd: str,
) -> tuple[list[str], list[str], list[tuple[str, bool, bool, bool]]] | None:
    positionals = _non_flags(args)
    if not positionals:
        return None
    archive = _abs_operand(positionals[0], cwd)
    operands = positionals[1:]
    recurse_paths = _has_any_option(args, ("-r", "--recurse-paths"))
    recurse_patterns = _has_any_option(args, ("-R", "--recurse-patterns"))
    if recurse_patterns:
        reads = [cwd]
        scopes = [(cwd, True, True, False)]
    else:
        reads = [_abs_operand(item, cwd) for item in operands]
        scopes = [(path, recurse_paths, True, False) for path in reads]
    return reads, [archive], [*scopes, (archive, False, True, False)]


def _looks_like_remote_media(value: str) -> bool:
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return False
    parsed = urlsplit(value)
    return bool(parsed.scheme and parsed.scheme.casefold() not in {"file"})


def _ffmpeg_paths(
    args: list[str], cwd: str,
) -> tuple[list[str], list[str]] | None:
    if any(token in _FFMPEG_IMPLICIT_WRITE_OPTIONS for token in args):
        return None
    # Refuse every URL/protocol-shaped operand, not only the common ``-i``
    # position.  ffmpeg permits network outputs and protocol-bearing option
    # values in several places; the local profile intentionally describes
    # only local inspection/transforms.
    if any(
        _looks_like_remote_media(token)
        for token in args
        if token and not token.startswith("-")
    ):
        return None
    inputs: list[str] = []
    input_indexes: set[int] = set()
    option_value_indexes: set[int] = set()
    index = 0
    while index < len(args):
        if args[index] == "-i":
            if index + 1 >= len(args):
                return None
            source = args[index + 1]
            if _looks_like_remote_media(source):
                return None
            inputs.append(source)
            input_indexes.add(index + 1)
            index += 2
            continue
        if args[index] in _FFMPEG_VALUE_OPTIONS:
            if index + 1 >= len(args):
                return None
            option_value_indexes.add(index + 1)
            index += 2
            continue
        index += 1
    operands = [
        token for index, token in enumerate(args)
        if index not in input_indexes
        and index not in option_value_indexes
        and token not in {"-", "pipe:", "pipe:1"}
        and not token.startswith("-")
    ]
    if any(_looks_like_remote_media(output) for output in operands):
        return None
    return (
        [_abs_operand(item, cwd) for item in inputs],
        [_abs_operand(output, cwd) for output in operands],
    )


def _parse_pip(args: list[str]) -> dict[str, Any]:
    if not args or args[0] not in {"list", "show", "freeze", "check"}:
        return _unknown_profile("opaque interpreter/package execution is not allowed", "pip")
    command, rest = args[0], args[1:]
    flag_options = {
        "list": {"--local", "--user", "--exclude-editable", "--include-editable", "--no-color"},
        "show": {"-f", "--files", "--verbose", "-v", "--no-color"},
        "freeze": {"--all", "--local", "--user", "--exclude-editable", "--no-color"},
        "check": {"--no-color"},
    }[command]
    value_options = {
        "list": {"--format", "--path"},
        "show": set(),
        "freeze": {"--exclude", "--path"},
        "check": set(),
    }[command]
    index = 0
    while index < len(rest):
        token = rest[index]
        if token == "--":
            if command not in {"show"}:
                return _unknown_profile("pip offline command has an ambiguous operand", "pip")
            break
        if token in flag_options:
            index += 1
            continue
        if token in value_options:
            if index + 1 >= len(rest):
                return _unknown_profile("pip option is missing its value", "pip")
            index += 2
            continue
        if any(token.startswith(option + "=") for option in value_options):
            index += 1
            continue
        if token.startswith("-"):
            return _unknown_profile("pip option is outside the offline inspection grammar", "pip")
        if command != "show":
            return _unknown_profile("pip offline command has an unexpected operand", "pip")
        index += 1
    return {
        "mutability": "read", "sensitivity": "private", "egress": "none",
        "unknown_reason": None, "profile": "pip", "read_paths": [],
        "write_paths": [], "semantic_selectors": [],
    }


def _generic_paths(base: str, args: list[str], cwd: str) -> tuple[list[str], list[str]]:
    positional = _non_flags(args)
    reads: list[str] = []
    writes: list[str] = []
    if base == "ls":
        reads = positional or ["."]
    elif base == "find":
        return _find_roots(args, cwd), []
    elif base in _PATTERN_READERS:
        if base in {"grep", "rg"}:
            if base == "rg":
                roots = _rg_file_roots(args, cwd)
                if roots is not None:
                    return roots, []
            return _pattern_reader_paths(base, args, cwd), []
        reads = positional[1:]
        for index, item in enumerate(args):
            if item in {"-f", "--file"} and index + 1 < len(args):
                reads.append(args[index + 1])
            elif item.startswith("--file="):
                reads.append(item.split("=", 1)[1])
    elif base in _FILE_READERS:
        reads = positional
    elif base in {"mkdir", "touch", "tee"}:
        writes = positional
    elif base in {"cp", "mv", "ln"} and len(positional) >= 2:
        reads = positional[:-1]
        writes = positional[-1:]
        if base == "mv":
            writes = positional
    elif base in {"gzip", "gunzip", "pandoc", "whisper-cli"}:
        reads = positional
        writes = positional
    elif base == "unzip" and positional:
        reads = positional[:1]
        output = _option_value(args, ("--directory",), short_name="-d")
        if not _has_any_option(args, ("-c", "-p", "-t", "-l", "-v")):
            writes = [output or cwd]
    if base == "sed" and any(item == "-i" or item.startswith("-i") for item in args):
        writes.extend(positional[1:])
    if base == "sort":
        output = _option_value(args, ("--output",), short_name="-o")
        if output:
            writes.append(output)
    if base == "uniq" and len(positional) >= 2:
        reads = positional[:1]
        writes = positional[1:2]
    if base == "base64":
        output = _option_value(args, ("--output",), short_name="-o")
        if output:
            writes.append(output)
    if base == "xxd" and _has_any_option(args, ("-r", "--revert")) and len(positional) >= 2:
        reads = positional[:1]
        writes = positional[1:2]
    return (
        [_abs_operand(item, cwd) for item in reads],
        [_abs_operand(item, cwd) for item in writes],
    )


def _generic_authority_scopes(
    base: str,
    args: list[str],
    reads: Iterable[str],
    writes: Iterable[str],
) -> list[tuple[str, bool, bool, bool]]:
    recursive = _recursive_option(base, args)
    read_recursive = recursive or base in {"du"}
    write_recursive = recursive and base in {
        "cp", "mv", "rm", "gzip", "gunzip", "unzip",
    }
    if base == "unzip":
        write_recursive = True
    if base == "npm":
        read_recursive = True
    scopes = [
        (path, read_recursive, True, base == "ls" and not read_recursive)
        for path in reads
    ]
    scopes.extend(
        (
            path,
            write_recursive or (base == "mv" and os.path.isdir(path)),
            True,
            base in {"cp", "mv", "ln"} and not write_recursive,
        )
        for path in writes
    )
    return scopes


def _unknown_profile(reason: str, base: str) -> dict[str, Any]:
    return {**_UNKNOWN_AXES, "unknown_reason": reason, "profile": base}


def _public_selector(prefix: str, validated: network_policy.ValidatedURL) -> str:
    digest = hashlib.sha256(validated.url.encode("utf-8")).hexdigest()
    return f"{prefix}:{validated.origin}#sha256:{digest}"


def _parse_curl(args: list[str], cwd: str) -> dict[str, Any]:
    urls: list[str] = []
    output: str | None = None
    output_count = 0
    final_args = list(args)
    method = "GET"
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            urls.extend(args[index + 1:])
            break
        name, equals, attached = token.partition("=") if token.startswith("--") else (token, "", "")
        if name in _CURL_FLAG_OPTIONS:
            index += 1
            continue
        if name in _CURL_VALUE_OPTIONS:
            if equals:
                value = attached
            else:
                if index + 1 >= len(args):
                    return _unknown_profile("curl option is missing its value", "curl")
                index += 1
                value = args[index]
            kind = _CURL_VALUE_OPTIONS[name]
            if kind == "output":
                output_count += 1
                output = value if value == "-" else _abs_operand(value, cwd)
                if equals:
                    final_args[index] = f"{name}={output}"
                else:
                    final_args[index] = output
            elif kind == "url":
                urls.append(value)
            elif kind == "method":
                method = value.upper()
                if method not in {"GET", "HEAD"}:
                    return _unknown_profile("curl permits only GET or HEAD", "curl")
            index += 1
            continue
        if token.startswith("-o") and len(token) > 2 and not token.startswith("--"):
            output_count += 1
            raw_output = token[2:]
            output = raw_output if raw_output == "-" else _abs_operand(raw_output, cwd)
            final_args[index] = "-o" + output
            index += 1
            continue
        if token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
            if method not in {"GET", "HEAD"}:
                return _unknown_profile("curl permits only GET or HEAD", "curl")
            index += 1
            continue
        if token.startswith("-") and len(token) > 2 and all(
            f"-{char}" in _CURL_FLAG_OPTIONS for char in token[1:]
        ):
            index += 1
            continue
        if token.startswith("-"):
            return _unknown_profile("curl option is outside the public download grammar", "curl")
        urls.append(token)
        index += 1
    if len(urls) != 1 or output_count > 1:
        return _unknown_profile("curl requires exactly one explicit destination", "curl")
    try:
        destination = network_policy.validate_public_url(urls[0])
    except network_policy.NetworkPolicyError as exc:
        return _unknown_profile(str(exc), "curl")
    write_paths: list[str] = []
    if output and output != "-":
        write_paths.append(output)
    mutability = "reversible_write" if write_paths else "read"
    return {
        "mutability": mutability,
        "sensitivity": "private",
        "egress": "external",
        "unknown_reason": None,
        "profile": "curl",
        "read_paths": [],
        "write_paths": write_paths,
        "semantic_selectors": [_public_selector("network-read", destination)],
        "network_urls": [destination.url],
        "final_args": [
            "--disable", "--proto", "=http,https", "--max-redirs", "0",
            "--no-netrc", *final_args,
        ],
        "audit_urls": {urls[0]: network_policy.safe_url_label(urls[0])},
    }


def _parse_wget(args: list[str], cwd: str) -> dict[str, Any]:
    urls: list[str] = []
    output: str | None = None
    output_count = 0
    final_args = list(args)
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            urls.extend(args[index + 1:])
            break
        name, equals, attached = token.partition("=") if token.startswith("--") else (token, "", "")
        if name in _WGET_FLAG_OPTIONS:
            index += 1
            continue
        if name in _WGET_VALUE_OPTIONS:
            if equals:
                value = attached
            else:
                if index + 1 >= len(args):
                    return _unknown_profile("wget option is missing its value", "wget")
                index += 1
                value = args[index]
            if _WGET_VALUE_OPTIONS[name] == "output":
                output_count += 1
                output = value if value == "-" else _abs_operand(value, cwd)
                if equals:
                    final_args[index] = f"{name}={output}"
                else:
                    final_args[index] = output
            index += 1
            continue
        if token.startswith("-O") and len(token) > 2 and not token.startswith("--"):
            output_count += 1
            raw_output = token[2:]
            output = raw_output if raw_output == "-" else _abs_operand(raw_output, cwd)
            final_args[index] = "-O" + output
            index += 1
            continue
        if token in {"-qO-", "-O-q"}:
            output_count += 1
            output = "-"
            index += 1
            continue
        if token.startswith("-"):
            return _unknown_profile("wget option is outside the public download grammar", "wget")
        urls.append(token)
        index += 1
    if len(urls) != 1 or output is None or output_count != 1:
        return _unknown_profile("wget requires one destination and an exact -O output (or -O -)", "wget")
    try:
        destination = network_policy.validate_public_url(urls[0])
    except network_policy.NetworkPolicyError as exc:
        return _unknown_profile(str(exc), "wget")
    write_paths = [] if output == "-" else [output]
    return {
        "mutability": "reversible_write" if write_paths else "read",
        "sensitivity": "private",
        "egress": "external",
        "unknown_reason": None,
        "profile": "wget",
        "read_paths": [],
        "write_paths": write_paths,
        "semantic_selectors": [_public_selector("network-read", destination)],
        "network_urls": [destination.url],
        "final_args": ["--no-config", "--max-redirect=0", *final_args],
        "audit_urls": {urls[0]: network_policy.safe_url_label(urls[0])},
    }


def _git_metadata(cwd: str) -> tuple[str | None, str | None]:
    current = Path(cwd)
    for candidate in (current, *current.parents):
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            return str(candidate.resolve()), str((dot_git / "config").resolve())
        if dot_git.is_file():
            try:
                line = dot_git.read_text(encoding="utf-8").strip()
            except OSError:
                return None, None
            if not line.casefold().startswith("gitdir:"):
                return None, None
            raw = line.split(":", 1)[1].strip()
            admin = Path(raw)
            if not admin.is_absolute():
                admin = candidate / admin
            admin = admin.resolve()
            common = admin / "commondir"
            if common.is_file():
                common_raw = common.read_text(encoding="utf-8").strip()
                common_dir = Path(common_raw)
                if not common_dir.is_absolute():
                    common_dir = admin / common_dir
                config = common_dir.resolve() / "config"
            else:
                config = admin / "config"
            return str(candidate.resolve()), str(config.resolve())
        if (candidate / "HEAD").is_file() and (candidate / "objects").is_dir():
            return str(candidate.resolve()), str((candidate / "config").resolve())
    return None, None


def _git_config_parser(config_path: str | None) -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    if not config_path or not os.path.isfile(config_path):
        return parser
    try:
        parser.read(config_path, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        raise CommandPreparationError("Git repository config is unreadable") from exc
    return parser


def _git_config_key_is_helper(key: str) -> bool:
    normalized = str(key or "").strip().casefold()
    return normalized in _GIT_HELPER_CONFIG_EXACT or any(
        pattern.match(normalized) for pattern in _GIT_HELPER_CONFIG_KEYS
    )


def _git_repo_has_unbound_helpers(config_path: str | None) -> bool:
    """Detect local config that may launch an unbound child process.

    The command's clean environment removes global/system config and hardens
    the fixed helper keys. Dynamic filter/merge names and includes cannot be
    exhaustively neutralized with ``-c`` entries, so helper-capable repository
    operations refuse when local config declares them.
    """

    parser = _git_config_parser(config_path)
    for section in parser.sections():
        lowered = section.casefold()
        if lowered.startswith("include"):
            return True
        if lowered.startswith('filter "') and any(
            parser.has_option(section, option)
            and bool(parser.get(section, option, fallback="").strip())
            for option in ("clean", "smudge", "process")
        ):
            return True
        if lowered.startswith('merge "') and parser.has_option(section, "driver"):
            if parser.get(section, "driver", fallback="").strip():
                return True
    return False


def _git_network_has_unbound_helpers(config_path: str | None) -> bool:
    parser = _git_config_parser(config_path)
    for section in parser.sections():
        lowered = section.casefold()
        if lowered.startswith("include"):
            return True
        if lowered == "core" and parser.has_option(section, "sshcommand"):
            if parser.get(section, "sshcommand", fallback="").strip():
                return True
        if lowered.startswith('remote "') and any(
            parser.has_option(section, option)
            and bool(parser.get(section, option, fallback="").strip())
            for option in ("proxy", "receivepack", "uploadpack")
        ):
            return True
    return False


def _git_option_is_output(token: str) -> bool:
    return _git_long_option_matches(token, ("--output",))


def _git_long_option_matches(token: str, options: Iterable[str]) -> bool:
    """Match Git's exact, equals-attached, and unique-prefix long options."""

    name = token.split("=", 1)[0]
    if not name.startswith("--") or len(name) <= 2:
        return False
    return any(name == option or option.startswith(name) for option in options)


def _git_option_is_signature(token: str) -> bool:
    return (
        _git_long_option_matches(token, _GIT_SIGNATURE_OPTIONS)
        or (token.startswith("-S") and token != "-S")
        or token == "-S"
    )


def _git_option_is_execution_bearing(token: str) -> bool:
    """Match exact, attached, and abbreviated Git helper options."""

    # ``--text`` is an exact, inert diff option and therefore is not Git's
    # abbreviation of the execution-bearing ``--textconv`` option.
    if token.split("=", 1)[0] == "--text":
        return False
    return _git_long_option_matches(token, _GIT_EXECUTION_OPTIONS)


def _git_option_is_strategy(token: str) -> bool:
    """Reject strategy/helper selectors, including attached spellings."""

    return (
        token in {"-s", "-X", "--strategy", "--strategy-option"}
        or token.startswith(("-s", "-X")) and token not in {"-s", "-X"}
        or _git_long_option_matches(
            token, ("--strategy", "--strategy-option"),
        )
    )


def _read_remote(config_path: str | None, name: str, *, push: bool) -> str:
    if not config_path or not os.path.isfile(config_path):
        raise CommandPreparationError("Git remote cannot be resolved from the exact repository config")
    parser = _git_config_parser(config_path)
    for section in parser.sections():
        lowered = section.casefold()
        if lowered.startswith("include") or lowered.startswith('url "'):
            raise CommandPreparationError("Git include and URL-rewrite config is not admitted for network commands")
    section = f'remote "{name}"'
    if not parser.has_section(section):
        raise CommandPreparationError("Git remote name is not present in the exact repository config")
    option = "pushurl" if push and parser.has_option(section, "pushurl") else "url"
    value = parser.get(section, option, fallback="").strip()
    if not value:
        raise CommandPreparationError("Git remote has no exact URL")
    return value


def _validate_git_remote(value: str) -> tuple[str, str]:
    if "::" in value or value.startswith(("ext::", "fd::")):
        raise CommandPreparationError("Git external remote helpers are not allowed")
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        checked = network_policy.validate_public_url(value)
        return checked.origin, _public_selector("network-read", checked)
    if parsed.scheme in {"ssh", "git"}:
        if parsed.username is not None and parsed.password is not None:
            raise CommandPreparationError("Git remote may not contain a password")
        host = parsed.hostname or ""
    elif parsed.scheme or "://" in value:
        raise CommandPreparationError("Git remote helper schemes are not allowed")
    else:
        match = re.match(r"^(?:[^@/:]+@)?([^:/]+):.+$", value)
        if not match:
            raise CommandPreparationError("Git network command requires an HTTP(S), SSH, or git remote")
        host = match.group(1)
    try:
        addresses = network_policy._resolve_addresses(host, 22 if parsed.scheme != "git" else 9418)
        if any(network_policy._forbidden_address(address) for address in addresses):
            raise network_policy.NetworkPolicyError("destination resolves to a non-public address")
    except network_policy.NetworkPolicyError as exc:
        raise CommandPreparationError(str(exc)) from exc
    label = f"{parsed.scheme or 'ssh'}://{host}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return label, f"network-read:{label}#sha256:{digest}"


def _git_global(args: list[str], cwd: str) -> tuple[list[str], str, str | None]:
    remaining = list(args)
    effective = cwd
    while remaining and remaining[0].startswith("-"):
        token = remaining.pop(0)
        if token == "--":
            break
        if token == "-C":
            if not remaining:
                raise CommandPreparationError("git -C is missing its directory")
            target = remaining.pop(0)
            effective = _abs_operand(target, effective)
            if not os.path.isdir(effective):
                raise CommandPreparationError("git -C directory is unavailable")
            continue
        if token.startswith("-C") and len(token) > 2:
            effective = _abs_operand(token[2:], effective)
            if not os.path.isdir(effective):
                raise CommandPreparationError("git -C directory is unavailable")
            continue
        if token in {"--no-pager", "--no-replace-objects", "--literal-pathspecs", "--no-optional-locks"}:
            continue
        if token in {"--version", "--help"}:
            return [], effective, token
        if token in {"-c", "--config-env", "--git-dir", "--work-tree", "--namespace", "--exec-path"}:
            if remaining:
                remaining.pop(0)
            raise CommandPreparationError("Git global config, directory, and executable overrides are not allowed")
        if any(token.startswith(prefix + "=") for prefix in (
            "--config-env", "--git-dir", "--work-tree", "--namespace", "--exec-path",
        )) or (token.startswith("-c") and len(token) > 2):
            raise CommandPreparationError("Git global config, directory, and executable overrides are not allowed")
        raise CommandPreparationError("Git global option is outside the admitted grammar")
    return remaining, effective, None


def _git_network_positionals(args: list[str], *, subcommand: str) -> list[str]:
    value_options = {
        "--depth", "--deepen", "--shallow-since", "--shallow-exclude",
        "--filter", "--jobs", "-j", "--branch", "-b", "--origin", "-o",
    }
    allowed_flags = {
        "--quiet", "-q", "--verbose", "-v", "--progress", "--prune",
        "--tags", "--no-tags", "--single-branch", "--no-single-branch",
        "--no-checkout", "-n",
        "--ff-only", "--no-ff", "--rebase", "--no-rebase",
    }
    out: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if _git_option_is_execution_bearing(token) or (
            subcommand in {"clone", "fetch", "pull"}
            and (token == "-u" or (token.startswith("-u") and len(token) > 2))
        ):
            raise CommandPreparationError("Git execution-bearing option is not allowed")
        if token in {"--all", "--multiple", "--mirror", "--force", "-f", "--delete", "-d", "--force-with-lease"}:
            if subcommand == "push" and token in {"--force", "-f", "--delete", "-d", "--force-with-lease"}:
                allowed_flags.add(token)
            else:
                raise CommandPreparationError("Git multi-target or mirror option is ambiguous")
        if token in value_options:
            if index + 1 >= len(args):
                raise CommandPreparationError("Git option is missing its value")
            index += 2
            continue
        if any(token.startswith(item + "=") for item in value_options if item.startswith("--")):
            index += 1
            continue
        if token in allowed_flags:
            index += 1
            continue
        if token == "--":
            out.extend(args[index + 1:])
            break
        if token.startswith("-"):
            raise CommandPreparationError("Git network option is outside the admitted grammar")
        out.append(token)
        index += 1
    return out


def _git_no_index_paths(args: list[str], cwd: str) -> tuple[str, str] | None:
    """Extract the two real operands of ``git diff --no-index``."""

    operands: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            operands.extend(args[index + 1:])
            break
        if token in {"--no-index", "--no-ext-diff", "--no-textconv"}:
            index += 1
            continue
        if token in {"-U", "--unified", "--src-prefix", "--dst-prefix", "--line-prefix", "--inter-hunk-context", "--word-diff-regex"}:
            if index + 1 >= len(args):
                return None
            index += 2
            continue
        if token.startswith(("-U", "--unified=", "--src-prefix=", "--dst-prefix=", "--line-prefix=", "--inter-hunk-context=", "--word-diff-regex=")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        operands.append(token)
        index += 1
    if len(operands) != 2:
        return None
    if any(item == "-" for item in operands):
        return None
    return tuple(_abs_operand(item, cwd) for item in operands)  # type: ignore[return-value]


def _parse_git_config_shape(subargs: list[str]) -> tuple[bool, str | None]:
    """Return ``(mutation, key)`` for the deliberately small local grammar."""

    if any(
        item in {
            "--global", "--system", "--worktree", "--file", "--blob",
            "--includes", "--no-includes", "--edit", "-e",
            "--rename-section", "--remove-section",
        }
        or item.startswith(("--file=", "--blob="))
        for item in subargs
    ):
        raise CommandPreparationError("Git config scope or action is outside the exact repository")
    read_actions = {"--get", "--get-all", "--get-regexp", "--list", "-l"}
    write_actions = {"--add", "--replace-all", "--unset", "--unset-all"}
    inert_flags = {
        "--local", "--show-origin", "--show-scope", "--name-only",
        "--fixed-value", "--null", "-z", "--bool", "--int", "--bool-or-int",
        "--path", "--expiry-date",
    }
    action: str | None = None
    positional: list[str] = []
    index = 0
    while index < len(subargs):
        token = subargs[index]
        if token in read_actions | write_actions:
            if action is not None:
                raise CommandPreparationError("Git config has multiple actions")
            action = token
            index += 1
            continue
        if token in inert_flags or token.startswith("--type="):
            index += 1
            continue
        if token in {"--type", "--default"}:
            if index + 1 >= len(subargs):
                raise CommandPreparationError("Git config option is missing its value")
            index += 2
            continue
        if token == "--":
            positional.extend(subargs[index + 1:])
            break
        if token.startswith("-"):
            raise CommandPreparationError("Git config option is outside the admitted grammar")
        positional.append(token)
        index += 1
    if action in {"--list", "-l"}:
        if positional:
            raise CommandPreparationError("Git config list does not take a key")
        return False, None
    if action in read_actions:
        if not positional:
            raise CommandPreparationError("Git config read requires an exact key or pattern")
        return False, positional[0]
    if action in write_actions:
        if not positional:
            raise CommandPreparationError("Git config mutation requires an exact key")
        return True, positional[0]
    if len(positional) == 1:
        return False, positional[0]
    if len(positional) == 2:
        return True, positional[0]
    raise CommandPreparationError("Git config shape is unknown or ambiguous")


def _parse_git(args: list[str], cwd: str) -> dict[str, Any]:
    try:
        remaining, effective_cwd, terminal = _git_global(args, cwd)
    except CommandPreparationError as exc:
        return _unknown_profile(str(exc), "git")
    if terminal:
        return {
            "mutability": "read", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": "git", "read_paths": [],
            "write_paths": [], "semantic_selectors": [], "final_args": list(_GIT_HARDENING) + args,
        }
    if not remaining:
        return _unknown_profile("Git subcommand is required", "git")
    subcommand, subargs = remaining[0], remaining[1:]
    if subcommand.startswith("-") or any(
        _git_option_is_execution_bearing(item) for item in subargs
    ):
        return _unknown_profile("Git execution-bearing or malformed shape is not allowed", "git")
    repo_root, config_path = _git_metadata(effective_cwd)
    repo = repo_root or effective_cwd
    repo_selector = f"repo:{repo}"
    final_args = list(_GIT_HARDENING) + args
    dependencies: list[str] = []

    # Strategy selection is an execution hook for every subcommand that can
    # invoke merge/apply/cherry-pick machinery, not just ``merge``. Reject
    # attached and equals spellings before any local-write profile is admitted.
    if subcommand in _GIT_STRATEGY_SUBCOMMANDS and any(
        _git_option_is_strategy(item) for item in subargs
    ):
        return _unknown_profile(
            "Git external strategy/helper selection is not allowed", "git",
        )

    if subcommand in _GIT_READ_SUBCOMMANDS:
        if any(_git_option_is_output(item) for item in subargs):
            return _unknown_profile("Git read output must remain on stdout", "git")
        if any(_git_option_is_signature(item) for item in subargs):
            return _unknown_profile("Git signature helper execution is not allowed", "git")
        if subcommand == "diff" and "--no-index" in subargs:
            pair = _git_no_index_paths(subargs, effective_cwd)
            if pair is None:
                return _unknown_profile(
                    "git diff --no-index requires exactly two bound paths", "git",
                )
            left, right = pair
            insert_at = final_args.index(subcommand) + 1
            final_args[insert_at:insert_at] = ["--no-ext-diff", "--no-textconv"]
            return {
                "mutability": "read", "sensitivity": "private", "egress": "none",
                "unknown_reason": None, "profile": "git",
                "read_paths": [left, right], "write_paths": [],
                "semantic_selectors": [
                    f"filesystem-read:{left}", f"filesystem-read:{right}",
                ],
                "final_args": final_args,
                "authority_scopes": [
                    (left, True, True, False), (right, True, True, False),
                ],
            }
        if subcommand in {"log", "diff", "show"}:
            insert_at = final_args.index(subcommand) + 1
            final_args[insert_at:insert_at] = ["--no-ext-diff", "--no-textconv"]
        return {
            "mutability": "read", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": "git", "read_paths": [repo],
            "write_paths": [], "semantic_selectors": [repo_selector],
            "final_args": final_args,
            "authority_scopes": [(repo, True, True, False)],
        }

    if subcommand == "config":
        if not config_path:
            return _unknown_profile("Git config target cannot be resolved", "git")
        try:
            mutation, key = _parse_git_config_shape(subargs)
        except CommandPreparationError as exc:
            return _unknown_profile(str(exc), "git")
        if mutation and key and _git_config_key_is_helper(key):
            return _unknown_profile("Git execution-bearing configuration is not allowed", "git")
        return {
            "mutability": "reversible_write" if mutation else "read",
            "sensitivity": "private", "egress": "none", "unknown_reason": None,
            "profile": "git", "read_paths": [config_path],
            "write_paths": [config_path] if mutation else [],
            "semantic_selectors": [repo_selector, f"git-config:{config_path}"],
            "final_args": final_args,
            "authority_scopes": [(config_path, False, True, False)],
        }

    if subcommand == "remote":
        operation = next((item for item in subargs if not item.startswith("-")), "")
        if operation in {"update", "prune"}:
            return _unknown_profile(
                "git remote update/prune are network mutations; use an exact git fetch shape",
                "git",
            )
        if operation == "show" and not any(
            item in {"-n", "--no-query"} for item in subargs
        ):
            return _unknown_profile("git remote show may contact the network without -n", "git")
        if operation == "add" and _has_any_option(subargs, ("-f", "--fetch")):
            return _unknown_profile("git remote add --fetch is a network mutation", "git")
        if operation == "set-head" and any(
            item in {"-a", "--auto"} for item in subargs
        ):
            return _unknown_profile("git remote set-head --auto contacts the network", "git")
        mutation_words = {"add", "remove", "rm", "rename", "set-head", "set-branches", "set-url"}
        if operation in mutation_words:
            if not config_path:
                return _unknown_profile("Git remote config target cannot be resolved", "git")
            return {
                "mutability": "reversible_write", "sensitivity": "private", "egress": "none",
                "unknown_reason": None, "profile": "git", "read_paths": [repo],
                "write_paths": [repo], "semantic_selectors": [repo_selector, f"git-remote:{operation}"],
                "final_args": final_args,
                "authority_scopes": [(repo, True, True, False)],
            }
        if operation not in {"", "show", "get-url"}:
            return _unknown_profile("Git remote operation is outside the admitted grammar", "git")
        return {
            "mutability": "read", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": "git", "read_paths": [config_path] if config_path else [repo],
            "write_paths": [], "semantic_selectors": [repo_selector], "final_args": final_args,
            "authority_scopes": [((config_path or repo), False, True, False)],
        }

    if subcommand in {"branch", "tag"}:
        if subcommand == "tag" and any(
            _git_option_is_signature(item)
            or item in {"-s", "--sign", "-u", "--local-user", "-v", "--verify"}
            or item.startswith("--local-user=")
            for item in subargs
        ):
            return _unknown_profile("Git tag signature helper execution is not allowed", "git")
        mutation_flags = {"-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "-a", "-s", "-u", "-F", "-m", "--unset-upstream"}
        positional = [item for item in subargs if not item.startswith("-")]
        listing = not positional or any(item in {"--list", "-l", "--show-current"} for item in subargs)
        mutation = (
            bool(set(subargs) & mutation_flags)
            or any(item.startswith("--set-upstream-to=") for item in subargs)
            or "--set-upstream-to" in subargs
            or not listing
        )
        return {
            "mutability": "reversible_write" if mutation else "read",
            "sensitivity": "private", "egress": "none", "unknown_reason": None,
            "profile": "git", "read_paths": [repo], "write_paths": [repo] if mutation else [],
            "semantic_selectors": [repo_selector, f"git-ref:{subcommand}:{','.join(positional) or 'list'}"],
            "final_args": final_args,
            "authority_scopes": [(repo, True, True, False)],
        }

    if subcommand in _GIT_LOCAL_WRITE_SUBCOMMANDS:
        if any(_git_option_is_signature(item) for item in subargs):
            return _unknown_profile("Git signature helper execution is not allowed", "git")
        if subcommand == "commit" and _has_any_option(
            subargs, ("-F", "--file", "--file=")
        ):
            return _unknown_profile(
                "Git commit message files are outside the exact local grammar",
                "git",
            )
        if subcommand in {"worktree"}:
            return _unknown_profile("Git worktree writes require a dedicated exact-path surface", "git")
        if subcommand == "init" and any(
            item in {"--template", "--separate-git-dir"}
            or item.startswith(("--template=", "--separate-git-dir="))
            for item in subargs
        ):
            return _unknown_profile("Git init template/directory overrides are not allowed", "git")
        if subcommand == "init":
            positionals: list[str] = []
            index = 0
            value_options = {"-b", "--initial-branch", "--object-format", "--ref-format"}
            flag_options = {"-q", "--quiet", "--bare", "--shared"}
            while index < len(subargs):
                token = subargs[index]
                if token == "--":
                    positionals.extend(subargs[index + 1:])
                    break
                if token in value_options:
                    if index + 1 >= len(subargs):
                        return _unknown_profile("Git init option is missing its value", "git")
                    index += 2
                    continue
                if token in flag_options or token.startswith("--shared=") or any(
                    token.startswith(option + "=")
                    for option in value_options
                    if option.startswith("--")
                ):
                    index += 1
                    continue
                if token.startswith("-"):
                    return _unknown_profile("Git init option is outside the admitted grammar", "git")
                positionals.append(token)
                index += 1
            if len(positionals) > 1:
                return _unknown_profile("Git init requires at most one exact target", "git")
            target = _abs_operand(positionals[0], effective_cwd) if positionals else effective_cwd
            return {
                "mutability": "reversible_write", "sensitivity": "private", "egress": "none",
                "unknown_reason": None, "profile": "git", "read_paths": [],
                "write_paths": [target], "semantic_selectors": [repo_selector, f"git-init:{target}"],
                "final_args": final_args,
                "authority_scopes": [(target, True, True, True)],
            }
        helper_sensitive = {
            "add", "checkout", "switch", "restore", "merge", "stash",
            "reset", "cherry-pick", "revert",
        }
        if subcommand == "commit" and _has_any_option(subargs, ("-a", "--all")):
            helper_sensitive.add("commit")
        try:
            if subcommand in helper_sensitive and _git_repo_has_unbound_helpers(config_path):
                return _unknown_profile("Git repository declares an unbound filter or merge helper", "git")
        except CommandPreparationError as exc:
            return _unknown_profile(str(exc), "git")
        return {
            "mutability": "reversible_write", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": "git", "read_paths": [repo],
            "write_paths": [repo], "semantic_selectors": [repo_selector, f"git-operation:{subcommand}"],
            "final_args": final_args,
            "authority_scopes": [(repo, True, True, False)],
        }

    if subcommand in {"fetch", "pull", "clone", "push"}:
        try:
            positional = _git_network_positionals(subargs, subcommand=subcommand)
            if subcommand == "clone":
                if len(positional) != 2:
                    raise CommandPreparationError("git clone requires an explicit source and destination")
                remote_value = positional[0]
                destination = _abs_operand(positional[1], effective_cwd)
                target_repo = destination
                read_paths: list[str] = []
                write_paths = [destination]
            else:
                minimum = 2 if subcommand in {"pull", "push"} else 1
                if len(positional) < minimum:
                    raise CommandPreparationError(f"git {subcommand} requires an explicit remote" + (" and ref" if minimum == 2 else ""))
                remote_name = positional[0]
                remote_value = remote_name if urlsplit(remote_name).scheme or ":" in remote_name else _read_remote(config_path, remote_name, push=subcommand == "push")
                target_repo = repo
                read_paths = [repo]
                write_paths = [repo]
                if config_path:
                    dependencies.append(config_path)
            if subcommand != "clone" and _git_network_has_unbound_helpers(config_path):
                raise CommandPreparationError("Git network command has an unbound repository helper")
            label, network_selector = _validate_git_remote(remote_value)
            if subcommand == "pull" and _git_repo_has_unbound_helpers(config_path):
                raise CommandPreparationError("git pull may invoke an unbound filter or merge helper")
        except (CommandPreparationError, network_policy.NetworkPolicyError) as exc:
            return _unknown_profile(str(exc), "git")
        refs = positional[1:] if subcommand != "clone" else positional[:1]
        semantic = [repo_selector, network_selector, f"git-remote:{label}"]
        if subcommand == "push":
            semantic[1] = semantic[1].replace("network-read:", "remote-write:", 1)
        semantic.extend(f"git-ref:{ref}" for ref in refs)
        mutability = "external_write" if subcommand == "push" else "reversible_write"
        if subcommand == "push" and any(item in {"--force", "-f", "--delete", "-d", "--force-with-lease"} or item.startswith("--force-with-lease=") for item in subargs):
            mutability = "irreversible"
        return {
            "mutability": mutability, "sensitivity": "private", "egress": "external",
            "unknown_reason": None, "profile": "git", "read_paths": read_paths,
            "write_paths": write_paths, "semantic_selectors": semantic,
            "final_args": final_args, "dependency_paths": dependencies,
            "git_push": subcommand == "push", "target_repo": target_repo,
            "authority_scopes": [
                *((path, True, True, False) for path in read_paths),
                *((path, True, True, False) for path in write_paths),
            ],
        }

    return _unknown_profile("Git subcommand is unknown or ambiguous", "git")


def _parse_sysctl(args: list[str]) -> dict[str, Any]:
    """Admit inspection only; every assignment/config-load shape refuses."""

    def write_option(token: str) -> bool:
        if token in {"-w", "-p", "-f", "--write", "--load", "--system"}:
            return True
        if token.startswith(("--write=", "--load=", "--system=")):
            return True
        if not token.startswith("-") or token.startswith("--") or len(token) <= 2:
            return False
        short = token[1:]
        if short[0] in {"r", "B"}:  # attached value, not a flag cluster
            return False
        return any(char in {"w", "p", "f"} for char in short)

    if any(write_option(item) for item in args):
        return _unknown_profile("sysctl writes are outside the read grammar", "sysctl")

    safe_long_flags = {
        "--all", "--binary", "--deprecated", "--ignore", "--names",
        "--values", "--table", "--help", "--version",
    }
    value_options = {"-B", "-r", "--pattern"}
    safe_short_flags = frozenset("aAbdehiNnoqxXT")
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            if any("=" in item for item in args[index + 1:]):
                return _unknown_profile(
                    "sysctl writes are outside the read grammar", "sysctl",
                )
            break
        if token in value_options:
            if index + 1 >= len(args):
                return _unknown_profile("sysctl option is missing its value", "sysctl")
            index += 2
            continue
        if token.startswith("--pattern=") or (
            token.startswith(("-B", "-r")) and len(token) > 2
        ):
            index += 1
            continue
        if token in safe_long_flags or (
            token.startswith("-")
            and not token.startswith("--")
            and len(token) > 1
            and all(char in safe_short_flags for char in token[1:])
        ):
            index += 1
            continue
        if token.startswith("-"):
            return _unknown_profile("sysctl option is outside the read grammar", "sysctl")
        if "=" in token:
            return _unknown_profile("sysctl writes are outside the read grammar", "sysctl")
        index += 1
    return {
        "mutability": "read", "sensitivity": "private", "egress": "none",
        "unknown_reason": None, "profile": "sysctl", "read_paths": [],
        "write_paths": [], "semantic_selectors": [],
    }


def _profile(base: str, args: list[str], cwd: str, executable: str) -> dict[str, Any]:
    if not _known_executable(executable):
        return _unknown_profile("executable is outside trusted command roots", base)
    if base == "env":
        index = 0
        while index < len(args):
            item = args[index]
            if _ENV_ASSIGN_RE.match(item) or item in {"-i", "--ignore-environment", "-0", "--null"}:
                index += 1
                continue
            if item in {"-u", "--unset"} and index + 1 < len(args):
                index += 2
                continue
            if item.startswith("--unset="):
                index += 1
                continue
            return _unknown_profile("env may inspect only; utility execution is not allowed", base)
        return {
            "mutability": "read", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base, "read_paths": [],
            "write_paths": [], "semantic_selectors": [],
        }
    if base in _STATE_BUILTINS or base in _COMMAND_LAUNCHERS:
        return _unknown_profile("shell state and command-launching utilities are not allowed", base)
    if base == "git":
        return _parse_git(args, cwd)
    if base == "curl":
        return _parse_curl(args, cwd)
    if base == "wget":
        return _parse_wget(args, cwd)
    if base in {"pip", "pip3"}:
        profile = _parse_pip(args)
        profile["profile"] = base
        return profile
    if base == "npm" and args and args[0] in {"ls", "list"}:
        return {
            "mutability": "read", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base, "read_paths": [cwd],
            "write_paths": [], "semantic_selectors": [],
            "authority_scopes": [(cwd, True, True, False)],
        }
    if base == "brew" and args and args[0] in {"list"}:
        return {
            "mutability": "read", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base, "read_paths": [],
            "write_paths": [], "semantic_selectors": [],
        }
    if base == "sysctl":
        return _parse_sysctl(args)
    if base in {"python", "python3", "node", "npm", "pip", "pip3", "brew"}:
        if len(args) == 1 and args[0] in {"--version", "-V", "--help", "-h"}:
            return {
                "mutability": "read", "sensitivity": "private", "egress": "none",
                "unknown_reason": None, "profile": base, "read_paths": [],
                "write_paths": [], "semantic_selectors": [],
            }
        return _unknown_profile("opaque interpreter/package execution is not allowed", base)
    if base == "rm":
        paths = [_abs_operand(item, cwd) for item in _non_flags(args)]
        if not paths:
            return _unknown_profile("rm requires exact target paths", base)
        recursive = _recursive_option(base, args)
        return {
            "mutability": "irreversible", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base, "read_paths": [],
            "write_paths": paths, "semantic_selectors": [],
            "authority_scopes": [
                (path, recursive, True, False) for path in paths
            ],
        }
    if base == "find" and any(
        item in {
            "-delete", "-exec", "-execdir", "-ok", "-okdir",
            "-fprint", "-fprint0", "-fprintf", "-fls",
        }
        for item in args
    ):
        return _unknown_profile("find execution, deletion, and file-output predicates are not allowed", base)
    if base == "rg" and any(
        item == "--ignore-file" or item.startswith("--ignore-file=")
        for item in args
    ):
        return _unknown_profile(
            "rg ignore-file reads are outside the exact authority grammar", base,
        )
    risky_options = _UTILITY_EXECUTION_OPTIONS.get(base, ())
    if risky_options and _has_any_option(args, risky_options):
        return _unknown_profile("command-launching option is not allowed", base)
    if base == "zip" and any(item.startswith("-TT") for item in args):
        return _unknown_profile("command-launching option is not allowed", base)
    if base == "tar":
        parsed = _tar_paths(args, cwd)
        if parsed is None:
            return _unknown_profile("tar mode, archive, or operand shape is ambiguous", base)
        reads, writes, scopes = parsed
        return {
            "mutability": "reversible_write" if writes else "read",
            "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base,
            "read_paths": reads, "write_paths": writes,
            "semantic_selectors": [], "authority_scopes": scopes,
        }
    if base == "sed":
        parsed = _sed_paths(args, cwd)
        if parsed is None:
            return _unknown_profile("sed program or output shape is ambiguous", base)
        reads, writes = parsed
        return {
            "mutability": "reversible_write" if writes else "read",
            "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base,
            "read_paths": reads, "write_paths": writes,
            "semantic_selectors": [],
            "authority_scopes": _generic_authority_scopes(base, args, reads, writes),
        }
    if base == "zip":
        parsed = _zip_paths(args, cwd)
        if parsed is None:
            return _unknown_profile("zip archive or operand shape is ambiguous", base)
        reads, writes, scopes = parsed
        return {
            "mutability": "reversible_write", "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base,
            "read_paths": reads, "write_paths": writes,
            "semantic_selectors": [], "authority_scopes": scopes,
        }
    if base == "ffmpeg":
        parsed = _ffmpeg_paths(args, cwd)
        if parsed is None:
            return _unknown_profile("remote or ambiguous ffmpeg input/output is not allowed", base)
        reads, writes = parsed
        return {
            "mutability": "reversible_write" if writes else "read",
            "sensitivity": "private", "egress": "none",
            "unknown_reason": None, "profile": base,
            "read_paths": reads, "write_paths": writes,
            "semantic_selectors": [],
            "authority_scopes": _generic_authority_scopes(base, args, reads, writes),
        }
    reads, writes = _generic_paths(base, args, cwd)
    if base in _READ_ONLY_BASES:
        mutability = "reversible_write" if writes else "read"
    elif base in _LOCAL_WRITE_BASES:
        mutability = "reversible_write"
    else:
        return _unknown_profile("command has no admitted single-command profile", base)
    return {
        "mutability": mutability, "sensitivity": "private", "egress": "none",
        "unknown_reason": None, "profile": base, "read_paths": reads,
        "write_paths": writes, "semantic_selectors": [],
        "authority_scopes": _generic_authority_scopes(
            base, args, reads, writes,
        ),
    }


def _expand_command_argument(item: str) -> str:
    """Expand a leading home marker in an argv value or option assignment."""

    if item.startswith("~"):
        return os.path.expanduser(item)
    if "=" in item:
        prefix, value = item.split("=", 1)
        if value.startswith("~"):
            return f"{prefix}={os.path.expanduser(value)}"
    if len(item) > 2 and item[:2] in {"-o", "-O"} and item[2:].startswith("~"):
        return item[:2] + os.path.expanduser(item[2:])
    return item


def _arg_touches_dot_ora(args: Iterable[str]) -> bool:
    """Return whether an operand names a protected ``.ora`` path segment."""

    for item in args:
        if not item or item.startswith("-"):
            continue
        if ".ora" in item.replace("\\", "/").casefold().split("/"):
            return True
    return False


def _segment_axes(segment: str) -> dict[str, Any]:
    """Compatibility classifier for legacy callers of the old helper.

    Production dispatch uses the immutable prepared command directly.  This
    wrapper preserves the historical inspection API without creating a second
    parser or execution path.
    """

    profile = resolve_shell_profile(segment, cwd=WORKSPACE)
    try:
        tokens = _split_command_line(segment)
    except (CommandPreparationError, ValueError):
        tokens = []
    if tokens and _arg_touches_dot_ora(tokens[1:]):
        profile = dict(profile)
        profile["mutability"] = "irreversible"
    return profile


def prepare_command(command_string: str, cwd: str | None = None) -> PreparedCommand:
    """Parse exactly once and bind the final argv, cwd, env, and identities."""

    _scan_shell_grammar(command_string)
    tokens = _split_command_line(command_string)
    if not tokens:
        raise CommandPreparationError("command is required")
    if _ENV_ASSIGN_RE.match(tokens[0]):
        raise CommandPreparationError("leading environment assignments are not allowed")
    tokens = [tokens[0], *(_expand_command_argument(item) for item in tokens[1:])]
    canonical_cwd = os.path.realpath(os.path.expanduser(cwd or WORKSPACE))
    if not os.path.isdir(canonical_cwd):
        raise CommandPreparationError("explicit working directory is unavailable")
    base_env = _clean_env()
    executable_path = _resolve_executable(tokens[0], canonical_cwd, base_env)
    # A semantic grammar belongs only to the clean resolver's selected utility.
    # Real-path comparison retains platform aliases (for example /usr/bin/tar
    # resolving to bsdtar) without letting another executable named ``tar`` or
    # ``cat`` borrow that utility's authority profile.
    base = _basename(tokens[0])
    if base in _STATE_BUILTINS:
        raise CommandPreparationError("cwd and background must use explicit tool parameters")
    if _is_canonical_profile_executable(base, executable_path, canonical_cwd, base_env):
        profile = _profile(base, list(tokens[1:]), canonical_cwd, executable_path)
    else:
        profile = _unknown_profile(
            "path-qualified executable does not match the clean resolver's trusted canonical utility",
            base,
        )
    env = _clean_env(git_push=bool(profile.get("git_push")))
    # Resolve again with the final environment; a future per-command PATH rule
    # cannot silently diverge classification from execution.
    final_executable = _resolve_executable(tokens[0], canonical_cwd, env)
    if final_executable != executable_path:
        raise CommandPreparationError("clean execution PATH changed during preparation")
    executable_identity = _identity(final_executable)
    dependency_identities = tuple(
        _identity(path, force_digest=True)
        for path in profile.get("dependency_paths", [])
        if os.path.isfile(path)
    )
    final_args = list(profile.get("final_args", tokens[1:]))
    argv = (final_executable, *final_args)
    read_paths = tuple(dict.fromkeys(str(item) for item in profile.get("read_paths", [])))
    write_paths = tuple(dict.fromkeys(str(item) for item in profile.get("write_paths", [])))
    declared_scopes = profile.get("authority_scopes")
    if declared_scopes is None:
        declared_scopes = [
            *((path, False, True, False) for path in read_paths),
            *((path, False, True, False) for path in write_paths),
        ]
    scopes = tuple(
        (str(path), bool(recursive), bool(patterns), bool(children))
        for path, recursive, patterns, children in declared_scopes
    )
    semantic = list(profile.get("semantic_selectors", []))
    semantic.append(f"executable:{final_executable}")
    if profile.get("git_push") and env.get("SSH_AUTH_SOCK"):
        digest = hashlib.sha256(env["SSH_AUTH_SOCK"].encode("utf-8")).hexdigest()
        semantic.append(f"auth:ssh-agent#sha256:{digest}")
    audit_tokens = list(tokens)
    for raw_url, safe in profile.get("audit_urls", {}).items():
        audit_tokens = [safe if item == raw_url else item for item in audit_tokens]
    return PreparedCommand(
        argv=tuple(argv), cwd=canonical_cwd,
        env_items=tuple(sorted(env.items())), env_digest=_env_digest(env),
        executable=executable_identity, dependencies=dependency_identities,
        profile_name=str(profile.get("profile") or base),
        mutability=str(profile.get("mutability") or _UNKNOWN_AXES["mutability"]),
        sensitivity=str(profile.get("sensitivity") or _UNKNOWN_AXES["sensitivity"]),
        egress=str(profile.get("egress") or _UNKNOWN_AXES["egress"]),
        read_paths=read_paths, write_paths=write_paths,
        authority_scopes=scopes,
        semantic_selectors=tuple(dict.fromkeys(semantic)),
        network_urls=tuple(dict.fromkeys(profile.get("network_urls", []))),
        unknown_reason=profile.get("unknown_reason"),
        audit_command=shlex.join(audit_tokens),
    )


def revalidate_prepared_command(prepared: PreparedCommand) -> None:
    if not isinstance(prepared, PreparedCommand):
        raise CommandPreparationError("execution requires a prepared command")
    if _env_digest(prepared.env) != prepared.env_digest:
        raise CommandPreparationError("prepared execution environment drifted")
    if not _identity_matches(prepared.executable):
        raise CommandPreparationError("prepared executable identity drifted")
    if any(not _identity_matches(item) for item in prepared.dependencies):
        raise CommandPreparationError("prepared command dependency drifted")
    for value in prepared.network_urls:
        try:
            network_policy.validate_public_url(value)
        except network_policy.NetworkPolicyError as exc:
            raise CommandPreparationError(
                f"prepared network destination is no longer public: {exc}",
            ) from exc


def resolve_shell_profile(command_string: str, cwd: str | None = None) -> dict[str, Any]:
    """Compatibility classifier; execution itself never uses a shell."""

    try:
        return prepare_command(command_string, cwd=cwd).profile()
    except CommandPreparationError as exc:
        base = "unknown"
        try:
            parsed = _split_command_line(str(command_string))
            if parsed:
                base = _basename(parsed[0])
        except ValueError:
            pass
        return {
            **_UNKNOWN_AXES, "unknown": True, "reason": str(exc),
            "profile": base, "read_paths": [], "write_paths": [],
            "authority_scopes": [], "semantic_selectors": [],
        }


def classify_command(command: str | PreparedCommand) -> dict[str, str]:
    try:
        prepared = command if isinstance(command, PreparedCommand) else prepare_command(command)
    except CommandPreparationError as exc:
        return {"level": "blocked", "reason": str(exc)}
    if prepared.unknown:
        return {"level": "blocked", "reason": prepared.unknown_reason or "unclassified command"}
    if prepared.mutability in {"irreversible", "external_write"}:
        return {"level": "dangerous", "reason": f"{prepared.profile_name} requires exact approval"}
    if prepared.mutability == "reversible_write":
        return {"level": "moderate", "reason": "bounded reversible effect"}
    return {"level": "safe", "reason": "single-command read"}


def _refusal(message: str, *, background: bool) -> dict[str, Any]:
    text = f"SYSTEM PROTECTION: {message}; command was not executed"
    if background:
        return {"pid": None, "status": text}
    return {
        "stdout": "", "stderr": text, "returncode": -1,
        "timed_out": False, "truncated": False,
    }


def _protected_direct_call_allowed(prepared: PreparedCommand) -> bool:
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        if any(
            system_protection.approval_authority_conflict(
                path,
                recursive=recursive,
                patterns=patterns,
                children=children,
            )
            for path, recursive, patterns, children in prepared.authority_scopes
        ):
            return False
        if prepared.mutability not in {"irreversible", "external_write"}:
            return True
        return system_protection._ACTIVE_EXECUTION.get() is not None
    except Exception:
        return False


def execute_command(
    command: str | PreparedCommand,
    timeout: int = 60,
    cwd: str | None = None,
    background: bool = False,
    max_output_chars: int = 10_000,
) -> dict[str, Any]:
    """Run one already-prepared argv with ``shell=False``."""

    try:
        prepared = command if isinstance(command, PreparedCommand) else prepare_command(command, cwd=cwd)
        if cwd is not None and os.path.realpath(os.path.expanduser(cwd)) != prepared.cwd:
            raise CommandPreparationError("execution cwd differs from the prepared cwd")
        if prepared.unknown:
            raise CommandPreparationError(prepared.unknown_reason or "unclassified command")
        if not _protected_direct_call_allowed(prepared):
            raise CommandPreparationError("protected direct execution lacks the existing approval context")
        # This is the final practical check before spawn.  There remains a
        # non-atomic same-user replacement race on macOS; do not describe this
        # as an atomic guarantee in callers or tests.
        revalidate_prepared_command(prepared)
    except CommandPreparationError as exc:
        return _refusal(str(exc), background=background)

    kwargs = {
        "cwd": prepared.cwd,
        "env": prepared.env,
        "shell": False,
    }
    if background:
        try:
            process = subprocess.Popen(
                list(prepared.argv),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            MANAGED_PROCESSES.append(process)
            return {
                "pid": process.pid,
                "status": "started in background",
                "managed_pids": [item.pid for item in MANAGED_PROCESSES if item.poll() is None],
            }
        except Exception as exc:
            return {"pid": None, "status": f"failed to start: {exc}"}
    try:
        result = subprocess.run(
            list(prepared.argv), capture_output=True, text=True,
            timeout=timeout, **kwargs,
        )
        stdout, stderr = result.stdout or "", result.stderr or ""
        truncated = False
        if len(stdout) > max_output_chars:
            total = len(stdout)
            stdout = stdout[:max_output_chars] + f"\n\n[OUTPUT TRUNCATED — showing first {max_output_chars} of {total} characters.]"
            truncated = True
        if len(stderr) > max_output_chars:
            total = len(stderr)
            stderr = stderr[:max_output_chars] + f"\n\n[STDERR TRUNCATED — showing first {max_output_chars} of {total} characters.]"
            truncated = True
        return {
            "stdout": stdout, "stderr": stderr, "returncode": result.returncode,
            "timed_out": False, "truncated": truncated,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "", "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1, "timed_out": True, "truncated": False,
        }
    except Exception as exc:
        return {
            "stdout": "", "stderr": str(exc), "returncode": -1,
            "timed_out": False, "truncated": False,
        }


def stop_process(pid: int) -> str:
    target = next((item for item in MANAGED_PROCESSES if item.pid == pid), None)
    if target is None:
        return f"PID {pid} is not a managed process."
    try:
        target.send_signal(signal.SIGTERM)
        try:
            target.wait(timeout=5)
        except subprocess.TimeoutExpired:
            target.kill()
            target.wait(timeout=2)
        if target in MANAGED_PROCESSES:
            MANAGED_PROCESSES.remove(target)
        return f"Process {pid} stopped."
    except Exception as exc:
        return f"Error stopping PID {pid}: {exc}"


def cleanup_all() -> str:
    stopped: list[int] = []
    for process in list(MANAGED_PROCESSES):
        try:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                stopped.append(process.pid)
        except Exception:
            pass
    MANAGED_PROCESSES.clear()
    return f"Stopped {len(stopped)} background processes: {stopped}" if stopped else "No background processes to stop."


__all__ = [
    "CommandPreparationError", "FileIdentity", "MANAGED_PROCESSES",
    "PreparedCommand", "classify_command", "cleanup_all", "execute_command",
    "prepare_command", "resolve_shell_profile", "revalidate_prepared_command",
    "stop_process",
]
