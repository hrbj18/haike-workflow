"""Offline contracts for the local runtime installer; no DLL is loaded here."""

import importlib.util
import errno
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_msvc", ROOT / "_distribution-tools/setup_msvc.py")
msvc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(msvc)


class MsvcSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "signed-source"
        self.source.mkdir()
        header = bytearray(70)
        header[:2] = b"MZ"
        struct.pack_into("<I", header, 60, 64)
        header[64:] = b"PE\0\0\x64\x86"
        for name in msvc.DLL_NAMES:
            (self.source / name).write_bytes(header + name.encode("ascii"))
        self.records = [dict(name=name, version="14.44.35211.0", status="Valid",
                             signer="CN=Publisher, O=Microsoft Corporation, C=US")
                        for name in msvc.DLL_NAMES]
        self.venv = self.root / "Haike_video/.venv"
        python = self.venv / "Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"fixture, never executed")
        template = self.root / "_distribution-tools/sitecustomize.py"
        template.parent.mkdir()
        template.write_text("# owned startup hook\n", encoding="utf-8")

    def _inspection(self):
        return patch.object(msvc.subprocess, "run", return_value=types.SimpleNamespace(stdout=json.dumps(self.records)))

    def test_signed_matching_x64_set_passes_without_loading_a_dll(self):
        with self._inspection() as inspect:
            self.assertEqual(msvc.inspect_runtime(self.source), (14, 44, 35211, 0))
        self.assertEqual(inspect.call_args.kwargs["timeout"], 15)
        self.assertEqual(inspect.call_args.kwargs["env"]["HAIKE_MSVC_SOURCE_DIR"], str(self.source))

    def test_wrong_architecture_is_rejected_before_signature_process(self):
        file = self.source / msvc.DLL_NAMES[0]
        header = bytearray(file.read_bytes())
        header[68:70] = b"\x4c\x01"
        file.write_bytes(header)
        with self._inspection() as inspect:
            with self.assertRaisesRegex(ValueError, "x64"):
                msvc.inspect_runtime(self.source)
        inspect.assert_not_called()

    def test_untrusted_mixed_old_or_incomplete_sets_are_rejected(self):
        variants = [dict(status="UnknownError"), dict(signer="CN=Other, O=Other"),
                    dict(version="14.42.34433.0")]
        for variant in variants:
            with self.subTest(variant=variant):
                saved = self.records[0].copy()
                self.records[0].update(variant)
                with self._inspection(), self.assertRaises(ValueError):
                    msvc.inspect_runtime(self.source)
                self.records[0] = saved
        for item in self.records:
            item["version"] = "14.42.34433.0"
        with self._inspection(), self.assertRaisesRegex(ValueError, "14.44"):
            msvc.inspect_runtime(self.source)
        self.records.pop()
        with self._inspection(), self.assertRaisesRegex(ValueError, "Incomplete"):
            msvc.inspect_runtime(self.source)

    def test_install_is_idempotent_and_always_rechecks_real_native_contract(self):
        with patch.object(msvc, "ROOT", self.root), self._inspection(), patch.object(msvc, "native_ready", return_value=True) as probe:
            first = msvc.configure(self.venv, self.source)
            second = msvc.configure(self.venv)
        self.assertEqual(first, second)
        self.assertEqual(probe.call_count, 2)
        for name in msvc.DLL_NAMES:
            self.assertEqual((self.venv / "msvc" / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual((self.venv / "Lib/site-packages/sitecustomize.py").read_bytes(),
                         (self.root / "_distribution-tools/sitecustomize.py").read_bytes())

    def test_unknown_startup_hook_is_preserved_without_copying_runtime(self):
        hook = self.venv / "Lib/site-packages/sitecustomize.py"
        hook.parent.mkdir(parents=True)
        hook.write_text("# somebody else's hook", encoding="utf-8")
        with patch.object(msvc, "ROOT", self.root), self._inspection(), patch.object(msvc, "native_ready") as probe:
            with self.assertRaisesRegex(ValueError, "not owned"):
                msvc.configure(self.venv, self.source)
        self.assertEqual(hook.read_text(encoding="utf-8"), "# somebody else's hook")
        self.assertFalse((self.venv / "msvc").exists())
        probe.assert_not_called()

    def test_existing_different_runtime_is_not_overwritten(self):
        target = self.venv / "msvc" / msvc.DLL_NAMES[0]
        target.parent.mkdir()
        target.write_bytes(b"retain previous runtime")
        with patch.object(msvc, "ROOT", self.root), self._inspection():
            with self.assertRaisesRegex(ValueError, "differs"):
                msvc.configure(self.venv, self.source)
        self.assertEqual(target.read_bytes(), b"retain previous runtime")
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_target_file_symlinks_cannot_create_or_modify_an_outside_file(self):
        index = 0
        for relative in ("msvc/msvcp140.dll", "Lib/site-packages/sitecustomize.py"):
            for exists in (False, True):
                with self.subTest(relative=relative, existing_outside=exists):
                    index += 1
                    case_root = self.root / f"symlink-case-{index}"
                    case_root.mkdir()
                    case_root = case_root.resolve()
                    venv = case_root / "Haike_video/.venv"
                    python = venv / "Scripts/python.exe"
                    python.parent.mkdir(parents=True)
                    python.write_bytes(b"fixture, never executed")
                    outside = case_root / "outside-venv.dll"
                    if exists:
                        outside.write_bytes(b"preserve unrelated file")
                    target = venv / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self.assertFalse(os.path.lexists(target))
                    try:
                        target.symlink_to(outside)
                    except OSError as error:
                        if getattr(error, "winerror", None) == 1314 or error.errno in {errno.EPERM, errno.EACCES, errno.ENOTSUP}:
                            self.skipTest(f"Symlink creation unavailable: {error}")
                        raise
                    try:
                        # FindFirstFile-backed directory metadata remains valid
                        # on Windows even when lstat cannot open a dangling link.
                        with os.scandir(target.parent) as entries:
                            entry = next(item for item in entries if item.name == target.name)
                            self.assertTrue(entry.is_symlink())
                            self.assertTrue(msvc.stat.S_ISLNK(entry.stat(follow_symlinks=False).st_mode))
                        if os.name == "nt":
                            self.assertTrue(msvc._windows_attributes(target) & msvc.stat.FILE_ATTRIBUTE_REPARSE_POINT)
                        with patch.object(msvc, "ROOT", case_root), self._inspection() as inspect, patch.object(msvc, "native_ready") as probe:
                            with self.assertRaises(ValueError):
                                msvc.configure(venv, self.source)
                        inspect.assert_not_called()
                        probe.assert_not_called()
                        self.assertEqual(outside.exists(), exists)
                        if exists:
                            self.assertEqual(outside.read_bytes(), b"preserve unrelated file")
                    finally:
                        # This Windows filesystem cannot unlink a dangling
                        # reparse entry until its target exists. Materialize only
                        # our own cleanup fixture after the zero-write assertion.
                        if not outside.exists():
                            outside.write_bytes(b"owned cleanup fixture")
                        with os.scandir(target.parent) as entries:
                            owned_link = any(item.name == target.name and item.is_symlink() for item in entries)
                        if owned_link:
                            target.unlink()

    @unittest.skipUnless(sys.platform == "win32", "Windows attribute error contract")
    def test_attribute_access_error_fails_closed_but_absent_paths_are_allowed(self):
        import ctypes

        get_attributes = Mock(return_value=0xFFFFFFFF)
        kernel = types.SimpleNamespace(GetFileAttributesW=get_attributes)
        target = self.venv / "msvc/msvcp140.dll"
        with patch.object(ctypes, "WinDLL", return_value=kernel), patch.object(ctypes, "get_last_error", return_value=5):
            with self.assertRaises(OSError) as failure:
                msvc._safe_target(target, self.venv.resolve())
        self.assertEqual(failure.exception.winerror, 5)
        for error in (2, 3):
            with self.subTest(absent_error=error), patch.object(ctypes, "WinDLL", return_value=kernel), patch.object(ctypes, "get_last_error", return_value=error):
                self.assertEqual(msvc._windows_attributes(target), 0)

    @unittest.skipUnless(sys.platform == "win32", "Windows short-path aliases")
    def test_short_path_alias_and_long_boundary_identify_the_same_directory(self):
        import ctypes
        from ctypes import wintypes

        get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        get_short_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        get_short_path.restype = wintypes.DWORD
        long_root = self.root.resolve()
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_short_path(str(long_root), buffer, len(buffer))
        self.assertGreater(length, 0, ctypes.get_last_error())
        self.assertLess(length, len(buffer))
        short_root = Path(buffer.value)
        if str(short_root).casefold() == str(long_root).casefold():
            self.skipTest("No distinct 8.3 alias is available on this volume")
        self.assertEqual(short_root.resolve(), long_root)
        short_venv = short_root / "Haike_video/.venv"
        msvc._safe_target(short_venv / "msvc", long_root)
        with patch.object(msvc, "ROOT", long_root), patch.object(msvc, "native_ready", return_value=True) as probe:
            self.assertIn("System VC runtime", msvc.configure(short_venv))
        probe.assert_called_once_with(self.venv.resolve() / "Scripts/python.exe")

    def test_reparse_point_is_rejected_even_when_it_resolves_inside_venv(self):
        target = self.venv / "msvc/msvcp140.dll"
        info = types.SimpleNamespace(st_mode=0, st_file_attributes=msvc.stat.FILE_ATTRIBUTE_REPARSE_POINT)
        with patch.object(Path, "lstat", return_value=info), self.assertRaisesRegex(ValueError, "reparse"):
            msvc._safe_target(target, self.venv)

    @unittest.skipUnless(sys.platform == "win32", "Requires the Windows PowerShell parser")
    def test_signature_inspection_script_is_valid_real_powershell(self):
        parser = r"""
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseInput($env:HAIKE_MSVC_PARSER_SOURCE, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | ForEach-Object { $_.Message }; exit 1 }
"""
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parser],
            env={**os.environ, "HAIKE_MSVC_PARSER_SOURCE": msvc._INSPECT_SCRIPT},
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_native_import_is_reported_after_install(self):
        with patch.object(msvc, "ROOT", self.root), self._inspection(), patch.object(msvc, "native_ready", return_value=False):
            with self.assertRaisesRegex(ValueError, "still failed"):
                msvc.configure(self.venv, self.source)

    def test_working_system_needs_no_source_and_failure_is_actionable(self):
        with patch.object(msvc, "ROOT", self.root), patch.object(msvc, "native_ready", return_value=True):
            self.assertIn("System VC runtime", msvc.configure(self.venv))
        self.assertFalse((self.venv / "msvc").exists())
        with patch.object(msvc, "ROOT", self.root), patch.object(msvc, "native_ready", return_value=False):
            with self.assertRaisesRegex(ValueError, "-MsvcSource"):
                msvc.configure(self.venv)

    def test_default_setup_configures_both_native_venvs_from_one_verified_source(self):
        copy_venv = self.root / "copy_skill/copy_skill-main/.venv"
        copy_python = copy_venv / "Scripts/python.exe"
        copy_python.parent.mkdir(parents=True)
        copy_python.write_bytes(b"fixture, never executed")
        local = self.venv / "msvc"
        local.mkdir()
        for name in msvc.DLL_NAMES:
            (local / name).write_bytes((self.source / name).read_bytes())
        with patch.object(msvc, "ROOT", self.root), self._inspection() as inspect, patch.object(msvc, "native_ready", return_value=True) as probe:
            result = msvc.configure_all()
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].startswith("Haike_video/.venv:"))
        self.assertTrue(result[1].startswith("copy_skill/copy_skill-main/.venv:"))
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual([call.args[0] for call in probe.call_args_list],
                         [self.venv.resolve() / "Scripts/python.exe", copy_python.resolve()])
        for venv in (self.venv, copy_venv):
            for name in msvc.DLL_NAMES:
                self.assertEqual((venv / "msvc" / name).read_bytes(), (self.source / name).read_bytes())
            self.assertEqual((venv / "Lib/site-packages/sitecustomize.py").read_bytes(),
                             (self.root / "_distribution-tools/sitecustomize.py").read_bytes())
        self.assertFalse((self.root / "creatorhub").exists())
        self.assertFalse((self.root / "api-platform").exists())

    def test_default_setup_fails_when_copy_native_capability_is_unavailable(self):
        copy_python = self.root / "copy_skill/copy_skill-main/.venv/Scripts/python.exe"
        copy_python.parent.mkdir(parents=True)
        copy_python.write_bytes(b"fixture, never executed")
        with patch.object(msvc, "ROOT", self.root), patch.object(msvc, "native_ready", side_effect=[True, False]) as probe:
            with self.assertRaisesRegex(ValueError, "Native imports failed"):
                msvc.configure_all()
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(probe.call_args.args[0], copy_python.resolve())


if __name__ == "__main__":
    unittest.main()
