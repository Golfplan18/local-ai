"""Cross-platform contract tests for the native Windows AppContainer runner.

These tests validate ctypes ABI, launch marshaling, inherited stdio, Job Object
ordering, SID-specific ACLs, and durable recovery on macOS/Linux CI.  They do not
claim kernel isolation; ``test_windows_appcontainer_live.py`` is the mandatory
Windows target-machine proof.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401

import windows_appcontainer as wac  # noqa: E402
import platform_check as pc  # noqa: E402


class _Fn:
    def __init__(self, callback=None, default=1):
        self.callback = callback
        self.default = default
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args) if self.callback else self.default


class _DLL:
    def __init__(self):
        self._functions = {}

    def __getattr__(self, name):
        if name not in self._functions:
            self._functions[name] = _Fn()
        return self._functions[name]


def _set_void(pointer, value):
    ctypes.cast(pointer, ctypes.POINTER(wac.LPVOID))[0] = wac.LPVOID(value)


def _set_dword(pointer, value):
    ctypes.cast(pointer, ctypes.POINTER(wac.DWORD))[0] = wac.DWORD(value)


class TestABI(unittest.TestCase):
    def test_fixed_width_structure_sizes_on_64_bit(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("64-bit ABI assertions")
        self.assertEqual(ctypes.sizeof(wac.SECURITY_CAPABILITIES), 24)
        self.assertEqual(ctypes.sizeof(wac.STARTUPINFOW), 104)
        self.assertEqual(ctypes.sizeof(wac.STARTUPINFOEXW), 112)
        self.assertEqual(ctypes.sizeof(wac.PROCESS_INFORMATION), 24)
        self.assertEqual(ctypes.sizeof(wac.JOBOBJECT_BASIC_LIMIT_INFORMATION), 64)
        self.assertEqual(ctypes.sizeof(wac.IO_COUNTERS), 48)
        self.assertEqual(ctypes.sizeof(wac.JOBOBJECT_EXTENDED_LIMIT_INFORMATION), 144)

    def test_required_dlls_and_signatures_are_declared_lazily(self):
        dlls = {name: _DLL() for name in ("kernel32", "advapi32", "userenv")}

        def loader(name, *, use_last_error):
            self.assertTrue(use_last_error)
            return dlls[name]

        # Import already succeeded on POSIX; only this explicit construction is
        # allowed to ask for WinDLL.
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.object(os, "name", "nt"), \
             mock.patch.object(wac.ctypes, "WinDLL", loader, create=True):
            api = wac._WinAPI()
        self.assertIs(api.kernel32, dlls["kernel32"])
        create = dlls["userenv"].CreateAppContainerProfile
        self.assertIs(create.restype, wac.HRESULT)
        self.assertEqual(create.argtypes[-1], ctypes.POINTER(wac.LPVOID))
        update = dlls["kernel32"].UpdateProcThreadAttribute
        self.assertEqual(update.argtypes[2], wac.ULONG_PTR)
        self.assertEqual(update.argtypes[4], wac.SIZE_T)
        get_acl = dlls["advapi32"].GetNamedSecurityInfoW
        self.assertIs(get_acl.restype, wac.DWORD)

    def test_non_windows_available_never_loads_api(self):
        with mock.patch.object(wac, "_load_api", side_effect=AssertionError("loaded")), \
             mock.patch.object(sys, "platform", "darwin"):
            self.assertFalse(wac.available())

    def test_security_and_job_constants_are_exact(self):
        self.assertEqual(wac.PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, 0x00020009)
        self.assertEqual(wac.PROC_THREAD_ATTRIBUTE_HANDLE_LIST, 0x00020002)
        self.assertEqual(wac.PROC_THREAD_ATTRIBUTE_JOB_LIST, 0x0002000D)
        self.assertEqual(wac.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, 0x2000)
        caps = wac.SECURITY_CAPABILITIES(wac.LPVOID(123), None, 0, 0)
        self.assertEqual(caps.AppContainerSid, 123)
        self.assertFalse(caps.Capabilities)
        self.assertEqual(caps.CapabilityCount, 0)
        self.assertEqual(caps.Reserved, 0)


class TestStartupRecovery(unittest.TestCase):
    def test_windows_startup_recovers_without_execution_opt_in(self):
        module = types.SimpleNamespace(recover_pending=mock.Mock())
        with mock.patch.object(pc, "detect_platform", return_value={
                "os": "Windows", "arch": "AMD64", "apple_silicon": False,
                "recommended_engine": "ollama"}), \
             mock.patch.object(pc.os.path, "exists", return_value=False), \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORA_WINDOWS_APPCONTAINER", None)
            pc.startup_check()
        module.recover_pending.assert_called_once_with()

    def test_windows_startup_surfaces_recovery_failure_without_crashing(self):
        module = types.SimpleNamespace(
            recover_pending=mock.Mock(side_effect=RuntimeError("revoke failed")))
        with mock.patch.object(pc, "detect_platform", return_value={
                "os": "Windows", "arch": "AMD64", "apple_silicon": False,
                "recommended_engine": "ollama"}), \
             mock.patch.object(pc.os.path, "exists", return_value=False), \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}):
            messages = pc.startup_check()
        self.assertTrue(any("AppContainer recovery failed" in item for item in messages))

    def test_non_windows_startup_does_not_touch_appcontainer(self):
        module = types.SimpleNamespace(recover_pending=mock.Mock())
        with mock.patch.object(pc, "detect_platform", return_value={
                "os": "Darwin", "arch": "arm64", "apple_silicon": True,
                "recommended_engine": "mlx"}), \
             mock.patch.object(pc.os.path, "exists", return_value=False), \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}):
            pc.startup_check()
        module.recover_pending.assert_not_called()


class TestMarshaling(unittest.TestCase):
    def test_unicode_environment_is_double_nul_terminated(self):
        block = wac._environment_block({"z": "last", "A": "first"})
        value = "".join(block)
        self.assertTrue(value.startswith("A=first\x00z=last\x00"))
        self.assertTrue(value.endswith("\x00\x00"))

    def test_resolve_executable_rejects_implicit_shell_shim(self):
        root = Path(tempfile.mkdtemp())
        try:
            shim = root / "tool.cmd"
            shim.write_text("echo no", encoding="utf-8")
            with self.assertRaisesRegex(wac.AppContainerError, "implicit shell"):
                wac._resolve_executable([str(shim)], {"PATH": str(root)})
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _launch_api(self, *, wait_result=wac.WAIT_OBJECT_0):
        events = []
        captures = {"attributes": []}
        kernel = _DLL()
        advapi = _DLL()
        userenv = _DLL()
        next_handle = iter(range(10, 30))

        def create_pipe(read_ptr, write_ptr, _sa, _size):
            _set_void(read_ptr, next(next_handle))
            _set_void(write_ptr, next(next_handle))
            return 1

        def create_job(_sa, _name):
            events.append("create_job")
            return 90

        def set_job(_job, _kind, info_ptr, size):
            events.append("set_job")
            info = ctypes.cast(
                info_ptr, ctypes.POINTER(wac.JOBOBJECT_EXTENDED_LIMIT_INFORMATION)).contents
            captures["job_flags"] = info.BasicLimitInformation.LimitFlags
            captures["job_size"] = size
            return 1

        def init_attributes(pointer, count, _flags, size_ptr):
            captures.setdefault("attribute_counts", []).append(count)
            if not pointer:
                ctypes.cast(size_ptr, ctypes.POINTER(wac.SIZE_T))[0] = wac.SIZE_T(256)
                return 0
            events.append("init_attributes")
            return 1

        def update_attribute(_list, _flags, key, value, size, _prev, _returned):
            captures["attributes"].append((key, size))
            if key == wac.PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES:
                caps = ctypes.cast(
                    value, ctypes.POINTER(wac.SECURITY_CAPABILITIES)).contents
                captures["sid"] = caps.AppContainerSid
                captures["capability_count"] = caps.CapabilityCount
            elif key == wac.PROC_THREAD_ATTRIBUTE_HANDLE_LIST:
                handles = ctypes.cast(value, ctypes.POINTER(wac.HANDLE * 3)).contents
                captures["handle_list"] = [item for item in handles]
            elif key == wac.PROC_THREAD_ATTRIBUTE_JOB_LIST:
                jobs = ctypes.cast(value, ctypes.POINTER(wac.HANDLE * 1)).contents
                captures["job_list"] = [item for item in jobs]
            return 1

        def create_process(app, _cmd, _pa, _ta, inherit, flags, _env, cwd,
                           startup_ptr, proc_ptr):
            events.append("create_process")
            startup = ctypes.cast(
                startup_ptr, ctypes.POINTER(wac.STARTUPINFOEXW)).contents
            captures.update({
                "application": app,
                "inherit": inherit,
                "flags": flags,
                "cwd": cwd,
                "startup_cb": startup.StartupInfo.cb,
                "startup_flags": startup.StartupInfo.dwFlags,
                "stdio": [startup.StartupInfo.hStdInput,
                          startup.StartupInfo.hStdOutput,
                          startup.StartupInfo.hStdError],
            })
            proc = ctypes.cast(proc_ptr, ctypes.POINTER(wac.PROCESS_INFORMATION))
            proc.contents.hProcess = wac.HANDLE(70)
            proc.contents.hThread = wac.HANDLE(71)
            return 1

        waits = iter([wait_result, wac.WAIT_OBJECT_0])

        def wait(_handle, _timeout):
            return next(waits, wac.WAIT_OBJECT_0)

        def resume(_thread):
            events.append("resume")
            return 1

        def read_file(_handle, _buffer, _size, read_ptr, _overlapped):
            _set_dword(read_ptr, 0)
            return 1

        def get_exit(_process, code_ptr):
            _set_dword(code_ptr, 124 if wait_result == wac.WAIT_TIMEOUT else 0)
            return 1

        def terminate(_job, code):
            events.append(("terminate_job", code))
            return 1

        kernel.CreatePipe = _Fn(create_pipe)
        kernel.SetHandleInformation = _Fn(default=1)
        kernel.CreateJobObjectW = _Fn(create_job)
        kernel.SetInformationJobObject = _Fn(set_job)
        kernel.InitializeProcThreadAttributeList = _Fn(init_attributes)
        kernel.UpdateProcThreadAttribute = _Fn(update_attribute)
        kernel.DeleteProcThreadAttributeList = _Fn(default=None)
        kernel.CreateProcessW = _Fn(create_process)
        kernel.ResumeThread = _Fn(resume)
        kernel.WaitForSingleObject = _Fn(wait)
        kernel.ReadFile = _Fn(read_file)
        kernel.GetExitCodeProcess = _Fn(get_exit)
        kernel.TerminateJobObject = _Fn(terminate)
        kernel.CloseHandle = _Fn(default=1)
        api = types.SimpleNamespace(kernel32=kernel, advapi32=advapi, userenv=userenv)
        return api, events, captures

    def test_launch_uses_zero_capabilities_exact_handles_job_and_stdio(self):
        api, events, captured = self._launch_api()
        logged = io.StringIO()
        with redirect_stderr(logged), \
             mock.patch.object(wac, "_last_error", return_value=wac.ERROR_INSUFFICIENT_BUFFER):
            result = wac._launch(
                api, [r"C:\Python\python.exe", "-c", "print('ok')"],
                executable=r"C:\Python\python.exe", cwd=r"C:\repo",
                env={"TEMP": r"C:\scratch"}, timeout=5, sid=wac.LPVOID(1234))
        self.assertTrue(result.started)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured["attribute_counts"], [3, 3])
        self.assertEqual({key for key, _ in captured["attributes"]}, {
            wac.PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            wac.PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            wac.PROC_THREAD_ATTRIBUTE_JOB_LIST,
        })
        self.assertEqual(captured["sid"], 1234)
        self.assertEqual(captured["capability_count"], 0)
        self.assertEqual(captured["handle_list"], captured["stdio"])
        self.assertEqual(captured["job_list"], [90])
        self.assertTrue(captured["inherit"])
        self.assertEqual(captured["startup_cb"], ctypes.sizeof(wac.STARTUPINFOEXW))
        self.assertEqual(captured["startup_flags"], wac.STARTF_USESTDHANDLES)
        self.assertEqual(
            captured["flags"],
            wac.EXTENDED_STARTUPINFO_PRESENT | wac.CREATE_UNICODE_ENVIRONMENT
            | wac.CREATE_SUSPENDED | wac.CREATE_NO_WINDOW,
        )
        self.assertLess(events.index("set_job"), events.index("create_process"))
        self.assertLess(events.index("create_process"), events.index("resume"))
        self.assertEqual(
            captured["job_flags"],
            wac.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | wac.JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION,
        )
        self.assertIn("INFO: engaged job=0x5a", logged.getvalue())

    def test_timeout_terminates_entire_job(self):
        api, events, _captured = self._launch_api(wait_result=wac.WAIT_TIMEOUT)
        with mock.patch.object(wac, "_last_error", return_value=wac.ERROR_INSUFFICIENT_BUFFER):
            result = wac._launch(
                api, [r"C:\Python\python.exe"], executable=r"C:\Python\python.exe",
                cwd=r"C:\repo", env={}, timeout=1, sid=wac.LPVOID(1234))
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.returncode)
        self.assertIn(("terminate_job", 124), events)


class TestACLAndRecovery(unittest.TestCase):
    def _home_tree(self):
        return Path(tempfile.mkdtemp(prefix="wac-test-", dir=str(Path.home())))

    def test_acl_uses_exact_profile_sid_and_frees_native_buffers(self):
        root = self._home_tree()
        seen = {}
        freed = []
        advapi = _DLL()
        kernel = _DLL()

        def get_info(_path, _kind, _flags, _owner, _group, dacl, _sacl, descriptor):
            _set_void(dacl, 11)
            _set_void(descriptor, 12)
            return 0

        def set_entries(_count, entry_ptr, _old, new_acl):
            entry = ctypes.cast(entry_ptr, ctypes.POINTER(wac.EXPLICIT_ACCESSW)).contents
            seen.update({
                "sid": entry.Trustee.ptstrName,
                "form": entry.Trustee.TrusteeForm,
                "mode": entry.grfAccessMode,
                "mask": entry.grfAccessPermissions,
                "inheritance": entry.grfInheritance,
            })
            _set_void(new_acl, 13)
            return 0

        advapi.GetNamedSecurityInfoW = _Fn(get_info)
        advapi.SetEntriesInAclW = _Fn(set_entries)
        advapi.SetNamedSecurityInfoW = _Fn(default=0)
        kernel.LocalFree = _Fn(lambda ptr: freed.append(ptr.value) or None)
        api = types.SimpleNamespace(advapi32=advapi, kernel32=kernel)
        try:
            wac._acl_entry(api, str(root), wac.LPVOID(0x123456), grant=True,
                           writable=False)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertEqual(seen["sid"], 0x123456)
        self.assertEqual(seen["form"], wac.TRUSTEE_IS_SID)
        self.assertEqual(seen["mode"], wac.GRANT_ACCESS)
        self.assertEqual(seen["mask"], wac.READ_EXECUTE_MASK)
        self.assertEqual(seen["inheritance"],
                         wac.OBJECT_INHERIT_ACE | wac.CONTAINER_INHERIT_ACE)
        self.assertCountEqual(freed, [13, 12])

    def test_grant_cannot_engulf_sensitive_or_recovery_root(self):
        parent = self._home_tree()
        grants = [{"path": str(parent), "writable": False}]
        try:
            with mock.patch.object(wac._rp, "DATA_DIR", parent / "private-data"):
                with self.assertRaisesRegex(wac.AppContainerError, "sensitive root"):
                    wac._validate_grant_boundaries(grants, parent / "state")
            with mock.patch.object(wac._rp, "DATA_DIR", Path.home() / "unrelated-data"):
                with self.assertRaisesRegex(wac.AppContainerError, "crash-recovery"):
                    wac._validate_grant_boundaries(
                        [{"path": str(parent), "writable": True}], parent / "state")
        finally:
            shutil.rmtree(parent, ignore_errors=True)

    def _fake_api(self, events):
        advapi = _DLL()
        advapi.FreeSid = _Fn(lambda sid: events.append(("free_sid", sid.value)) or None)
        return types.SimpleNamespace(advapi32=advapi, kernel32=_DLL(), userenv=_DLL())

    def test_write_ahead_journal_precedes_grants_and_cleanup_is_reverse_order(self):
        repo = self._home_tree()
        scratch = repo / "scratch"
        scratch.mkdir()
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        events = []
        api = self._fake_api(events)
        original_write = wac._write_journal
        original_log = wac._log

        def write(path, payload):
            events.append(("journal", payload["grants_started"]))
            original_write(path, payload)

        def acl(_api, path, _sid, *, grant, writable):
            events.append(("grant" if grant else "revoke", path, writable))

        def log(level, message):
            events.append(("log", level, message))
            original_log(level, message)

        try:
            logged = io.StringIO()
            with redirect_stderr(logged), \
                 mock.patch.object(wac, "_resolve_executable", return_value=sys.executable), \
                 mock.patch.object(wac, "_runtime_acl_roots", return_value=[]), \
                 mock.patch.object(wac, "_create_profile",
                                   side_effect=lambda _a, _n: events.append("profile") or wac.LPVOID(44)), \
                 mock.patch.object(wac, "_sid_text", return_value="S-1-15-2-44"), \
                 mock.patch.object(wac, "_write_journal", side_effect=write), \
                 mock.patch.object(wac, "_log", side_effect=log), \
                 mock.patch.object(wac, "_acl_entry", side_effect=acl), \
                 mock.patch.object(wac, "_delete_profile",
                                   side_effect=lambda _a, _n: events.append("delete_profile")), \
                 mock.patch.object(wac, "_launch",
                                   return_value=wac.SandboxResult(True, 0, "ok", "")):
                result = wac.run(
                    [sys.executable, "-c", "pass"], cwd=str(repo), env={"PATH": ""},
                    timeout=5, readonly_roots=[str(repo)],
                    writable_roots=[str(scratch)], api=api, state_root=state)
            self.assertEqual(result.returncode, 0)
            self.assertIn("INFO: engaged profile=ora.evidence.", logged.getvalue())
            self.assertIn("sid=S-1-15-2-44", logged.getvalue())
            first_grant = next(i for i, item in enumerate(events)
                               if isinstance(item, tuple) and item[0] == "grant")
            started_journal = events.index(("journal", True))
            profile_log = next(i for i, item in enumerate(events)
                               if isinstance(item, tuple) and item[:2] == ("log", "INFO"))
            self.assertLess(started_journal, profile_log)
            self.assertLess(profile_log, first_grant)
            grants = [item[1] for item in events
                      if isinstance(item, tuple) and item[0] == "grant"]
            revokes = [item[1] for item in events
                       if isinstance(item, tuple) and item[0] == "revoke"]
            self.assertEqual(revokes, list(reversed(grants)))
            self.assertEqual(list(state.glob("lease-*.json")), [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_stale_recovery_failure_retains_journal_and_blocks_progress(self):
        repo = self._home_tree()
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        journal = state / "lease-deadbeef.json"
        payload = {
            "version": 1,
            "profile": "ora.evidence.deadbeef",
            "sid": "S-1-15-2-44",
            "grants_started": True,
            "grants": [{"path": str(repo), "writable": False}],
        }
        wac._write_journal(journal, payload)
        events = []
        api = self._fake_api(events)
        try:
            with mock.patch.object(wac, "_derive_profile_sid", return_value=wac.LPVOID(44)), \
                 mock.patch.object(wac, "_sid_text", return_value="S-1-15-2-44"), \
                 mock.patch.object(wac, "_acl_entry", side_effect=OSError("revoke failed")), \
                 mock.patch.object(wac, "_delete_profile") as delete_profile:
                with self.assertRaisesRegex(wac.AppContainerError, "cleanup incomplete"):
                    wac.recover_orphans(api=api, state_root=state)
            self.assertTrue(journal.exists())
            delete_profile.assert_not_called()  # preserve SID derivation for retry
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_recovery_uses_journaled_sid_if_profile_state_is_indeterminate(self):
        repo = self._home_tree()
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        journal = state / "lease-deadbeef.json"
        payload = {
            "version": 1,
            "profile": "ora.evidence.deadbeef",
            "sid": "S-1-15-2-44",
            "grants_started": True,
            "grants": [{"path": str(repo), "writable": False}],
        }
        wac._write_journal(journal, payload)
        events = []
        api = self._fake_api(events)
        api.kernel32.LocalFree = _Fn(lambda sid: events.append(("local_free", sid.value)))
        try:
            with mock.patch.object(wac, "_derive_profile_sid",
                                   side_effect=wac.AppContainerError("profile absent")), \
                 mock.patch.object(wac, "_sid_from_text", return_value=wac.LPVOID(55)), \
                 mock.patch.object(wac, "_sid_text", return_value="S-1-15-2-44"), \
                 mock.patch.object(wac, "_acl_entry",
                                   side_effect=lambda *_a, **_k: events.append("revoke")), \
                 mock.patch.object(wac, "_delete_profile",
                                   side_effect=lambda *_a: events.append("delete")):
                wac.recover_orphans(api=api, state_root=state)
            self.assertIn("revoke", events)
            self.assertIn("delete", events)
            self.assertIn(("local_free", 55), events)
            self.assertFalse(journal.exists())
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_recovery_treats_a_removed_grant_root_as_already_clean(self):
        vanished = self._home_tree()
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        journal = state / "lease-deadbeef.json"
        payload = {
            "version": 1,
            "profile": "ora.evidence.deadbeef",
            "sid": "S-1-15-2-44",
            "grants_started": True,
            "grants": [{"path": str(vanished), "writable": True}],
        }
        wac._write_journal(journal, payload)
        shutil.rmtree(vanished)
        events = []
        api = self._fake_api(events)
        try:
            with mock.patch.object(wac, "_derive_profile_sid", return_value=wac.LPVOID(44)), \
                 mock.patch.object(wac, "_sid_text", return_value="S-1-15-2-44"), \
                 mock.patch.object(wac, "_delete_profile"):
                wac.recover_orphans(api=api, state_root=state)
            self.assertFalse(journal.exists())
        finally:
            shutil.rmtree(state, ignore_errors=True)

    def test_pregrant_journal_cleans_when_profile_is_missing_or_exists(self):
        # grants_started=False spans both sides of profile creation.  In either
        # state there are no ACLs, but an existing profile still must be deleted.
        for status in (0, ctypes.c_int32(0x80070490).value):
            with self.subTest(status=status):
                state = Path(tempfile.mkdtemp(prefix="wac-state-"))
                journal = state / "lease-deadbeef.json"
                journal.write_text("planned", encoding="utf-8")
                userenv = _DLL()
                userenv.DeleteAppContainerProfile = _Fn(default=status)
                api = types.SimpleNamespace(
                    userenv=userenv, advapi32=_DLL(), kernel32=_DLL())
                payload = {
                    "version": 1,
                    "profile": "ora.evidence.deadbeef",
                    "sid": None,
                    "grants_started": False,
                    "grants": [],
                }
                try:
                    wac._cleanup_lease(
                        api, journal, payload, sid=None,
                        sid_owned_by_profile=False)
                    self.assertFalse(journal.exists())
                finally:
                    shutil.rmtree(state, ignore_errors=True)

    def test_pregrant_profile_delete_failure_retains_journal(self):
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        journal = state / "lease-deadbeef.json"
        journal.write_text("planned", encoding="utf-8")
        userenv = _DLL()
        userenv.DeleteAppContainerProfile = _Fn(
            default=ctypes.c_int32(0x80070005).value)
        api = types.SimpleNamespace(
            userenv=userenv, advapi32=_DLL(), kernel32=_DLL())
        payload = {
            "version": 1,
            "profile": "ora.evidence.deadbeef",
            "sid": None,
            "grants_started": False,
            "grants": [],
        }
        try:
            with self.assertRaisesRegex(wac.AppContainerError, "cleanup incomplete"):
                wac._cleanup_lease(
                    api, journal, payload, sid=None,
                    sid_owned_by_profile=False)
            self.assertTrue(journal.exists())
        finally:
            shutil.rmtree(state, ignore_errors=True)

    def test_corrupt_journal_does_not_block_later_valid_recovery(self):
        repo = self._home_tree()
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        corrupt = state / "lease-0000.json"
        valid = state / "lease-1111.json"
        corrupt.write_text("{not-json", encoding="utf-8")
        wac._write_journal(valid, {
            "version": 1,
            "profile": "ora.evidence.1111",
            "sid": None,
            "grants_started": False,
            "grants": [{"path": str(repo), "writable": False}],
        })
        api = self._fake_api([])
        logged = io.StringIO()
        try:
            with redirect_stderr(logged), \
                 mock.patch.object(wac, "_delete_profile") as delete_profile:
                with self.assertRaisesRegex(
                        wac.AppContainerError, "orphan recovery incomplete"):
                    wac.recover_orphans(api=api, state_root=state)
            self.assertTrue(corrupt.exists())
            self.assertFalse(valid.exists())
            delete_profile.assert_called_once_with(
                api, "ora.evidence.1111", missing_ok=True)
            self.assertIn("journal=lease-0000.json recovery failed", logged.getvalue())
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_tampered_journal_cannot_revoke_outside_contained_roots(self):
        state = Path(tempfile.mkdtemp(prefix="wac-state-"))
        journal = state / "lease-deadbeef.json"
        journal.write_text(json.dumps({
            "version": 1,
            "profile": "ora.evidence.deadbeef",
            "sid": "S-1-15-2-44",
            "grants_started": True,
            "grants": [{"path": "/etc", "writable": False}],
        }), encoding="utf-8")
        try:
            with self.assertRaisesRegex(wac.AppContainerError, "outside contained"):
                wac._read_journal(journal)
        finally:
            shutil.rmtree(state, ignore_errors=True)

    def test_unexpected_profile_collision_never_reuses_or_deletes_profile(self):
        create = _Fn(default=ctypes.c_int32(0x800700B7).value)
        userenv = _DLL()
        userenv.CreateAppContainerProfile = create
        api = types.SimpleNamespace(userenv=userenv)
        with self.assertRaises(wac._ProfileCollision):
            wac._create_profile(api, "ora.evidence.deadbeef")


if __name__ == "__main__":
    unittest.main()
