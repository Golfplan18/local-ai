"""Standalone Programming for Ora.

Programming is entered explicitly.  It inspects a Git repository, asks only
material questions, produces one user-approved plan, gives an Ora-configured
model repository tools, and has a fresh model call review the actual repository
and checks.  Git branches and accepted-slice commits are the only execution
state and rollback mechanism.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


OUTCOMES = {"CONTINUE", "FIX", "DONE", "ASK USER"}
_MODEL_TOOL_RE = re.compile(
    r"<tool_call>\s*<n>(.*?)</n>\s*<parameters>(.*?)</parameters>\s*</tool_call>",
    re.DOTALL,
)
_SBPL_UNSAFE = ('"', "\\", "(", ")", "\n", "\r")
_RECOVERY_REFLOG_PREFIX = "Programming approved plan "
_ROLE_REPOSITORY_TOOLS = {
    "plan": {"repo_read", "repo_search"},
    "execute": {
        "repo_status", "repo_read", "repo_search", "repo_command",
        "repo_write", "repo_edit", "repo_delete",
    },
    "review": {
        "repo_status", "repo_read", "repo_search", "repo_command",
        "web_search", "web_fetch", "inspect_image", "inspect_pdf",
        "inspect_interface", "inspect_audio", "inspect_video", "inspect_artifact",
    },
}
_PLAN_REQUIRED_CATEGORIES = (
    ("outcome", r"\boutcome\s*:"),
    ("component scope", r"\b(?:component\s+)?scope\s*:"),
    ("non-goals", r"\bnon[- ]goals?\s*:"),
    ("protected work", r"\bprotected\s+work\s*:"),
    ("milestones", r"\bmilestones?\s*:"),
    ("completion criteria", r"\bcompletion(?:\s+criteria)?\s*:"),
    ("checks", r"\bchecks?\s*:"),
    ("authorized effects", r"\bauthorized\s+effects?\s*:"),
    ("Git finish line", r"\bgit\s+finish\s+line\s*:"),
)


class ProgrammingError(RuntimeError):
    """A request cannot safely cross the Programming boundary."""


def _run(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
    check: bool = False,
    env: dict[str, str] | None = None, input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
            input=input_text,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProgrammingError(f"command failed to run: {' '.join(argv)}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise ProgrammingError(f"{' '.join(argv)} failed: {detail}")
    return result


def _git(root: Path, *args: str, check: bool = True, timeout: int = 120) -> str:
    result = _run(["git", *args], cwd=root, timeout=timeout, check=check)
    return result.stdout.strip()


def _repository_root(value: str | os.PathLike[str]) -> Path:
    supplied = Path(value).expanduser()
    if supplied.is_symlink():
        raise ProgrammingError("repository path cannot be a symlink")
    try:
        supplied = supplied.resolve(strict=True)
    except OSError as exc:
        raise ProgrammingError("repository path is unavailable") from exc
    if not supplied.is_dir():
        raise ProgrammingError("repository path must be a directory")
    discovered = _run(
        ["git", "rev-parse", "--show-toplevel"], cwd=supplied, check=True
    ).stdout.strip()
    root = Path(discovered).resolve(strict=True)
    if root != supplied:
        raise ProgrammingError("repository path must be the Git worktree root")
    return root


def _safe_path(root: Path, value: str, *, must_exist: bool = False) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProgrammingError("repository-relative path is required")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or ".git" in relative.parts:
        raise ProgrammingError("path must stay inside the repository and outside .git")
    candidate = (root / relative).resolve(strict=must_exist)
    if os.path.commonpath((str(root), str(candidate))) != str(root):
        raise ProgrammingError("path escapes the repository")
    return candidate


def _text(path: Path, limit: int = 80_000) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return f"[unreadable: {exc}]"
    if b"\x00" in raw[:4096]:
        return "[binary file]"
    body = raw.decode("utf-8", "replace")
    if len(body) > limit:
        return body[:limit] + f"\n[truncated after {limit} characters]"
    return body


def _configured_remotes(root: Path) -> list[dict[str, Any]]:
    remotes = []
    for name in _git(root, "remote", check=False).splitlines():
        fetch_urls = _git(
            root, "remote", "get-url", "--all", name, check=False
        ).splitlines()
        push_urls = _git(
            root, "remote", "get-url", "--push", "--all", name, check=False
        ).splitlines()
        remotes.append({"name": name, "fetch_urls": fetch_urls, "push_urls": push_urls})
    return remotes


def inspect_repository(repository_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Inspect Git, instructions, tests, and live automation before questions."""
    root = _repository_root(repository_path)
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current", check=False) or "(detached)"
    status = _git(root, "status", "--porcelain=v1", check=False)
    tracked = _git(root, "ls-files", check=False).splitlines()

    instruction_names = {"AGENTS.md", "CLAUDE.md", "README.md", "README.rst"}
    instructions: list[dict[str, str]] = []
    for name in tracked:
        path = root / name
        if path.name in instruction_names and path.is_file():
            instructions.append({"path": name, "content": _text(path, 50_000)})

    test_markers = (
        "test", "spec", "pyproject.toml", "pytest.ini", "tox.ini",
        "package.json", "Makefile", "justfile", "Cargo.toml", "go.mod",
    )
    tests = [
        name for name in tracked
        if any(marker.casefold() in name.casefold() for marker in test_markers)
    ][:400]

    automation_paths = [
        name for name in tracked
        if name.startswith((".github/workflows/", ".gitlab-ci", ".circleci/"))
        or name in {"Jenkinsfile", "Taskfile.yml"}
    ]
    hook_path = _git(root, "config", "--get", "core.hooksPath", check=False)
    effective_hooks = Path(
        hook_path or _git(root, "rev-parse", "--git-path", "hooks")
    ).expanduser()
    if not effective_hooks.is_absolute():
        effective_hooks = root / effective_hooks
    active_hooks = []
    if effective_hooks.is_dir():
        for path in sorted(effective_hooks.iterdir()):
            if path.is_file() and os.access(path, os.X_OK) and not path.name.endswith(".sample"):
                active_hooks.append({"name": path.name, "content": _text(path, 30_000)})
                if len(active_hooks) >= 20:
                    break
    automation = {
        "paths": automation_paths[:100],
        "contents": {
            name: _text(root / name, 30_000) for name in automation_paths[:20]
            if (root / name).is_file()
        },
        "git_hooks_path": hook_path or ".git/hooks (default)",
        "active_git_hooks": active_hooks,
        "remotes": _configured_remotes(root),
    }
    return {
        "root": str(root),
        "head": head,
        "branch": branch,
        "status": status,
        "tracked_files": tracked[:2_000],
        "tracked_file_count": len(tracked),
        "instructions": instructions,
        "test_candidates": tests,
        "automation": automation,
    }


def _tool_calls(text: str) -> list[dict[str, Any]]:
    calls = []
    for raw_name, raw_parameters in _MODEL_TOOL_RE.findall(text or ""):
        try:
            parameters = json.loads(raw_parameters.strip())
        except json.JSONDecodeError as exc:
            parameters = {"_parse_error": str(exc), "raw": raw_parameters.strip()}
        calls.append({"name": raw_name.strip(), "parameters": parameters})
    return calls


def _without_tool_calls(text: str) -> str:
    return _MODEL_TOOL_RE.sub("", text or "").strip()


def _call_model(
    call_model_fn: Callable[..., str],
    messages: list[dict[str, str]],
    endpoint: dict[str, Any],
    images: list[dict[str, str]] | None = None,
) -> str:
    bounded_endpoint = dict(endpoint)
    bounded_endpoint.setdefault("request_timeout_seconds", 120)
    try:
        return call_model_fn(messages, bounded_endpoint, images=images)
    except TypeError:
        return call_model_fn(messages, bounded_endpoint)


def _sandbox_path(path: Path) -> str:
    value = os.path.realpath(path)
    if any(character in value for character in _SBPL_UNSAFE):
        raise ProgrammingError("repository path cannot be represented safely in the sandbox")
    return value


def _copy_working_tree(root: Path, snapshot: Path) -> None:
    """Overlay the exact working filesystem without copying any Git metadata."""
    for item in snapshot.iterdir():
        if item.name == ".git":
            continue
        if item.is_symlink() or item.is_file():
            item.unlink()
        else:
            shutil.rmtree(item)

    def exclude_git(_directory: str, names: list[str]) -> set[str]:
        return {".git"} if ".git" in names else set()

    for item in root.iterdir():
        if item.name == ".git":
            continue
        destination = snapshot / item.name
        if item.is_symlink():
            destination.symlink_to(os.readlink(item))
        elif item.is_dir():
            shutil.copytree(
                item, destination, symlinks=True, ignore=exclude_git
            )
        else:
            shutil.copy2(item, destination, follow_symlinks=False)


