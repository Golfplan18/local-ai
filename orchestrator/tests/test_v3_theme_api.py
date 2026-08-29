#!/usr/bin/env python3
"""Focused tests for Ora V3 theme import/export and customization safety."""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))
sys.path.insert(0, str(ROOT / "server"))

try:
    from server import app as S  # type: ignore  # noqa: E402
    from orchestrator import project_registry as PR  # noqa: E402
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - skip path
    S = None
    PR = None
    IMPORT_ERROR = exc


OBSIDIAN_CSS = """
.theme-light {
  --background-primary: #ffffff;
  --background-secondary: #eeeeee;
  --background-modifier-border: #cccccc;
  --text-normal: #111111;
  --text-muted: #555555;
  --interactive-accent: #3366ff;
  --color-green: #008000;
  --color-red: #cc0000;
}
.theme-dark {
  --background-primary: #101010;
  --background-secondary: #202020;
  --background-modifier-border: #303030;
  --text-normal: #eeeeee;
  --text-muted: #aaaaaa;
  --interactive-accent: #88aaff;
  --color-green: #55aa55;
  --color-red: #ff5555;
}
.workspace-tabs { border-radius: 99px; }
"""


class TestV3ThemeApi(unittest.TestCase):
    def setUp(self):
        if IMPORT_ERROR is not None:
            self.skipTest(f"could not import server.py: {IMPORT_ERROR}")

        self.tmpdir = Path(tempfile.mkdtemp(prefix="ora_theme_api_"))
        self.themes_dir = self.tmpdir / "themes"
        self.default_dir = self.themes_dir / "default"
        self.default_dir.mkdir(parents=True)
        (self.default_dir / "manifest.json").write_text(
            json.dumps({
                "name": "Ora Default",
                "version": "1.0.0",
                "modes": ["dark", "light"],
            }),
            encoding="utf-8",
        )
        (self.default_dir / "theme.css").write_text(
            '@import url("../../styles/ora-default.css");\n',
            encoding="utf-8",
        )
        (self.themes_dir / "index.json").write_text(
            json.dumps({
                "themes": [{
                    "id": "default",
                    "name": "Ora Default",
                    "directory": "default",
                    "bundled": True,
                }],
            }),
            encoding="utf-8",
        )

        self.old_dir = S.V3_THEMES_DIR
        self.old_index = S.V3_THEMES_INDEX
        self.old_cache = S._V3_DEFAULT_THEME_VARS_CACHE
        S.V3_THEMES_DIR = str(self.themes_dir) + "/"
        S.V3_THEMES_INDEX = str(self.themes_dir / "index.json")
        S._V3_DEFAULT_THEME_VARS_CACHE = None
        self.client = S.app.test_client()

    def tearDown(self):
        if S is not None:
            S.V3_THEMES_DIR = self.old_dir
            S.V3_THEMES_INDEX = self.old_index
            S._V3_DEFAULT_THEME_VARS_CACHE = self.old_cache
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def response_json(self, response):
        return json.loads(response.get_data(as_text=True))

    def _make_project_theme(self):
        project_root = self.tmpdir / "project"
        theme_dir = project_root / "themes" / "publisher" / "deep-theme"
        theme_dir.mkdir(parents=True)
        (theme_dir / "manifest.json").write_text(
            json.dumps({"name": "Deep Project Theme", "version": "1.0.0"}),
            encoding="utf-8",
        )
        (theme_dir / "theme.css").write_text(
            ".theme-light { --text-normal: #123456; }\n",
            encoding="utf-8",
        )
        (project_root / "ora-project.json").write_text(
            json.dumps({
                "nexus": "test-project",
                "name": "Test Project",
                "themes": [{
                    "id": "deep-project",
                    "name": "Deep Project Theme",
                    "directory": "themes/publisher/deep-theme",
                }],
            }),
            encoding="utf-8",
        )
        return PR.load_project_at(project_root), theme_dir

    def _patch_project_registry(self, project):
        return (
            mock.patch.object(PR, "list_projects", return_value=[project]),
            mock.patch.object(PR, "get_project", return_value=project),
        )

    def test_obsidian_conversion_derives_ora_variables(self):
        converted = S._v3_convert_obsidian_theme(OBSIDIAN_CSS, {"name": "Seed"})
        self.assertIn(".theme-light", converted)
        self.assertIn(".theme-dark", converted)
        self.assertIn("--background-primary: #ffffff;", converted)
        self.assertIn("--ora-wordmark-base: #555555;", converted)
        self.assertIn("--ora-mode-private-pane-border: #008000;", converted)
        self.assertIn("--ora-vis-bg: #ffffff;", converted)
        self.assertIn("--ora-visual-toolbar-bg: #eeeeee;", converted)
        self.assertIn("--ora-visual-toolbar-border: #cccccc;", converted)
        self.assertNotIn(".workspace-tabs", converted)

    def test_install_converts_and_keeps_existing_theme(self):
        first = self.client.post(
            "/api/v3-themes/install",
            json={"name": "Sample", "css": OBSIDIAN_CSS, "manifest": {"name": "Sample"}},
        )
        second = self.client.post(
            "/api/v3-themes/install",
            json={"name": "Sample", "css": OBSIDIAN_CSS, "manifest": {"name": "Sample"}},
        )

        first_data = self.response_json(first)
        second_data = self.response_json(second)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first_data["id"], "sample")
        self.assertEqual(second_data["id"], "sample-2")

        css = (self.themes_dir / "sample" / "theme.css").read_text(encoding="utf-8")
        self.assertIn("Converted from Obsidian CSS for Ora", css)
        self.assertIn("--ora-vis-bg: #ffffff;", css)
        self.assertNotIn(".workspace-tabs", css)

    def test_duplicate_default_persists_copy_without_touching_default(self):
        before = (self.default_dir / "theme.css").read_text(encoding="utf-8")
        resp = self.client.post(
            "/api/v3-themes/default/duplicate",
            json={"customizations": {"--text-normal": "#123456"}},
        )
        data = self.response_json(resp)

        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(data["id"], "default")
        self.assertEqual((self.default_dir / "theme.css").read_text(encoding="utf-8"), before)
        css = (self.themes_dir / data["id"] / "theme.css").read_text(encoding="utf-8")
        self.assertIn(S.V3_CUSTOMIZATIONS_START, css)
        self.assertIn("--text-normal: #123456;", css)

    def test_save_customizations_rejects_default_and_updates_user_theme(self):
        S._v3_install(
            "editable",
            "Editable",
            {"name": "Editable", "oraThemeFormat": S.V3_ORA_THEME_FORMAT},
            "body {}\n",
        )

        default_resp = self.client.post(
            "/api/v3-themes/default/save-customizations",
            json={"customizations": {"--text-normal": "#000000"}},
        )
        editable_resp = self.client.post(
            "/api/v3-themes/editable/save-customizations",
            json={"customizations": {"--link-color": "#abcdef"}},
        )

        self.assertEqual(default_resp.status_code, 409)
        self.assertEqual(editable_resp.status_code, 200)
        css = (self.themes_dir / "editable" / "theme.css").read_text(encoding="utf-8")
        self.assertIn("--link-color: #abcdef;", css)

    def test_export_zip_contains_customary_theme_files(self):
        resp = self.client.get("/api/v3-themes/default/export")
        self.assertEqual(resp.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            self.assertEqual(set(zf.namelist()), {"manifest.json", "theme.css"})
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            css = zf.read("theme.css").decode("utf-8")
        self.assertEqual(manifest["oraThemeFormat"], S.V3_ORA_THEME_FORMAT)
        self.assertIn("ora-default.css", css)

    def test_install_zip_preserves_ora_theme_css(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps({
                    "name": "Zipped Ora",
                    "version": "1.0.0",
                    "oraThemeFormat": S.V3_ORA_THEME_FORMAT,
                }),
            )
            zf.writestr("theme.css", ".theme-light { --text-normal: #010203; }\n")
        buf.seek(0)

        resp = self.client.post(
            "/api/v3-themes/install-zip",
            data={"file": (buf, "zipped-ora.ora-theme.zip")},
            content_type="multipart/form-data",
        )
        data = self.response_json(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["id"], "zipped-ora")
        css = (self.themes_dir / "zipped-ora" / "theme.css").read_text(encoding="utf-8")
        self.assertEqual(css, ".theme-light { --text-normal: #010203; }\n")

    def test_nested_project_theme_lists_and_serves_nested_asset(self):
        project, theme_dir = self._make_project_theme()
        nested = theme_dir / "assets" / "palette.css"
        nested.parent.mkdir()
        nested.write_text("/* nested project asset */\n", encoding="utf-8")
        list_patch, get_patch = self._patch_project_registry(project)
        with list_patch, get_patch:
            listed = self.client.get("/api/v3-themes/list")
            served = self.client.get(
                "/themes/project/test-project/assets/palette.css",
            )

        self.assertEqual(listed.status_code, 200)
        entries = {
            entry["id"]: entry for entry in self.response_json(listed)["themes"]
        }
        self.assertEqual(entries["deep-project"]["origin"], "project:test-project")
        self.assertEqual(
            entries["deep-project"]["manifest"]["name"],
            "Deep Project Theme",
        )
        self.assertEqual(
            entries["deep-project"]["theme_css_url"],
            "/themes/project/test-project/theme.css",
        )
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.get_data(as_text=True), "/* nested project asset */\n")

    def test_project_theme_parent_traversal_request_forbidden(self):
        project, _theme_dir = self._make_project_theme()
        list_patch, get_patch = self._patch_project_registry(project)
        with list_patch, get_patch:
            response = self.client.get(
                "/themes/project/test-project/%2e%2e/outside.css",
            )
        self.assertEqual(response.status_code, 403)

    def test_project_theme_directory_symlink_swap_is_not_listed_or_served(self):
        project, theme_dir = self._make_project_theme()
        outside = self.tmpdir / "outside-theme"
        outside.mkdir()
        (outside / "manifest.json").write_text(
            json.dumps({"name": "Outside Secret"}), encoding="utf-8",
        )
        (outside / "theme.css").write_text(
            "/* outside secret css */\n", encoding="utf-8",
        )
        shutil.rmtree(theme_dir)
        theme_dir.symlink_to(outside, target_is_directory=True)

        list_patch, get_patch = self._patch_project_registry(project)
        with list_patch, get_patch:
            listed = self.client.get("/api/v3-themes/list")
            served = self.client.get(
                "/themes/project/test-project/theme.css",
            )

        ids = {
            entry["id"] for entry in self.response_json(listed)["themes"]
        }
        self.assertNotIn("deep-project", ids)
        self.assertEqual(served.status_code, 403)
        self.assertNotIn(b"outside secret css", served.data)

    def test_project_theme_asset_symlink_swap_blocks_internal_reads(self):
        project, theme_dir = self._make_project_theme()
        outside_css = self.tmpdir / "outside-secret.css"
        outside_css.write_text("/* outside secret css */\n", encoding="utf-8")
        (theme_dir / "theme.css").unlink()
        (theme_dir / "theme.css").symlink_to(outside_css)

        list_patch, get_patch = self._patch_project_registry(project)
        with list_patch, get_patch:
            listed = self.client.get("/api/v3-themes/list")
            served = self.client.get(
                "/themes/project/test-project/theme.css",
            )
            exported = self.client.get(
                "/api/v3-themes/deep-project/export",
            )

        ids = {
            entry["id"] for entry in self.response_json(listed)["themes"]
        }
        self.assertNotIn("deep-project", ids)
        self.assertEqual(served.status_code, 403)
        self.assertNotIn(b"outside secret css", served.data)
        self.assertEqual(exported.status_code, 404)


if __name__ == "__main__":
    unittest.main()
