# `.ora/tools/` — Execution Review adapter-family check scripts

Execution Review Phase 8 Chunk C (§4). These are **self-contained, import-free**
check scripts that the Ora evidence runner executes inside its sandbox. They are
the canonical templates; copy the ones you need into any repo's own `.ora/tools/`
and declare them in that repo's `.ora/evidence.yaml`.

## Why self-contained

The evidence runner's sandbox denies reads under `~/ora` (Ora's own module tree)
and under the private roots, and a linked worktree's `.git` is unreadable inside
it. So a check script:

- imports **only the Python standard library** (plus PyYAML, which lives in
  site-packages outside the deny roots) — **never `orchestrator.*`**; and
- runs **no `git`** inside the sandbox. Every git-derived input (the changed-file
  list, the note-title universe) is precomputed by the runner *outside* the
  sandbox and handed to the check as a read-only file.

## Inputs contract

A check declares what it needs with `inputs:` in the catalog. The runner builds
each declared input into a read-only directory and points the check at it via the
`ORA_CHECK_INPUTS` environment variable:

| input            | file in `$ORA_CHECK_INPUTS` | contents |
|------------------|-----------------------------|----------|
| `changed_files`  | `changed-files.txt`         | one repo-relative path per line (deletions excluded) |
| `title_universe` | `title-universe.txt`        | one repo-relative path per line = the note universe at check time, including this turn's new notes |

A check that declares inputs but runs with no pre-execution base (base-unknown) is
refused cleanly by the runner — it never runs against a missing input.

## The scripts

- **`vault_frontmatter_lint.py`** — strict YAML parse of each changed markdown
  file's frontmatter; distinguishes *malformed* from *absent*. Args:
  `--frontmatter optional|required`, `--require <k1,k2,…>`.
- **`vault_wikilink_check.py`** — resolves body `[[targets]]` against
  `title-universe.txt` (Obsidian bare-title semantics). Args:
  `--allow-file <path>` (a tolerated-targets allowlist). Runs **no git**.
- **`render_validity.py`** — mechanical validity of rendered artifacts (SVG/XML
  parse, docx/pptx/xlsx zip-open, PDF header). Perceptual quality is out of scope
  by construction — that stays a judgment lane.

Every script: stdout is machine-readable JSON; exit `0` iff ok, `1` on findings,
`2` on usage error, `3` on tooling unavailable; a listed-but-missing file is
skipped (`skipped_missing`), never a crash — a deleted note/artifact must not
false-FAIL a routine turn.

## Declaring in `.ora/evidence.yaml`

```yaml
checks:
  vault-frontmatter:
    argv: [python, .ora/tools/vault_frontmatter_lint.py, --frontmatter, optional, --require, type]
    mutates: false
    network: deny
    inputs: [changed_files]
    scope: changed_files
  vault-wikilinks:
    argv: [python, .ora/tools/vault_wikilink_check.py, --allow-file, .ora/tools/wikilink-allowlist.txt]
    mutates: false
    network: deny
    inputs: [changed_files, title_universe]
    scope: changed_files
```

`python` resolves to the running interpreter (`sys.executable`), so the
python-vs-python3 split never bites and the invocation stays platform-neutral.

## `.ora/` is write-protected

`.ora/` anywhere in any repo is a write-protected config path: a model-issued
write into it (including via `git checkout/restore/mv` of a pathspec touching
`.ora/`) escalates to the irreversible gate. A check script is as load-bearing as
the catalog that names it. The write-gate raises the bar; the verify stage and the
planning-set acceptance criteria are the architectural closure against an executor
weakening its own check.