def _sandbox_profile(root: Path, snapshot: Path, temporary: Path) -> str:
    source = _sandbox_path(root)
    copy = _sandbox_path(snapshot)
    scratch = _sandbox_path(temporary)
    home = _sandbox_path(Path.home())
    if os.path.commonpath((source, scratch)) == source:
        raise ProgrammingError("sandbox scratch directory cannot be inside the repository")
    return "".join((
        "(version 1)",
        "(allow default)",
        "(deny network*)(deny appleevent-send)(deny signal)",
        '(allow network-bind (local ip "localhost:*"))',
        '(allow network-inbound (local ip "localhost:*"))',
        '(allow network-outbound (remote ip "localhost:*"))',
        f'(deny file-read* (subpath "{home}"))',
        f'(deny file-read* (subpath "{source}"))',
        f'(allow file-read* (subpath "{scratch}"))',
        f'(allow file-read* (subpath "{copy}"))',
        f'(deny file-read* (subpath "{source}"))',
        "(deny file-write*)",
        f'(allow file-write* (subpath "{scratch}"))',
        '(allow file-write* (subpath "/dev"))',
        f'(deny file-write* (subpath "{source}"))',
    ))


def _command_environment(home: Path, temporary: Path) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL")
        if key in os.environ
    }
    environment.update({"HOME": str(home), "TMPDIR": str(temporary),
                        "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    return environment


def _command_tool(root: Path, parameters: dict[str, Any], _role: str) -> str:
    root = root.resolve(strict=True)
    argv = parameters.get("argv")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(item, str) and item for item in argv
    ):
        raise ProgrammingError("repo_command argv must be a non-empty string list")
    relative_cwd = str(parameters.get("cwd") or ".")
    cwd = _safe_path(root, relative_cwd, must_exist=True)
    if not cwd.is_dir():
        raise ProgrammingError("repo_command cwd must be a directory")
    timeout = int(parameters.get("timeout") or 120)
    timeout = max(1, min(timeout, 1_800))
    sandbox = shutil.which("sandbox-exec") if sys.platform == "darwin" else None
    if not sandbox:
        raise ProgrammingError("repo_command is unavailable without the Darwin sandbox")
    temporary_root = Path("/private/tmp").resolve(strict=True)
    if os.path.commonpath((str(root), str(temporary_root))) == str(root):
        raise ProgrammingError("repository cannot contain the sandbox scratch root")
    temporary_path: Path | None = None
    result: subprocess.CompletedProcess[str]
    with tempfile.TemporaryDirectory(prefix="ora-programming-command-",
                                     dir=temporary_root) as raw_temporary:
        temporary_path = Path(raw_temporary).resolve()
        snapshot = temporary_path / "repository"
        home = temporary_path / "home"
        home.mkdir()
        _run(
            ["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(root), str(snapshot)],
            cwd=temporary_path,
            timeout=300,
            check=True,
        )
        for name in _git(snapshot, "remote", check=False).splitlines():
            _git(snapshot, "remote", "remove", name)
        for remote in _configured_remotes(root):
            fetch_urls = remote["fetch_urls"]
            if not fetch_urls:
                continue
            _git(snapshot, "remote", "add", remote["name"], fetch_urls[0])
            for url in fetch_urls[1:]:
                _git(snapshot, "remote", "set-url", "--add", remote["name"], url)
            for url in remote["push_urls"]:
                _git(snapshot, "remote", "set-url", "--add", "--push", remote["name"], url)
        _run(["git", "read-tree", "HEAD"], cwd=snapshot, check=True)
        _copy_working_tree(root, snapshot)
        snapshot_cwd = _safe_path(
            snapshot, str(cwd.relative_to(root)), must_exist=True
        )
        profile = _sandbox_profile(root, snapshot, temporary_path)
        try:
            result = subprocess.run(
                [sandbox, "-p", profile, *argv],
                cwd=str(snapshot_cwd),
                text=True,
                capture_output=True,
                timeout=timeout,
                env=_command_environment(home, temporary_path),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProgrammingError(f"sandboxed command failed to run: {exc}") from exc
    if temporary_path.exists():
        raise ProgrammingError("sandboxed command cleanup failed")
    output = (result.stdout or "") + (result.stderr or "")
    if len(output) > 80_000:
        output = output[:80_000] + "\n[output truncated]"
    return json.dumps({"returncode": result.returncode, "output": output})


def _image_payload(path: Path) -> dict[str, str]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if not mime.startswith("image/"):
        raise ProgrammingError("inspect_image requires an image file")
    return {
        "name": path.name,
        "mime": mime,
        "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
    }


def _pdf_payloads(
    path: Path, start_page: int = 1, end_page: int | None = None,
) -> list[dict[str, str]]:
    if path.suffix.casefold() != ".pdf":
        raise ProgrammingError("inspect_pdf requires a PDF file")
    with tempfile.TemporaryDirectory(prefix="ora-programming-pdf-") as temp:
        prefix = Path(temp) / "page"
        page_args = ["-f", str(start_page)]
        if end_page is not None:
            page_args.extend(("-l", str(end_page)))
        result = subprocess.run(
            ["pdftoppm", *page_args, "-png", "-r", "120", str(path), str(prefix)],
            text=True,
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise ProgrammingError(f"PDF rendering failed: {result.stderr.strip()}")
        return [_image_payload(item) for item in sorted(Path(temp).glob("page-*.png"))]


def _interface_payloads(root: Path, parameters: dict[str, Any]) -> list[dict[str, str]]:
    url = str(parameters.get("url") or "").strip()
    if url and not re.match(r"^https?://", url, re.IGNORECASE):
        raise ProgrammingError("inspect_interface URL must use HTTP or HTTPS")
    if not url:
        path = _safe_path(root, str(parameters.get("path") or ""), must_exist=True)
        url = path.as_uri()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ProgrammingError("inspect_interface requires Playwright") from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(url, wait_until="load", timeout=90_000)
            raw = page.screenshot(full_page=True, type="png")
        finally:
            browser.close()
    return [{"name": "interface.png", "mime": "image/png",
             "base64": base64.b64encode(raw).decode("ascii")}]


def _media_metadata(path: Path) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        text=True, capture_output=True, timeout=60,
    )
    if result.returncode != 0:
        raise ProgrammingError(f"media inspection failed: {result.stderr.strip()}")
    return result.stdout.strip()[:40_000]


def _local_transcript(path: Path, temporary: Path) -> str:
    unavailable = "Local transcription unavailable; spoken content remains unverified."
    try:
        try:
            from orchestrator import transcription as local_transcription
        except ImportError:
            import transcription as local_transcription
        wav, output = temporary / "audio.wav", temporary / "transcript"
        local_transcription._extract_to_wav(path, wav)
        result = subprocess.run(
            [local_transcription.WHISPER_BINARY, "-m", str(local_transcription._resolve_model_path({})),
             "-f", str(wav), "-l", "auto", "-oj", "-of", str(output), "-np"],
            text=True, capture_output=True, timeout=600,
        )
        data = json.loads(output.with_suffix(".json").read_text()) if result.returncode == 0 else {}
        segments = [{"text": item.get("text", "")} for item in data.get("transcription", [])]
        kept, _ = local_transcription._filter_hallucinations(segments)
        return "Local transcript: " + re.sub(r"\s+", " ", " ".join(item["text"] for item in kept)).strip()
    except Exception as exc:
        return unavailable + f" ({type(exc).__name__})"


def _audio_payloads(path: Path) -> tuple[str, list[dict[str, str]]]:
    mime = mimetypes.guess_type(path.name)[0] or ""
    if not mime.startswith("audio/"):
        raise ProgrammingError("inspect_audio requires an audio file")
    with tempfile.TemporaryDirectory(prefix="ora-programming-audio-") as temp:
        transcript = _local_transcript(path, Path(temp))
        outputs = []
        for name, filter_value in (
            ("waveform.png", "showwavespic=s=1200x300:colors=0x2563eb"),
            ("spectrogram.png", "showspectrumpic=s=1200x600:legend=1"),
        ):
            target = Path(temp) / name
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                 "-lavfi", filter_value, "-frames:v", "1", str(target)],
                text=True, capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                raise ProgrammingError(f"audio rendering failed: {result.stderr.strip()}")
            outputs.append(_image_payload(target))
        return _media_metadata(path) + "\n" + transcript, outputs


def _video_payloads(path: Path, samples: int = 5) -> tuple[str, list[dict[str, str]]]:
    mime = mimetypes.guess_type(path.name)[0] or ""
    if not mime.startswith("video/"):
        raise ProgrammingError("inspect_video requires a video file")
    metadata = _media_metadata(path)
    try:
        duration = float((json.loads(metadata).get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        duration = 0
    count = max(1, min(int(samples), 12))
    positions = [0.0] if count == 1 or duration <= 0 else [duration * i / count for i in range(count)]
    with tempfile.TemporaryDirectory(prefix="ora-programming-video-") as temp:
        images = []
        for index, position in enumerate(positions, 1):
            target = Path(temp) / f"frame-{index:02d}.png"
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{position:.3f}",
                 "-i", str(path), "-frames:v", "1", "-vf",
                 "scale=-2:720:force_original_aspect_ratio=decrease", str(target)],
                text=True, capture_output=True, timeout=120,
            )
            if result.returncode != 0 or not target.exists():
                raise ProgrammingError(f"video frame extraction failed: {result.stderr.strip()}")
            images.append(_image_payload(target))
        return metadata + "\n" + _local_transcript(path, Path(temp)), images


def _artifact_payloads(path: Path) -> list[dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="ora-programming-artifact-") as temp:
        temporary = Path(temp)
        converter = shutil.which("soffice")
        if converter:
            result = subprocess.run(
                [converter, "--headless", "--convert-to", "pdf", "--outdir", str(temporary), str(path)],
                text=True, capture_output=True, timeout=180,
            )
            rendered = next(temporary.glob("*.pdf"), None)
            if result.returncode == 0 and rendered:
                return _pdf_payloads(rendered)
        quicklook = shutil.which("qlmanage")
        if quicklook:
            result = subprocess.run(
                [quicklook, "-t", "-s", "1600", "-o", str(temporary), str(path)],
                text=True, capture_output=True, timeout=120,
            )
            previews = sorted(temporary.glob("*.png"))
            if result.returncode == 0 and previews:
                return [_image_payload(item) for item in previews]
    raise ProgrammingError("no available renderer could inspect this artifact")


def _tool_result(
    root: Path,
    name: str,
    parameters: dict[str, Any],
    role: str,
    web_fetch_fn: Callable[..., Any] | None,
    web_search_fn: Callable[..., Any] | None,
) -> tuple[str, list[dict[str, str]]]:
    if parameters.get("_parse_error"):
        raise ProgrammingError(f"malformed parameters for {name}: {parameters['_parse_error']}")
    if name == "repo_status":
        return json.dumps({
            "head": _git(root, "rev-parse", "HEAD"),
            "branch": _git(root, "branch", "--show-current", check=False),
            "status": _git(root, "status", "--porcelain=v1", check=False),
        }), []
    if name == "repo_read":
        path = _safe_path(root, str(parameters.get("path") or ""), must_exist=True)
        if not path.is_file():
            raise ProgrammingError("repo_read path must be a file")
        lines = _text(path, 300_000).splitlines()
        start = max(1, int(parameters.get("start_line") or 1))
        end = min(len(lines), int(parameters.get("end_line") or (start + 499)))
        body = "\n".join(lines[start - 1:end])
        return f"{parameters['path']}:{start}-{end}\n{body}", []
    if name == "repo_search":
        query = str(parameters.get("query") or "")
        if not query:
            raise ProgrammingError("repo_search query is required")
        target = str(parameters.get("path") or ".")
        _safe_path(root, target, must_exist=True)
        result = _run(["rg", "-n", "--", query, target], cwd=root, timeout=60)
        body = ((result.stdout or "") + (result.stderr or ""))[:80_000]
        return json.dumps({"returncode": result.returncode, "output": body}), []
    if name == "repo_command":
        return _command_tool(root, parameters, role), []
    if name in {"repo_write", "repo_edit", "repo_delete"}:
        if role != "execute":
            raise ProgrammingError(f"{name} is executor-only")
        path = _safe_path(root, str(parameters.get("path") or ""))
        if path.exists() and path.is_symlink():
            raise ProgrammingError("repository writes cannot follow symlinks")
        if name == "repo_delete":
            if not path.is_file():
                raise ProgrammingError("repo_delete only removes files")
            path.unlink()
            return f"deleted {path.relative_to(root)}", []
        if name == "repo_edit":
            if not path.is_file():
                raise ProgrammingError("repo_edit requires an existing file")
            old = str(parameters.get("old") or "")
            new = str(parameters.get("new") or "")
            body = path.read_text(encoding="utf-8")
            count = body.count(old)
            if not old or count != 1:
                raise ProgrammingError(f"repo_edit old text must occur exactly once; found {count}")
            content = body.replace(old, new, 1)
        else:
            content = parameters.get("content")
            if not isinstance(content, str):
                raise ProgrammingError("repo_write content must be text")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".ora-programming-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return f"wrote {path.relative_to(root)}", []
    if name == "web_fetch":
        if role != "review":
            raise ProgrammingError("external evidence is reviewer-only")
        if web_fetch_fn is None:
            try:
                from orchestrator.tools.web_fetch import web_fetch as web_fetch_fn
            except ImportError:
                from tools.web_fetch import web_fetch as web_fetch_fn
        result = web_fetch_fn(str(parameters.get("url") or ""), raw=True)
        return json.dumps(result, default=str)[:120_000], []
    if name == "web_search":
        if role != "review":
            raise ProgrammingError("external evidence is reviewer-only")
        if web_search_fn is None:
            try:
                from orchestrator.tools.web_search import web_search as web_search_fn
            except ImportError:
                from tools.web_search import web_search as web_search_fn
        result = web_search_fn(
            str(parameters.get("query") or ""),
            max_results=max(1, min(int(parameters.get("max_results") or 5), 10)),
        )
        return str(result)[:120_000], []
    if name == "inspect_image":
        if role != "review":
            raise ProgrammingError("non-text evidence is reviewer-only")
        path = _safe_path(root, str(parameters.get("path") or ""), must_exist=True)
        return f"Attached {path.relative_to(root)} for direct visual inspection.", [_image_payload(path)]
    if name == "inspect_pdf":
        if role != "review":
            raise ProgrammingError("non-text evidence is reviewer-only")
        path = _safe_path(root, str(parameters.get("path") or ""), must_exist=True)
        start_page = max(1, int(parameters.get("start_page") or 1))
        raw_end = parameters.get("end_page")
        end_page = int(raw_end) if raw_end not in (None, "") else None
        if end_page is not None and end_page < start_page:
            raise ProgrammingError("inspect_pdf end_page precedes start_page")
        images = _pdf_payloads(path, start_page, end_page)
        return f"Attached {len(images)} rendered page(s) from {path.relative_to(root)}.", images
    if name == "inspect_interface":
        if role != "review":
            raise ProgrammingError("non-text evidence is reviewer-only")
        images = _interface_payloads(root, parameters)
        return "Attached a browser-rendered interface screenshot.", images
    if name in {"inspect_audio", "inspect_video", "inspect_artifact"}:
        if role != "review":
            raise ProgrammingError("non-text evidence is reviewer-only")
        path = _safe_path(root, str(parameters.get("path") or ""), must_exist=True)
        if name == "inspect_audio":
            metadata, images = _audio_payloads(path)
            return f"Direct audio-derived waveform, spectrogram, and metadata:\n{metadata}", images
        if name == "inspect_video":
            metadata, images = _video_payloads(path, int(parameters.get("samples") or 5))
            return f"Attached {len(images)} frames sampled across the video. Metadata:\n{metadata}", images
        images = _artifact_payloads(path)
        return f"Attached {len(images)} rendered view(s) of {path.relative_to(root)}.", images
    raise ProgrammingError(f"unknown Programming tool: {name}")


def _tool_instructions(role: str) -> str:
    common = """
Tools use this exact form:
<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>
<tool_call><n>repo_read</n><parameters>{"path":"relative/file","start_line":1,"end_line":500}</parameters></tool_call>
<tool_call><n>repo_search</n><parameters>{"query":"literal text","path":"."}</parameters></tool_call>
<tool_call><n>repo_command</n><parameters>{"argv":["command","arg"],"cwd":".","timeout":120}</parameters></tool_call>
"""
    if role == "execute":
        common += """
<tool_call><n>repo_write</n><parameters>{"path":"relative/file","content":"complete text"}</parameters></tool_call>
<tool_call><n>repo_edit</n><parameters>{"path":"relative/file","old":"exact unique text","new":"replacement"}</parameters></tool_call>
<tool_call><n>repo_delete</n><parameters>{"path":"relative/file"}</parameters></tool_call>
"""
    if role == "review":
        common += """
<tool_call><n>web_search</n><parameters>{"query":"outside fact","max_results":5}</parameters></tool_call>
<tool_call><n>web_fetch</n><parameters>{"url":"https://authoritative.example/path"}</parameters></tool_call>
<tool_call><n>inspect_image</n><parameters>{"path":"relative/image.png"}</parameters></tool_call>
<tool_call><n>inspect_pdf</n><parameters>{"path":"relative/document.pdf"}</parameters></tool_call>
<tool_call><n>inspect_interface</n><parameters>{"path":"relative/interface.html"}</parameters></tool_call>
<tool_call><n>inspect_interface</n><parameters>{"url":"http://localhost:3000"}</parameters></tool_call>
<tool_call><n>inspect_audio</n><parameters>{"path":"relative/audio.wav"}</parameters></tool_call>
<tool_call><n>inspect_video</n><parameters>{"path":"relative/video.mp4","samples":5}</parameters></tool_call>
<tool_call><n>inspect_artifact</n><parameters>{"path":"relative/document.docx"}</parameters></tool_call>
"""
    return common


def _agent(
    *,
    root: Path,
    endpoint: dict[str, Any] | list[dict[str, Any]],
    messages: list[dict[str, str]],
    role: str,
    call_model_fn: Callable[..., str],
    web_fetch_fn: Callable[..., Any] | None = None,
    web_search_fn: Callable[..., Any] | None = None,
    terminal_validator: Callable[[str], str | None] | None = None,
    terminal_correction: str = "",
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    used_tools: list[str] = []
    changed_paths: set[str] = set()
    candidate_successful_tools: list[str] = []
    pending_images: list[dict[str, str]] | None = None
    candidates = _endpoint_candidates(endpoint)
    candidate_index = 0
    tool_corrections: set[str] = set()
    terminal_corrections: set[str] = set()
    failures: list[str] = []
    while True:
        if candidate_index >= len(candidates):
            attempted = ", ".join(filter(None, (_endpoint_id(item) for item in candidates)))
            detail = "; ".join(failures[-3:]) or "no usable response"
            raise ProgrammingError(
                f"configured {role} endpoints failed ({attempted or 'unidentified'}): {detail}"
            )
        active_endpoint = candidates[candidate_index]
        active_id = _endpoint_id(active_endpoint) or f"candidate-{candidate_index + 1}"
        try:
            response = _call_model(
                call_model_fn, messages, active_endpoint, pending_images
            )
        except Exception as exc:
            failures.append(f"{active_id}: {type(exc).__name__}")
            candidate_index += 1
            candidate_successful_tools = []
            continue
        if _model_error_response(response):
            failures.append(f"{active_id}: transport/auth/quota response")
            candidate_index += 1
            candidate_successful_tools = []
            continue
        pending_images = None
        calls = _tool_calls(response)
        if not calls:
            required = _ROLE_REPOSITORY_TOOLS.get(role)
            if required and not any(
                name in required for name in candidate_successful_tools
            ):
                if active_id not in tool_corrections:
                    tool_corrections.add(active_id)
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "PROTOCOL CORRECTION: the repository and evidence tools "
                            "listed in the system message are available. Use at least "
                            "one of them now to inspect or change the real task repository "
                            "as your role requires. Do not return a tools-unavailable "
                            "refusal or unsupported prose."
                        ),
                    })
                    continue
                failures.append(f"{active_id}: no successful repository/evidence tool use")
                candidate_index += 1
                candidate_successful_tools = []
                continue
            terminal = _without_tool_calls(response)
            issue = terminal_validator(terminal) if terminal_validator else None
            if issue:
                if active_id not in terminal_corrections:
                    terminal_corrections.add(active_id)
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": terminal_correction or (
                            "PROTOCOL CORRECTION: " + issue + ". Return a valid "
                            "terminal response now."
                        ),
                    })
                    continue
                failures.append(f"{active_id}: invalid terminal response")
                candidate_index += 1
                candidate_successful_tools = []
                continue
            return {
                "response": terminal,
                "tools": used_tools,
                "endpoint": active_id,
                "changed_paths": sorted(changed_paths),
            }
        rendered = []
        next_images: list[dict[str, str]] = []
        for call in calls:
            name = call["name"]
            try:
                result, images = _tool_result(
                    root, name, call["parameters"], role, web_fetch_fn, web_search_fn
                )
                rendered.append(f"[Tool: {name} | outcome: ok]\n{result}")
                next_images.extend(images)
                candidate_successful_tools.append(name)
                if role == "execute" and name in {"repo_write", "repo_edit", "repo_delete"}:
                    changed_paths.add(_safe_path(
                        root, str(call["parameters"].get("path") or "")
                    ).relative_to(root).as_posix())
            except Exception as exc:
                rendered.append(f"[Tool: {name} | outcome: error]\n{exc}")
            used_tools.append(name)
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": "[Tool results]\n" + "\n\n".join(rendered)})
        pending_images = next_images or None


