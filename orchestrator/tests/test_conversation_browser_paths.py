"""Relocated-vault paths used by the conversation browser."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
for value in (REPO, REPO / "orchestrator", REPO / "server"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))
os.environ.setdefault("ORA_HOME", str(REPO))

from orchestrator.embedding import install_test_stub  # noqa: E402

install_test_stub()
from server import app as server  # noqa: E402


class ConversationBrowserPathTests(unittest.TestCase):
    def test_legacy_source_metadata_uses_configured_vault(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            server.rp, "vault_dir", return_value=Path(td) / "Relocated Vault",
        ):
            row = server._browser_row_from_chroma_hit(
                logical_collection="knowledge",
                embedding_id="engram-1",
                document="# A note\n\nBody",
                metadata={"type": "engram", "source": "A Note.md"},
                query="note",
                score=1.0,
            )
        self.assertEqual(
            row["path"],
            str(Path(td) / "Relocated Vault" / "Engrams" / "A Note.md"),
        )

    def test_markdown_fallback_checks_configured_vault(self):
        vault = Path(tempfile.gettempdir()) / "conversation-browser-vault"
        with (
            mock.patch.object(server.rp, "vault_dir", return_value=vault),
            mock.patch.object(server.os.path, "isdir", return_value=False) as isdir,
        ):
            self.assertEqual(server._browser_vault_markdown_rows("needle"), [])
        isdir.assert_called_once_with(str(vault))


if __name__ == "__main__":
    unittest.main()
