"""orchestrator/evidence_runner.py — Execution Review Phase 5 (code adapter).

The ``.ora/evidence.yaml`` catalog parser + the evidence RUNNER + the
planning-stage Evidence Contract producer + the three dirty-state modes, as ONE
consolidated module (the vault consolidated-files rule; these are one cohesive
unit, as ``execution_packet.py`` was for Phase 4).

Catalog vs. Contract — stated plainly so no future reader misreads it (spec §10):
  * The **catalog** (``.ora/evidence.yaml``) declares *what checks exist and how
    they must run* — a repo-level, write-*protected* (``evidence.yaml`` ∈
    ``tool_events._PROTECTED_BASENAMES``), executor-independent fact.
  * The **Evidence Contract** is *task-specific and produced at planning time*:
    which catalog checks matter for THIS task, what bespoke probe proves THIS
    feature, and what result counts as sufficient.
Conflating them is how the loop's integrity quietly leaks: if the executor picks
its own checks at runtime, self-reporting sneaks back in one level up.

The load-bearing sentence (spec §10 / §16-2), landed in code and the packet:
  A green evidence run means *nothing broke that you knew to check* — it does NOT
  mean the executor solved the right problem (that is the planning-stage
  acceptance criteria + the verify stage), and NOT that the checks themselves are
  honest if the executor wrote the code they run (that is §12's verify-authored
  adversarial tests). ``EvidenceLane.sufficient`` is judged against the Contract's
  declared sufficiency, never self-asserted.

ENFORCE-OR-REFUSE (spec §7; the design-gate resolution): the runner is itself an
executor and must run each check *under its declared constraints*. A check runs
ONLY under a backend that actually ENFORCES its declared network policy — macOS
``sandbox-exec``, a declared ``ORA_EVIDENCE_SANDBOX`` wrapper (the first-class
Windows enforcement route), or native Linux ``unshare -rn`` (capability-probed,
degrades to refuse). Where no enforcing backend exists, the check **refuses
cleanly** (``skipped=True`` + ``skip_reason``) — it is NEVER run under an
unenforced ``network: deny``. A check that ran is genuinely ``orchestrated``;
there is no "ran-but-unenforced" state.

Portability (release-blocking amendment): the runner MACHINERY (parse / validate
/ discover / Contract / git-state) is pure Python and runs on macOS + Windows +
Linux. Check EXECUTION runs under an enforcing backend or refuses; on Windows the
supported route is a declared ``ORA_EVIDENCE_SANDBOX``. Commands are shell-free
``argv`` by default (``subprocess.run(argv, shell=False)``); a ``cmd`` +
``shell: true`` check runs under ``ORA_POSIX_SHELL`` and refuses cleanly (never
``cmd.exe``) when it is unset. All paths derive from ``runtime_paths`` /
``tempfile`` / ``pathlib`` — never a hardcoded root.

Nothing here raises into the pipeline: parse/run/contract are best-effort, and a
caught failure stamps an observable marker (``tool_events._note_failure``).
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

try:  # runtime import shape mirrors the rest of orchestrator/
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

try:
    import tool_events as _te
except ImportError:  # pragma: no cover
    from orchestrator import tool_events as _te

# ── Provisional constants (flagged per house rule: retunable, not calibrated) ──
_DEFAULT_TIMEOUT = 300
_STDOUT_TAIL_CAP = 8_000          # per-check captured-output cap (redacted, tailed)
_CATALOG_RELPATH = os.path.join(".ora", "evidence.yaml")
_MAX_DISCOVERY_WALK = 40          # pathlib upward-walk ceiling (cross-platform)
_ENV_SANDBOX = "ORA_EVIDENCE_SANDBOX"     # declared wrapper (first-class Windows route)
_ENV_POSIX_SHELL = "ORA_POSIX_SHELL"

_VALID_ENV = {"isolated"}          # SEC-5: 'inherit' would leak credentials — not offered in P5
_VALID_ON_UNKNOWN = {"gated", "skip"}


# ── Catalog types (§10) ───────────────────────────────────────────────────────
@dataclass
class Check:
    """One declared check. Exactly ONE execution form: ``argv`` (shell-free, the
    portable default) OR ``cmd`` + ``shell`` (needs a real shell) — plus optional
    per-platform ``argv_windows``/``argv_posix`` (or ``cmd_*``) variants."""

    name: str
    argv: list[str] | None = None
    cmd: str | None = None
    shell: bool = False
    argv_windows: list[str] | None = None
    argv_posix: list[str] | None = None
    cmd_windows: str | None = None
    cmd_posix: str | None = None
    mutates: bool = False
    timeout: int = _DEFAULT_TIMEOUT
    network: str = "deny"          # deny | local | allow
    # Phase 8 Chunk C (§4.1/§2.2): declared, harness-built check INPUTS +
    # delta scoping. ``inputs`` names artifacts the actuator precomputes OUTSIDE
    # the sandbox (git works there) and hands the check via the read-only
    # ``ORA_CHECK_INPUTS`` directory — the check runs NO git and reads NO ora
    # code in the sandbox. ``scope`` drives sparse checkout (changed-files-only
    # vault checks stay O(delta), not O(137k)).
    inputs: list | None = None     # subset of {"changed_files", "title_universe"}
    scope: str = "repo"            # "repo" | "changed_files"


_VALID_CHECK_INPUTS = {"changed_files", "title_universe"}
_VALID_CHECK_SCOPE = {"repo", "changed_files"}
_CHECK_INPUTS_ENV = "ORA_CHECK_INPUTS"     # read-only inputs dir handed to a check
# Filenames the actuator writes into the inputs dir, one per declared input.
_INPUTS_FILENAMES = {"changed_files": "changed-files.txt",
                     "title_universe": "title-universe.txt"}


@dataclass
class Recipe:
    """A named, repo-declared, write-protected standing/probe recipe (§4.1). Lives
    in the catalog's ``recipes:`` block so a model can never inject a probe URL or
    weaken a check — the recipe body always comes from the §6-protected file."""

    name: str
    lane: str                      # deploy_probe | render_inspect | run_observe
    target: str
    standing: bool = False
    probes: list | None = None     # deploy_probe recipes
    rollback: str | None = None    # MANDATORY for deploy_probe
    check: str | None = None       # render_inspect recipes — a catalog check name


@dataclass
class Runner:
    """The catalog ``runner:`` block — how checks must run (§7/§10)."""

    working_dir: str = "<repo-root>"
    env: str = "isolated"
    network: str = "deny"
    redact: str = "by-sensitivity"
    on_unknown: str = "gated"


@dataclass
class Catalog:
    checks: dict[str, Check] = field(default_factory=dict)
    runner: Runner = field(default_factory=Runner)
    path: str | None = None
    recipes: dict[str, Recipe] = field(default_factory=dict)


@dataclass
class CheckResult:
    """One check's mechanical outcome. ``enforcement_model`` is ``orchestrated``
    for a check that RAN under an enforcing backend; a REFUSED check carries
    ``skipped=True`` + ``skip_reason`` and no enforcement claim."""

    name: str
    generated_by: list[str] = field(default_factory=list)   # the argv/cmd actually run
    exit_code: int | None = None
    passed: bool = False
    stdout_tail: str = ""           # capped + redacted
    duration_ms: int | None = None
    enforcement_model: str | None = None    # 'orchestrated' when ran; None when refused
    backend: str | None = None      # sandbox-exec | ora-evidence-sandbox | unshare | None
    mutates: bool = False
    skipped: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _mark_failure(err: Exception, where: str) -> None:
    """Observable marker for a caught failure (never re-raises)."""
    try:
        _te._note_failure(err, where)
    except Exception:
        pass


# ── Catalog parse + validate ──────────────────────────────────────────────────
def validate_runner_block(runner: dict) -> list[str]:
    """Validate the ``runner:`` block (§7/§10). ``redact`` is REQUIRED — the code
    default ``EVIDENCE_RUNNER_DEFAULTS`` omits it, but §7/§10 make redaction
    load-bearing, so a catalog that drops it is invalid."""
    errors: list[str] = []
    if not runner.get("working_dir"):
        errors.append("runner missing required 'working_dir'")
    if runner.get("env", "isolated") not in _VALID_ENV:
        errors.append(f"invalid runner env: {runner.get('env')!r}")
    if runner.get("network", "deny") not in _te._EVIDENCE_NETWORK:
        errors.append(f"invalid runner network: {runner.get('network')!r}")
    if not runner.get("redact"):
        errors.append("runner missing required 'redact' (secret-redaction is load-bearing, §7/§10)")
    if runner.get("on_unknown", "gated") not in _VALID_ON_UNKNOWN:
        errors.append(f"invalid runner on_unknown: {runner.get('on_unknown')!r}")
    return errors


def validate_check(name: str, check: dict) -> list[str]:
    """Validate one check entry. Extends ``tool_events.validate_check_declaration``
    (which requires ``cmd``) to accept an ``argv`` list OR ``cmd`` — exactly one
    execution form; ``shell: true`` only with ``cmd``; a per-platform variant only
    in a matched pair."""
    errors: list[str] = []
    # An execution form is EITHER the argv family (argv / argv_windows / argv_posix)
    # OR the cmd family (cmd / cmd_windows / cmd_posix) — never both, and never
    # neither (P3 — the malformed-combination catch).
    argv_forms = [k for k in ("argv", "argv_windows", "argv_posix") if check.get(k) is not None]
    cmd_forms = [k for k in ("cmd", "cmd_windows", "cmd_posix") if check.get(k) is not None]
    if not argv_forms and not cmd_forms:
        errors.append(f"check {name!r}: needs an 'argv' list or a 'cmd' string")
    if argv_forms and cmd_forms:
        errors.append(f"check {name!r}: cannot mix argv-form and cmd-form execution "
                      f"(has {argv_forms + cmd_forms}) — choose one")
    if check.get("argv") is not None and not isinstance(check["argv"], list):
        errors.append(f"check {name!r}: 'argv' must be a list")
    if check.get("cmd") is not None and not isinstance(check["cmd"], str):
        errors.append(f"check {name!r}: 'cmd' must be a string")
    # A cmd form runs under a shell → it REQUIRES 'shell: true' (else run_check
    # refuses it at runtime — a silent dead check).
    if cmd_forms and not check.get("shell"):
        errors.append(f"check {name!r}: a 'cmd' form requires 'shell: true'")
    # 'shell: true' is only meaningful with a cmd form (never with argv).
    if check.get("shell") and not cmd_forms:
        errors.append(f"check {name!r}: 'shell: true' is only valid with a 'cmd' form")
    # Per-platform variants MUST come as a matched pair (P2-2): a POSIX-only
    # declaration would silently pass validation and then refuse on Windows,
    # violating the release-blocking "runs on macOS AND Windows" requirement. A
    # check without a base argv/cmd must supply BOTH sides of a variant family.
    for base, win, pos in (("argv", "argv_windows", "argv_posix"),
                           ("cmd", "cmd_windows", "cmd_posix")):
        has_win, has_pos = check.get(win) is not None, check.get(pos) is not None
        if (has_win or has_pos) and check.get(base) is None and not (has_win and has_pos):
            errors.append(f"check {name!r}: per-platform variants must be a matched "
                          f"pair — declare BOTH {win} and {pos} (or a base {base})")
    for k in ("argv_windows", "argv_posix"):
        if check.get(k) is not None and not isinstance(check[k], list):
            errors.append(f"check {name!r}: {k!r} must be a list")
    for k in ("cmd_windows", "cmd_posix"):
        if check.get(k) is not None and not isinstance(check[k], str):
            errors.append(f"check {name!r}: {k!r} must be a string")
    if "timeout" in check and not isinstance(check["timeout"], (int, float)):
        errors.append(f"check {name!r}: timeout must be numeric")
    if "mutates" in check and not isinstance(check["mutates"], bool):
        errors.append(f"check {name!r}: mutates must be boolean")
    if check.get("network", "deny") not in _te._EVIDENCE_NETWORK:
        errors.append(f"check {name!r}: invalid network {check.get('network')!r}")
    # Phase 8 Chunk C: declared inputs + delta scope (fixed vocabularies so a
    # typo is a LOUD parse error, never a silently-ignored input).
    if "inputs" in check:
        inp = check["inputs"]
        if not isinstance(inp, list):
            errors.append(f"check {name!r}: 'inputs' must be a list")
        else:
            bad = [x for x in inp if x not in _VALID_CHECK_INPUTS]
            if bad:
                errors.append(f"check {name!r}: unknown inputs {bad} "
                              f"(valid: {sorted(_VALID_CHECK_INPUTS)})")
    if "scope" in check and check["scope"] not in _VALID_CHECK_SCOPE:
        errors.append(f"check {name!r}: invalid scope {check.get('scope')!r} "
                      f"(valid: {sorted(_VALID_CHECK_SCOPE)})")
    return errors


_VALID_RECIPE_LANES = {"deploy_probe", "render_inspect", "run_observe"}


def validate_recipe(name: str, recipe: dict, check_names: set) -> list[str]:
    """Validate one ``recipes:`` entry (§4.1). A ``deploy_probe`` recipe REQUIRES a
    ``rollback`` field (⚖ design Rev 3 — a reviewer of a deploy delta must always
    see the recovery posture); a ``render_inspect`` recipe REQUIRES a ``check`` that
    exists in the catalog. The recipe body is repo-declared + §6-protected, so a
    model can never inject a probe URL through it."""
    errors: list[str] = []
    lane = recipe.get("lane")
    if lane not in _VALID_RECIPE_LANES:
        errors.append(f"recipe {name!r}: invalid lane {lane!r} "
                      f"(valid: {sorted(_VALID_RECIPE_LANES)})")
    if not recipe.get("target"):
        errors.append(f"recipe {name!r}: missing required 'target'")
    if "standing" in recipe and not isinstance(recipe["standing"], bool):
        errors.append(f"recipe {name!r}: 'standing' must be boolean")
    if lane == "deploy_probe":
        probes = recipe.get("probes")
        if not isinstance(probes, list) or not probes:
            errors.append(f"recipe {name!r}: deploy_probe needs a non-empty 'probes' list")
        # Mandatory rollback — absence is an ERROR, never a silent default.
        rb = recipe.get("rollback")
        if not (isinstance(rb, str) and rb.strip()):
            errors.append(f"recipe {name!r}: deploy_probe requires a 'rollback' string "
                          "(a recovery ref, or the explicit literal 'none: <recovery contract>')")
    if lane == "render_inspect":
        chk = recipe.get("check")
        if not chk:
            errors.append(f"recipe {name!r}: render_inspect needs a 'check' (a catalog check name)")
        elif chk not in check_names:
            errors.append(f"recipe {name!r}: render_inspect 'check' {chk!r} not in the catalog checks")
    return errors


def parse_catalog(path: str) -> Catalog:
    """Parse + validate a ``.ora/evidence.yaml``. Raises ``ValueError`` LOUDLY on a
    malformed file or a validation error — never returns a silent empty catalog
    that reads as "no checks" (a lazy/failing catalog must be visible)."""
    try:
        import yaml  # PyYAML 6.x is in the runtime
    except ImportError as e:  # pragma: no cover
        raise ValueError(f"cannot parse {path}: PyYAML unavailable ({e})")
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"malformed evidence catalog {path}: {e}")
    if not isinstance(raw, dict):
        raise ValueError(f"evidence catalog {path} is not a mapping")

    runner_raw = raw.get("runner") or {}
    if not isinstance(runner_raw, dict):
        raise ValueError(f"evidence catalog {path}: 'runner' must be a mapping")
    errs = validate_runner_block(runner_raw)

    checks_raw = raw.get("checks") or {}
    if not isinstance(checks_raw, dict):
        raise ValueError(f"evidence catalog {path}: 'checks' must be a mapping")

    checks: dict[str, Check] = {}
    for name, c in checks_raw.items():
        if not isinstance(c, dict):
            errs.append(f"check {name!r} must be a mapping")
            continue
        errs.extend(validate_check(name, c))
        checks[name] = Check(
            name=name, argv=c.get("argv"), cmd=c.get("cmd"),
            shell=bool(c.get("shell", False)),
            argv_windows=c.get("argv_windows"), argv_posix=c.get("argv_posix"),
            cmd_windows=c.get("cmd_windows"), cmd_posix=c.get("cmd_posix"),
            mutates=bool(c.get("mutates", False)),
            timeout=int(c.get("timeout", _DEFAULT_TIMEOUT)),
            network=c.get("network", runner_raw.get("network", "deny")),
            inputs=c.get("inputs"), scope=c.get("scope", "repo"))

    # Phase 8 Chunk C: the optional recipes: block (declared lanes). Unknown keys
    # inside a recipe would be silently ignored by dataclass construction, so we
    # validate the shape LOUDLY; the recipe body is write-protected (§6).
    recipes_raw = raw.get("recipes") or {}
    if not isinstance(recipes_raw, dict):
        raise ValueError(f"evidence catalog {path}: 'recipes' must be a mapping")
    check_names = set(checks.keys())
    recipes: dict[str, Recipe] = {}
    for rname, r in recipes_raw.items():
        if not isinstance(r, dict):
            errs.append(f"recipe {rname!r} must be a mapping")
            continue
        errs.extend(validate_recipe(rname, r, check_names))
        recipes[rname] = Recipe(
            name=rname, lane=r.get("lane"), target=r.get("target"),
            standing=bool(r.get("standing", False)), probes=r.get("probes"),
            rollback=r.get("rollback"), check=r.get("check"))

    if errs:
        raise ValueError(f"invalid evidence catalog {path}: " + "; ".join(errs))
    runner = Runner(
        working_dir=runner_raw.get("working_dir", "<repo-root>"),
        env=runner_raw.get("env", "isolated"),
        network=runner_raw.get("network", "deny"),
        redact=runner_raw.get("redact", "by-sensitivity"),
        on_unknown=runner_raw.get("on_unknown", "gated"))
    return Catalog(checks=checks, runner=runner, path=path, recipes=recipes)


def discover_catalog(repo_root: str | None = None) -> str | None:
    """Find ``.ora/evidence.yaml`` cross-platform (pathlib, no shell). Order:
    explicit ``repo_root`` → ``ORA_PROJECT_ROOT`` env → a pathlib upward walk from
    cwd. Returns the catalog path or None."""
    from pathlib import Path
    candidates: list[Path] = []
    if repo_root:
        candidates.append(Path(repo_root))
    proj = os.environ.get("ORA_PROJECT_ROOT")
    if proj:
        candidates.append(Path(proj))
    for base in candidates:
        p = base / ".ora" / "evidence.yaml"
        if p.is_file():
            return str(p)
    # Upward walk from cwd (bounded, cross-platform).
    try:
        cur = Path(os.getcwd()).resolve()
    except Exception:
        return None
    for _ in range(_MAX_DISCOVERY_WALK):
        p = cur / ".ora" / "evidence.yaml"
        if p.is_file():
            return str(p)
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


# ── Platform: clean env, argv resolution, enforcement backend ─────────────────
def _clean_env(work_home: str, tmpdir: str, inputs_dir: str | None = None) -> dict:
    """Credential-stripping clean env the runner BUILDS ITSELF (defense in depth on
    every backend). Platform-aware: POSIX ``HOME``/``TMPDIR``; Windows
    ``USERPROFILE``/``TEMP``/``TMP`` + ``SystemRoot``/``COMSPEC``/``PATHEXT`` (a
    spawned Windows process needs these to start). Deliberately does NOT reuse
    ``bash_execute._clean_env`` — that one is a leaky allowlist preserving
    ``HOME``/``USER``/``SSH_AUTH_SOCK`` (an agent socket is a live credential).
    Phase 8 Chunk C: when the check declares ``inputs``, the read-only inputs dir
    is announced via ``ORA_CHECK_INPUTS`` (env, not argv — argv is exec'd
    shell-free and cannot expand a variable)."""
    env: dict[str, str] = {}
    for key in ("PATH", "LANG", "LC_ALL"):
        if key in os.environ:
            env[key] = os.environ[key]
    if os.name == "nt":
        env["USERPROFILE"] = work_home
        env["TEMP"] = tmpdir
        env["TMP"] = tmpdir
        for key in ("SystemRoot", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS",
                    "PROCESSOR_ARCHITECTURE"):
            if key in os.environ:
                env[key] = os.environ[key]
    else:
        env["HOME"] = work_home
        env["TMPDIR"] = tmpdir
    if inputs_dir:
        env[_CHECK_INPUTS_ENV] = inputs_dir
    return env


def resolve_command(check: Check) -> tuple[list[str] | None, str | None, bool]:
    """Resolve a check to (argv | None, cmd | None, shell). Prefers a matched
    per-platform variant, else the base ``argv``/``cmd``. A bare ``python``/
    ``python3`` argv[0] resolves to ``sys.executable`` (kills the python-vs-python3
    split cross-platform)."""
    win = os.name == "nt"
    argv = check.argv
    cmd = check.cmd
    if win and (check.argv_windows or check.cmd_windows):
        argv, cmd = check.argv_windows, check.cmd_windows
    elif not win and (check.argv_posix or check.cmd_posix):
        argv, cmd = check.argv_posix, check.cmd_posix
    if argv:
        argv = list(argv)
        if argv and argv[0] in ("python", "python3"):
            argv[0] = sys.executable
        return argv, None, False
    return None, cmd, bool(check.shell)


def _macos_sandbox_available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("sandbox-exec"))


def _declared_wrapper() -> list[str] | None:
    """A declared ``ORA_EVIDENCE_SANDBOX`` wrapper command (the first-class Windows
    enforcement route). Must name a real executable (its first token), mirroring
    ``ORA_POSIX_SHELL`` validation; an invalid value counts as no wrapper. Parsed
    with ``shlex`` (platform-aware) so a quoted executable or a path WITH SPACES —
    e.g. ``"C:\\Program Files\\sandbox\\run.exe"`` on Windows — is not mangled by a
    naive whitespace split (P2-1)."""
    raw = (os.environ.get(_ENV_SANDBOX) or "").strip()
    if not raw:
        return None
    try:
        # posix=False on Windows keeps backslashes literal (Windows paths) and
        # honors "quotes" — but RETAINS the surrounding quote chars in the token, so
        # strip a balanced surrounding pair afterwards (posix mode already stripped
        # them). Without this a quoted `"C:\Program Files\x.exe"` keeps its quotes
        # and fails isabs/which (the P2-1 re-check catch).
        parts = shlex.split(raw, posix=(os.name != "nt"))
        if os.name == "nt":
            parts = [(p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in ('"', "'")
                      else p) for p in parts]
    except ValueError:
        return None
    if not parts:
        return None
    exe = parts[0]
    if os.path.isabs(exe):
        if not os.path.isfile(exe):
            return None
    elif shutil.which(exe) is None:
        return None
    return parts


_unshare_probe_cache: bool | None = None
_wrapper_probe_cache: dict[str, bool] = {}

# A tiny network-egress probe: prints DENIED if a socket connect fails (network
# blocked), OPEN otherwise. Used to VERIFY a backend actually enforces deny.
_NET_PROBE_CODE = (
    "import socket\n"
    "try:\n socket.create_connection(('1.1.1.1',80),timeout=4); print('OPEN')\n"
    "except Exception: print('DENIED')\n")


def _linux_unshare_available() -> bool:
    """Capability-probe native Linux ``unshare -rn`` (unprivileged user+net
    namespace). Judge direction: include it ONLY if it can be probed and safely
    degrades to refuse. Platform-gated FIRST (a cache hit never returns True
    off-Linux — PORT-2), then cached; any probe failure → False (→ refuse)."""
    global _unshare_probe_cache
    if not sys.platform.startswith("linux"):
        return False
    if _unshare_probe_cache is not None:
        return _unshare_probe_cache
    ok = False
    if shutil.which("unshare"):
        try:
            r = subprocess.run(
                ["unshare", "-rn", "true"], capture_output=True, timeout=10)
            ok = r.returncode == 0
        except Exception:
            ok = False
    _unshare_probe_cache = ok
    return ok


def _net_probe(prefix: list[str]) -> str:
    """Run the net-egress probe, optionally UNDER ``prefix`` (a wrapper argv).
    Returns 'OPEN' (network reached), 'DENIED' (blocked or unreachable), or 'ERROR'."""
    try:
        r = subprocess.run([*prefix, sys.executable, "-c", _NET_PROBE_CODE],
                           capture_output=True, text=True, timeout=15)
        out = r.stdout or ""
        if "OPEN" in out:
            return "OPEN"
        if "DENIED" in out:
            return "DENIED"
        return "ERROR"
    except Exception:
        return "ERROR"


def _wrapper_is_demonstrable_passthrough() -> bool:
    """A SOUND, REJECT-ONLY probe (SEC-4 + the fold re-check). True ONLY when the
    declared wrapper DEMONSTRABLY does not isolate network — the probe target is
    reachable WITHOUT the wrapper (baseline OPEN) AND still reachable THROUGH it
    (wrapped OPEN). Any other result is NOT a demonstrated passthrough → False:
      * baseline DENIED/ERROR → the target is unreachable regardless of the wrapper
        (offline / egress-filtered CI / firewall), so DENIED-through-the-wrapper is
        UN-attributable — we must not read it as enforcement (the false-positive the
        re-check found), and equally cannot call it a passthrough → False.
      * wrapped DENIED → the wrapper blocked at least the probe → not a passthrough.
    This probe NEVER confirms enforcement (a wrapper is operator-ATTESTED, labeled
    ``declared-sandbox`` — never runner-verified ``orchestrated`` — and the probe
    cannot cover the check's real argv anyway). It only refuses an OBVIOUS
    online passthrough. Cached per wrapper string."""
    wrapper = _declared_wrapper()
    if not wrapper:
        return False
    key = " ".join(wrapper)
    if key in _wrapper_probe_cache:
        return _wrapper_probe_cache[key]
    result = False
    if _net_probe([]) == "OPEN":              # baseline: target genuinely reachable
        result = _net_probe(wrapper) == "OPEN"  # still reachable through wrapper → passthrough
    _wrapper_probe_cache[key] = result
    return result


def enforcement_backend(network: str) -> str | None:
    """The backend that will ENFORCE ``network`` for a check, or None (→ refuse).
    ``deny`` is enforceable by macOS sandbox-exec / native Linux unshare (both
    runner-VERIFIED → ``orchestrated``) or a declared ``ORA_EVIDENCE_SANDBOX``
    wrapper (operator-ATTESTED → ``declared-sandbox``; used unless it is a
    demonstrable online passthrough). ``local`` and ``allow`` are NOT enforceable in
    P5 (no localhost scoping, no egress-logging proxy) → None → refuse (spec §7)."""
    if network != "deny":
        return None
    if _macos_sandbox_available():
        return "sandbox-exec"
    # A declared wrapper is trusted (operator responsibility, like ORA_POSIX_SHELL)
    # and recorded HONESTLY as declared-sandbox — but a DEMONSTRABLE online
    # passthrough (e.g. `env`) is still refused.
    if _declared_wrapper() is not None and not _wrapper_is_demonstrable_passthrough():
        return "ora-evidence-sandbox"
    if _linux_unshare_available():
        return "unshare"
    return None


# enforcement_model recorded per backend: sandbox-exec / unshare are runner-VERIFIED
# kernel isolation (orchestrated); a declared wrapper is operator-ATTESTED, not
# runner-verified, so it is honestly a distinct, weaker label (§7/§17 — never
# overclaim). No backend that RAN a check ever records less than this.
_ENFORCEMENT_MODEL = {"sandbox-exec": "orchestrated", "unshare": "orchestrated",
                      "ora-evidence-sandbox": "declared-sandbox"}


# ── The macOS sandbox profile (generalized from code_execute for a repo_root) ──
# SBPL string literals cannot safely carry a `"`, `\`, `(`, `)`, or newline (an
# unescaped `"` closes the subpath string and lets a crafted path inject arbitrary
# rules — e.g. `(allow network*)` — defeating the network-deny guarantee). Normal
# git worktrees never contain these, so the runner REFUSES a check whose sandbox
# paths are unsafe rather than escape-and-hope.
_SBPL_UNSAFE = ('"', "\\", "(", ")", "\n", "\r")


def _sbpl_path_safe(path: str) -> bool:
    return not any(c in path for c in _SBPL_UNSAFE)


def _private_deny_roots() -> list[str]:
    roots = [os.path.realpath(os.path.expanduser("~"))]
    for root in (_rp.WORKSPACE, _rp.VAULT_STR, _rp.CONVERSATIONS_STR):
        try:
            r = os.path.realpath(os.path.expanduser(str(root)))
        except Exception:
            continue
        if r and r != "/" and r not in roots:
            roots.append(r)
    return roots


def _is_within(child: str, parent: str) -> bool:
    """True if ``child`` is ``parent`` or nested under it (realpath'd)."""
    c = os.path.realpath(child)
    p = os.path.realpath(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def sandbox_worktree_unsafe(worktree: str, tmpdir: str) -> str | None:
    """Return a refusal reason if the worktree/tmp cannot be safely sandboxed under
    the macOS profile, else None. Refuses (SEC-1) any path carrying an SBPL-unsafe
    character, and (SEC-2) a worktree that is EQUAL TO or an ANCESTOR OF a sensitive
    private root ($HOME / vault / conversations) — re-allowing such a worktree would
    re-expose that root. A worktree UNDER a private root (the ~/ora self-review case)
    is fine; only an ancestor-of-a-sensitive-root is refused."""
    real_wt = os.path.realpath(worktree)
    real_tmp = os.path.realpath(tmpdir)
    for p in (real_wt, real_tmp):
        if not _sbpl_path_safe(p):
            return ("sandbox path contains a character unsafe for the sandbox "
                    "profile (\" \\ ( ) or newline); refusing rather than risk "
                    "profile injection")
    for sensitive in (os.path.realpath(os.path.expanduser("~")),
                      os.path.realpath(_rp.VAULT_STR),
                      os.path.realpath(_rp.CONVERSATIONS_STR)):
        if _is_within(sensitive, real_wt):
            return (f"worktree is equal to or an ancestor of a sensitive root "
                    f"({sensitive}); re-allowing it would re-expose that root — refused")
    return None


def _macos_profile(worktree: str, tmpdir: str, allow_write_repo: bool,
                   inputs_dir: str | None = None) -> str:
    """Deny reads under $HOME + every Ora private root, RE-ALLOW reads (and, for a
    mutating check, writes) under the SPECIFIC worktree, then RE-DENY any private
    root nested under the worktree (belt-and-suspenders for SEC-2 — the runner also
    refuses an ancestor worktree pre-flight). ``(deny network*)`` enforces
    ``network: deny``. Callers pass only SBPL-safe paths (``sandbox_worktree_unsafe``
    is checked first). Phase 8 Chunk C: ``inputs_dir`` (under SCRATCH_DIR, i.e.
    under a denied private root) gets an explicit read-ONLY re-allow so the check
    can read the harness-precomputed inputs — never a write-allow."""
    real_wt = os.path.realpath(worktree)
    real_tmp = os.path.realpath(tmpdir)
    deny_roots = _private_deny_roots()
    denies = "".join(f'(deny file-read* (subpath "{r}"))' for r in deny_roots)
    # Re-deny any private root nested UNDER the worktree, AFTER the worktree allow,
    # so last-match-wins keeps it denied even though the worktree is re-allowed.
    nested = [r for r in deny_roots
              if r != real_wt and r.startswith(real_wt.rstrip(os.sep) + os.sep)]
    re_denies = "".join(f'(deny file-read* (subpath "{r}"))' for r in nested)
    parts = [
        "(version 1)", "(allow default)", "(deny network*)", denies,
        f'(allow file-read* (subpath "{real_wt}"))',
        f'(allow file-read* (subpath "{real_tmp}"))',
    ]
    if inputs_dir:
        parts.append(f'(allow file-read* (subpath "{os.path.realpath(inputs_dir)}"))')
    parts += [
        re_denies,                       # nested private roots stay denied
        "(deny file-write*)",
        f'(allow file-write* (subpath "{real_tmp}"))',
        '(allow file-write* (subpath "/dev"))',
    ]
    if allow_write_repo:
        parts.append(f'(allow file-write* (subpath "{real_wt}"))')
    return "".join(parts)


def _wrap_argv(backend: str, argv: list[str], worktree: str, tmpdir: str,
               allow_write_repo: bool, inputs_dir: str | None = None) -> list[str]:
    """Build the OS argv that runs ``argv`` UNDER the enforcing backend."""
    if backend == "sandbox-exec":
        profile = _macos_profile(worktree, tmpdir, allow_write_repo, inputs_dir)
        return [shutil.which("sandbox-exec") or "sandbox-exec", "-p", profile, *argv]
    if backend == "unshare":
        # Unprivileged user+net namespace: no network interfaces → deny enforced.
        return ["unshare", "-rn", *argv]
    if backend == "ora-evidence-sandbox":
        wrapper = _declared_wrapper() or []
        return [*wrapper, *argv]
    return list(argv)


# ── run_check — ENFORCE-OR-REFUSE + the Phase-1 gate ──────────────────────────
def _refused(check: Check, argv_or_cmd: list[str] | str | None, reason: str) -> CheckResult:
    gen = (list(argv_or_cmd) if isinstance(argv_or_cmd, list)
           else [argv_or_cmd] if argv_or_cmd else [])
    return CheckResult(name=check.name, generated_by=gen, skipped=True,
                       skip_reason=reason, mutates=check.mutates)


def _redact_tail(text: str, runner: Runner) -> str:
    """Cap + tail captured output; drive secret redaction by the §7 sensitivity
    axis via the existing recorder redaction (best-effort)."""
    if not text:
        return ""
    tail = text[-_STDOUT_TAIL_CAP:]
    if len(text) > _STDOUT_TAIL_CAP:
        tail = "…[capped]\n" + tail
    try:
        # Secret-redaction driven by the §7 sensitivity axis, via the existing
        # recorder scrub (returns (scrubbed_text, found_bool)).
        scrub = getattr(_te, "scrub_content", None)
        if callable(scrub):
            scrubbed, _found = scrub(tail)
            tail = scrubbed
    except Exception:
        pass
    return tail


def _gate_check(check: Check, backend: str | None) -> tuple[bool, str | None]:
    """Route the check through the Phase-1 manifest via a DIRECT
    ``tool_events.gate`` call (NOT ``dispatcher.dispatch`` — which would inherit
    the ``approve-each`` ``input()`` prompt a programmatic runner can't answer).
    An unenforceable check is mapped to ``unknown`` → the gate fails closed."""
    if backend is None:
        # No enforcing backend → treat as unknown so the gate blocks fail-closed.
        axes = {"category": "execute", "mutability": "irreversible",
                "sensitivity": "secret", "egress": "external", "unknown": True,
                "enforcement": "boundary_only"}
    else:
        # A check EXECUTES repo code, so even a non-mutating check is
        # reversible_write, not read (matches code_execute_axes; ⚖ code-F6). The
        # enforcement is the HONEST per-backend level (declared-sandbox for a
        # wrapper, orchestrated for verified kernel isolation) — never overclaimed.
        axes = {"category": "execute", "mutability": "reversible_write",
                "sensitivity": "private", "egress": "none",
                "enforcement": _ENFORCEMENT_MODEL.get(backend, "orchestrated")}
    try:
        decision = _te.gate(f"evidence_check:{check.name}", axes,
                            params={"check": check.name},
                            description=f"evidence check {check.name}",
                            model_facing=True, interactive_approver=None)
        return bool(decision.allowed), decision.why
    except Exception as e:
        _mark_failure(e, "evidence_runner_gate")
        return False, f"gate error: {e}"


def _record_check_event(check: Check, result: CheckResult) -> None:
    """Leave a DURABLE tool-event for the check — reality contact is OBSERVED, not
    narrated (§16-3). ``tool_events.gate`` records only on a BLOCK, and the runner
    returns preflight refusals directly, so WITHOUT this a check (ran or refused)
    would be invisible to the tool-event log. Every outcome records exactly one
    event. Never raises."""
    try:
        ran = not result.skipped
        evt = {
            "event": "evidence_check",
            "action": f"evidence_check:{check.name}",
            "category": "execute",
            "mutability": "reversible_write" if ran else "read",
            "sensitivity": "private", "egress": "none",
            # A RAN check carries the backend's honest enforcement level; a REFUSED
            # check was refused by the runner itself → in_harness.
            "enforcement_model": (result.enforcement_model if ran else "in_harness"),
            "mutates": bool(check.mutates),
            "network": check.network,
            "exit": {"ok": bool(result.passed), "code": result.exit_code},
            "gate": {"decision": ("allowed" if ran else "blocked"),
                     "why": (result.skip_reason or "ran under "
                             + str(result.backend or "?"))},
        }
        # Phase 8 Chunk C: which harness-built inputs the check declared (observed,
        # not narrated — the reviewer sees the check's delta scope in the log).
        if getattr(check, "inputs", None):
            evt["inputs"] = list(check.inputs)
        _te.record(evt)
    except Exception as e:
        _mark_failure(e, "evidence_runner_record")


def run_check(check: Check, runner: Runner, repo_root: str, *,
              worktree: str | None = None, mode: str | None = None,
              inputs_dir: str | None = None) -> CheckResult:
    """Run ONE check ENFORCE-OR-REFUSE, and RECORD a tool-event for the outcome
    (observed, not narrated — §16-3). Returns a CheckResult; never raises.
    ``inputs_dir`` (Phase 8 Chunk C) is a read-only directory of harness-built
    check inputs, announced to the check via ``ORA_CHECK_INPUTS``."""
    result = _run_check_impl(check, runner, repo_root, worktree=worktree, mode=mode,
                             inputs_dir=inputs_dir)
    _record_check_event(check, result)
    return result


def _run_check_impl(check: Check, runner: Runner, repo_root: str, *,
                    worktree: str | None = None, mode: str | None = None,
                    inputs_dir: str | None = None) -> CheckResult:
    """The enforce-or-refuse body. A check runs only under a backend that enforces
    its declared network policy; else it refuses cleanly. ``mutates: true`` runs
    only under an explicit ``clean_worktree``."""
    try:
        argv, cmd, shell = resolve_command(check)

        # 0. A check that DECLARED inputs but got no inputs dir (base-unknown, or
        # the builder failed) REFUSES cleanly — never runs against a missing input
        # file and reports a false FAIL, and never a GUESSED input (§2.2).
        if getattr(check, "inputs", None) and not inputs_dir:
            return _refused(check, argv or cmd,
                            "declared inputs unavailable (no base / not built); "
                            "the check is not run against a missing input")

        # 1. mutates:true only under clean_worktree (never mutate a tree the user
        # owns). Absence of an explicit mode FAILS SAFE — a missing mode context
        # REFUSES a mutating check rather than permitting it (SEC-3).
        if check.mutates and mode != "clean_worktree":
            return _refused(check, argv or cmd,
                            f"mutates:true refused under mode={mode!r} "
                            "(only an explicit clean_worktree may run a mutating check)")

        # 2. A shell check needs a POSIX shell. On POSIX that is /bin/sh; on Windows
        # it is a declared ORA_POSIX_SHELL, and the check refuses cleanly (never
        # cmd.exe) when unset (PORT-1: /bin/sh must be used on the primary targets,
        # not bash_execute._posix_shell_path which is the Windows-only resolver).
        if cmd is not None and shell:
            if os.name == "nt":
                try:
                    import bash_execute as _be
                except ImportError:  # pragma: no cover
                    from orchestrator.tools import bash_execute as _be
                sh = _be._posix_shell_path()
            else:
                sh = shutil.which("sh") or "/bin/sh"
            if sh is None:
                return _refused(check, cmd,
                                f"shell:true check needs {_ENV_POSIX_SHELL} "
                                "(a real POSIX shell); refused (never cmd.exe)")
            argv = [sh, "-c", cmd]
        elif cmd is not None and not shell:
            # A bare cmd string with no shell is ambiguous — require argv or shell.
            return _refused(check, cmd,
                            "a 'cmd' string needs 'shell: true'; prefer an 'argv' list")

        if not argv:
            return _refused(check, None, "no runnable command (argv/cmd) for this platform")

        # 3. ENFORCE-OR-REFUSE: is there a backend that enforces the network policy?
        backend = enforcement_backend(check.network)
        if backend is None:
            return _refused(
                check, argv,
                f"network:{check.network} cannot be enforced on this platform; "
                f"declare {_ENV_SANDBOX} (a network-isolating wrapper) or run where "
                "a native backend exists — the check is NOT run unenforced (§7)")

        # 4. Gate through the Phase-1 manifest (direct gate; never dispatch).
        allowed, why = _gate_check(check, backend)
        if not allowed:
            return _refused(check, argv, f"gated: {why}")

        # 5. Sandbox setup — worktree cwd + a scratch home/tmp, all runtime_paths-derived.
        wt = worktree or repo_root
        scratch_base = os.path.join(_rp.SCRATCH_DIR_STR, "evidence-runner")
        os.makedirs(scratch_base, exist_ok=True)
        run_home = tempfile.mkdtemp(prefix="home-", dir=scratch_base)
        run_tmp = tempfile.mkdtemp(prefix="tmp-", dir=scratch_base)
        # SEC-1/SEC-2: for the macOS profile, refuse an SBPL-unsafe or
        # ancestor-of-a-sensitive-root worktree BEFORE building the profile — a
        # subverted profile could otherwise record a FALSE `orchestrated` claim.
        if backend == "sandbox-exec":
            _bad = sandbox_worktree_unsafe(wt, run_tmp)
            # SEC-1: the inputs dir also lands in the SBPL profile, so an
            # unsafe-char inputs path could inject the profile — refuse it too.
            if not _bad and inputs_dir and not _sbpl_path_safe(os.path.realpath(inputs_dir)):
                _bad = ("inputs dir contains a character unsafe for the sandbox "
                        "profile; refusing rather than risk profile injection")
            if _bad:
                shutil.rmtree(run_home, ignore_errors=True)
                shutil.rmtree(run_tmp, ignore_errors=True)
                return _refused(check, argv, _bad)
        # SEC-5: always run under the credential-stripping clean env. `env: inherit`
        # is not offered in P5 (it would pass SSH_AUTH_SOCK / API keys through); a
        # future dedicated-HOME variant can add a SAFE inherit that still strips
        # credentials.
        env = _clean_env(run_home, run_tmp, inputs_dir)
        os_argv = _wrap_argv(backend, argv, wt, run_tmp,
                             allow_write_repo=check.mutates, inputs_dir=inputs_dir)

        # 6. Run, capture, redact. enforcement_model is the HONEST level of the
        # backend that ran it (orchestrated for verified kernel isolation;
        # declared-sandbox for an operator-attested wrapper) — never overclaimed.
        enf = _ENFORCEMENT_MODEL.get(backend, "orchestrated")
        import time as _time
        t0 = _time.time()
        try:
            r = subprocess.run(os_argv, capture_output=True, text=True,
                               timeout=check.timeout, cwd=wt, env=env)
            dur = int((_time.time() - t0) * 1000)
            out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            return CheckResult(
                name=check.name, generated_by=argv, exit_code=r.returncode,
                passed=(r.returncode == 0), stdout_tail=_redact_tail(out, runner),
                duration_ms=dur, enforcement_model=enf, backend=backend,
                mutates=check.mutates)
        except subprocess.TimeoutExpired:
            dur = int((_time.time() - t0) * 1000)
            return CheckResult(
                name=check.name, generated_by=argv, exit_code=None, passed=False,
                stdout_tail=f"[timeout after {check.timeout}s]", duration_ms=dur,
                enforcement_model=enf, backend=backend, mutates=check.mutates)
        finally:
            shutil.rmtree(run_home, ignore_errors=True)
            shutil.rmtree(run_tmp, ignore_errors=True)
    except Exception as e:
        _mark_failure(e, "evidence_runner_run_check")
        return _refused(check, None, f"runner error: {e}")


# ── The planning-stage Evidence Contract producer (sibling to apply_criteria) ──
def run_evidence_contract_pass(instruction: str, catalog: Catalog | None,
                               criteria: str | None, *, invoker=None
                               ) -> tuple[dict | None, str | None]:
    """Produce the task-specific Evidence Contract BEFORE + SEPARATE FROM execution
    (spec §16-2). ``invoker(system, user)`` is a model-call callback (sidebar
    slot), injected for testability; no-op when absent. Returns (contract, error).
    Never raises."""
    if invoker is None:
        return None, "no-invoker"
    try:
        available = sorted((catalog.checks or {}).keys()) if catalog else []
        system = (
            "You author an Evidence Contract for a task BEFORE it is executed. Do "
            "NOT attempt the task. Given the task and the repo's available checks, "
            "output THREE short sections:\n"
            "REQUIRED CHECKS: a subset of the available checks that matter for THIS "
            "task (names only; empty if none apply).\n"
            "BESPOKE PROBE: one line describing what would demonstrate THIS feature "
            "actually works (a description, not a command).\n"
            "SUFFICIENCY: one line — what result counts as enough.")
        user = (f"TASK:\n{instruction}\n\nAVAILABLE CHECKS: "
                f"{', '.join(available) if available else '(none — no catalog found)'}\n"
                f"ACCEPTANCE CRITERIA (for context):\n{criteria or '(none)'}\n")
        out = invoker(system, user)
        if not out or not out.strip():
            return None, "empty"
        required, probe, suff = _parse_contract(out, available)
        return ({"required_standard_checks": required, "bespoke_probes": probe,
                 "sufficiency": suff, "repo_less": not available}, None)
    except Exception as e:
        return None, f"contract: {e}"


def _parse_contract(text: str, available: list[str]) -> tuple[list[str], list[str], str]:
    required: list[str] = []
    probe: list[str] = []
    suff = ""
    section = None
    for line in text.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("required checks"):
            section = "req"
            rest = s.split(":", 1)[1] if ":" in s else ""
            required += [t.strip() for t in rest.replace(",", " ").split() if t.strip()]
            continue
        if low.startswith("bespoke probe"):
            section = "probe"
            rest = s.split(":", 1)[1].strip() if ":" in s else ""
            if rest:
                probe.append(rest)
            continue
        if low.startswith("sufficiency"):
            section = "suff"
            suff = s.split(":", 1)[1].strip() if ":" in s else ""
            continue
        if not s:
            continue
        if section == "req":
            required += [t.strip() for t in s.lstrip("-*").replace(",", " ").split() if t.strip()]
        elif section == "probe":
            probe.append(s.lstrip("-* "))
        elif section == "suff" and not suff:
            suff = s
    # Only keep declared checks (executor cannot invent a check that isn't in the catalog).
    required = [c for c in required if c in available]
    return required, probe, suff


def lanes_from_catalog(catalog: Any) -> list:
    """The declared-lane block for the Evidence Contract, sourced from the catalog's
    write-protected ``recipes:`` (§16-2 — the model never invents a lane; the recipe
    body is the §6-protected file). ``[{lane, target, recipe}]``; empty when the
    catalog declares no recipes (all live ora turns)."""
    out: list = []
    for name, r in (getattr(catalog, "recipes", None) or {}).items():
        lane = getattr(r, "lane", None)
        target = getattr(r, "target", None)
        if lane and target:
            out.append({"lane": lane, "target": target, "recipe": name})
    return out


def apply_evidence_contract(context_pkg: dict, instruction: str, risk_tier: str, *,
                            invoker=None, repo_root: str | None = None) -> str | None:
    """The sibling to ``risk_gate.apply_criteria`` — run at the SAME planning point,
    standard+ only. Discovers a catalog (repo_root → ORA_PROJECT_ROOT → pathlib
    walk); produces the Contract (a repo-less one when no catalog is found) and
    stashes it on ``context_pkg['evidence_contract']``. Returns a directive
    (None/``WARN:``/``HOLD:``), mirroring ``apply_criteria``. Never raises."""
    try:
        if risk_tier == "light":
            return None
        catalog = None
        cat_path = discover_catalog(repo_root)
        if cat_path:
            try:
                catalog = parse_catalog(cat_path)
            except Exception as e:
                _mark_failure(e, "evidence_runner_apply_contract_parse")
                catalog = None
        # Phase 8 Chunk C: the declared-lane block comes from the catalog's
        # write-protected recipes (deterministic, model-independent — §16-2).
        _lanes = lanes_from_catalog(catalog)
        criteria = context_pkg.get("acceptance_criteria")
        contract, err = run_evidence_contract_pass(
            instruction, catalog, criteria, invoker=invoker)
        if contract and not err:
            if _lanes:
                contract["lanes"] = _lanes
            context_pkg["evidence_contract"] = contract
            try:
                _te.record({"event": "evidence_contract", "action": "evidence_contract",
                            "category": "execute", "mutability": "read",
                            "sensitivity": "public", "egress": "none",
                            "enforcement_model": "in_harness", "risk_tier": risk_tier})
            except Exception:
                pass
            return None
        # No model contract, but the repo declares recipes → still emit the
        # declared lanes (a repo's deploy_probe/render_inspect lane is a catalog
        # fact, not a task-specific model choice). Zero existing catalogs declare
        # recipes, so this path is inert for every pre-Chunk-C repo (parity).
        if _lanes:
            context_pkg["evidence_contract"] = {
                "required_standard_checks": [], "bespoke_probes": [],
                "sufficiency": "", "repo_less": not (catalog and catalog.checks),
                "lanes": _lanes}
            return None
        if err == "no-invoker":
            return None
        try:
            _te.record({"event": "evidence_contract", "action": "evidence_contract",
                        "category": "execute", "mutability": "read",
                        "sensitivity": "public", "egress": "none",
                        "enforcement_model": "in_harness", "risk_tier": risk_tier,
                        "contract_error": err})
        except Exception:
            pass
        msg = f"Evidence Contract could not be generated for this {risk_tier} task ({err})."
        try:
            if _rgate_tier_at_least(risk_tier, "high-risk"):
                return "HOLD:" + msg + " Holding for your review."
        except Exception:
            pass
        return "WARN:" + msg + " Proceeding without a pre-set evidence contract."
    except Exception as e:
        _mark_failure(e, "evidence_runner_apply_contract")
        return None


def _rgate_tier_at_least(tier: str, floor: str) -> bool:
    try:
        try:
            import risk_gate as _rg
        except ImportError:  # pragma: no cover
            from orchestrator import risk_gate as _rg
        return _rg.tier_at_least(tier, floor)
    except Exception:
        return False


# ── Dirty-state modes + git state snapshots (§9/§11) ──────────────────────────
def _git(repo: str, args: list[str], *, env: dict | None = None,
         timeout: int = 30) -> tuple[int, str]:
    """``git -C <repo> <args>`` (mirrors ``engram_promotion._git``). Returns
    (exit, stdout). Never raises. Optional ``env`` overrides the child environment
    (``None`` = inherit, identical to before) — the Phase-6 escalation-branch
    primitive uses it to redirect ``GIT_INDEX_FILE`` so a tree snapshot is committed
    onto an isolated branch WITHOUT touching the user's real index or HEAD.
    ``timeout`` (Phase 8): the 30s default holds for plumbing reads; the
    worktree/temp-commit lifecycle passes a larger bound (vault-scale
    ``add -A`` / ``worktree add`` outgrow 30s)."""
    try:
        r = subprocess.run(["git", "-C", repo, *args],
                           capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout or "").strip()
    except Exception as e:
        return 1, str(e)


# ── Phase 8 Chunk B — the isolated mutating-check actuator substrate (§3) ─────
# `git worktree add` a disposable checkout of the turn's FULL delta (a ref-less
# temp commit of the CURRENT tree parented at the pre-exec base — captures
# untracked files, which the delta_ref patch does not), run declared checks in
# it under mode="clean_worktree" (the only mode the runner permits mutating
# checks under), remove it. The user's HEAD/index/working tree are NEVER
# touched: the only repo-side writes are the throwaway-index temp commit (the
# proven Phase-6 escalation idiom — object-store only, ref-less) and git's
# .git/worktrees/ METADATA for the lifetime of the disposable checkout.

_WT_ROOT_SUBDIR = "exec-review-worktrees"
_WT_GIT_TIMEOUT = 300   # worktree add / add -A on large repos outgrows the 30s
                        # default (PROVISIONAL — vault-scale measured slow)


def _worktree_root() -> str:
    """Scratch root for disposable worktrees — runtime-paths-derived
    (portability amendment), same base the runner already uses for its
    per-run homes, so SBPL-safety and SEC-2 posture are the proven ones."""
    return os.path.join(_rp.SCRATCH_DIR_STR, _WT_ROOT_SUBDIR)


def inplace_checks_refused(repo_root: str) -> str | None:
    """The §3.3 routing predicate: would ``run_check``'s own pre-flight
    refuse checks run IN PLACE against this repo? Keyed on where that
    refusal ACTUALLY happens — the macOS sandbox-exec backend's SEC-1/SEC-2
    pre-flight. Other backends (unshare, declared wrapper) never
    path-preflight, so in-place behavior is unchanged there. **Windows
    regression guard (pre-check blocker fold): every Windows path contains
    a backslash and is SBPL-unsafe BY CHARACTER SET — keying this predicate
    on the raw ``sandbox_worktree_unsafe`` would have misrouted EVERY repo
    into the worktree path off-mac and then deferred every check when the
    worktree path was refused too.** Returns the refusal reason or None."""
    try:
        if not _macos_sandbox_available():
            return None
        return sandbox_worktree_unsafe(str(repo_root), str(repo_root))
    except Exception:
        return None


def _worktree_containment_refusal(wt: str) -> str | None:
    """Platform-universal share of the worktree pre-flight: SEC-2 ancestry
    (never a worktree equal to / an ancestor of a private root). The SBPL
    character check is macOS-only — on Windows every path carries ``\\``
    and would spuriously refuse (pre-check blocker fold)."""
    real_wt = os.path.realpath(wt)
    for sensitive in (os.path.realpath(os.path.expanduser("~")),
                      os.path.realpath(_rp.VAULT_STR),
                      os.path.realpath(_rp.CONVERSATIONS_STR)):
        if _is_within(sensitive, real_wt):
            return (f"worktree is equal to or an ancestor of a sensitive root "
                    f"({sensitive})")
    return None


def tree_commit_at(repo_root: str, base_sha: str,
                   *, timeout: int = _WT_GIT_TIMEOUT) -> str | None:
    """Create a REF-LESS commit of the repo's CURRENT tree parented at
    ``base_sha`` via a throwaway index (read-tree base → add -A → write-tree →
    commit-tree). Captures untracked files; never touches the user's index,
    HEAD, or working tree. REF-LESS is deliberate (design ⚖ Rev 3): a crash
    leaves only an unreachable object that git GC collects — a ref would pin
    a full snapshot of the user's tree (possibly-sensitive uncommitted
    content) in their repo forever. Returns the commit sha or None."""
    idx_path = None
    try:
        fd, idx_path = tempfile.mkstemp(prefix="er-wt-idx-")
        os.close(fd)
        try:
            os.unlink(idx_path)   # git wants to create the index fresh
        except OSError:
            pass
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = idx_path
        rc, _ = _git(repo_root, ["read-tree", base_sha], env=env,
                     timeout=timeout)
        if rc != 0:
            return None
        rc, _ = _git(repo_root, ["add", "-A"], env=env, timeout=timeout)
        if rc != 0:
            return None
        rc, tree = _git(repo_root, ["write-tree"], env=env, timeout=timeout)
        if rc != 0 or not tree:
            return None
        rc, commit = _git(
            repo_root,
            ["commit-tree", tree, "-p", base_sha, "-m",
             "execution-review: isolated-check snapshot (ref-less, disposable)"],
            env=env, timeout=timeout)
        if rc != 0 or not commit:
            return None
        return commit.strip()
    except Exception as e:
        _mark_failure(e, "evidence_runner_tree_commit")
        return None
    finally:
        if idx_path:
            try:
                os.unlink(idx_path)
            except OSError:
                pass


def create_isolated_worktree(repo_root: str, commit_sha: str,
                             *, sparse: list | None = None,
                             timeout: int = _WT_GIT_TIMEOUT) -> str | None:
    """``git worktree add --detach`` a disposable checkout of ``commit_sha``
    under the scratch root. Pre-flights the SAME containment the sandbox
    demands (``sandbox_worktree_unsafe`` — SBPL-unsafe chars + never an
    ancestor of a private root) and refuses honestly on any failure (the
    caller falls back to the deferred marker; a half-built worktree is
    removed before returning None). ``sparse`` materializes only the given
    paths (``--no-checkout`` + ``sparse-checkout set`` + ``checkout``) for
    vault-scale repos. Returns the worktree path or None."""
    wt = None
    try:
        root = _worktree_root()
        os.makedirs(root, exist_ok=True)
        wt = tempfile.mkdtemp(prefix="wt-", dir=root)
        # Containment first (house helper, case-normalized — never a bare
        # startswith), then the pre-flight the ACTIVE backend will apply:
        # the full SBPL check only where sandbox-exec runs (its character
        # set spuriously refuses every backslashed Windows path — pre-check
        # blocker fold); the SEC-2 ancestry share everywhere.
        if not _rp.within_base(wt, _rp.SCRATCH_DIR_STR):
            raise RuntimeError("worktree escaped the scratch root")
        bad = (sandbox_worktree_unsafe(wt, wt)
               if _macos_sandbox_available()
               else _worktree_containment_refusal(wt))
        if bad:
            raise RuntimeError(f"worktree path refused: {bad}")
        if sparse:
            # DISCLOSED side effect (pre-check fold, empirically pinned): git's
            # sparse-checkout builtin, invoked from a linked worktree, durably
            # writes `[extensions] worktreeConfig = true` into the MAIN repo's
            # shared .git/config — permanent metadata that survives
            # remove+prune. Benign on modern git, but it is user-repo residue:
            # the Chunk-C addendum decides the vault-family opt-in posture
            # BEFORE any caller passes sparse= (none does in Chunk B).
            rc, out = _git(repo_root, ["worktree", "add", "--detach",
                                       "--no-checkout", wt, commit_sha],
                           timeout=timeout)
            if rc != 0:
                raise RuntimeError(f"worktree add failed: {out[:200]}")
            rc, out = _git(wt, ["sparse-checkout", "set", "--no-cone",
                                *[str(p) for p in sparse]], timeout=timeout)
            if rc != 0:
                raise RuntimeError(f"sparse-checkout failed: {out[:200]}")
            rc, out = _git(wt, ["checkout", "--detach", commit_sha],
                           timeout=timeout)
            if rc != 0:
                raise RuntimeError(f"sparse checkout failed: {out[:200]}")
        else:
            rc, out = _git(repo_root, ["worktree", "add", "--detach", wt,
                                       commit_sha], timeout=timeout)
            if rc != 0:
                raise RuntimeError(f"worktree add failed: {out[:200]}")
        return wt
    except Exception as e:
        _mark_failure(e, "evidence_runner_worktree_add")
        if wt:
            remove_isolated_worktree(repo_root, wt)
        return None


def remove_isolated_worktree(repo_root: str, wt_path: str) -> bool:
    """Remove a disposable worktree: ``git worktree remove --force`` (retry
    once — Windows can hold handles briefly), then an ``rmtree`` fallback,
    then ``git worktree prune`` so no ``.git/worktrees`` metadata lingers.
    CONTAINMENT-GUARDED: refuses to touch any path outside the scratch
    worktree root — this function can never be aimed at user content."""
    try:
        if not _rp.within_base(wt_path, _worktree_root()):
            _mark_failure(RuntimeError(
                f"refused to remove non-scratch path: {wt_path!r}"),
                "evidence_runner_worktree_remove_containment")
            return False
        rc, _ = _git(repo_root, ["worktree", "remove", "--force", wt_path])
        if rc != 0 and os.path.exists(wt_path):
            rc, _ = _git(repo_root, ["worktree", "remove", "--force", wt_path])
        if os.path.exists(wt_path):
            shutil.rmtree(wt_path, ignore_errors=True)
        _git(repo_root, ["worktree", "prune"])
        return not os.path.exists(wt_path)
    except Exception as e:
        _mark_failure(e, "evidence_runner_worktree_remove")
        return False


def _worktree_owner_repo(wt_path: str) -> str | None:
    """Resolve the OWNING repo of a linked worktree from its ``.git`` file
    (a one-line ``gitdir: <repo>/.git/worktrees/<id>`` pointer). Never
    raises; None when unreadable/not a linked worktree."""
    try:
        gitfile = os.path.join(wt_path, ".git")
        if not os.path.isfile(gitfile):
            return None
        with open(gitfile, "r", encoding="utf-8", errors="replace") as f:
            line = f.read().strip()
        if not line.lower().startswith("gitdir:"):
            return None
        gitdir = line.split(":", 1)[1].strip()
        # <repo>/.git/worktrees/<id> → <repo>
        marker = os.sep + "worktrees" + os.sep
        norm = gitdir.replace("/", os.sep).replace("\\", os.sep)
        idx = norm.rfind(marker)
        if idx == -1:
            return None
        dotgit = norm[:idx]
        return os.path.dirname(dotgit) if dotgit.endswith(".git") else None
    except Exception:
        return None


def prune_orphan_worktrees(repo_root: str, *, max_age_seconds: int = 86_400) -> None:
    """Best-effort crash-residue cleanup, run at actuator start: rmtree of
    scratch worktree dirs older than ``max_age_seconds`` (a live actuator run
    never approaches that age; a crashed one's disposable checkout — which
    can contain private repo content — should not outlive the day), with
    ``git worktree prune`` fired against each swept dir's OWNING repo and,
    afterwards, against ``repo_root``.

    The per-owner prune is LOAD-BEARING (pre-check major fold, empirically
    pinned): a linked worktree's detached HEAD in ``.git/worktrees/<id>`` is
    a GC reachability ROOT — deleting the scratch dir WITHOUT pruning the
    owner leaves the ref-less snapshot commit (a full capture of that repo's
    uncommitted tree) retrievable in the OWNER's object store indefinitely,
    silently defeating the ref-less design's crash story. The scratch root is
    shared across repos, so the owner may not be ``repo_root``. Never raises."""
    try:
        root = _worktree_root()
        if os.path.isdir(root):
            import time as _time
            now = _time.time()
            for name in os.listdir(root):
                p = os.path.join(root, name)
                try:
                    if not (os.path.isdir(p)
                            and now - os.path.getmtime(p) > max_age_seconds
                            and _rp.within_base(p, root)):
                        continue
                    owner = _worktree_owner_repo(p)
                    shutil.rmtree(p, ignore_errors=True)
                    if owner and os.path.isdir(owner):
                        _git(owner, ["worktree", "prune"])
                except OSError:
                    continue
        # Trailing prune on the CURRENT repo (after the sweep, so a same-repo
        # dir deleted this pass is released even when this lifecycle aborts
        # before remove_isolated_worktree's own prune — pre-check fold).
        _git(repo_root, ["worktree", "prune"])
    except Exception as e:
        _mark_failure(e, "evidence_runner_worktree_prune")


def _git_state(repo_root: str) -> dict:
    """A small, flat git state snapshot (§9: git → commit/tree hash)."""
    _, head = _git(repo_root, ["rev-parse", "HEAD"])
    _, tree = _git(repo_root, ["rev-parse", "HEAD^{tree}"])
    _, dirty = _git(repo_root, ["status", "--porcelain"])
    import hashlib
    dirty_hash = hashlib.sha1(dirty.encode("utf-8", "replace")).hexdigest()[:16] if dirty else None
    return {"head": head or None, "tree": tree or None, "dirty_hash": dirty_hash}


def snapshot_before(repo_root: str, mode: str) -> dict:
    """``state_before`` per §11 mode — git SHAs/tree-hashes only (small, flat)."""
    st = _git_state(repo_root)
    st["mode"] = mode
    return st


def snapshot_after(repo_root: str, mode: str, trace_dir: str | None,
                   before: dict | None) -> tuple[dict, str | None]:
    """``state_after`` + a ``delta.ref`` (the ``git diff`` written trace-local, a
    reference — never inlined, §9). The git-state helper + diff-writer run OUTSIDE
    any sandbox (they operate on the repo directly)."""
    st = _git_state(repo_root)
    st["mode"] = mode
    delta_ref = None
    if trace_dir:
        try:
            base = (before or {}).get("head") or "HEAD"
            _, diff = _git(repo_root, ["diff", base])
            os.makedirs(trace_dir, exist_ok=True)
            path = os.path.join(trace_dir, "evidence-diff.patch")
            with open(path, "w") as f:
                f.write(diff)
            delta_ref = path
        except Exception as e:
            _mark_failure(e, "evidence_runner_snapshot_after")
    return st, delta_ref


# ── Lane fill — attach filled evidence to the Phase-4 packet (additive) ────────
def contract_sufficient(results: list[CheckResult], contract: dict | None) -> bool:
    """Sufficiency judged against the Evidence Contract, never self-asserted
    (§10/§16-2). True only when EVERY Contract-required check ran and passed. A
    refused/failed/absent required check → not sufficient. A green run means
    nothing broke that you knew to check — NOT that the right problem was solved."""
    if not contract:
        return False
    required = contract.get("required_standard_checks") or []
    if not required:
        # No required checks declared → nothing was proven sufficient.
        return False
    by_name = {r.name: r for r in results}
    for name in required:
        r = by_name.get(name)
        if r is None or r.skipped or not r.passed:
            return False
    return True


def fill_evidence_lanes(packet: Any, results: list[CheckResult],
                        contract: dict | None = None, delta_ref: str | None = None) -> Any:
    """Fill the Phase-4 diff_validate ``EvidenceLane`` from runner results —
    additive, never raises, returns the packet. ``generated_by`` ties each lane to
    the DECLARED commands actually run (not an executor self-report); ``sufficient``
    is judged against the Contract."""
    try:
        lanes = getattr(packet, "evidence_lanes", None) or []
        suff = contract_sufficient(results, contract)
        payload = [r.to_dict() for r in results]
        cmds: list[str] = []
        for r in results:
            cmds += [" ".join(map(str, r.generated_by))] if r.generated_by else []
        for lane in lanes:
            if getattr(lane, "lane", None) == "diff_validate":
                lane.generated_by = cmds
                lane.result = {"checks": payload, "delta_ref": delta_ref}
                lane.sufficient = suff
        return packet
    except Exception as e:
        _mark_failure(e, "evidence_runner_fill_lanes")
        return packet


# ── Terminal convenience: run a Contract's required checks over a repo ─────────
def run_contract(catalog: Catalog, contract: dict, repo_root: str, *,
                 worktree: str | None = None, mode: str | None = None,
                 inputs_dir: str | None = None
                 ) -> list[CheckResult]:
    """Run the Contract's ``required_standard_checks`` (a subset of the catalog).
    A required check missing from the catalog is recorded as refused (the executor
    cannot invent checks). Never raises. ``inputs_dir`` (Phase 8 Chunk C) is the
    shared read-only directory of harness-built check inputs — each check reads
    only the files it declared in its ``inputs`` list, via ``ORA_CHECK_INPUTS``."""
    results: list[CheckResult] = []
    for name in (contract.get("required_standard_checks") or []):
        check = (catalog.checks or {}).get(name)
        if check is None:
            # A declared-required check missing from the catalog is a refusal that
            # must ALSO be OBSERVED, not narrated (§16-3) — record a tool-event, the
            # same as run_check does for its own outcomes (the P2 recording gap).
            missing = CheckResult(name=name, skipped=True,
                                  skip_reason="declared-required but not in catalog")
            _record_check_event(Check(name=name), missing)
            results.append(missing)
            continue
        # A check gets an inputs dir only if it DECLARED inputs (else None keeps
        # the pre-Chunk-C behavior byte-identical — no env var, no read-allow).
        chk_inputs = inputs_dir if getattr(check, "inputs", None) else None
        results.append(run_check(check, catalog.runner, repo_root,
                                 worktree=worktree, mode=mode,
                                 inputs_dir=chk_inputs))
    return results


# ── Phase 8 Chunk C — harness-built check INPUTS (§2.2) ───────────────────────
# Every git-derived check input is precomputed IN-HARNESS (outside the sandbox,
# where git works), written into a read-only inputs dir, and read by the
# self-contained check via ORA_CHECK_INPUTS. The check runs NO git and reads NO
# ora code inside the sandbox (design ⚖ Rev 3; addendum §2.2/§3).

def changed_files_at(repo_root: str, base_sha: str,
                     delta_commit: str | None = None,
                     *, timeout: int = _WT_GIT_TIMEOUT) -> list[str]:
    """The turn's changed files, EXCLUDING deletions (``--diff-filter=d`` lowercase
    = exclude deleted) so a deleted/renamed-away path never reaches a check that
    would then open a missing file (⚖ Rev-4/C2 false-FAIL fix). Isolated path
    (``delta_commit`` given): ``git diff base..delta``. In-place path: ``git diff
    base`` ∪ current untracked. Returns repo-relative forward-slash paths."""
    paths: list[str] = []
    if delta_commit:
        rc, out = _git(repo_root, ["diff", "--name-only", "--diff-filter=d",
                                   base_sha, delta_commit], timeout=timeout)
        if rc == 0:
            paths = [p for p in out.splitlines() if p.strip()]
    else:
        rc, out = _git(repo_root, ["diff", "--name-only", "--diff-filter=d",
                                   base_sha], timeout=timeout)
        if rc == 0:
            paths = [p for p in out.splitlines() if p.strip()]
        rc2, out2 = _git(repo_root, ["ls-files", "--others", "--exclude-standard"],
                         timeout=timeout)
        if rc2 == 0:
            paths += [p for p in out2.splitlines() if p.strip()]
    # De-dup, stable order.
    seen: set = set()
    uniq = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _title_universe_at(repo_root: str, base_sha: str,
                       delta_commit: str | None = None,
                       *, timeout: int = _WT_GIT_TIMEOUT) -> list[str]:
    """The note-title universe as it exists AT CHECK TIME, including this turn's
    NEW notes. Isolated: ``git ls-tree -r <delta_commit>`` (the delta commit's
    ``add -A`` already captured untracked new files). In-place: ``git ls-files
    --cached --others --exclude-standard`` (current tracked + untracked) — NOT the
    base tree, which omits the turn's new notes and would false-dangle a
    new-note→new-note link (⚖ Rev-4/C3)."""
    if delta_commit:
        rc, out = _git(repo_root, ["ls-tree", "-r", "--name-only", delta_commit],
                       timeout=timeout)
    else:
        rc, out = _git(repo_root, ["ls-files", "--cached", "--others",
                                   "--exclude-standard"], timeout=timeout)
    if rc != 0:
        return []
    return [p for p in out.splitlines() if p.strip()]


def build_check_inputs(repo_root: str, dest_dir: str, needed: set, base_sha: str,
                       delta_commit: str | None = None,
                       *, changed: list | None = None,
                       timeout: int = _WT_GIT_TIMEOUT) -> list[str]:
    """Write each declared input into ``dest_dir`` (one file per input, UTF-8). All
    git runs OUTSIDE the sandbox. Returns the input names actually written (recorded
    on the check event — observed, not narrated). ``changed`` may be passed to
    reuse an already-computed changed-file list (avoids a second ``git diff``)."""
    written: list[str] = []
    try:
        os.makedirs(dest_dir, exist_ok=True)
        if "changed_files" in needed:
            cf = changed if changed is not None else changed_files_at(
                repo_root, base_sha, delta_commit, timeout=timeout)
            with open(os.path.join(dest_dir, _INPUTS_FILENAMES["changed_files"]),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(cf) + ("\n" if cf else ""))
            written.append("changed_files")
        if "title_universe" in needed:
            tu = _title_universe_at(repo_root, base_sha, delta_commit, timeout=timeout)
            with open(os.path.join(dest_dir, _INPUTS_FILENAMES["title_universe"]),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(tu) + ("\n" if tu else ""))
            written.append("title_universe")
    except Exception as e:
        _mark_failure(e, "evidence_runner_build_inputs")
    return written


def make_inputs_dir() -> str:
    """A fresh read-only-destined inputs directory under the runner's scratch base
    (runtime-paths-derived — portability amendment). Caller removes it
    finally-guaranteed."""
    base = os.path.join(_rp.SCRATCH_DIR_STR, "evidence-runner")
    os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix="inputs-", dir=base)


def collect_declared_inputs(catalog: Any, check_names: list) -> set:
    """Union of declared ``inputs`` across the named checks (what the inputs dir
    must contain for this batch)."""
    needed: set = set()
    checks = getattr(catalog, "checks", None) or {}
    for n in check_names:
        c = checks.get(n)
        for i in (getattr(c, "inputs", None) or []):
            needed.add(i)
    return needed


def batch_all_changed_scope(catalog: Any, check_names: list) -> bool:
    """True iff EVERY named check declares ``scope: changed_files`` — the condition
    for a sparse worktree (a ``scope: repo`` check in the batch would silently miss
    files in a sparse tree, so any such check forces a full checkout)."""
    checks = getattr(catalog, "checks", None) or {}
    names = list(check_names)
    if not names:
        return False
    for n in names:
        c = checks.get(n)
        if getattr(c, "scope", "repo") != "changed_files":
            return False
    return True