def _endpoint_id(endpoint: dict[str, Any] | None) -> str:
    if not endpoint:
        return ""
    return str(endpoint.get("id") or endpoint.get("name") or endpoint.get("model") or "")


def _endpoint_family(endpoint: dict[str, Any]) -> str:
    return str(
        endpoint.get("training_family")
        or endpoint.get("provider")
        or endpoint.get("service")
        or endpoint.get("engine")
        or _endpoint_id(endpoint)
    ).casefold()


def _endpoint_candidates(
    endpoint: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw = endpoint if isinstance(endpoint, list) else [endpoint]
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict) or not _standalone_endpoint(item):
            continue
        key = (_endpoint_id(item), _endpoint_family(item))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(item)
    if not candidates:
        raise ProgrammingError("no standalone Ora model is configured for Programming")
    return candidates


def _model_error_response(response: Any) -> bool:
    if not isinstance(response, str):
        return False
    text = response.strip().casefold()
    if not text:
        return False
    if text.startswith("[error"):
        return True
    if len(text) > 2_000 or _tool_calls(response):
        return False
    if re.match(
        r"^(?:error(?:\s+code)?\s*[:=-]?\s*)?(?:http\s*)?[45]\d\d\b",
        text,
    ):
        return True
    return any(marker in text for marker in (
        "insufficient balance",
        "insufficient quota",
        "quota exceeded",
        "rate limit exceeded",
        "authentication failed",
        "invalid api key",
    ))


