"""Focused tests for the D-03 runtime-root resolver."""
from __future__ import annotations

import ctypes
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from orchestrator import runtime_paths as rp


class RuntimeRootResolutionTests(unittest.TestCase):
    def test_documents_override_bypasses_known_folder_and_derives_children(self):
        docs = r"C:\Users\Ora\OneDrive\Documents"
        known = mock.Mock(side_effect=AssertionError("must not be called"))
        roots = rp.resolve_runtime_roots(
            {"ORA_DOCUMENTS": docs},
            os_name="nt",
            home=Path(r"C:\Users\Ora"),
            known_documents_resolver=known,
        )
        self.assertEqual(str(roots.documents), docs)
        self.assertEqual(str(roots.vault), docs + r"\vault")
        self.assertEqual(str(roots.conversations), docs + r"\conversations")
        self.assertEqual(
            str(roots.historical_archive), docs + r"\Commercial AI archives"
        )
        known.assert_not_called()

    def test_windows_drive_and_unc_absolute_validation(self):
        home = Path(r"C:\Users\Ora")
        for value in (
            r"C:\Ora\Documents",
            "D:/Ora/Documents",
            r"\\server\share\Ora\Documents",
        ):
            with self.subTest(value=value):
                roots = rp.resolve_runtime_roots(
                    {"ORA_DOCUMENTS": value}, os_name="nt", home=home
                )
                self.assertEqual(
                    rp._comparison_key(roots.documents, "nt"),
                    rp._comparison_key(Path(value), "nt"),
                )

        for value in (r"C:relative\Documents", r"\rooted-without-drive", "relative"):
            with self.subTest(value=value), self.assertRaises(
                rp.PathConfigurationError
            ):
                rp.resolve_runtime_roots(
                    {"ORA_DOCUMENTS": value}, os_name="nt", home=home
                )

    def test_child_overrides_win_independently(self):
        root = Path(tempfile.gettempdir()) / "ora-roots"
        env = {
            "ORA_DOCUMENTS": str(root / "docs"),
            "ORA_VAULT": str(root / "elsewhere" / "vault"),
            "ORA_CONVERSATIONS": str(root / "talk"),
            "ORA_HISTORICAL_ARCHIVE": str(root / "history"),
            "ORA_CHROMADB_PATH": str(root / "chroma"),
        }
        roots = rp.resolve_runtime_roots(env, home=root / "home")
        self.assertEqual(roots.vault, root / "elsewhere" / "vault")
        self.assertEqual(roots.conversations, root / "talk")
        self.assertEqual(roots.historical_archive, root / "history")
        self.assertEqual(roots.chromadb, root / "chroma")

    def test_blank_override_is_unset_and_relative_override_is_rejected(self):
        home = Path(tempfile.gettempdir()) / "blank-home"
        roots = rp.resolve_runtime_roots({"ORA_DOCUMENTS": "  "}, home=home)
        self.assertEqual(roots.documents, home / "Documents")
        with self.assertRaisesRegex(rp.PathConfigurationError, "absolute"):
            rp.resolve_runtime_roots({"ORA_DOCUMENTS": "relative/docs"}, home=home)

    def test_vault_alias_contract(self):
        base = Path(tempfile.gettempdir()) / "vault-alias"
        canonical = rp.resolve_runtime_roots({"ORA_VAULT": str(base)}, home=base.parent)
        legacy = rp.resolve_runtime_roots({"ORA_VAULT_PATH": str(base)}, home=base.parent)
        equal = rp.resolve_runtime_roots(
            {"ORA_VAULT": str(base), "ORA_VAULT_PATH": str(base / ".")},
            home=base.parent,
        )
        self.assertEqual(canonical.vault, base)
        self.assertEqual(legacy.vault, base)
        self.assertEqual(equal.vault, base)

    def test_conflicting_vault_aliases_fail_loud(self):
        base = Path(tempfile.gettempdir()) / "vault-conflict"
        with self.assertRaisesRegex(
            rp.PathConfigurationError, "ORA_VAULT.*ORA_VAULT_PATH"
        ):
            rp.resolve_runtime_roots(
                {"ORA_VAULT": str(base / "a"), "ORA_VAULT_PATH": str(base / "b")},
                home=base,
            )

    def test_stale_legacy_default_cannot_split_redirected_documents(self):
        home = Path(r"C:\Users\Ora")
        redirected = Path(r"C:\Users\Ora\OneDrive\Documents")
        with self.assertRaisesRegex(rp.PathConfigurationError, "pre-redirection"):
            rp.resolve_runtime_roots(
                {"ORA_VAULT_PATH": r"C:\Users\Ora\Documents\vault"},
                os_name="nt",
                home=home,
                known_documents_resolver=lambda: redirected,
            )

    def test_existing_old_default_requires_explicit_choice_after_redirection(self):
        home = Path(r"C:\Users\Ora")
        redirected = Path(r"C:\Users\Ora\OneDrive\Documents")
        old_vault_key = rp._comparison_key(
            Path(r"C:\Users\Ora\Documents\vault"), "nt"
        )

        def exists(path: Path) -> bool:
            return rp._comparison_key(path, "nt") == old_vault_key

        with self.assertRaisesRegex(
            rp.PathConfigurationError, "vault already exists.*pre-redirection"
        ):
            rp.resolve_runtime_roots(
                {},
                os_name="nt",
                home=home,
                known_documents_resolver=lambda: redirected,
                path_exists=exists,
            )

        explicit = rp.resolve_runtime_roots(
            {"ORA_VAULT": r"C:\Users\Ora\Documents\vault"},
            os_name="nt",
            home=home,
            known_documents_resolver=lambda: redirected,
            path_exists=exists,
        )
        self.assertEqual(
            rp._comparison_key(explicit.vault, "nt"), old_vault_key
        )

    def test_windows_known_folder_and_fallback_diagnostics(self):
        home = Path(r"C:\Users\Ora")
        onedrive = Path(r"C:\Users\Ora\OneDrive\Documents")
        roots = rp.resolve_runtime_roots(
            {}, os_name="nt", home=home,
            known_documents_resolver=lambda: onedrive,
        )
        self.assertEqual(str(roots.documents), str(onedrive))
        self.assertEqual(roots.sources["documents"], "windows-known-folder")
        self.assertEqual(roots.warnings, ())

        fallback = rp.resolve_runtime_roots(
            {}, os_name="nt", home=home,
            known_documents_resolver=mock.Mock(side_effect=OSError("shell unavailable")),
        )
        self.assertEqual(str(fallback.documents), r"C:\Users\Ora\Documents")
        self.assertEqual(fallback.sources["documents"], "home-fallback")
        self.assertIn("shell unavailable", fallback.warnings[0])

    def test_accessors_observe_environment_after_import(self):
        vault = Path(tempfile.gettempdir()) / "late-vault"
        with mock.patch.dict(os.environ, {"ORA_VAULT_PATH": str(vault)}, clear=True):
            self.assertEqual(rp.vault_dir(), vault)

    def test_posix_resolution_never_touches_windll(self):
        with mock.patch.object(ctypes, "WinDLL", create=True) as win_dll:
            roots = rp.resolve_runtime_roots(
                {}, os_name="posix", home=Path(tempfile.gettempdir()) / "posix-home"
            )
        win_dll.assert_not_called()
        self.assertEqual(roots.sources["documents"], "home-default")

    def test_home_relative_display_is_portable(self):
        self.assertEqual(
            rp.home_relative_display(
                r"C:\Users\Ora\Documents\conversations\raw\chat.md",
                home=r"c:\users\ora",
            ),
            "~/Documents/conversations/raw/chat.md",
        )
        self.assertEqual(
            rp.home_relative_display(
                "/Users/ora/Documents/conversations/raw/chat.md",
                home="/Users/ora",
            ),
            "~/Documents/conversations/raw/chat.md",
        )
        other_drive = r"D:\Archive\chat.md"
        self.assertEqual(
            rp.home_relative_display(other_drive, home=r"C:\Users\Ora"),
            other_drive,
        )


