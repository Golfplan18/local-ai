# Persistent Context Directory

Every .md file in this directory is loaded automatically at the start of every
session and injected into the system prompt after boot.md and mind.md.

Use this for observations, decisions, conventions, and any lightweight persistent
memory that should be available every session without going through RAG retrieval.

Keep files small. The total content of this directory should not exceed ~2,000
tokens (roughly 8,000 characters). Large files belong in the vault, not here.

The model can write to this directory using the file_write tool (subject to
user approval). Files are plain Markdown.