def _standalone_endpoint(endpoint: dict[str, Any] | None) -> bool:
    if not endpoint:
        return False
    fields = " ".join(
        str(endpoint.get(key) or "")
        for key in ("provider", "engine", "type", "transport", "id", "name")
    ).casefold()
    return "claude-code" not in fields and "claude_code" not in fields and "codex" not in fields


def configured_endpoints() -> dict[str, list[dict[str, Any]]]:
    """Resolve resilient role candidates from Ora's existing configured slots."""
    try:
        from orchestrator.boot import get_slot_endpoint, load_routing_config
    except ImportError:
        from boot import get_slot_endpoint, load_routing_config
    config = load_routing_config()

    def candidates(*slots: str) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        seen_families: set[str] = set()
        deferred_same_family: list[dict[str, Any]] = []
        for slot in slots:
            endpoint = get_slot_endpoint(config, slot)
            if not _standalone_endpoint(endpoint):
                continue
            family = _endpoint_family(endpoint)
            if family in seen_families:
                deferred_same_family.append(endpoint)
                continue
            seen_families.add(family)
            resolved.append(endpoint)
        resolved.extend(deferred_same_family)
        return _endpoint_candidates(resolved)

    planner = candidates("breadth", "fast", "step1_cleanup", "rag_planner")
    executor = candidates("depth", "breadth", "fast", "step1_cleanup")
    reviewer = candidates(
        "vision_input", "verification", "evaluator", "breadth", "fast"
    )
    return {"planner": planner, "executor": executor, "reviewer": reviewer}


def _json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.DOTALL)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise ProgrammingError("planner did not return a JSON object")
        value = json.loads(stripped[start:end + 1])
    if not isinstance(value, dict):
        raise ProgrammingError("planner response must be an object")
    return value


def _plan_contract_contradictions(plan: str) -> list[str]:
    """Return observed planner text that conflicts with coordinator authority."""
    text = str(plan or "")
    rules = (
        (
            "exact-file whitelist",
            r"\b(?:(?:only|exclusively)\s+(?:change|edit|modify|touch|write|update)"
            r"\s+(?:the\s+)?(?:following\s+)?files?|(?:exact|fixed)\s+"
            r"(?:file|path)\s+(?:list|whitelist)|files?\s*:[^\n]{0,200}\bonly\b|"
            r"restrict\s+(?:changes|modifications)\s+to\s+(?:these\s+|the\s+following\s+)?"
            r"exact\s+files?|do\s+not\s+(?:change|edit|modify|touch|update)\s+any\s+other\s+files?|"
            r"(?:scope|authorized\s+effects?)\s*:[^\n]{0,100}\bonly\b[^\n]{0,100}"
            r"\b[\w.-]+\.[a-z0-9]{1,8}\b|\bonly\s+[\w./-]+\.[a-z0-9]{1,8}\s+"
            r"(?:is|was|may\s+be|can\s+be|should\s+be)?\s*(?:changed|edited|modified|touched)|"
            r"nothing\s+else\s+(?:in|within)\s+(?:the\s+)?(?:repo|repository|worktree)\s+"
            r"(?:changes|is\s+(?:changed|edited|modified|touched))|"
            r"(?:diff|status)[^\n]{0,100}\bshows?\s+only\b[^\n]{0,100}"
            r"(?:changed|edited|modified|touched)|\bno\s+(?:edits?|changes?)\s+to\b"
            r"[^\n]{0,160}\bother\s+than\b|\bonly\s+(?:the\s+)?[a-z][a-z0-9 _.-]{0,50}"
            r"\s+(?:is|was|may\s+be|can\s+be|should\s+be)?\s*(?:changed|edited|modified|touched))",
        ),
        (
            "task-branch prohibition",
            r"\b(?:(?:do\s+not|don't|avoid|without)\s+(?:create|creating|use|using)"
            r"(?:\s+or\s+switch)?\s+(?:a\s+)?(?:task\s+)?branches?|"
            r"no\s+(?:task\s+)?branch\s+creation|(?:stay|remain|work)\s+on\s+"
            r"(?:the\s+)?(?:current|main|master)\s+branch)\b",
        ),
        (
            "direct-main Git finish",
            r"\b(?:(?:work|commit|push)\s+directly\s+(?:on|to)\s+(?:the\s+)?"
            r"(?:main|master)|(?:commit|push|merge)\s+(?:directly\s+)?"
            r"(?:to|into|on)\s+(?:the\s+)?(?:main|master))\b",
        ),
    )
    return [label for label, pattern in rules if re.search(pattern, text, re.IGNORECASE)]


