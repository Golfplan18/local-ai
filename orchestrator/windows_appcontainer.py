"""Native Windows AppContainer runner for evidence checks.

This module is intentionally lazy: importing it on macOS/Linux never loads a
Windows DLL.  On Windows it launches a child with three load-bearing controls:

* a unique, zero-capability AppContainer profile (therefore no network
  capability);
* an atomically attached Job Object with kill-on-close semantics; and
* an explicit inherited-handle list containing only stdin/stdout/stderr pipes.

Ora's temporary file-access ACLs name only the unique profile SID (the token may
still retain access conferred by pre-existing Windows application-package
ACLs). Every planned ACL change and the profile name are durably journaled before
the first OS mutation. Native runs are serialized with a cross-process file lock
so the next run can safely recover a journal left by a crashed parent without
racing an active lease. A journal is removed only after all ACL entries are
revoked and the profile is deleted.

The implementation uses ctypes because pywin32 does not wrap the AppContainer
profile + STARTUPINFOEX launch path.  It targets Windows 10+ (Ora's G1.13 target
is Windows 11) and refuses rather than weakening containment when any required
API or process attribute is unavailable.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


# Fixed-width aliases are deliberate.  ``ctypes.c_long`` is 64-bit on macOS,
# unlike Windows LONG/DWORD, which would make cross-platform ABI tests lie.
BOOL = ctypes.c_int32
DWORD = ctypes.c_uint32
HRESULT = ctypes.c_int32
WORD = ctypes.c_uint16
UINT = ctypes.c_uint32
ULONG_PTR = ctypes.c_size_t
SIZE_T = ctypes.c_size_t
HANDLE = ctypes.c_void_p
LPVOID = ctypes.c_void_p
LPWSTR = ctypes.c_wchar_p
LPCWSTR = ctypes.c_wchar_p


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", DWORD),
        ("lpSecurityDescriptor", LPVOID),
        ("bInheritHandle", BOOL),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", LPVOID), ("Attributes", DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", LPVOID),
        ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
        ("CapabilityCount", DWORD),
        ("Reserved", DWORD),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", DWORD),
        ("lpReserved", LPWSTR),
        ("lpDesktop", LPWSTR),
        ("lpTitle", LPWSTR),
        ("dwX", DWORD),
        ("dwY", DWORD),
        ("dwXSize", DWORD),
        ("dwYSize", DWORD),
        ("dwXCountChars", DWORD),
        ("dwYCountChars", DWORD),
        ("dwFillAttribute", DWORD),
        ("dwFlags", DWORD),
        ("wShowWindow", WORD),
        ("cbReserved2", WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
        ("hStdInput", HANDLE),
        ("hStdOutput", HANDLE),
        ("hStdError", HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", LPVOID)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", HANDLE),
        ("hThread", HANDLE),
        ("dwProcessId", DWORD),
        ("dwThreadId", DWORD),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", DWORD),
        ("MinimumWorkingSetSize", SIZE_T),
        ("MaximumWorkingSetSize", SIZE_T),
        ("ActiveProcessLimit", DWORD),
        ("Affinity", ULONG_PTR),
        ("PriorityClass", DWORD),
        ("SchedulingClass", DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", SIZE_T),
        ("JobMemoryLimit", SIZE_T),
        ("PeakProcessMemoryUsed", SIZE_T),
        ("PeakJobMemoryUsed", SIZE_T),
    ]


class TRUSTEE_W(ctypes.Structure):
    _fields_ = [
        ("pMultipleTrustee", LPVOID),
        ("MultipleTrusteeOperation", ctypes.c_int32),
        ("TrusteeForm", ctypes.c_int32),
        ("TrusteeType", ctypes.c_int32),
        # With TRUSTEE_IS_SID this is a PSID, not a string.
        ("ptstrName", LPVOID),
    ]


class EXPLICIT_ACCESSW(ctypes.Structure):
    _fields_ = [
        ("grfAccessPermissions", DWORD),
        ("grfAccessMode", ctypes.c_int32),
        ("grfInheritance", DWORD),
        ("Trustee", TRUSTEE_W),
    ]


# Process / attribute constants.
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
INFINITE = 0xFFFFFFFF
STILL_ACTIVE = 259
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_BROKEN_PIPE = 109
ERROR_ALREADY_EXISTS = 183

# Job constants.  No active-process limit: test runners/compilers may spawn.
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400

# ACL constants.
SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004
GRANT_ACCESS = 1
REVOKE_ACCESS = 4
NO_MULTIPLE_TRUSTEE = 0
TRUSTEE_IS_SID = 0
TRUSTEE_IS_UNKNOWN = 0
OBJECT_INHERIT_ACE = 0x1
CONTAINER_INHERIT_ACE = 0x2
FILE_GENERIC_READ = 0x00120089
FILE_GENERIC_WRITE = 0x00120116
FILE_GENERIC_EXECUTE = 0x001200A0
DELETE = 0x00010000
FILE_DELETE_CHILD = 0x00000040
READ_EXECUTE_MASK = FILE_GENERIC_READ | FILE_GENERIC_EXECUTE
MODIFY_MASK = READ_EXECUTE_MASK | FILE_GENERIC_WRITE | DELETE | FILE_DELETE_CHILD

_PROFILE_PREFIX = "ora.evidence."
_JOURNAL_VERSION = 1
_STREAM_RETAIN_CAP = 1_000_000


class AppContainerError(RuntimeError):
    """Native sandbox setup, launch, or recovery failed closed."""


class AppContainerUnavailable(AppContainerError):
    """The platform does not expose the required Windows 10+ API surface."""


class _ProfileCollision(AppContainerError):
    """A supposedly unique profile name already existed; it is not ours to delete."""


@dataclass
class SandboxResult:
    started: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str | None = None
    cleanup_error: str | None = None


def _last_error() -> int:
    getter = getattr(ctypes, "get_last_error", None)
    return int(getter()) if callable(getter) else 0


def _u32(value: int) -> int:
    return int(value) & 0xFFFFFFFF


def _win_error(where: str, code: int | None = None) -> AppContainerError:
    value = _last_error() if code is None else int(code)
    try:
        detail = ctypes.FormatError(value).strip()
    except Exception:
        detail = "Windows error"
    return AppContainerError(f"{where} failed ({value}): {detail}")


def _set_signature(fn: Any, argtypes: list[Any], restype: Any) -> None:
    fn.argtypes = argtypes
    fn.restype = restype


class _WinAPI:
    """Loaded DLL exports with explicit signatures and last-error capture."""

    def __init__(self) -> None:
        if sys.platform != "win32" or os.name != "nt":
            raise AppContainerUnavailable("AppContainer is available only on Windows")
        loader = getattr(ctypes, "WinDLL", None)
        if loader is None:
            raise AppContainerUnavailable("ctypes.WinDLL is unavailable")
        try:
            self.kernel32 = loader("kernel32", use_last_error=True)
            self.advapi32 = loader("advapi32", use_last_error=True)
            self.userenv = loader("userenv", use_last_error=True)
        except Exception as exc:
            raise AppContainerUnavailable(f"required Windows DLL unavailable: {exc}") from exc

        k, a, u = self.kernel32, self.advapi32, self.userenv
        required = [
            (k, "InitializeProcThreadAttributeList"),
            (k, "UpdateProcThreadAttribute"),
            (k, "DeleteProcThreadAttributeList"),
            (k, "CreateJobObjectW"),
            (k, "SetInformationJobObject"),
            (k, "TerminateJobObject"),
            (k, "CreatePipe"),
            (k, "SetHandleInformation"),
            (k, "CreateProcessW"),
            (k, "ResumeThread"),
            (k, "WaitForSingleObject"),
            (k, "GetExitCodeProcess"),
            (k, "ReadFile"),
            (k, "CloseHandle"),
            (k, "LocalFree"),
            (a, "FreeSid"),
            (a, "ConvertSidToStringSidW"),
            (a, "ConvertStringSidToSidW"),
            (a, "GetNamedSecurityInfoW"),
            (a, "SetEntriesInAclW"),
            (a, "SetNamedSecurityInfoW"),
            (u, "CreateAppContainerProfile"),
            (u, "DeriveAppContainerSidFromAppContainerName"),
            (u, "DeleteAppContainerProfile"),
        ]
        missing = [name for dll, name in required if not hasattr(dll, name)]
        if missing:
            raise AppContainerUnavailable("missing Win32 exports: " + ", ".join(missing))

        _set_signature(k.InitializeProcThreadAttributeList,
                       [LPVOID, DWORD, DWORD, ctypes.POINTER(SIZE_T)], BOOL)
        _set_signature(k.UpdateProcThreadAttribute,
                       [LPVOID, DWORD, ULONG_PTR, LPVOID, SIZE_T, LPVOID,
                        ctypes.POINTER(SIZE_T)], BOOL)
        _set_signature(k.DeleteProcThreadAttributeList, [LPVOID], None)
        _set_signature(k.CreateJobObjectW,
                       [ctypes.POINTER(SECURITY_ATTRIBUTES), LPCWSTR], HANDLE)
        _set_signature(k.SetInformationJobObject, [HANDLE, ctypes.c_int32, LPVOID, DWORD], BOOL)
        _set_signature(k.TerminateJobObject, [HANDLE, UINT], BOOL)
        _set_signature(k.CreatePipe,
                       [ctypes.POINTER(HANDLE), ctypes.POINTER(HANDLE),
                        ctypes.POINTER(SECURITY_ATTRIBUTES), DWORD], BOOL)
        _set_signature(k.SetHandleInformation, [HANDLE, DWORD, DWORD], BOOL)
        _set_signature(k.CreateProcessW,
                       [LPCWSTR, LPWSTR, ctypes.POINTER(SECURITY_ATTRIBUTES),
                        ctypes.POINTER(SECURITY_ATTRIBUTES), BOOL, DWORD, LPVOID,
                        LPCWSTR, ctypes.POINTER(STARTUPINFOW),
                        ctypes.POINTER(PROCESS_INFORMATION)], BOOL)
        _set_signature(k.ResumeThread, [HANDLE], DWORD)
        _set_signature(k.WaitForSingleObject, [HANDLE, DWORD], DWORD)
        _set_signature(k.GetExitCodeProcess, [HANDLE, ctypes.POINTER(DWORD)], BOOL)
        _set_signature(k.ReadFile,
                       [HANDLE, LPVOID, DWORD, ctypes.POINTER(DWORD), LPVOID], BOOL)
        _set_signature(k.CloseHandle, [HANDLE], BOOL)
        _set_signature(k.LocalFree, [LPVOID], LPVOID)

        _set_signature(a.FreeSid, [LPVOID], LPVOID)
        _set_signature(a.ConvertSidToStringSidW,
                       [LPVOID, ctypes.POINTER(LPWSTR)], BOOL)
        _set_signature(a.ConvertStringSidToSidW,
                       [LPCWSTR, ctypes.POINTER(LPVOID)], BOOL)
        _set_signature(a.GetNamedSecurityInfoW,
                       [LPCWSTR, ctypes.c_int32, DWORD, ctypes.POINTER(LPVOID),
                        ctypes.POINTER(LPVOID), ctypes.POINTER(LPVOID),
                        ctypes.POINTER(LPVOID), ctypes.POINTER(LPVOID)], DWORD)
        _set_signature(a.SetEntriesInAclW,
                       [DWORD, ctypes.POINTER(EXPLICIT_ACCESSW), LPVOID,
                        ctypes.POINTER(LPVOID)], DWORD)
        _set_signature(a.SetNamedSecurityInfoW,
                       [LPWSTR, ctypes.c_int32, DWORD, LPVOID, LPVOID, LPVOID, LPVOID], DWORD)

        _set_signature(u.CreateAppContainerProfile,
                       [LPCWSTR, LPCWSTR, LPCWSTR, ctypes.POINTER(SID_AND_ATTRIBUTES),
                        DWORD, ctypes.POINTER(LPVOID)], HRESULT)
        _set_signature(u.DeriveAppContainerSidFromAppContainerName,
                       [LPCWSTR, ctypes.POINTER(LPVOID)], HRESULT)
        _set_signature(u.DeleteAppContainerProfile, [LPCWSTR], HRESULT)


_api_cache: _WinAPI | None = None
_api_cache_failed = False


def _load_api() -> _WinAPI:
    global _api_cache, _api_cache_failed
    if _api_cache is not None:
        return _api_cache
    if _api_cache_failed:
        raise AppContainerUnavailable("required AppContainer API surface is unavailable")
    try:
        _api_cache = _WinAPI()
        return _api_cache
    except Exception:
        _api_cache_failed = True
        raise


def available() -> bool:
    """Return whether the required native API surface is present.

    This is only a surface probe.  ACL/profile/process failures still refuse at
    launch time, and the Windows-only acceptance test is the proof that a target
    machine can run its installed Python/runtime inside the container.
    """
    if sys.platform != "win32" or os.name != "nt":
        return False
    try:
        _load_api()
        return True
    except Exception:
        return False


def _close(api: _WinAPI, handle: HANDLE | int | None) -> None:
    value = handle.value if isinstance(handle, ctypes.c_void_p) else handle
    if value:
        try:
            api.kernel32.CloseHandle(HANDLE(value))
        except Exception:
            pass


def _sid_text(api: _WinAPI, sid: LPVOID) -> str:
    raw = LPWSTR()
    if not api.advapi32.ConvertSidToStringSidW(sid, ctypes.byref(raw)):
        raise _win_error("ConvertSidToStringSidW")
    try:
        return str(raw.value or "")
    finally:
        if raw:
            api.kernel32.LocalFree(ctypes.cast(raw, LPVOID))


def _sid_from_text(api: _WinAPI, value: str) -> LPVOID:
    """Rehydrate a journaled SID even if profile deletion was indeterminate."""
    sid = LPVOID()
    if not api.advapi32.ConvertStringSidToSidW(value, ctypes.byref(sid)):
        raise _win_error("ConvertStringSidToSidW")
    if not sid.value:
        raise AppContainerError("ConvertStringSidToSidW returned a null SID")
    return sid


def _create_profile(api: _WinAPI, name: str) -> LPVOID:
    sid = LPVOID()
    hr = api.userenv.CreateAppContainerProfile(
        name, "Ora evidence check", "Ephemeral Ora evidence sandbox",
        None, 0, ctypes.byref(sid),
    )
    if _u32(hr) == (0x80070000 | ERROR_ALREADY_EXISTS):
        raise _ProfileCollision("unique AppContainer profile name unexpectedly already exists")
    if hr != 0 or not sid.value:
        raise AppContainerError(f"CreateAppContainerProfile failed (HRESULT 0x{_u32(hr):08x})")
    return sid


def _derive_profile_sid(api: _WinAPI, name: str) -> LPVOID:
    sid = LPVOID()
    hr = api.userenv.DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(sid))
    if hr != 0 or not sid.value:
        raise AppContainerError(
            f"DeriveAppContainerSidFromAppContainerName failed (HRESULT 0x{_u32(hr):08x})")
    return sid


def _delete_profile(api: _WinAPI, name: str) -> None:
    hr = api.userenv.DeleteAppContainerProfile(name)
    if hr != 0:
        raise AppContainerError(
            f"DeleteAppContainerProfile failed (HRESULT 0x{_u32(hr):08x})")


def _acl_entry(api: _WinAPI, path: str, sid: LPVOID, *, grant: bool,
               writable: bool = False) -> None:
    """Merge or revoke one inherited ACE for the exact profile SID."""
    if not os.path.exists(path):
        if grant:
            raise AppContainerError(f"ACL grant path does not exist: {path}")
        return
    dacl = LPVOID()
    descriptor = LPVOID()
    status = api.advapi32.GetNamedSecurityInfoW(
        path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
        None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor),
    )
    if status != 0:
        raise _win_error(f"GetNamedSecurityInfoW({path})", status)
    new_acl = LPVOID()
    try:
        if not dacl.value:
            raise AppContainerError(f"refusing ACL mutation on NULL-DACL path: {path}")
        entry = EXPLICIT_ACCESSW()
        entry.grfAccessPermissions = (MODIFY_MASK if writable else READ_EXECUTE_MASK) if grant else 0
        entry.grfAccessMode = GRANT_ACCESS if grant else REVOKE_ACCESS
        entry.grfInheritance = OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
        entry.Trustee.pMultipleTrustee = None
        entry.Trustee.MultipleTrusteeOperation = NO_MULTIPLE_TRUSTEE
        entry.Trustee.TrusteeForm = TRUSTEE_IS_SID
        entry.Trustee.TrusteeType = TRUSTEE_IS_UNKNOWN
        entry.Trustee.ptstrName = sid
        status = api.advapi32.SetEntriesInAclW(
            1, ctypes.byref(entry), dacl, ctypes.byref(new_acl))
        if status != 0:
            raise _win_error(f"SetEntriesInAclW({path})", status)
        status = api.advapi32.SetNamedSecurityInfoW(
            path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            None, None, new_acl, None,
        )
        if status != 0:
            raise _win_error(f"SetNamedSecurityInfoW({path})", status)
    finally:
        if new_acl.value:
            api.kernel32.LocalFree(new_acl)
        if descriptor.value:
            api.kernel32.LocalFree(descriptor)


def _canonical_existing(path: str | os.PathLike[str]) -> str:
    value = os.path.realpath(os.path.abspath(os.fspath(path)))
    if not os.path.exists(value):
        raise AppContainerError(f"sandbox path does not exist: {value}")
    return value


def _dedupe_paths(entries: Iterable[tuple[str, bool]]) -> list[dict[str, Any]]:
    """Collapse duplicate/ancestor grants, preserving the stronger access mask."""
    merged: dict[str, dict[str, Any]] = {}
    for raw, writable in entries:
        path = _canonical_existing(raw)
        key = os.path.normcase(path)
        prior = merged.get(key)
        if prior is None:
            merged[key] = {"path": path, "writable": bool(writable)}
        elif writable:
            prior["writable"] = True
    # Grant parents before children, revoke in reverse.  Keeping exact entries is
    # intentional: worktree and scratch access have different masks.
    return sorted(merged.values(), key=lambda item: (len(Path(item["path"]).parts), item["path"]))


def _allowed_journal_path(path: str) -> bool:
    """Recovery containment: temporary ACLs may touch only user-owned roots.

    Evidence worktrees and user-installed runtimes live below the user profile;
    Ora's configured roots are included for redirected Documents/scratch layouts.
    System locations need no temporary user SID ACE and are never journal targets.
    """
    candidates = [Path.home(), Path(_rp.ORA_HOME), Path(_rp.SCRATCH_DIR),
                  Path(_rp.DOCUMENTS), Path(_rp.VAULT)]
    target = Path(path)
    for base in candidates:
        try:
            relative = target.resolve(strict=False).relative_to(base.resolve(strict=False))
        except (OSError, ValueError):
            continue
        # Never grant/revoke the entire user profile or configured root itself.
        if relative.parts:
            return True
    return False


def _validate_grants(grants: list[dict[str, Any]]) -> None:
    if not grants:
        raise AppContainerError("AppContainer ACL plan is empty")
    for item in grants:
        if set(item) != {"path", "writable"} or not isinstance(item["path"], str):
            raise AppContainerError("invalid AppContainer ACL journal entry")
        if not isinstance(item["writable"], bool):
            raise AppContainerError("invalid AppContainer ACL access mode")
        if not os.path.isabs(item["path"]) or not _allowed_journal_path(item["path"]):
            raise AppContainerError(
                f"ACL journal path is outside contained user roots: {item['path']}")


def _validate_grant_boundaries(grants: list[dict[str, Any]], state_root: Path) -> None:
    """Refuse an inherited grant that would engulf private or recovery state."""
    sensitive = [Path.home(), Path(_rp.VAULT), Path(_rp.CONVERSATIONS),
                 Path(_rp.DATA_DIR), Path(_rp.CONFIG_DIR)]
    for item in grants:
        grant = Path(item["path"])
        for private in sensitive:
            if _rp.within_base(private, grant):
                raise AppContainerError(
                    "AppContainer grant root is equal to or an ancestor of a "
                    f"sensitive root ({private}): {grant}")
        if item["writable"] and _rp.within_base(state_root, grant):
            raise AppContainerError(
                "AppContainer writable grant would contain its crash-recovery "
                f"journal: {grant}")


def _write_journal(path: Path, payload: dict[str, Any]) -> None:
    _rp.atomic_write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _read_journal(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppContainerError(f"invalid AppContainer recovery journal {path.name}: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {
            "version", "profile", "sid", "grants_started", "grants"}:
        raise AppContainerError(f"invalid AppContainer recovery journal schema: {path.name}")
    if raw["version"] != _JOURNAL_VERSION:
        raise AppContainerError(f"unsupported AppContainer journal version: {raw['version']}")
    profile = raw["profile"]
    if (not isinstance(profile, str) or not profile.startswith(_PROFILE_PREFIX)
            or len(profile) > 64 or not profile.removeprefix(_PROFILE_PREFIX).isalnum()):
        raise AppContainerError(f"invalid AppContainer profile in journal: {path.name}")
    if raw["sid"] is not None and not (
            isinstance(raw["sid"], str) and raw["sid"].startswith("S-1-15-2-")):
        raise AppContainerError(f"invalid AppContainer SID in journal: {path.name}")
    if not isinstance(raw["grants_started"], bool) or not isinstance(raw["grants"], list):
        raise AppContainerError(f"invalid AppContainer journal state: {path.name}")
    _validate_grants(raw["grants"])
    return raw


def _cleanup_lease(api: _WinAPI, journal: Path, payload: dict[str, Any],
                   sid: LPVOID | None = None, *, sid_owned_by_profile: bool = True) -> None:
    """Idempotently revoke a lease and delete its profile.

    The journal remains when any cleanup step fails so a later serialized run
    retries.  Every step is attempted even after an earlier failure.
    """
    errors: list[str] = []
    cleanup_sid = sid
    cleanup_allocator: str | None = None
    try:
        if payload["grants_started"] and not (cleanup_sid and cleanup_sid.value):
            try:
                cleanup_sid = _derive_profile_sid(api, payload["profile"])
                cleanup_allocator = "free_sid"
            except Exception as derive_exc:
                # DeleteAppContainerProfile failure has explicitly indeterminate
                # state.  The contained, user-owned journal's textual SID lets us
                # revoke the unique ACE even if the profile can no longer derive.
                try:
                    if not payload["sid"]:
                        raise derive_exc
                    cleanup_sid = _sid_from_text(api, payload["sid"])
                    cleanup_allocator = "local_free"
                except Exception as text_exc:
                    errors.append(f"{derive_exc}; SID recovery also failed: {text_exc}")
        sid_matches = True
        if payload["grants_started"] and cleanup_sid and cleanup_sid.value:
            try:
                observed = _sid_text(api, cleanup_sid)
                if payload["sid"] and observed != payload["sid"]:
                    raise AppContainerError("derived profile SID does not match recovery journal")
            except Exception as exc:
                errors.append(str(exc))
                sid_matches = False
            for item in reversed(payload["grants"]) if sid_matches else ():
                try:
                    _acl_entry(api, item["path"], cleanup_sid, grant=False,
                               writable=item["writable"])
                except Exception as exc:
                    errors.append(str(exc))
        # Never delete the profile while any ACE may remain.  Keeping the profile
        # keeps SID derivation available to the next serialized recovery pass.
        if not errors:
            try:
                _delete_profile(api, payload["profile"])
            except Exception as exc:
                errors.append(str(exc))
    finally:
        if cleanup_allocator == "free_sid" and cleanup_sid and cleanup_sid.value:
            api.advapi32.FreeSid(cleanup_sid)
        elif cleanup_allocator == "local_free" and cleanup_sid and cleanup_sid.value:
            api.kernel32.LocalFree(cleanup_sid)
        elif sid_owned_by_profile and sid and sid.value:
            api.advapi32.FreeSid(sid)
    if errors:
        raise AppContainerError("AppContainer cleanup incomplete: " + "; ".join(errors))
    try:
        journal.unlink()
    except FileNotFoundError:
        pass


def recover_orphans(*, api: _WinAPI | None = None,
                    state_root: str | os.PathLike[str] | None = None) -> None:
    """Recover every stale journal.  Caller must hold the global lease lock."""
    api = api or _load_api()
    root = Path(state_root) if state_root else Path(_rp.DATA_DIR) / "evidence-appcontainer"
    if not root.exists():
        return
    for journal in sorted(root.glob("lease-*.json")):
        payload = _read_journal(journal)
        _cleanup_lease(api, journal, payload, sid=None, sid_owned_by_profile=False)


def recover_pending(*, api: _WinAPI | None = None,
                    state_root: str | os.PathLike[str] | None = None) -> None:
    """Acquire the global lease lock and recover residue without launching.

    Startup calls this even when the experimental backend opt-in is disabled.
    Recovery therefore cannot be stranded merely because G1.13 returns to its
    default degraded mode after an interrupted opt-in spike.
    """
    api = api or _load_api()
    root = (Path(state_root) if state_root
            else _rp.safe_owned_subdir(_rp.DATA_DIR, "evidence-appcontainer", create=True))
    root.mkdir(parents=True, exist_ok=True)
    with _rp.locked_file(root / "native-run", timeout=5.0):
        recover_orphans(api=api, state_root=root)


def _resolve_executable(argv: list[str], env: dict[str, str]) -> str:
    if not argv or not argv[0]:
        raise AppContainerError("empty AppContainer argv")
    candidate = argv[0]
    if os.path.isabs(candidate) and os.path.isfile(candidate):
        resolved = candidate
    else:
        resolved = shutil.which(candidate, path=env.get("PATH")) or ""
    if not resolved or not os.path.isfile(resolved):
        raise AppContainerError(f"AppContainer executable not found: {candidate}")
    if Path(resolved).suffix.lower() in {".bat", ".cmd", ".ps1"}:
        raise AppContainerError("AppContainer refuses implicit shell/script shims")
    return os.path.realpath(os.path.abspath(resolved))


def _environment_block(env: dict[str, str]) -> ctypes.Array:
    entries = []
    for key in sorted(env, key=str.casefold):
        value = str(env[key])
        if "\x00" in key or "\x00" in value or "=" in key:
            raise AppContainerError(f"invalid environment entry: {key!r}")
        entries.append(f"{key}={value}")
    return ctypes.create_unicode_buffer("\x00".join(entries) + "\x00\x00")


def _make_pipe(api: _WinAPI) -> tuple[HANDLE, HANDLE]:
    read = HANDLE()
    write = HANDLE()
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, 1)
    if not api.kernel32.CreatePipe(ctypes.byref(read), ctypes.byref(write),
                                   ctypes.byref(sa), 0):
        raise _win_error("CreatePipe")
    return read, write


def _make_parent_end_private(api: _WinAPI, handle: HANDLE) -> None:
    if not api.kernel32.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, 0):
        raise _win_error("SetHandleInformation")


def _read_pipe(api: _WinAPI, handle: HANDLE, sink: dict[str, Any], key: str) -> None:
    tail = bytearray()
    error: str | None = None
    try:
        while True:
            chunk = ctypes.create_string_buffer(65536)
            read = DWORD()
            ok = api.kernel32.ReadFile(handle, chunk, len(chunk), ctypes.byref(read), None)
            if not ok:
                code = _last_error()
                if code == ERROR_BROKEN_PIPE:
                    break
                error = str(_win_error(f"ReadFile({key})", code))
                break
            if read.value == 0:
                break
            tail.extend(chunk.raw[:read.value])
            if len(tail) > _STREAM_RETAIN_CAP:
                del tail[:-_STREAM_RETAIN_CAP]
    finally:
        sink[key] = tail.decode("utf-8", errors="replace")
        if error:
            sink[key + "_error"] = error


def _update_attribute(api: _WinAPI, attribute_list: LPVOID, key: int,
                      value: Any, size: int) -> None:
    if not api.kernel32.UpdateProcThreadAttribute(
            attribute_list, 0, key, ctypes.cast(value, LPVOID), size, None, None):
        raise _win_error(f"UpdateProcThreadAttribute(0x{key:x})")


def _launch(api: _WinAPI, argv: list[str], *, executable: str, cwd: str,
            env: dict[str, str], timeout: int, sid: LPVOID) -> SandboxResult:
    """Create and supervise one AppContainer process via inherited stdio."""
    handles: list[HANDLE] = []
    attribute_list = LPVOID()
    attribute_initialized = False
    process_created = False
    resumed = False
    timed_out = False
    job = HANDLE()
    proc = PROCESS_INFORMATION()
    stdout_state: dict[str, Any] = {}
    reader_threads: list[threading.Thread] = []

    stdin_read = stdin_write = HANDLE()
    stdout_read = stdout_write = HANDLE()
    stderr_read = stderr_write = HANDLE()
    try:
        stdin_read, stdin_write = _make_pipe(api)
        handles += [stdin_read, stdin_write]
        stdout_read, stdout_write = _make_pipe(api)
        handles += [stdout_read, stdout_write]
        stderr_read, stderr_write = _make_pipe(api)
        handles += [stderr_read, stderr_write]
        for parent_end in (stdin_write, stdout_read, stderr_read):
            _make_parent_end_private(api, parent_end)

        job = api.kernel32.CreateJobObjectW(None, None)
        if not job:
            raise _win_error("CreateJobObjectW")
        handles.append(job)
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        )
        if not api.kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation, ctypes.byref(limits),
                ctypes.sizeof(limits)):
            raise _win_error("SetInformationJobObject")

        needed = SIZE_T()
        first = api.kernel32.InitializeProcThreadAttributeList(None, 3, 0,
                                                               ctypes.byref(needed))
        if first or _last_error() != ERROR_INSUFFICIENT_BUFFER or not needed.value:
            raise AppContainerError(
                "InitializeProcThreadAttributeList sizing did not return "
                "ERROR_INSUFFICIENT_BUFFER")
        attribute_buffer = ctypes.create_string_buffer(needed.value)
        attribute_list = ctypes.cast(attribute_buffer, LPVOID)
        if not api.kernel32.InitializeProcThreadAttributeList(
                attribute_list, 3, 0, ctypes.byref(needed)):
            raise _win_error("InitializeProcThreadAttributeList")
        attribute_initialized = True

        capabilities = SECURITY_CAPABILITIES(sid, None, 0, 0)
        child_handles = (HANDLE * 3)(stdin_read, stdout_write, stderr_write)
        job_handles = (HANDLE * 1)(job)
        _update_attribute(api, attribute_list,
                          PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                          ctypes.byref(capabilities), ctypes.sizeof(capabilities))
        _update_attribute(api, attribute_list, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                          child_handles, ctypes.sizeof(child_handles))
        _update_attribute(api, attribute_list, PROC_THREAD_ATTRIBUTE_JOB_LIST,
                          job_handles, ctypes.sizeof(job_handles))

        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = stdin_read
        startup.StartupInfo.hStdOutput = stdout_write
        startup.StartupInfo.hStdError = stderr_write
        startup.lpAttributeList = attribute_list
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        environment = _environment_block(env)
        flags = (EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
                 | CREATE_SUSPENDED | CREATE_NO_WINDOW)
        if not api.kernel32.CreateProcessW(
                executable, command_line, None, None, 1, flags,
                ctypes.cast(environment, LPVOID), cwd,
                ctypes.cast(ctypes.byref(startup), ctypes.POINTER(STARTUPINFOW)),
                ctypes.byref(proc)):
            raise _win_error("CreateProcessW(AppContainer)")
        process_created = True
        handles += [proc.hProcess, proc.hThread]

        # Parent closes its copies of child-only ends immediately.  This and the
        # HANDLE_LIST attribute make inherited stdio the only result channel.
        for child_end in (stdin_read, stdout_write, stderr_write):
            _close(api, child_end)
            handles.remove(child_end)

        for key, pipe in (("stdout", stdout_read), ("stderr", stderr_read)):
            thread = threading.Thread(target=_read_pipe,
                                      args=(api, pipe, stdout_state, key), daemon=True)
            thread.start()
            reader_threads.append(thread)

        if api.kernel32.ResumeThread(proc.hThread) == 0xFFFFFFFF:
            raise _win_error("ResumeThread")
        resumed = True
        _close(api, proc.hThread)
        handles.remove(proc.hThread)
        _close(api, stdin_write)  # EOF: evidence checks receive no interactive input.
        handles.remove(stdin_write)

        timeout_ms = max(1, min(int(timeout * 1000), 0xFFFFFFFE))
        wait = api.kernel32.WaitForSingleObject(proc.hProcess, timeout_ms)
        timed_out = wait == WAIT_TIMEOUT
        if wait not in (WAIT_OBJECT_0, WAIT_TIMEOUT):
            raise _win_error("WaitForSingleObject")
        if timed_out:
            if not api.kernel32.TerminateJobObject(job, 124):
                raise _win_error("TerminateJobObject(timeout)")
            if api.kernel32.WaitForSingleObject(proc.hProcess, 5000) != WAIT_OBJECT_0:
                raise AppContainerError("timed-out AppContainer process did not terminate")
        exit_code = DWORD(STILL_ACTIVE)
        if not api.kernel32.GetExitCodeProcess(proc.hProcess, ctypes.byref(exit_code)):
            raise _win_error("GetExitCodeProcess")
        # Primary exit does not imply descendants exited.  Kill the job so inherited
        # stdout/stderr writers cannot keep the pipes open forever.
        if not api.kernel32.TerminateJobObject(job, 0):
            raise _win_error("TerminateJobObject(descendants)")
        for thread in reader_threads:
            thread.join(timeout=5)
        for pipe in (stdout_read, stderr_read):
            _close(api, pipe)
            if pipe in handles:
                handles.remove(pipe)
        for thread in reader_threads:
            thread.join(timeout=1)
        if any(thread.is_alive() for thread in reader_threads):
            raise AppContainerError("inherited stdio pipes did not close after Job termination")

        errors = [stdout_state.get("stdout_error"), stdout_state.get("stderr_error")]
        error = "; ".join(item for item in errors if item) or None
        code = None if timed_out or exit_code.value == STILL_ACTIVE else int(exit_code.value)
        return SandboxResult(
            started=True, returncode=code,
            stdout=stdout_state.get("stdout", ""),
            stderr=stdout_state.get("stderr", ""),
            timed_out=timed_out, error=error,
        )
    except Exception as exc:
        if process_created:
            try:
                api.kernel32.TerminateJobObject(job, 125)
                api.kernel32.WaitForSingleObject(proc.hProcess, 5000)
            except Exception:
                pass
        if resumed:
            for thread in reader_threads:
                thread.join(timeout=2)
            return SandboxResult(
                started=True, returncode=1,
                stdout=stdout_state.get("stdout", ""),
                stderr=stdout_state.get("stderr", ""),
                timed_out=timed_out, error=str(exc),
            )
        raise
    finally:
        if attribute_initialized:
            try:
                api.kernel32.DeleteProcThreadAttributeList(attribute_list)
            except Exception:
                pass
        # Job closes after process and pipe handles; kill-on-close remains armed.
        for handle in reversed(handles):
            _close(api, handle)


def _runtime_acl_roots(executable: str) -> list[str]:
    """Return user-owned install roots that need a temporary RX ACE."""
    roots: list[str] = []
    executable_path = Path(executable).resolve(strict=False)
    for candidate in (Path(sys.base_prefix), Path(sys.exec_prefix), executable_path.parent):
        try:
            rel = executable_path.relative_to(candidate.resolve(strict=False))
        except ValueError:
            continue
        if rel.parts and _allowed_journal_path(str(candidate)):
            roots.append(str(candidate))
    if not roots and _allowed_journal_path(str(executable_path.parent)):
        roots.append(str(executable_path.parent))
    return roots


def run(argv: list[str], *, cwd: str, env: dict[str, str], timeout: int,
        readonly_roots: Iterable[str] = (), writable_roots: Iterable[str] = (),
        api: _WinAPI | None = None,
        state_root: str | os.PathLike[str] | None = None) -> SandboxResult:
    """Run one process in an ephemeral zero-capability AppContainer.

    A pre-resume error raises :class:`AppContainerError` and therefore carries no
    enforcement claim.  Once resumed, the returned result has ``started=True``;
    callers may honestly record orchestrated execution even when the child exits
    non-zero or times out.
    """
    api = api or _load_api()
    root = (Path(state_root) if state_root
            else _rp.safe_owned_subdir(_rp.DATA_DIR, "evidence-appcontainer", create=True))
    root.mkdir(parents=True, exist_ok=True)
    lock_target = root / "native-run"

    # One native lease at a time.  A crashed process releases the OS lock; the next
    # holder can then distinguish every journal as stale without PID/mutex races.
    with _rp.locked_file(lock_target, timeout=5.0):
        recover_orphans(api=api, state_root=root)
        executable = _resolve_executable(list(argv), env)
        resolved_cwd = _canonical_existing(cwd)
        entries: list[tuple[str, bool]] = [(resolved_cwd, False)]
        entries += [(os.fspath(item), False) for item in readonly_roots]
        entries += [(os.fspath(item), True) for item in writable_roots]
        entries += [(item, False) for item in _runtime_acl_roots(executable)]
        grants = _dedupe_paths(entries)
        _validate_grants(grants)
        _validate_grant_boundaries(grants, root)

        profile = _PROFILE_PREFIX + uuid.uuid4().hex
        if len(profile) > 64:  # defensive; current prefix + UUID is 45 chars.
            raise AppContainerError("generated AppContainer profile exceeds 64 characters")
        journal = root / f"lease-{profile.removeprefix(_PROFILE_PREFIX)}.json"
        payload: dict[str, Any] = {
            "version": _JOURNAL_VERSION,
            "profile": profile,
            "sid": None,
            "grants_started": False,
            "grants": grants,
        }
        # Write-ahead record before profile creation, not merely before ACL grants.
        _write_journal(journal, payload)
        sid = LPVOID()
        result: SandboxResult | None = None
        primary_error: Exception | None = None
        try:
            sid = _create_profile(api, profile)
            payload["sid"] = _sid_text(api, sid)
            payload["grants_started"] = True
            _write_journal(journal, payload)  # durable before the first grant
            for item in grants:
                _acl_entry(api, item["path"], sid, grant=True,
                           writable=item["writable"])
            result = _launch(api, list(argv), executable=executable,
                             cwd=resolved_cwd, env=env, timeout=timeout, sid=sid)
        except _ProfileCollision:
            # The collision is vanishingly unlikely, but an existing profile is
            # not ours.  Remove only our still-pre-mutation journal and refuse.
            try:
                journal.unlink()
            except FileNotFoundError:
                pass
            raise
        except Exception as exc:
            primary_error = exc

        cleanup_error: Exception | None = None
        try:
            _cleanup_lease(api, journal, payload, sid=sid,
                           sid_owned_by_profile=True)
            sid = LPVOID()  # ownership consumed by cleanup
        except Exception as exc:
            cleanup_error = exc

        if primary_error is not None:
            if cleanup_error is not None:
                raise AppContainerError(
                    f"{primary_error}; additionally {cleanup_error}") from primary_error
            raise primary_error
        if result is None:
            raise AppContainerError("AppContainer launch produced no result")
        if cleanup_error is not None:
            result.cleanup_error = str(cleanup_error)
            result.error = "; ".join(filter(None, [result.error, result.cleanup_error]))
            result.returncode = result.returncode if result.returncode not in (0, None) else 1
        return result


__all__ = [
    "AppContainerError", "AppContainerUnavailable", "SandboxResult",
    "available", "recover_orphans", "recover_pending", "run",
]
