#!/usr/bin/env python3
"""
refresh-image-modes.py — Submit the 4 remaining image-input modes with
their images attached, poll for completion, patch each Paper, commit.

Reuses helpers from refresh-mode-pages.py:
  * extract_assistant_body
  * patch_paper
  * find_canonical_conversation
  * commit_and_push

Sequential one-at-a-time (Ora's pipeline serializes anyway under our
configuration). Each image-mode pipeline run is ~13 minutes including
the depth-retry path the first run exercised. Total ~52 min if all
succeed first try; doubles if depth retries fire.
"""

from __future__ import annotations
import base64, json, sys, time, urllib.request
from pathlib import Path

# Import shared helpers from the main script
import importlib.util
spec = importlib.util.spec_from_file_location("rmp", "/Users/oracle/ora/scripts/refresh-mode-pages.py")
rmp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rmp)

VAULT = Path.home() / "Documents/vault"
IMG_DIR = Path.home() / "Documents/refresh-mode-images"
LOG_PATH = Path.home() / "Documents/conversations/refresh-image-modes-log.txt"
PLACEHOLDER = rmp.PLACEHOLDER_LINE
PORT = 5000
TIMEOUT_PER_MODE = 60 * 35  # 35 min per mode (allow for depth retries)

# (slug, image_filename, paper_filename, prime_prompt) per mode
MANIFEST = [
    (
        "place-reading-genius-loci",
        "place-reading-genius-loci.jpg",
        "Paper — Place Reading and Genius Loci.md",
        "Place reading of the new High Line extension — genius loci, prospect-refuge, Christopher Alexander pattern language, Kevin Lynch's imageability, the affordances the design surfaces and the ones it forecloses. What this place teaches about urban-park design.",
    ),
    (
        "compositional-dynamics",
        "compositional-dynamics.jpg",
        "Paper — Compositional Dynamics.md",
        "Compositional dynamics reading of the new MoMA exhibition poster — figure-ground, gestalt grouping (common-fate, good-continuation, proximity), Arnheim force vectors, what the eye traces and where it settles, where the tension and resolution land in the layout.",
    ),
    (
        "information-density",
        "information-density.png",
        "Paper — Information Density.md",
        "Critique this chart with a Tufte data-ink-ratio audit: a quarterly revenue dashboard with stacked bar segments for product line, secondary axis with a line series for margin %, gridlines, a legend on the right, and a colored background. Apply Tufte plus Bertin variables plus Cleveland-McGill elementary perceptual tasks ranking.",
    ),
    (
        "spatial-reasoning",
        "spatial-reasoning.jpg",
        "Paper — Spatial Reasoning.md",
        "Annotate my concept map of organizational change. Nodes: leadership-buy-in, middle-management-resistance, frontline-adoption, training-program, change-champions, communication-cadence, success-metrics. Where are the missing edges? Which clusters are under-specified? Tversky-correspondence checks on proximity / containment / connection.",
    ),
]


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def ensure_placeholder(paper_path: Path, prime_prompt: str) -> None:
    """Reset the Paper's `## Ora's output` section to use the canonical
    placeholder and the supplied prime prompt as Example question.

    Idempotent — safe to call even if the placeholder is already present.
    """
    text = paper_path.read_text(encoding="utf-8")
    if PLACEHOLDER in text:
        log(f"  placeholder already in {paper_path.name}")
        return
    # Replace the section between `## Ora's output` and the next `## ` heading
    start = text.find("## Ora's output")
    if start < 0:
        log(f"  WARN: no '## Ora's output' section in {paper_path.name} — inserting one")
        # Find a reasonable insertion point; for safety, append at end
        text = text + "\n\n## Ora's output\n\n"
        start = text.find("## Ora's output")
    end = text.find("\n## ", start + 1)
    if end < 0:
        end = len(text)
    new_section = (
        "## Ora's output\n\n"
        f"**Example question:** {prime_prompt}\n\n"
        "**Ora's response:**\n\n"
        f"{PLACEHOLDER}\n\n"
    )
    text = text[:start] + new_section + text[end:]
    paper_path.write_text(text, encoding="utf-8")
    log(f"  reset placeholder in {paper_path.name}")


def submit_with_image(slug: str, prompt: str, image_path: Path) -> tuple[str, float]:
    """POST /chat with image attached. Returns (panel_id, submit_time)."""
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    panel_id = f"refresh-img-{slug}-{int(time.time())}"
    body = json.dumps({
        "message": prompt,
        "history": [],
        "panel_id": panel_id,
        "is_main_feed": True,
        "tag": "",
        "manual_mode_selection": slug,
        "framework_selected": "",
        "attachments": [{
            "name": image_path.name,
            "type": mime,
            "data": f"data:{mime};base64,{img_b64}",
        }],
    }).encode()
    submit_time = time.time()
    req = urllib.request.Request(
        f"http://localhost:{PORT}/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            try:
                resp.read(1)
            except Exception:
                pass
    except Exception:
        pass  # SSE timeout-on-read is expected
    return panel_id, submit_time


def poll(prompt: str, submit_time: float) -> str | None:
    """Poll for the canonical conversation file."""
    deadline = time.time() + TIMEOUT_PER_MODE
    while time.time() < deadline:
        path = rmp.find_canonical_conversation(prompt, submit_time)
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8")
                body = rmp.extract_assistant_body(text)
                if body and len(body) > 500:
                    return body
            except Exception:
                pass
        time.sleep(20)
    return None


def commit_paper(slug: str) -> None:
    import subprocess
    try:
        subprocess.run(
            ["git", "-C", str(VAULT), "add", "-A"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(VAULT), "commit", "-m",
             f"refresh-image-modes: {slug} (image-attached resubmission)"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(VAULT), "push"],
            check=True, capture_output=True,
        )
        log(f"  committed + pushed: {slug}")
    except subprocess.CalledProcessError as e:
        log(f"  WARN: commit failed for {slug}: {e}")


def main() -> int:
    log("=== refresh-image-modes start ===")
    succeeded = []
    failed = []
    for slug, img_name, paper_name, prompt in MANIFEST:
        log(f"--- {slug} ---")
        img = IMG_DIR / img_name
        paper = VAULT / paper_name
        if not img.exists():
            log(f"  SKIP: missing image {img}")
            failed.append((slug, "missing image"))
            continue
        if not paper.exists():
            log(f"  SKIP: missing paper {paper}")
            failed.append((slug, "missing paper"))
            continue

        ensure_placeholder(paper, prompt)

        log(f"  submitting with image ({img.stat().st_size:,} bytes)...")
        panel_id, submit_time = submit_with_image(slug, prompt, img)
        log(f"  panel_id={panel_id} submitted at {submit_time:.0f}")

        log(f"  polling (up to {TIMEOUT_PER_MODE//60} min)...")
        body = poll(prompt, submit_time)
        if body is None:
            log(f"  TIMEOUT — no canonical conversation found")
            failed.append((slug, "timeout"))
            continue
        log(f"  poll returned {len(body)} chars")
        ok = rmp.patch_paper(paper, body)
        if not ok:
            log(f"  PATCH FAILED — placeholder may have shifted")
            failed.append((slug, "patch failed"))
            continue
        log(f"  patched + ready to commit")
        commit_paper(slug)
        succeeded.append(slug)

    log(f"=== done: succeeded={succeeded} failed={failed} ===")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