def _plan_payload_contract_contradictions(payload: dict[str, Any]) -> list[str]:
    """Validate every free-text field in a proposed plan payload."""
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(payload)
    observed: list[str] = []
    for label in _plan_contract_contradictions("\n".join(values)):
        if label not in observed:
            observed.append(label)
    return observed


def _plan_payload_issues(
    payload: dict[str, Any], configured_remotes: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return schema and authority-contract defects in a plan response."""
    issues = _plan_payload_contract_contradictions(payload)
    if payload.get("kind") != "plan":
        return issues + ["response is not a plan"]
    plan = str(payload.get("plan") or "").strip()
    if not plan:
        issues.append("missing plan narrative")
    else:
        for label, pattern in _PLAN_REQUIRED_CATEGORIES:
            if not re.search(pattern, plan, re.IGNORECASE):
                issues.append(f"missing {label}")
    milestones = payload.get("milestones")
    if (
        not isinstance(milestones, list)
        or not any(str(item).strip() for item in milestones)
    ):
        issues.append("missing milestones")
    finish = str(payload.get("git_finish_line") or "").strip()
    if finish not in {"local_commits", "push", "pull_request", "merge"}:
        issues.append("unsupported Git finish line")
    if finish != "local_commits":
        remote = str(payload.get("git_remote") or "").strip()
        target = str(payload.get("git_push_target") or "").strip()
        if not remote:
            issues.append("missing approved Git remote")
        if not target:
            issues.append("missing approved Git push target")
        if remote and not re.search(
            rf"\bgit\s+remote\s*:\s*{re.escape(remote)}(?:\b|\s|\.)", plan,
            re.IGNORECASE,
        ):
            issues.append("approved Git remote is not visible in plan")
        if target and target not in plan:
            issues.append("approved Git push target is not visible in plan")
        if configured_remotes is not None and remote and target:
            matching = [item for item in configured_remotes if item.get("name") == remote]
            if len(matching) != 1 or matching[0].get("push_urls") != [target]:
                issues.append("approved Git remote/push target is not configured exactly")
        if finish in {"pull_request", "merge"}:
            base = str(payload.get("git_pr_base") or "").strip()
            if not base:
                issues.append("missing approved pull-request base")
            elif not re.search(
                rf"\b(?:pull[- ]request|pr)\s+base\s*:\s*{re.escape(base)}(?:\b|\s|\.)",
                plan, re.IGNORECASE,
            ):
                issues.append("approved pull-request base is not visible in plan")
            try:
                _gh_repository(target)
            except ProgrammingError:
                issues.append("approved push target is not a GitHub repository")
    return issues


def plan_programming(
    *,
    objective: str,
    repository_path: str,
    question_round: int = 0,
    answers: list[dict[str, str]] | None = None,
    endpoints: dict[str, Any] | None = None,
    call_model_fn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Inspect first, then ask at most three material questions or return one plan."""
    if not str(objective or "").strip():
        raise ProgrammingError("objective is required")
    if question_round not in {0, 1, 2}:
        raise ProgrammingError("Programming permits at most two question rounds")
    snapshot = inspect_repository(repository_path)
    root = Path(snapshot["root"])
    if endpoints is None:
        endpoints = configured_endpoints()
    if call_model_fn is None:
        try:
            from orchestrator.boot import call_model as call_model_fn
        except ImportError:
            from boot import call_model as call_model_fn
    system = f"""You are Ora's Programming planner. You have no Codex or Claude Code dependency.

Inspect the repository, its instructions, implementation, tests, Git state, and live automation before asking anything. The initial inspection is below; use repository tools when more detail can change the plan.

Ask only questions whose answers materially change product outcome, scope, risk, cost, authority, or external effects. Ask at most three questions when fewer than two question rounds have occurred. This is planning pass {question_round + 1}; question rounds already used: {question_round}. On pass 3, choose reasonable defaults and return the plan instead of asking again.

Otherwise return one concise plan readable in about a minute. Use visible labels for Outcome, Component scope, Non-goals, Protected work, Milestones, Completion criteria, Checks, Authorized effects, and Git finish line. Do not include exact file whitelists, step counts, attempt ceilings, digests, schemas, ledgers, receipts, or tracking apparatus.

For push, pull request, or merge, visibly name exactly one configured Git remote and its single push URL, and return them as git_remote and git_push_target. For pull request or merge, also visibly name and return an explicit git_pr_base. Return JSON only. For questions: {{"kind":"questions","questions":["..."]}}. For a plan: {{"kind":"plan","plan":"...","milestones":["..."],"git_finish_line":"local_commits|push|pull_request|merge","git_remote":"...","git_push_target":"...","git_pr_base":"..."}}.
{_tool_instructions('plan')}
"""
    user = json.dumps({
        "objective": objective.strip(),
        "answers": answers or [],
        "repository_inspection": snapshot,
    }, ensure_ascii=False)
    planner_messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    result = _agent(
        root=root,
        endpoint=endpoints["planner"],
        messages=planner_messages,
        role="plan",
        call_model_fn=call_model_fn,
    )
    payload = _json_object(result["response"])
    if payload.get("kind") == "plan":
        issues = _plan_payload_issues(payload, snapshot["automation"]["remotes"])
        if issues:
            planner_messages.append({"role": "assistant", "content": result["response"]})
            planner_messages.append({
                "role": "user",
                "content": (
                    "PLANNING CONTRACT CORRECTION: the proposed plan conflicts with "
                    "the Programming operating contract: " + ", ".join(issues) +
                    ". The coordinator owns task-branch creation and the approved Git "
                    "finish line. Replace the plan now without exact-file whitelists or "
                    "direct-main/no-branch instructions. Name the expected component scope, "
                    "but do not prohibit other necessary paths the coordinator may discover "
                    "during implementation. Return one corrected plan JSON object."
                ),
            })
            result = _agent(
                root=root,
                endpoint=endpoints["planner"],
                messages=planner_messages,
                role="plan",
                call_model_fn=call_model_fn,
            )
            payload = _json_object(result["response"])
            remaining = _plan_payload_issues(payload, snapshot["automation"]["remotes"])
            if payload.get("kind") != "plan" or remaining:
                raise ProgrammingError(
                    "planner repeated an invalid Programming plan"
                )
    kind = payload.get("kind")
    if kind == "questions":
        questions = payload.get("questions")
        if question_round >= 2:
            raise ProgrammingError("planner asked questions after two question rounds")
        if not isinstance(questions, list) or not questions or len(questions) > 3:
            raise ProgrammingError("planner must ask one to three material questions")
        return {
            "kind": "questions",
            "questions": [str(item).strip() for item in questions],
            "question_round": question_round + 1,
            "inspection": {key: snapshot[key] for key in ("root", "head", "branch", "status")},
        }
    if kind != "plan":
        raise ProgrammingError("planner must return questions or one plan")
    plan = str(payload.get("plan") or "").strip()
    milestones = payload.get("milestones")
    finish = str(payload.get("git_finish_line") or "local_commits").strip()
    if not plan or not isinstance(milestones, list) or not milestones:
        raise ProgrammingError("planner returned an incomplete plan")
    if finish not in {"local_commits", "push", "pull_request", "merge"}:
        raise ProgrammingError("Git finish line is unsupported")
    planned = {
        "kind": "plan",
        "plan": plan,
        "milestones": [str(item).strip() for item in milestones if str(item).strip()],
        "git_finish_line": finish,
        "baseline": {key: snapshot[key] for key in ("root", "head", "branch", "status")},
    }
    for field in ("git_remote", "git_push_target", "git_pr_base"):
        if str(payload.get(field) or "").strip():
            planned[field] = str(payload[field]).strip()
    return planned


def _slug(objective: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", objective.casefold()).strip("-")
    return (value[:42].rstrip("-") or "programming-task")


def _task_branch_base(objective: str, baseline: str) -> str:
    return f"ora/{_slug(objective)}-{baseline[:8]}"


def _task_branch(
    root: Path, objective: str, baseline: str, approved_plan: dict[str, Any] | None = None,
) -> str:
    base = _task_branch_base(objective, baseline)
    name = base
    suffix = 2
    while _git(root, "show-ref", "--verify", f"refs/heads/{name}", check=False):
        name = f"{base}-{suffix}"
        suffix += 1
    if approved_plan is None:
        _git(root, "switch", "-c", name)
    else:
        recovery = base64.urlsafe_b64encode(json.dumps(
            {"objective": objective, "plan": approved_plan},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).decode("ascii")
        _git(root, "update-ref", "-m", _RECOVERY_REFLOG_PREFIX + recovery,
             f"refs/heads/{name}", baseline)
        _git(root, "switch", name)
    return name


def recover_programming(repository_path: str) -> dict[str, Any]:
    """Reconstruct a resumable approved task from its Git branch and reflog."""
    root = _repository_root(repository_path)
    branch = _git(root, "branch", "--show-current", check=False)
    if not branch:
        raise ProgrammingError("no checked-out Programming task branch")
    messages = _git(
        root, "reflog", "show", "--format=%gs", f"refs/heads/{branch}", check=False
    ).splitlines()
    encoded = next((line[len(_RECOVERY_REFLOG_PREFIX):] for line in messages
                    if line.startswith(_RECOVERY_REFLOG_PREFIX)), "")
    try:
        recovered = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
        objective = str(recovered["objective"])
        plan = recovered["plan"]
        baseline = str(plan["baseline"]["head"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProgrammingError("checked-out branch has no recoverable approved plan") from exc
    base = _task_branch_base(objective, baseline)
    suffix = branch.removeprefix(base) if branch.startswith(base) else "invalid"
    valid_branch = suffix == "" or (
        suffix.startswith("-") and suffix[1:].isdigit() and int(suffix[1:]) >= 2
    )
    ancestor = _run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"], cwd=root).returncode == 0
    if not valid_branch or not ancestor or plan.get("baseline", {}).get("root") != str(root):
        raise ProgrammingError("Programming task branch no longer matches its approved baseline")
    subjects = set(_git(root, "log", "--format=%s", f"{baseline}..HEAD", check=False).splitlines())
    accepted = [item for item in plan.get("milestones", []) if _commit_subject(str(item)) in subjects]
    return {
        "objective": objective, "plan": plan, "branch": branch,
        "accepted_milestones": accepted,
        "pending_milestones": [item for item in plan.get("milestones", []) if item not in accepted],
        "has_uncommitted_changes": bool(_git(root, "status", "--porcelain=v1", check=False)),
    }


def _raw_diff(root: Path, base: str) -> str:
    parts = [_git(root, "diff", "--no-ext-diff", "--binary", base, check=False)]
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                     cwd=root).stdout.split("\0")
    for name in (item for item in untracked if item):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or ".git" in relative.parts:
            raise ProgrammingError("Git returned an unsafe untracked path")
        result = _run(
            ["git", "diff", "--no-index", "--binary", "--", os.devnull, name],
            cwd=root,
        )
        if result.returncode not in {0, 1}:
            raise ProgrammingError(f"could not inspect untracked file {name}")
        parts.append(result.stdout)
    return "\n".join(part for part in parts if part)


def _tree_fingerprint(root: Path, base: str) -> str:
    diff = _raw_diff(root, base)
    status = _git(root, "status", "--porcelain=v1", check=False)
    return hashlib.sha256((diff + "\n" + status).encode("utf-8")).hexdigest()


def _dirty_paths(root: Path, base: str) -> list[str]:
    tracked = _run(
        ["git", "diff", "--no-renames", "--name-only", "-z", base, "--"],
        cwd=root,
    ).stdout.split("\0")
    untracked = _run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root
    ).stdout.split("\0")
    return sorted({path for path in (*tracked, *untracked) if path})


def _plan_mentions_path(plan: dict[str, Any], path: str) -> bool:
    approved_text = "\n".join((
        str(plan.get("plan") or ""),
        *(str(item) for item in plan.get("milestones") or []),
    ))
    leading_boundary = r"[\w./-]"
    return re.search(
        rf"(?<!{leading_boundary}){re.escape(path)}(?![\w/-]|\.\w)", approved_text
    ) is not None


def _commit_subject(milestone: str) -> str:
    return "Programming: " + re.sub(r"\s+", " ", milestone).strip()[:68]


def _commit_slice(root: Path, milestone: str, parent: str, patch: str) -> str | None:
    with tempfile.TemporaryDirectory(prefix="ora-programming-index-") as temporary:
        index = str(Path(temporary) / "index")
        environment = {"GIT_INDEX_FILE": index}
        _run(["git", "read-tree", parent], cwd=root, env=environment, check=True)
        if patch:
            _run(
                ["git", "apply", "--cached", "--binary", "--whitespace=nowarn", "-"],
                cwd=root,
                env=environment,
                input_text=patch + "\n",
                check=True,
            )
        tree = _run(["git", "write-tree"], cwd=root, env=environment,
                    check=True).stdout.strip()
    if tree == _git(root, "rev-parse", f"{parent}^{{tree}}"):
        return None
    commit = _run(
        ["git", "commit-tree", tree, "-p", parent, "-m", _commit_subject(milestone)],
        cwd=root,
        check=True,
    ).stdout.strip()
    branch_ref = _git(root, "symbolic-ref", "-q", "HEAD", check=False)
    if not branch_ref:
        raise ProgrammingError("accepted slice requires an attached task branch")
    _git(root, "update-ref", branch_ref, commit, parent)
    changed = _run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "-z", parent, commit],
        cwd=root,
        check=True,
    ).stdout.split("\0")
    paths = [path for path in changed if path]
    if paths:
        entries = _git(root, "ls-tree", "-r", "-z", commit, "--", *paths)
        removals = "".join(f"0 {'0' * len(commit)}\t{path}\0" for path in paths)
        _run(["git", "update-index", "-z", "--index-info"], cwd=root,
             input_text=removals + entries, check=True)
    return commit


def _parse_review(text: str) -> tuple[str, str]:
    lines = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        raise ProgrammingError("reviewer returned no outcome")
    first = lines[0].strip().upper()
    if first not in OUTCOMES:
        raise ProgrammingError("reviewer must begin with exactly CONTINUE, FIX, DONE, or ASK USER")
    return first, "\n".join(lines[1:]).strip()


def _review_terminal_issue(text: str) -> str | None:
    try:
        _parse_review(text)
    except ProgrammingError as exc:
        return str(exc)
    return None


def _review(
    *,
    root: Path,
    plan: dict[str, Any],
    milestone: str,
    runtime_baseline: dict[str, str],
    diff_base: str,
    endpoint: dict[str, Any] | list[dict[str, Any]],
    call_model_fn: Callable[..., str],
    web_fetch_fn: Callable[..., Any] | None,
    web_search_fn: Callable[..., Any] | None,
    include_worktree: bool = True,
) -> dict[str, Any]:
    review_parent = _git(root, "rev-parse", "HEAD")
    temporary = tempfile.TemporaryDirectory(prefix="ora-programming-review-")
    review_root = Path(temporary.name) / "repository"
    _run(
        ["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(root), str(review_root)],
        cwd=Path(temporary.name),
        timeout=300,
        check=True,
    )
    _run(["git", "read-tree", review_parent], cwd=review_root, check=True)
    _run(["git", "checkout-index", "-a"], cwd=review_root, check=True)
    if include_worktree:
        _copy_working_tree(root, review_root)
    diff = _raw_diff(review_root, diff_base)
    reviewed_patch = _raw_diff(review_root, review_parent)
    system = f"""You are Ora's clean-context Programming reviewer. This is a fresh model call. You receive no executor transcript, hidden reasoning, summary, or executor claims.

Inspect the repository, raw diff, and relevant checks yourself. Judge only the approved plan. Reject wrong user-visible behavior, unmet criteria, content or data loss, runtime failure, unauthorized scope, broken atomicity, or lost user work. Do not add preferred abstractions, speculative safeguards, documentation style, tracking, or unrequested generality.

For external facts or live state, independently inspect the smallest sufficient authoritative source with web_search/web_fetch. A citation or description is not evidence unless you inspect its source. For an image, PDF, rendered interface, audio, video, or other non-text criterion, use the matching inspection tool and directly inspect its attached evidence. Executor descriptions are never evidence. If required evidence cannot be obtained, keep it unverified.

Return one of exactly four tokens on the first line: CONTINUE, FIX, DONE, ASK USER. After FIX or ASK USER, give one consolidated, substantive explanation. CONTINUE means this slice is sound and approved work remains. DONE means the exact complete plan is satisfied. ASK USER is reserved for changed scope/authority, human-only access, unsafe user work, repeated no-progress, or the soft spend boundary.
{_tool_instructions('review')}
"""
    user = "\n\n".join((
        "APPROVED PLAN\n" + plan["plan"],
        "MILESTONES\n" + "\n".join(f"- {item}" for item in plan["milestones"]),
        "REVIEW TARGET\n" + milestone,
        "RUNTIME BASELINE\n" + json.dumps(runtime_baseline, ensure_ascii=False),
        "RAW TASK DIFF\n" + (diff or "[no diff]"),
    ))
    try:
        result = _agent(
            root=review_root,
            endpoint=endpoint,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            role="review",
            call_model_fn=call_model_fn,
            web_fetch_fn=web_fetch_fn,
            web_search_fn=web_search_fn,
            terminal_validator=_review_terminal_issue,
            terminal_correction=(
                "PROTOCOL CORRECTION: your review must begin with exactly one of "
                "CONTINUE, FIX, DONE, or ASK USER on the first line. Return the "
                "evidence-based review outcome now."
            ),
        )
    finally:
        temporary.cleanup()
    outcome, detail = _parse_review(result["response"])
    return {
        "outcome": outcome,
        "detail": detail,
        "tools": result["tools"],
        "endpoint": result["endpoint"],
        "_parent": review_parent,
        "_patch": reviewed_patch,
    }


def _review_with_provider_retry(**kwargs: Any) -> dict[str, Any]:
    for _attempt in range(2):
        try:
            return _review(**kwargs)
        except ProgrammingError as exc:
            if not str(exc).startswith("configured review endpoints failed"):
                raise
    return {
        "outcome": "ASK USER",
        "detail": (
            "two consecutive clean reviews could not obtain a valid response "
            "from any configured reviewer"
        ),
        "tools": [],
        "endpoint": "",
    }


def _gh_repository(remote_url: str) -> str:
    """Return gh's explicit HOST/OWNER/REPO selector for a remote URL."""
    value = str(remote_url or "").strip()
    if "://" in value:
        parsed = urlsplit(value)
        host, path = parsed.hostname or "", parsed.path
    else:
        match = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(.+)", value)
        if not match:
            raise ProgrammingError("approved push target is not a GitHub remote URL")
        host, path = match.groups()
    parts = [item for item in path.strip("/").removesuffix(".git").split("/") if item]
    if not host or len(parts) != 2:
        raise ProgrammingError("approved push target is not a GitHub repository URL")
    return f"{host}/{parts[0]}/{parts[1]}"

def _pr_number(url: str, repository: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    host, owner, name = repository.split("/", 2)
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if (
        (parsed.hostname or "").casefold() != host.casefold()
        or parts[:3] != [owner, name, "pull"]
        or len(parts) != 4
        or not parts[3].isdigit()
    ):
        raise ProgrammingError("pull-request URL does not match the approved repository")
    return parts[3]

def _finish(root: Path, branch: str, plan: dict[str, Any]) -> dict[str, str]:
    finish_line = str(plan.get("git_finish_line") or "local_commits")
    if finish_line == "local_commits":
        return {"finish_line": finish_line, "branch": branch}
    remote, target = str(plan.get("git_remote") or "").strip(), str(plan.get("git_push_target") or "").strip()
    configured = [item for item in _configured_remotes(root) if item["name"] == remote]
    if len(configured) != 1 or configured[0]["push_urls"] != [target]:
        raise ProgrammingError("approved Git remote/push target drifted")
    if finish_line == "push":
        _git(root, "push", "-u", remote, branch, timeout=600)
        return {"finish_line": finish_line, "branch": branch}
    repository, base = _gh_repository(target), str(plan.get("git_pr_base") or "").strip()
    head = _git(root, "rev-parse", "HEAD")
    listed = _run(
        ["gh", "pr", "list", "--repo", repository, "--head", branch,
         "--state", "all", "--json", "number,url,state,mergedAt,baseRefName,headRefName,isCrossRepository,headRefOid"],
        cwd=root, timeout=600, check=True,
    ).stdout
    try:
        matches = json.loads(listed or "[]")
    except json.JSONDecodeError as exc:
        raise ProgrammingError("gh returned invalid pull-request state") from exc
    if not isinstance(matches, list) or len(matches) > 1:
        raise ProgrammingError("matching pull-request state is ambiguous")
    existing = matches[0] if matches else None
    if existing and (
        existing.get("isCrossRepository") or existing.get("headRefName") != branch
        or existing.get("baseRefName") != base
    ):
        raise ProgrammingError("matching pull request is cross-repository or targets different branches")
    if existing:
        url = str(existing.get("url") or "")
        number = _pr_number(url, repository)
        if str(existing.get("number") or "") != number:
            raise ProgrammingError("pull-request URL and number disagree")
        merged = bool(existing.get("mergedAt")) or existing.get("state") == "MERGED"
        if not merged and existing.get("state") != "OPEN":
            raise ProgrammingError("matching pull request is closed without merge")
        if merged and existing.get("headRefOid") != head:
            raise ProgrammingError("merged pull request does not match local HEAD")
        if merged:
            return {"finish_line": finish_line, "branch": branch, "pull_request": url}
    _git(root, "push", "-u", remote, branch, timeout=600)
    if not existing:
        create = _run(
            ["gh", "pr", "create", "--repo", repository, "--base", base,
             "--head", branch, "--fill"],
            cwd=root, timeout=600, check=True,
        ).stdout.strip()
        url = next((line for line in create.splitlines() if line.startswith("http")), create)
        number = _pr_number(url, repository)
    if finish_line == "pull_request":
        return {"finish_line": finish_line, "branch": branch, "pull_request": url}
    _run(
        ["gh", "pr", "merge", number, "--repo", repository, "--merge", "--match-head-commit", head],
        cwd=root, timeout=600, check=True,
    )
    return {"finish_line": finish_line, "branch": branch, "pull_request": url}


def run_approved_programming(
    *,
    objective: str,
    repository_path: str,
    plan: dict[str, Any],
    approved: bool,
    endpoints: dict[str, Any] | None = None,
    call_model_fn: Callable[..., str] | None = None,
    web_fetch_fn: Callable[..., Any] | None = None,
    web_search_fn: Callable[..., Any] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    soft_boundary_seconds: int = 5_400,
    resume_branch: str | None = None,
    continuation: str = "",
) -> dict[str, Any]:
    """Execute one approved plan through fresh review and accepted-slice commits."""
    emit = progress or (lambda _event: None)
    if not approved:
        raise ProgrammingError("one explicit plan approval is required")
    if not isinstance(plan, dict):
        raise ProgrammingError("approved plan is incomplete")
    root = _repository_root(repository_path)
    plan_issues = _plan_payload_issues(plan, _configured_remotes(root))
    if plan_issues:
        raise ProgrammingError(
            "approved plan is incomplete or unauthorized: " + ", ".join(plan_issues)
        )
    baseline = dict(plan.get("baseline") or {})
    baseline_head = str(baseline.get("head") or "")
    current_head = _git(root, "rev-parse", "HEAD")
    current_branch = _git(root, "branch", "--show-current", check=False) or "(detached)"
    current_status = _git(root, "status", "--porcelain=v1", check=False)
    if baseline.get("root") != str(root) or not baseline_head:
        result = {"outcome": "ASK USER", "detail": "repository baseline changed after planning"}
        emit({"type": "decision", **result})
        return result

    resumed = bool(resume_branch)
    if resumed:
        branch = str(resume_branch)
        base = _task_branch_base(objective, baseline_head)
        suffix = branch.removeprefix(base) if branch.startswith(base) else "invalid"
        valid_branch = suffix == "" or (
            suffix.startswith("-") and suffix[1:].isdigit() and int(suffix[1:]) >= 2
        )
        ancestor = _run(
            ["git", "merge-base", "--is-ancestor", baseline_head, current_head],
            cwd=root,
        ).returncode == 0
        if (
            branch != current_branch
            or not valid_branch
            or not ancestor
        ):
            result = {
                "outcome": "ASK USER",
                "detail": "task branch cannot be resumed safely from the approved baseline",
            }
            emit({"type": "decision", **result})
            return result
    else:
        if (
            current_head != baseline_head
            or current_branch != baseline.get("branch")
            or current_status != str(baseline.get("status") or "")
        ):
            result = {
                "outcome": "ASK USER",
                "detail": "pre-existing or newly introduced work cannot be separated safely",
            }
            emit({"type": "decision", **result})
            return result
        if any(
            not _plan_mentions_path(plan, path)
            for path in _dirty_paths(root, baseline_head)
        ):
            result = {
                "outcome": "ASK USER",
                "detail": "pre-existing or newly introduced work cannot be separated safely",
            }
            emit({"type": "decision", **result})
            return result
        branch = _task_branch(root, objective, baseline_head, plan)

    def ask_for_separation(detail: str) -> dict[str, str]:
        result = {"outcome": "ASK USER", "detail": detail, "branch": branch}
        emit({"type": "decision", **result})
        return result

    recovery_paths = _dirty_paths(root, current_head) if resumed else []
    if any(
        not _plan_mentions_path(plan, path)
        for path in recovery_paths
    ):
        return ask_for_separation("some uncommitted task-branch paths cannot be separated safely during recovery")
    approved_recovery_patch = (
        _raw_diff(root, current_head) if recovery_paths else ""
    )

    if endpoints is None:
        endpoints = configured_endpoints()
    if call_model_fn is None:
        try:
            from orchestrator.boot import call_model as call_model_fn
        except ImportError:
            from boot import call_model as call_model_fn

    started = time.monotonic()
    runtime_baseline = {
        "head": baseline_head,
        "branch_before": baseline.get("branch", ""),
        "task_branch": branch,
    }
    action = "Resumed" if resumed else "Created"
    emit({"type": "progress", "message": f"{action} task branch {branch}", "branch": branch})
    milestones = [str(item) for item in plan["milestones"]]
    executor_messages: list[dict[str, str]] = [{
        "role": "system",
        "content": f"""You are Ora's repository executor. Implement only the approved plan in the real task repository. Inspect before editing, preserve unrelated behavior, run meaningful checks, and complete the named milestone as one coherent slice. repo_command runs in a disposable copy and cannot change the task tree; use repo_write, repo_edit, or repo_delete for intended source changes. Do not commit, stage, switch branches, push, deploy, publish, message, or use credentials; the coordinator owns Git and finish-line effects. Use the repository tools, then report concisely.\n{_tool_instructions('execute')}""",
    }]
    if resumed:
        executor_messages.append({
            "role": "user",
            "content": "USER CONTINUATION\n" + continuation.strip(),
        })
    accepted_subjects = set(
        _git(
            root,
            "log",
            "--format=%s",
            f"{baseline_head}..HEAD",
            check=False,
        ).splitlines()
    )
    last_failure: tuple[str, str] | None = None
    repeated_failure = 0
    first_pending_slice = True

    for milestone in milestones:
        if _commit_subject(milestone) in accepted_subjects:
            emit({"type": "milestone", "milestone": milestone,
                  "status": "accepted", "resumed": True})
            continue
        pending_patch = _raw_diff(root, _git(root, "rev-parse", "HEAD"))
        if (
            pending_patch
            and pending_patch != approved_recovery_patch
            and (accepted_subjects or resumed)
        ):
            return ask_for_separation("worktree changes appeared between accepted milestones and cannot be separated safely")
        approved_recovery_patch = ""
        slice_base = _git(root, "rev-parse", "HEAD")
        allowed_paths = set(_dirty_paths(root, slice_base)) if first_pending_slice else set()
        first_pending_slice = False
        correction = ""
        while True:
            if time.monotonic() - started >= soft_boundary_seconds:
                result = {"outcome": "ASK USER", "detail": "Programming reached the soft spend boundary", "branch": branch}
                emit({"type": "decision", **result})
                return result
            emit({"type": "milestone", "milestone": milestone, "status": "executing"})
            executor_messages.append({
                "role": "user",
                "content": "\n\n".join((
                    "APPROVED PLAN\n" + plan["plan"],
                    "CURRENT MILESTONE\n" + milestone,
                    ("REVIEW DEFECTS TO CORRECT\n" + correction) if correction else "",
                )).strip(),
            })
            executed = _agent(
                root=root,
                endpoint=endpoints["executor"],
                messages=executor_messages,
                role="execute",
                call_model_fn=call_model_fn,
            )
            allowed_paths.update(executed["changed_paths"])
            executor_messages.append({"role": "assistant", "content": executed["response"]})
            emit({
                "type": "progress",
                "message": f"Executor used {executed['endpoint']}",
                "milestone": milestone,
                "endpoint": executed["endpoint"],
                "tools": executed["tools"],
            })
            unexpected = set(_dirty_paths(root, slice_base)) - allowed_paths
            if unexpected:
                return ask_for_separation("unattributed worktree paths appeared before review")
            emit({"type": "progress", "message": f"Reviewing {milestone}", "milestone": milestone})
            review = _review_with_provider_retry(
                root=root,
                plan=plan,
                milestone=milestone,
                runtime_baseline=runtime_baseline,
                diff_base=slice_base,
                endpoint=endpoints["reviewer"],
                call_model_fn=call_model_fn,
                web_fetch_fn=web_fetch_fn,
                web_search_fn=web_search_fn,
            )
            public_review = {key: value for key, value in review.items() if not key.startswith("_")}
            emit({"type": "review", "milestone": milestone, **public_review})
            if review["outcome"] == "ASK USER":
                return {**public_review, "branch": branch}
            if review["outcome"] == "FIX":
                if (
                    _git(root, "rev-parse", "HEAD") != review["_parent"]
                    or _raw_diff(root, review["_parent"]) != review["_patch"]
                ):
                    return {
                        "outcome": "ASK USER",
                        "detail": "repository work changed during review and cannot be corrected safely",
                        "branch": branch,
                    }
                marker = (review["detail"], _tree_fingerprint(root, slice_base))
                repeated_failure = repeated_failure + 1 if marker == last_failure else 1
                last_failure = marker
                if repeated_failure >= 2:
                    result = {
                        "outcome": "ASK USER",
                        "detail": "two consecutive reviews reproduced the same failure without progress",
                        "branch": branch,
                    }
                    emit({"type": "decision", **result})
                    return result
                correction = review["detail"] or "Correct the substantive review defects."
                continue
            commit = _commit_slice(
                root, milestone, review["_parent"], review["_patch"]
            )
            accepted_subjects.add(_commit_subject(milestone))
            emit({
                "type": "milestone",
                "milestone": milestone,
                "status": "accepted",
                "commit": commit,
                "review_outcome": review["outcome"],
            })
            last_failure = None
            repeated_failure = 0
            break

    final_base = _git(root, "rev-parse", "HEAD")
    correction = ""
    final_executor_paths: set[str] = set()
    while True:
        if correction:
            emit({"type": "milestone", "milestone": "FINAL", "status": "correcting"})
            executor_messages.append({
                "role": "user",
                "content": "APPROVED PLAN\n" + plan["plan"] + "\n\nFINAL REVIEW DEFECTS\n" + correction,
            })
            executed = _agent(
                root=root,
                endpoint=endpoints["executor"],
                messages=executor_messages,
                role="execute",
                call_model_fn=call_model_fn,
            )
            final_executor_paths.update(executed["changed_paths"])
            executor_messages.append({"role": "assistant", "content": executed["response"]})
            emit({
                "type": "progress",
                "message": f"Executor used {executed['endpoint']}",
                "milestone": "FINAL",
                "endpoint": executed["endpoint"],
                "tools": executed["tools"],
            })
            if set(_dirty_paths(root, final_base)) - final_executor_paths:
                return ask_for_separation("unattributed worktree paths appeared before final review")
        review = _review_with_provider_retry(
            root=root,
            plan=plan,
            milestone="FINAL",
            runtime_baseline=runtime_baseline,
            diff_base=baseline_head,
            endpoint=endpoints["reviewer"],
            call_model_fn=call_model_fn,
            web_fetch_fn=web_fetch_fn,
            web_search_fn=web_search_fn,
            include_worktree=bool(correction),
        )
        public_review = {key: value for key, value in review.items() if not key.startswith("_")}
        emit({"type": "review", "milestone": "FINAL", **public_review})
        if review["outcome"] == "DONE":
            commit = _commit_slice(
                root, "final review corrections", review["_parent"], review["_patch"]
            )
            if commit:
                emit({"type": "milestone", "milestone": "FINAL", "status": "accepted", "commit": commit})
            finish_line = str(plan.get("git_finish_line") or "local_commits")
            try:
                finish = _finish(root, branch, plan)
            except ProgrammingError as exc:
                result = {
                    "outcome": "ASK USER", "detail": f"Git finish line failed: {exc}",
                    "branch": branch, "finish_line": finish_line, "retryable": True,
                }
                emit({"type": "decision", **result})
                return result
            result = {"outcome": "DONE", "detail": review["detail"], **finish}
            emit({"type": "done", **result})
            return result
        if review["outcome"] == "ASK USER":
            return {**public_review, "branch": branch}
        if review["outcome"] == "CONTINUE":
            review = {**review, "outcome": "FIX", "detail": "Final review did not establish completion."}
        if (
            _git(root, "rev-parse", "HEAD") != review["_parent"]
            or _raw_diff(root, review["_parent"]) != review["_patch"]
        ):
            return {
                "outcome": "ASK USER",
                "detail": "repository work changed during review and cannot be corrected safely",
                "branch": branch,
            }
        marker = (review["detail"], _tree_fingerprint(root, final_base))
        repeated_failure = repeated_failure + 1 if marker == last_failure else 1
        last_failure = marker
        if repeated_failure >= 2 or time.monotonic() - started >= soft_boundary_seconds:
            result = {"outcome": "ASK USER", "detail": "final correction made no further progress", "branch": branch}
            emit({"type": "decision", **result})
            return result
        correction = review["detail"] or "Correct the final substantive defects."


__all__ = [
    "OUTCOMES",
    "ProgrammingError",
    "configured_endpoints",
    "inspect_repository",
    "plan_programming",
    "recover_programming",
    "run_approved_programming",
]