class KnownFolderCtypesTests(unittest.TestCase):
    def test_ctypes_binding_returns_path_and_frees_buffer(self):
        target = r"C:\Users\Ora\OneDrive\Documents"

        class FakeFunction:
            def __init__(self, callback):
                self.callback = callback
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.callback(*args)

        freed = []

        captured_guid_bytes = []

        def get_path(guid, _flags, _token, out):
            guid_object = guid._obj
            captured_guid_bytes.append(
                ctypes.string_at(
                    ctypes.addressof(guid_object), ctypes.sizeof(guid_object)
                )
            )
            out._obj.value = target
            return 0

        shell = type("Shell", (), {})()
        shell.SHGetKnownFolderPath = FakeFunction(get_path)
        ole = type("Ole", (), {})()
        ole.CoTaskMemFree = FakeFunction(lambda ptr: freed.append(ptr))

        def dll(name, **_kwargs):
            return shell if name == "shell32" else ole

        with mock.patch.object(ctypes, "WinDLL", create=True, side_effect=dll):
            self.assertEqual(str(rp._windows_documents_dir()), target)
        self.assertEqual(len(freed), 1)
        self.assertEqual(
            captured_guid_bytes,
            [uuid.UUID(rp._FOLDERID_DOCUMENTS).bytes_le],
        )
        argtypes = shell.SHGetKnownFolderPath.argtypes
        self.assertEqual(len(argtypes), 4)
        self.assertEqual(
            [field_name for field_name, _field_type in argtypes[0]._type_._fields_],
            ["Data1", "Data2", "Data3", "Data4"],
        )
        self.assertIs(argtypes[1], ctypes.wintypes.DWORD)
        self.assertIs(argtypes[2], ctypes.wintypes.HANDLE)
        self.assertIs(argtypes[3]._type_, ctypes.c_wchar_p)

    def test_ctypes_binding_frees_buffer_on_failing_hresult(self):
        class FakeFunction:
            def __init__(self, callback):
                self.callback = callback
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.callback(*args)

        freed = []

        def get_path(_guid, _flags, _token, out):
            out._obj.value = r"C:\AllocatedDespiteFailure"
            return -2147024891  # 0x80070005, E_ACCESSDENIED

        shell = type("Shell", (), {})()
        shell.SHGetKnownFolderPath = FakeFunction(get_path)
        ole = type("Ole", (), {})()
        ole.CoTaskMemFree = FakeFunction(lambda ptr: freed.append(ptr))
        with mock.patch.object(
            ctypes,
            "WinDLL",
            create=True,
            side_effect=lambda name, **_kw: shell if name == "shell32" else ole,
        ):
            with self.assertRaisesRegex(OSError, "80070005"):
                rp._windows_documents_dir()
        self.assertEqual(len(freed), 1)

    def test_nonnegative_hresult_with_value_is_success(self):
        target = r"C:\Users\Ora\Documents"

        class FakeFunction:
            def __init__(self, callback):
                self.callback = callback
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.callback(*args)

        freed = []

        def get_path(_guid, _flags, _token, out):
            out._obj.value = target
            return 1  # nonnegative HRESULT is success under COM semantics

        shell = type("Shell", (), {})()
        shell.SHGetKnownFolderPath = FakeFunction(get_path)
        ole = type("Ole", (), {})()
        ole.CoTaskMemFree = FakeFunction(lambda ptr: freed.append(ptr))
        with mock.patch.object(
            ctypes,
            "WinDLL",
            create=True,
            side_effect=lambda name, **_kw: shell if name == "shell32" else ole,
        ):
            self.assertEqual(str(rp._windows_documents_dir()), target)
        self.assertEqual(len(freed), 1)

    def test_success_with_null_pointer_is_an_error_and_not_freed(self):
        class FakeFunction:
            def __init__(self, callback):
                self.callback = callback
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.callback(*args)

        freed = []
        shell = type("Shell", (), {})()
        shell.SHGetKnownFolderPath = FakeFunction(lambda *_args: 0)
        ole = type("Ole", (), {})()
        ole.CoTaskMemFree = FakeFunction(lambda ptr: freed.append(ptr))
        with mock.patch.object(
            ctypes,
            "WinDLL",
            create=True,
            side_effect=lambda name, **_kw: shell if name == "shell32" else ole,
        ):
            with self.assertRaisesRegex(OSError, "empty Documents"):
                rp._windows_documents_dir()
        self.assertEqual(freed, [])

    def test_decode_failure_still_frees_allocated_buffer(self):
        class FakeFunction:
            def __init__(self, callback):
                self.callback = callback
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.callback(*args)

        freed = []

        def get_path(_guid, _flags, _token, out):
            out._obj.value = r"C:\Allocated"
            return 0

        shell = type("Shell", (), {})()
        shell.SHGetKnownFolderPath = FakeFunction(get_path)
        ole = type("Ole", (), {})()
        ole.CoTaskMemFree = FakeFunction(lambda ptr: freed.append(ptr))
        with mock.patch.object(
            ctypes,
            "WinDLL",
            create=True,
            side_effect=lambda name, **_kw: shell if name == "shell32" else ole,
        ), mock.patch.object(
            rp, "_known_folder_text", side_effect=OSError("decode failed")
        ):
            with self.assertRaisesRegex(OSError, "decode failed"):
                rp._windows_documents_dir()
        self.assertEqual(len(freed), 1)

    def test_known_folder_text_wraps_decode_errors(self):
        class BadText:
            @property
            def value(self):
                raise UnicodeError("bad wchar")

        with self.assertRaisesRegex(OSError, "Could not decode"):
            rp._known_folder_text(BadText())


if __name__ == "__main__":
    unittest.main()
