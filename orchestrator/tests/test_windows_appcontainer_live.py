"""Mandatory Windows 11 live-fire acceptance for the D-02 sandbox spike.

This suite skips only when the host is not Windows.  On Windows, missing APIs,
an unreadable user-installed runtime, socket access, stdio breakage, Job Object
failure, or stale ACL/profile recovery failure is a real test failure—not green
by omission.  The G1.13 install attempt must run this file before the native
backend is considered validated on the target image.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401

import evidence_runner as er  # noqa: E402
import windows_appcontainer as wac  # noqa: E402


def _dacl_sddl(path: Path) -> str:
    """Return the exact DACL SDDL so a live test can detect a residual SID ACE."""
    api = wac._load_api()
    advapi, kernel = api.advapi32, api.kernel32
    convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [wac.LPVOID, wac.DWORD, wac.DWORD,
                        ctypes.POINTER(wac.LPWSTR), ctypes.POINTER(wac.DWORD)]
    convert.restype = wac.BOOL
    descriptor = wac.LPVOID()
    status = advapi.GetNamedSecurityInfoW(
        str(path), wac.SE_FILE_OBJECT, wac.DACL_SECURITY_INFORMATION,
        None, None, None, None, ctypes.byref(descriptor))
    if status:
        raise OSError(status, "GetNamedSecurityInfoW")
    text = ctypes.c_wchar_p()
    try:
        if not convert(
                descriptor, 1, wac.DACL_SECURITY_INFORMATION,
                ctypes.byref(text), None):
            raise OSError(ctypes.get_last_error(),
                          "ConvertSecurityDescriptorToStringSecurityDescriptorW")
        return text.value or ""
    finally:
        if text:
            kernel.LocalFree(ctypes.cast(text, wac.LPVOID))
        if descriptor:
            kernel.LocalFree(descriptor)


@unittest.skipUnless(sys.platform == "win32" and os.name == "nt",
                     "native Windows AppContainer acceptance")
class TestWindowsAppContainerLive(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ora-wac-live-", dir=str(Path.home())))
        self.repo = self.root / "repo"
        self.home = self.root / "sandbox-home"
        self.tmp = self.root / "sandbox-tmp"
        self.state = self.root / "state"
        for path in (self.repo, self.home, self.tmp, self.state):
            path.mkdir()
        (self.repo / "readable.txt").write_text("repo-readable", encoding="utf-8")
        self.outside = self.root / "outside-sentinel.txt"
        self.outside.write_text("must-stay-private", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _env(self):
        return er._clean_env(str(self.home), str(self.tmp))

    def _assert_profile_deleted(self, profile: str):
        """Re-creating the exact name proves cleanup removed the old profile."""
        api = wac._load_api()
        sid = wac._create_profile(api, profile)
        try:
            wac._delete_profile(api, profile)
        finally:
            api.advapi32.FreeSid(sid)

    def _assert_process_dead(self, pid: int):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wac.DWORD, wac.BOOL, wac.DWORD]
        kernel.OpenProcess.restype = wac.HANDLE
        kernel.WaitForSingleObject.argtypes = [wac.HANDLE, wac.DWORD]
        kernel.WaitForSingleObject.restype = wac.DWORD
        kernel.CloseHandle.argtypes = [wac.HANDLE]
        kernel.CloseHandle.restype = wac.BOOL
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel.OpenProcess(
            SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER is the normal "PID no longer exists" case.
            self.assertEqual(ctypes.get_last_error(), 87)
            return
        try:
            self.assertEqual(
                kernel.WaitForSingleObject(handle, 2000), wac.WAIT_OBJECT_0,
                f"Job descendant {pid} survived AppContainer timeout",
            )
        finally:
            kernel.CloseHandle(handle)

    def test_token_stdio_network_and_file_boundary(self):
        self.assertTrue(wac.available(), "required AppContainer APIs missing on Windows")
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        code = textwrap.dedent(
            """
            import ctypes, os, socket, sys
            from ctypes import wintypes
            TOKEN_QUERY = 0x0008
            TokenIsAppContainer = 29
            token = wintypes.HANDLE()
            adv = ctypes.WinDLL('advapi32', use_last_error=True)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetCurrentProcess.argtypes = []
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.HANDLE)]
            adv.OpenProcessToken.restype = wintypes.BOOL
            adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                ctypes.c_void_p, wintypes.DWORD,
                                                ctypes.POINTER(wintypes.DWORD)]
            adv.GetTokenInformation.restype = wintypes.BOOL
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            kernel.GetStdHandle.argtypes = [ctypes.c_int32]
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.GetFileType.argtypes = [wintypes.HANDLE]
            kernel.GetFileType.restype = wintypes.DWORD
            if not adv.OpenProcessToken(kernel.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
                raise OSError(ctypes.get_last_error(), 'OpenProcessToken')
            flag = wintypes.DWORD()
            returned = wintypes.DWORD()
            if not adv.GetTokenInformation(token, TokenIsAppContainer, ctypes.byref(flag),
                                           ctypes.sizeof(flag), ctypes.byref(returned)):
                raise OSError(ctypes.get_last_error(), 'GetTokenInformation')
            kernel.CloseHandle(token)
            print('TOKEN_APPCONTAINER=' + str(flag.value), flush=True)
            print('STDOUT_PIPE=' + str(kernel.GetFileType(kernel.GetStdHandle(-11)) == 3), flush=True)
            print('STDERR_MARKER', file=sys.stderr, flush=True)
            for label, address in [('LOOPBACK', ('127.0.0.1', int(sys.argv[1]))),
                                   ('EXTERNAL', ('1.1.1.1', 80))]:
                sock = socket.socket(); sock.settimeout(2)
                try:
                    sock.connect(address); outcome = 'OPEN'
                except OSError:
                    outcome = 'DENIED'
                finally:
                    sock.close()
                print(label + '=' + outcome, flush=True)
            print('REPO_READ=' + open('readable.txt', encoding='utf-8').read(), flush=True)
            try:
                open('should-not-write.txt', 'w').write('bad'); repo_write = 'OPEN'
            except OSError:
                repo_write = 'DENIED'
            print('REPO_WRITE=' + repo_write, flush=True)
            scratch = os.path.join(os.environ['TEMP'], 'scratch-write.txt')
            open(scratch, 'w').write('ok')
            print('SCRATCH_WRITE=' + open(scratch).read(), flush=True)
            try:
                open(sys.argv[2], encoding='utf-8').read(); outside = 'OPEN'
            except OSError:
                outside = 'DENIED'
            print('OUTSIDE_READ=' + outside, flush=True)
            """
        )
        captured = {}
        original_create = wac._create_profile

        def create_and_capture(api, name):
            sid = original_create(api, name)
            captured.update(profile=name, sid=wac._sid_text(api, sid))
            return sid

        try:
            with mock.patch.object(wac, "_create_profile", side_effect=create_and_capture):
                result = wac.run(
                    [sys.executable, "-c", code, str(port), str(self.outside)],
                    cwd=str(self.repo), env=self._env(), timeout=20,
                    readonly_roots=[str(self.repo)],
                    writable_roots=[str(self.home), str(self.tmp)],
                    state_root=self.state,
                )
        finally:
            listener.close()
        self.assertTrue(result.started)
        self.assertEqual(result.returncode, 0, result.stderr + (result.error or ""))
        self.assertIn("TOKEN_APPCONTAINER=1", result.stdout)
        self.assertIn("STDOUT_PIPE=True", result.stdout)
        self.assertIn("STDERR_MARKER", result.stderr)
        self.assertIn("LOOPBACK=DENIED", result.stdout)
        self.assertIn("EXTERNAL=DENIED", result.stdout)
        self.assertIn("REPO_READ=repo-readable", result.stdout)
        self.assertIn("REPO_WRITE=DENIED", result.stdout)
        self.assertIn("SCRATCH_WRITE=ok", result.stdout)
        self.assertIn("OUTSIDE_READ=DENIED", result.stdout)
        # Named crash-safety criterion: neither a root nor an existing/new child
        # retains the unique profile SID after normal cleanup.
        for path in (self.repo, self.repo / "readable.txt", self.home, self.tmp,
                     self.tmp / "scratch-write.txt"):
            self.assertNotIn(captured["sid"], _dacl_sddl(path), str(path))
        self._assert_profile_deleted(captured["profile"])

    def test_job_tree_timeout_and_crash_journal_recovery(self):
        child_code = (
            "import subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "print('DESCENDANT_PID='+str(p.pid),flush=True); time.sleep(60)"
        )
        result = wac.run(
            [sys.executable, "-c", child_code], cwd=str(self.repo), env=self._env(),
            timeout=1, readonly_roots=[str(self.repo)],
            writable_roots=[str(self.home), str(self.tmp)], state_root=self.state)
        self.assertTrue(result.started)
        self.assertTrue(result.timed_out)
        self.assertIn("DESCENDANT_PID=", result.stdout)
        descendant_pid = int(result.stdout.split("DESCENDANT_PID=", 1)[1].splitlines()[0])
        self._assert_process_dead(descendant_pid)

        helper = textwrap.dedent(
            f"""
            import os, sys
            sys.path.insert(0, {str(_ORCH)!r})
            import windows_appcontainer as w
            w._launch = lambda *a, **k: os._exit(91)
            w.run([sys.executable, '-c', 'pass'], cwd={str(self.repo)!r},
                  env={{'PATH': os.environ.get('PATH',''),
                       'SystemRoot': os.environ.get('SystemRoot',''),
                       'TEMP': {str(self.tmp)!r}, 'TMP': {str(self.tmp)!r},
                       'USERPROFILE': {str(self.home)!r}}}, timeout=5,
                  readonly_roots=[{str(self.repo)!r}],
                  writable_roots=[{str(self.home)!r}, {str(self.tmp)!r}],
                  state_root={str(self.state)!r})
            """
        )
        crashed = subprocess.run([sys.executable, "-c", helper], timeout=30)
        self.assertEqual(crashed.returncode, 91)
        journals = list(self.state.glob("lease-*.json"))
        self.assertEqual(len(journals), 1)
        orphan = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertIn(orphan["sid"], _dacl_sddl(self.repo))

        # A new serialized run must recover the orphan before creating its lease.
        recovered = wac.run(
            [sys.executable, "-c", "print('RECOVERED', flush=True)"],
            cwd=str(self.repo), env=self._env(), timeout=20,
            readonly_roots=[str(self.repo)],
            writable_roots=[str(self.home), str(self.tmp)], state_root=self.state)
        self.assertEqual(recovered.returncode, 0, recovered.error)
        self.assertIn("RECOVERED", recovered.stdout)
        self.assertEqual(list(self.state.glob("lease-*.json")), [])
        for path in (self.repo, self.repo / "readable.txt", self.home, self.tmp):
            self.assertNotIn(orphan["sid"], _dacl_sddl(path), str(path))
        self._assert_profile_deleted(orphan["profile"])


if __name__ == "__main__":
    unittest.main()
