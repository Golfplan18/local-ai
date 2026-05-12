"""Tests for msi_image_render — Hector cartoon + news image renderers.

Covers:
  - prompt construction (Hector + news) with vocab lists from spec §6
  - likeness gate (News Image Generator Layer 3 step 1)
  - LoRA trigger insertion when Slot 1 is the Civitai Hector LoRA
  - capability_registry invocation wrapper
  - potrace vectorization (subprocess mocked)
  - SVG text overlay compositing (banner + signature)
  - slugify edge cases
  - trim_alt_text WCAG 125-char rule
  - render_hector_cartoon end-to-end (registry mocked, paths to tmp dir)
  - render_news_image end-to-end + likeness-gate seed filtering
  - _patch_article_image_field add / replace / no-frontmatter
  - YAML emitter (dicts, lists, scalars with special chars)
  - /hector-render + /news-image-render slash command happy-path + errors
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import msi_image_render as mir  # noqa: E402
from capability_registry import CapabilityError, InvocationResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_registry(provider_id="openai-gpt-image-1", output=None,
                   chain=None, raise_codes=None):
    if output is None:
        # Default to a tiny real PNG so callers that pipe the bytes
        # through potrace_vectorize (which uses PIL.Image.open) succeed.
        import io as _io
        from PIL import Image as _Image
        _buf = _io.BytesIO()
        _Image.new("L", (4, 4), color=255).save(_buf, "PNG")
        output = _buf.getvalue()
    """Build a mock registry whose invoke() returns InvocationResult or raises
    the listed codes in order on successive calls."""
    registry = mock.MagicMock()
    registry.resolve_provider_chain.return_value = chain or [provider_id]

    call_state = {"i": 0}
    raise_seq = list(raise_codes or [])

    def fake_invoke(slot, inputs, provider_id=None):
        idx = call_state["i"]
        call_state["i"] += 1
        if idx < len(raise_seq):
            code = raise_seq[idx]
            raise CapabilityError(code, f"stub {code}", slot=slot)
        return InvocationResult(
            slot=slot,
            provider_id=provider_id or chain[0] if chain else provider_id or "openai-gpt-image-1",
            output=output,
            execution_pattern="sync",
            inputs_used=inputs,
            attempts=[{"provider_id": "openai-gpt-image-1",
                       "succeeded": True,
                       "error_code": None,
                       "error_message": None}],
        )

    registry.invoke = mock.Mock(side_effect=fake_invoke)
    return registry


SAMPLE_RECIPE = {
    "cluster_id": "test-cluster-001",
    "headline": "A Test Headline About Something Important",
    "lede": "An illustrative lede that introduces the cartoon's subject.",
    "publish_date": "2026-05-11",
    "composition_spec": ("A propagandist figure at a podium with butt-face "
                         "caricature; peanut gallery behind; gopher in "
                         "lower left frame."),
    "caption": "Strange certainties of fully-informed men.",
    "banner": "WE'RE JUST ASKING QUESTIONS",
    "likeness_verdict": {"public_figure_in_public_role": True},
    "sources": [],
    "metadata": {},
}

SAMPLE_REQUEST = {
    "article_slug": "test-article-slug",
    "article_headline": "Test Article Headline",
    "article_lede": "Article lede.",
    "visual_register": "photographic",
    "prompt_seeds": ["public square", "civic gathering"],
    "primary_entities": [
        {"name": "Jane Doe", "is_public_figure": True, "in_public_role": True},
        {"name": "John Roe", "is_public_figure": False, "in_public_role": False},
    ],
}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

class TestHectorPrompt(unittest.TestCase):

    def test_includes_composition_spec(self):
        recipe = mir.HectorCartoonRecipe(**SAMPLE_RECIPE)
        prompt = mir.construct_hector_prompt(recipe)
        self.assertIn("propagandist figure at a podium", prompt)

    def test_includes_visual_register_vocab(self):
        recipe = mir.HectorCartoonRecipe(**SAMPLE_RECIPE)
        prompt = mir.construct_hector_prompt(recipe)
        for term in ("heavy cross-hatching", "engraved aesthetic",
                     "butt-face caricature for propaganda figures",
                     "peanut gallery crowd",
                     "spectacled gopher in lower frame"):
            self.assertIn(term, prompt)

    def test_includes_forbidden_caricature_negatives(self):
        recipe = mir.HectorCartoonRecipe(**SAMPLE_RECIPE)
        prompt = mir.construct_hector_prompt(recipe)
        self.assertIn("racialized caricature", prompt)
        self.assertIn("antisemitic visual conventions", prompt)

    def test_includes_universal_negatives(self):
        recipe = mir.HectorCartoonRecipe(**SAMPLE_RECIPE)
        prompt = mir.construct_hector_prompt(recipe)
        self.assertIn("text in image", prompt)
        self.assertIn("photorealistic", prompt)

    def test_lora_trigger_when_active(self):
        recipe = mir.HectorCartoonRecipe(**SAMPLE_RECIPE)
        prompt_no_lora = mir.construct_hector_prompt(recipe, lora_active=False)
        prompt_lora = mir.construct_hector_prompt(recipe, lora_active=True)
        self.assertNotIn(mir.HECTOR_LORA_TRIGGER + " |", prompt_no_lora)
        # When lora_active=True, the trigger should appear as the first piece
        self.assertTrue(prompt_lora.startswith(mir.HECTOR_LORA_TRIGGER))


class TestNewsPrompt(unittest.TestCase):

    def test_photographic_register(self):
        req = mir.NewsImageRequest(**SAMPLE_REQUEST)
        prompt = mir.construct_news_prompt(req)
        self.assertIn("photojournalism", prompt)
        self.assertIn("public square", prompt)
        self.assertIn("civic gathering", prompt)

    def test_illustrated_register(self):
        d = dict(SAMPLE_REQUEST, visual_register="illustrated")
        req = mir.NewsImageRequest(**d)
        prompt = mir.construct_news_prompt(req)
        self.assertIn("editorial illustration", prompt)
        self.assertNotIn("photojournalism", prompt)

    def test_diagrammatic_register(self):
        d = dict(SAMPLE_REQUEST, visual_register="diagrammatic")
        req = mir.NewsImageRequest(**d)
        prompt = mir.construct_news_prompt(req)
        self.assertIn("clean lines", prompt)

    def test_text_negative_always_present(self):
        req = mir.NewsImageRequest(**SAMPLE_REQUEST)
        prompt = mir.construct_news_prompt(req)
        self.assertIn("text in image", prompt)


# ---------------------------------------------------------------------------
# Likeness gate
# ---------------------------------------------------------------------------

class TestLikenessGate(unittest.TestCase):

    def test_public_figure_in_public_role_kept(self):
        req = mir.NewsImageRequest(**SAMPLE_REQUEST)
        allowed, removed = mir.apply_likeness_gate(req)
        names_allowed = [e["name"] for e in allowed]
        self.assertIn("Jane Doe", names_allowed)
        self.assertIn("John Roe", removed)

    def test_private_person_removed(self):
        d = dict(SAMPLE_REQUEST)
        d["primary_entities"] = [
            {"name": "Private Person", "is_public_figure": False,
             "in_public_role": False},
        ]
        req = mir.NewsImageRequest(**d)
        allowed, removed = mir.apply_likeness_gate(req)
        self.assertEqual(allowed, [])
        self.assertEqual(removed, ["Private Person"])

    def test_public_figure_not_in_public_role_removed(self):
        d = dict(SAMPLE_REQUEST)
        d["primary_entities"] = [
            {"name": "Celebrity Out Of Role",
             "is_public_figure": True, "in_public_role": False},
        ]
        req = mir.NewsImageRequest(**d)
        allowed, removed = mir.apply_likeness_gate(req)
        self.assertEqual(allowed, [])
        self.assertIn("Celebrity Out Of Role", removed)


# ---------------------------------------------------------------------------
# Slug + alt text
# ---------------------------------------------------------------------------

class TestSlugify(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(mir.slugify("Hello World"), "hello-world")

    def test_strips_punctuation(self):
        self.assertEqual(mir.slugify("Hello, World!"), "hello-world")

    def test_collapses_repeated_separators(self):
        self.assertEqual(mir.slugify("Hello   ---   World"), "hello-world")

    def test_truncates_long(self):
        long_title = ("a-really-very-extremely-quite-long-title-that-"
                      "definitely-goes-past-the-max-length-cap")
        slug = mir.slugify(long_title, max_length=60)
        self.assertLessEqual(len(slug), 60)

    def test_empty_returns_untitled(self):
        self.assertEqual(mir.slugify(""), "untitled")
        self.assertEqual(mir.slugify("!!!"), "untitled")


class TestTrimAltText(unittest.TestCase):

    def test_short_unchanged(self):
        self.assertEqual(mir.trim_alt_text("short alt"), "short alt")

    def test_long_trimmed_at_word(self):
        text = "a " * 80  # 160 chars, all word-breakable
        trimmed = mir.trim_alt_text(text)
        self.assertLessEqual(len(trimmed), 125 + 1)  # +1 for ellipsis
        self.assertTrue(trimmed.endswith("…"))


# ---------------------------------------------------------------------------
# SVG overlay
# ---------------------------------------------------------------------------

class TestSvgOverlay(unittest.TestCase):

    BASIC_SVG = (
        '<?xml version="1.0"?>\n'
        '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M10,10 L90,90"/></svg>'
    )

    def test_signature_always_added(self):
        out = mir.composite_text_overlays(self.BASIC_SVG, banner=None)
        self.assertIn("Hector Rentier", out)
        self.assertIn("text-anchor=\"end\"", out)

    def test_banner_added_when_present(self):
        out = mir.composite_text_overlays(
            self.BASIC_SVG, banner="HEAR YE HEAR YE")
        self.assertIn("HEAR YE HEAR YE", out)

    def test_xml_escape_in_banner(self):
        out = mir.composite_text_overlays(
            self.BASIC_SVG, banner='Less <than> "quotes" & ampersand')
        self.assertIn("&lt;than&gt;", out)
        self.assertIn("&amp;", out)
        self.assertIn("&quot;quotes&quot;", out)

    def test_overlays_inside_svg(self):
        out = mir.composite_text_overlays(self.BASIC_SVG, banner=None)
        self.assertTrue(out.rstrip().endswith("</svg>"))
        # Overlays must precede the closing tag
        signature_pos = out.index("Hector Rentier")
        close_pos = out.rindex("</svg>")
        self.assertLess(signature_pos, close_pos)


# ---------------------------------------------------------------------------
# Potrace vectorization (subprocess mocked)
# ---------------------------------------------------------------------------

def _tiny_png_bytes():
    """Return a real 4x4 PNG byte sequence — Pillow can parse it; the
    mkbitmap step is mocked downstream so the actual content doesn't
    matter, only that PIL.Image.open succeeds.
    """
    import io as _io
    from PIL import Image as _Image
    buf = _io.BytesIO()
    _Image.new("L", (4, 4), color=255).save(buf, "PNG")
    return buf.getvalue()


class TestPotraceVectorize(unittest.TestCase):

    def test_invokes_mkbitmap_and_potrace(self):
        def fake_run(cmd, **kwargs):
            # The two-stage pipeline writes its outputs to file paths in cmd.
            # mkbitmap: ["mkbitmap", "-x", "-f", "10", "-t", "0.48",
            #            "-o", processed_pgm_path, input_pgm_path]
            # potrace:  ["potrace", "--svg", "--opttolerance", "0.4",
            #            "--output", svg_path, processed_pgm_path]
            if cmd[0] == "mkbitmap":
                pgm_path = cmd[cmd.index("-o") + 1]
                with open(pgm_path, "wb") as f:
                    f.write(b"P5\n10 10\n255\n" + b"\x00" * 100)
            elif cmd[0] == "potrace":
                svg_path = cmd[cmd.index("--output") + 1]
                with open(svg_path, "w") as f:
                    f.write(
                        '<?xml version="1.0"?>\n'
                        '<svg viewBox="0 0 100 100" '
                        'xmlns="http://www.w3.org/2000/svg">'
                        '<path fill="#000000" d="M10,10 L90,90"/></svg>'
                    )
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with mock.patch("subprocess.run", side_effect=fake_run):
            svg = mir.potrace_vectorize(_tiny_png_bytes())
        # Confirm we applied the CSS hooks per Image Spec §4.5
        self.assertIn('fill="currentColor"', svg)
        self.assertIn("background:transparent", svg)


# ---------------------------------------------------------------------------
# YAML emitter
# ---------------------------------------------------------------------------

class TestYamlEmit(unittest.TestCase):

    def test_scalar_string(self):
        self.assertEqual(mir._yaml_scalar_value("plain"), "plain")

    def test_scalar_string_with_colon_quoted(self):
        out = mir._yaml_scalar_value("has: colon")
        self.assertTrue(out.startswith('"'))
        self.assertIn("has: colon", out)

    def test_scalar_bool(self):
        self.assertEqual(mir._yaml_scalar_value(True), "true")
        self.assertEqual(mir._yaml_scalar_value(False), "false")

    def test_scalar_none(self):
        self.assertEqual(mir._yaml_scalar_value(None), "null")

    def test_dict_nested(self):
        out = mir._yaml_render("foo", {"a": 1, "b": "two"}, indent=0)
        self.assertIn("foo:", out)
        self.assertIn("a: 1", out)
        self.assertIn("b: two", out)

    def test_list_of_scalars(self):
        out = mir._yaml_render("items", [1, 2, 3], indent=0)
        self.assertIn("items:", out)
        self.assertIn("- 1", out)

    def test_list_of_dicts(self):
        out = mir._yaml_render(
            "items", [{"name": "x", "qty": 1}], indent=0)
        self.assertIn("items:", out)
        self.assertIn("- name: x", out)
        self.assertIn("qty: 1", out)

    def test_image_yaml_keys_in_canonical_order(self):
        schema = {
            "url": "/foo.png",
            "alt": "alt",
            "caption": "cap",
            "credit": "credit",
            "source": "ai_generated",
            "ai_model": "openai-gpt-image-1",
            "ai_prompt": "p",
            "disclosure": "d",
            "license": "lic",
        }
        out = mir._yaml_dump_image(schema)
        # url comes first, ai_prompt last (after disclosure → ai_model → prompt)
        self.assertTrue(out.startswith("image:"))
        url_pos = out.index("url:")
        alt_pos = out.index("alt:")
        self.assertLess(url_pos, alt_pos)


# ---------------------------------------------------------------------------
# Article-md image-field patcher
# ---------------------------------------------------------------------------

class TestPatchArticleImageField(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content):
        p = os.path.join(self.tmp, "article.md")
        with open(p, "w") as f:
            f.write(content)
        return p

    def test_adds_image_field_when_missing(self):
        path = self._write(
            "---\nheadline: hello\nlede: world\n---\nbody\n")
        ok = mir._patch_article_image_field(path, {
            "url": "/foo.png", "alt": "alt", "credit": "c",
            "source": "ai_generated"})
        self.assertTrue(ok)
        with open(path) as f:
            text = f.read()
        self.assertIn("image:", text)
        self.assertIn("url: /foo.png", text)
        self.assertIn("\nbody\n", text)

    def test_replaces_existing_image_block(self):
        path = self._write(
            "---\nheadline: hello\n"
            "image:\n"
            "  url: /old.png\n"
            "  alt: old\n"
            "  credit: old\n"
            "  source: placeholder\n"
            "lede: world\n---\nbody\n"
        )
        ok = mir._patch_article_image_field(path, {
            "url": "/new.png", "alt": "new", "credit": "new",
            "source": "ai_generated"})
        self.assertTrue(ok)
        with open(path) as f:
            text = f.read()
        self.assertIn("/new.png", text)
        self.assertNotIn("/old.png", text)
        # body intact
        self.assertIn("\nbody\n", text)

    def test_no_frontmatter_returns_false(self):
        path = self._write("just body, no frontmatter")
        ok = mir._patch_article_image_field(path, {
            "url": "/foo.png", "alt": "alt", "credit": "c",
            "source": "ai_generated"})
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# End-to-end Hector renderer (paths redirected to tmp, registry mocked)
# ---------------------------------------------------------------------------

class TestRenderHectorCartoon(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)

        # Redirect Astro paths to tmp
        self._orig_columns = mir.ASTRO_COLUMNS_DIR
        self._orig_public = mir.ASTRO_CARTOONS_PUBLIC_DIR
        mir.ASTRO_COLUMNS_DIR = os.path.join(self.tmp, "columns")
        mir.ASTRO_CARTOONS_PUBLIC_DIR = os.path.join(self.tmp, "cartoons")

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        mir.ASTRO_COLUMNS_DIR = self._orig_columns
        mir.ASTRO_CARTOONS_PUBLIC_DIR = self._orig_public

    def _potrace_stub(self, cmd, **kwargs):
        if cmd[0] == "mkbitmap":
            pgm_path = cmd[cmd.index("-o") + 1]
            with open(pgm_path, "wb") as f:
                f.write(b"P5\n10 10\n255\n" + b"\x00" * 100)
        elif cmd[0] == "potrace":
            svg_path = cmd[cmd.index("--output") + 1]
            with open(svg_path, "w") as f:
                f.write(
                    '<?xml version="1.0"?>\n'
                    '<svg viewBox="0 0 100 100" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    '<path fill="#000000" d="M10,10 L90,90"/></svg>'
                )
        return mock.Mock(returncode=0, stdout=b"", stderr=b"")

    def test_happy_path(self):
        registry = _stub_registry()
        with mock.patch("subprocess.run", side_effect=self._potrace_stub):
            result = mir.render_hector_cartoon(SAMPLE_RECIPE, registry=registry)
        self.assertTrue(result["success"], msg=result)
        self.assertTrue(os.path.isfile(result["svg_path"]))
        self.assertTrue(os.path.isfile(result["column_md_path"]))
        with open(result["column_md_path"]) as f:
            md = f.read()
        self.assertIn("pen_name: hector-rentier", md)
        self.assertIn("source: ai_generated", md)
        self.assertIn(result["slug"], md)

    def test_invalid_recipe_returns_error(self):
        result = mir.render_hector_cartoon({"missing": "required-fields"})
        self.assertFalse(result["success"])
        self.assertIn("Invalid recipe schema", result["error"])

    def test_generation_failure_twice_returns_error(self):
        registry = _stub_registry(
            raise_codes=["prompt_rejected", "prompt_rejected"])
        result = mir.render_hector_cartoon(SAMPLE_RECIPE, registry=registry)
        self.assertFalse(result["success"])
        self.assertIn("Generation failed twice", result["error"])
        # invoke was called twice
        self.assertEqual(registry.invoke.call_count, 2)

    def test_generation_recovery_on_retry(self):
        registry = _stub_registry(raise_codes=["prompt_rejected"])
        with mock.patch("subprocess.run", side_effect=self._potrace_stub):
            result = mir.render_hector_cartoon(SAMPLE_RECIPE, registry=registry)
        self.assertTrue(result["success"], msg=result)


# ---------------------------------------------------------------------------
# End-to-end News image renderer (paths redirected, registry mocked)
# ---------------------------------------------------------------------------

class TestRenderNewsImage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)
        self._orig_articles_dir = mir.ASTRO_ARTICLES_DIR
        self._orig_images = mir.ASTRO_ARTICLES_IMAGES_PUBLIC_DIR
        mir.ASTRO_ARTICLES_DIR = os.path.join(self.tmp, "articles-md")
        mir.ASTRO_ARTICLES_IMAGES_PUBLIC_DIR = os.path.join(
            self.tmp, "articles-img")

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        mir.ASTRO_ARTICLES_DIR = self._orig_articles_dir
        mir.ASTRO_ARTICLES_IMAGES_PUBLIC_DIR = self._orig_images

    def test_happy_path(self):
        registry = _stub_registry()
        result = mir.render_news_image(SAMPLE_REQUEST, registry=registry)
        self.assertTrue(result["success"], msg=result)
        self.assertTrue(os.path.isfile(result["image_path"]))
        # John Roe removed by likeness gate
        self.assertIn("John Roe", result["removed_entities"])
        self.assertNotIn("Jane Doe", result["removed_entities"])

    def test_patches_existing_article_md(self):
        # Pre-create an article md to be patched
        os.makedirs(mir.ASTRO_ARTICLES_DIR, exist_ok=True)
        md_path = os.path.join(
            mir.ASTRO_ARTICLES_DIR, SAMPLE_REQUEST["article_slug"] + ".md")
        with open(md_path, "w") as f:
            f.write("---\nheadline: existing\nlede: x\n---\nbody\n")

        registry = _stub_registry()
        result = mir.render_news_image(SAMPLE_REQUEST, registry=registry)
        self.assertTrue(result["success"])
        self.assertTrue(result["article_md_updated"])
        with open(md_path) as f:
            patched = f.read()
        self.assertIn("image:", patched)
        self.assertIn("source: ai_generated", patched)

    def test_editorial_cartoon_register_rejected(self):
        d = dict(SAMPLE_REQUEST, visual_register="editorial_cartoon")
        registry = _stub_registry()
        result = mir.render_news_image(d, registry=registry)
        self.assertFalse(result["success"])
        self.assertIn("render_hector_cartoon", result["error"])

    def test_missing_article_md_returns_not_updated(self):
        registry = _stub_registry()
        result = mir.render_news_image(SAMPLE_REQUEST, registry=registry)
        self.assertTrue(result["success"])
        self.assertFalse(result["article_md_updated"])


# ---------------------------------------------------------------------------
# Slot 1 LoRA detection
# ---------------------------------------------------------------------------

class TestSlot1LoraDetection(unittest.TestCase):

    def test_lora_detected_when_in_chain_head(self):
        registry = mock.MagicMock()
        registry.resolve_provider_chain.return_value = [
            "civitai-hector-lora-v1", "openai-gpt-image-1"]
        self.assertTrue(mir._slot1_is_hector_lora(registry))

    def test_lora_not_detected_for_other_providers(self):
        registry = mock.MagicMock()
        registry.resolve_provider_chain.return_value = ["openai-gpt-image-1"]
        self.assertFalse(mir._slot1_is_hector_lora(registry))

    def test_empty_chain_returns_false(self):
        registry = mock.MagicMock()
        registry.resolve_provider_chain.return_value = []
        self.assertFalse(mir._slot1_is_hector_lora(registry))


# ---------------------------------------------------------------------------
# Slash command integration
# ---------------------------------------------------------------------------

class TestSlashCommands(unittest.TestCase):

    def test_hector_render_no_args_returns_usage(self):
        import slash_commands
        result = slash_commands._cmd_hector_render([])
        self.assertIn("Usage:", result)
        self.assertIn("recipe.json", result)

    def test_news_image_render_no_args_returns_usage(self):
        import slash_commands
        result = slash_commands._cmd_news_image_render([])
        self.assertIn("Usage:", result)
        self.assertIn("request.json", result)

    def test_hector_render_missing_file(self):
        import slash_commands
        result = slash_commands._cmd_hector_render(
            ["nonexistent-recipe-file-9999.json"])
        self.assertIn("Recipe not found", result)

    def test_news_image_render_missing_file(self):
        import slash_commands
        result = slash_commands._cmd_news_image_render(
            ["nonexistent-request-file-9999.json"])
        self.assertIn("Request not found", result)

    def test_hector_render_invalid_json(self):
        import slash_commands
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            path = f.name
        try:
            result = slash_commands._cmd_hector_render([path])
            self.assertIn("JSON parse error", result)
        finally:
            os.unlink(path)

    def test_known_commands_includes_new(self):
        import slash_commands
        self.assertIn("/hector-render", slash_commands.KNOWN_COMMANDS)
        self.assertIn("/news-image-render", slash_commands.KNOWN_COMMANDS)

    def test_is_runtime_command_recognizes_new(self):
        import slash_commands
        self.assertTrue(slash_commands.is_runtime_command(
            "/hector-render foo.json"))
        self.assertTrue(slash_commands.is_runtime_command(
            "/news-image-render bar.json"))


if __name__ == "__main__":
    unittest.main()
