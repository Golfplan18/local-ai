"""
review.py — Human Review Interface for Document Processing Pipeline (Phase 10, Step 14)

Simple local web application for reviewing extracted notes.
Features:
  - Side-by-side note display with quality gate reasoning
  - Approve / reject / edit buttons
  - Batch navigation by topic
  - Edit-in-place with live preview

Runs on localhost:5005 to avoid conflict with the main chat server (5000).

Usage:
    /opt/homebrew/bin/python3 ~/ora/server/review.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, redirect, url_for

REVIEW_DIR = os.path.expanduser("~/ora/data/review-queue/")
STAGING_DIR = os.path.expanduser("~/ora/data/extraction-staging/")
REJECTED_DIR = os.path.expanduser("~/ora/data/review-rejected/")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# HTML template (single file — ~200 lines as specified)
# ---------------------------------------------------------------------------

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ora — Note Review</title>
    <style>
        :root {
            --bg: #1e1e2e;
            --surface: #282a36;
            --surface-bright: #313244;
            --text: #cdd6f4;
            --text-dim: #6c7086;
            --accent: #89b4fa;
            --green: #a6e3a1;
            --red: #f38ba8;
            --yellow: #f9e2af;
            --border: #45475a;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'SF Mono', monospace;
            background: var(--bg);
            color: var(--text);
            padding: 20px;
        }
        h1 { color: var(--accent); margin-bottom: 10px; font-size: 1.4em; }
        .stats {
            display: flex; gap: 20px; margin-bottom: 20px;
            color: var(--text-dim); font-size: 0.9em;
        }
        .stats span { padding: 4px 12px; border-radius: 4px; background: var(--surface); }
        .stats .pending { color: var(--yellow); }
        .stats .approved { color: var(--green); }
        .stats .rejected { color: var(--red); }

        .note-list {
            display: flex; flex-direction: column; gap: 12px;
        }
        .note-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            cursor: pointer;
            transition: border-color 0.2s;
        }
        .note-card:hover { border-color: var(--accent); }
        .note-card h3 { color: var(--text); font-size: 1em; margin-bottom: 8px; }
        .note-card .meta {
            font-size: 0.8em; color: var(--text-dim);
            display: flex; gap: 12px; flex-wrap: wrap;
        }
        .note-card .reasons {
            font-size: 0.8em; color: var(--yellow); margin-top: 8px;
        }

        .review-panel {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
        }
        .review-panel h2 { color: var(--accent); margin-bottom: 12px; }
        .review-panel .body-preview {
            background: var(--surface-bright);
            border-radius: 4px;
            padding: 16px;
            margin: 12px 0;
            white-space: pre-wrap;
            font-size: 0.9em;
            line-height: 1.6;
            max-height: 400px;
            overflow-y: auto;
        }
        .review-panel .checks {
            margin: 12px 0;
            font-size: 0.85em;
        }
        .review-panel .checks .pass { color: var(--green); }
        .review-panel .checks .fail { color: var(--red); }
        .review-panel .checks .flag { color: var(--yellow); }

        .actions {
            display: flex; gap: 10px; margin-top: 16px;
        }
        .btn {
            padding: 8px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            font-family: inherit;
        }
        .btn-approve { background: var(--green); color: var(--bg); }
        .btn-reject { background: var(--red); color: var(--bg); }
        .btn-edit { background: var(--yellow); color: var(--bg); }
        .btn-skip { background: var(--surface-bright); color: var(--text-dim); }
        .btn:hover { opacity: 0.9; }

        textarea {
            width: 100%;
            min-height: 300px;
            background: var(--surface-bright);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 12px;
            font-family: inherit;
            font-size: 0.9em;
            line-height: 1.6;
            resize: vertical;
        }
        .edit-title {
            width: 100%;
            background: var(--surface-bright);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 8px 12px;
            font-family: inherit;
            font-size: 1em;
            margin-bottom: 8px;
        }
        .nav {
            display: flex; justify-content: space-between; margin: 16px 0;
        }
        .nav a {
            color: var(--accent); text-decoration: none;
            padding: 4px 12px; border-radius: 4px;
            background: var(--surface);
        }
        .nav a:hover { background: var(--surface-bright); }
        .empty {
            text-align: center; padding: 60px;
            color: var(--text-dim); font-size: 1.1em;
        }
    </style>
</head>
<body>
    <h1>Ora — Note Review Queue</h1>
    {% if mode == 'list' %}
    <div class="stats">
        <span class="pending">Pending: {{ counts.pending }}</span>
        <span class="approved">Approved: {{ counts.approved }}</span>
        <span class="rejected">Rejected: {{ counts.rejected }}</span>
    </div>
    {% if notes %}
    <div class="note-list">
        {% for note in notes %}
        <a href="/review/{{ note.filename }}" style="text-decoration:none;">
        <div class="note-card">
            <h3>{{ note.title }}</h3>
            <div class="meta">
                <span>Type: {{ note.note_type }}{% if note.subtype %} / {{ note.subtype }}{% endif %}</span>
                <span>Source: {{ note.source_file | truncate(40) }}</span>
                <span>Status: {{ note.status }}</span>
            </div>
            {% if note.review_reasons %}
            <div class="reasons">{{ note.review_reasons | join('; ') | truncate(120) }}</div>
            {% endif %}
        </div>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div class="empty">No notes in the review queue.</div>
    {% endif %}

    {% elif mode == 'review' %}
    <div class="nav">
        <a href="/">← Back to list</a>
        {% if prev_file %}<a href="/review/{{ prev_file }}">← Previous</a>{% endif %}
        {% if next_file %}<a href="/review/{{ next_file }}">Next →</a>{% endif %}
    </div>
    <div class="review-panel">
        {% if editing %}
        <h2>Edit Note</h2>
        <form method="POST" action="/action/{{ filename }}">
            <input type="hidden" name="action" value="save_edit">
            <input class="edit-title" name="title" value="{{ note.title }}">
            <textarea name="body">{{ note.body }}</textarea>
            <div class="actions">
                <button type="submit" class="btn btn-approve">Save &amp; Approve</button>
                <a href="/review/{{ filename }}" class="btn btn-skip">Cancel</a>
            </div>
        </form>
        {% else %}
        <h2>{{ note.title }}</h2>
        <div class="meta" style="margin-bottom:12px; font-size:0.85em; color:var(--text-dim);">
            Type: {{ note.note_type }}{% if note.subtype %} / {{ note.subtype }}{% endif %}
            &nbsp;|&nbsp; Source: {{ note.source_file }}
        </div>
        <div class="body-preview">{{ note.body }}</div>

        {% if note.review_reasons %}
        <div class="checks">
            <strong>Review reasons:</strong>
            {% for reason in note.review_reasons %}
            <div class="flag">• {{ reason }}</div>
            {% endfor %}
        </div>
        {% endif %}

        {% if note.checks %}
        <div class="checks">
            <strong>Quality checks:</strong>
            {% for name, result in note.checks.items() %}
            <div class="{{ 'pass' if result.get('pass', result == 'pass') else 'fail' }}">
                {{ name }}: {{ result.get('detail', result) if result is mapping else result }}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if note.relationships %}
        <div class="checks">
            <strong>Relationships:</strong>
            {% for rel in note.relationships %}
            <div>→ {{ rel.type }}: {{ rel.target }} ({{ rel.confidence }})</div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="actions">
            <form method="POST" action="/action/{{ filename }}" style="display:inline;">
                <input type="hidden" name="action" value="approve">
                <button type="submit" class="btn btn-approve">Approve</button>
            </form>
            <form method="POST" action="/action/{{ filename }}" style="display:inline;">
                <input type="hidden" name="action" value="reject">
                <button type="submit" class="btn btn-reject">Reject</button>
            </form>
            <a href="/review/{{ filename }}?edit=1" class="btn btn-edit">Edit</a>
        </div>
        {% endif %}
    </div>
    {% endif %}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """List all notes in the review queue."""
    notes = _load_review_queue()
    counts = {
        "pending": sum(1 for n in notes if n.get("status") == "pending"),
        "approved": sum(1 for n in notes if n.get("status") == "approved"),
        "rejected": sum(1 for n in notes if n.get("status") == "rejected"),
    }
    return render_template_string(TEMPLATE, mode="list", notes=notes, counts=counts)


@app.route("/review/<filename>")
def review(filename):
    """Review a single note."""
    note = _load_note(filename)
    if not note:
        return redirect(url_for("index"))

    editing = request.args.get("edit") == "1"

    # Navigation
    all_files = _get_review_files()
    current_idx = all_files.index(filename) if filename in all_files else -1
    prev_file = all_files[current_idx - 1] if current_idx > 0 else None
    next_file = all_files[current_idx + 1] if current_idx < len(all_files) - 1 else None

    return render_template_string(
        TEMPLATE, mode="review", note=note, filename=filename,
        editing=editing, prev_file=prev_file, next_file=next_file,
    )


@app.route("/action/<filename>", methods=["POST"])
def action(filename):
    """Handle approve/reject/edit actions."""
    action_type = request.form.get("action")
    note = _load_note(filename)

    if not note:
        return redirect(url_for("index"))

    from datetime import datetime
    note["reviewed_at"] = datetime.now().isoformat()

    if action_type == "approve":
        note["status"] = "approved"
        _save_note(filename, note)
        # Move to staging directory as vault-ready file
        _approve_note(note)

    elif action_type == "reject":
        note["status"] = "rejected"
        _save_note(filename, note)
        # Move to rejected directory
        _reject_note(filename, note)

    elif action_type == "save_edit":
        # Update note with edited content
        note["title"] = request.form.get("title", note.get("title", ""))
        note["body"] = request.form.get("body", note.get("body", ""))
        note["status"] = "approved"
        _save_note(filename, note)
        _approve_note(note)

    # Navigate to next pending note
    next_pending = _get_next_pending(filename)
    if next_pending:
        return redirect(url_for("review", filename=next_pending))
    return redirect(url_for("index"))


@app.route("/api/stats")
def api_stats():
    """Return review queue statistics as JSON."""
    notes = _load_review_queue()
    return jsonify({
        "total": len(notes),
        "pending": sum(1 for n in notes if n.get("status") == "pending"),
        "approved": sum(1 for n in notes if n.get("status") == "approved"),
        "rejected": sum(1 for n in notes if n.get("status") == "rejected"),
    })


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def _load_review_queue() -> list[dict]:
    """Load all notes from the review queue directory."""
    notes = []
    if not os.path.exists(REVIEW_DIR):
        return notes

    for f in sorted(os.listdir(REVIEW_DIR)):
        if f.endswith(".json"):
            path = os.path.join(REVIEW_DIR, f)
            try:
                with open(path, "r") as fh:
                    data = json.load(fh)
                data["filename"] = f
                notes.append(data)
            except (json.JSONDecodeError, IOError):
                continue

    return notes


def _load_note(filename: str) -> dict | None:
    """Load a single note from the review queue."""
    path = os.path.join(REVIEW_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _save_note(filename: str, note: dict):
    """Save a note back to the review queue."""
    path = os.path.join(REVIEW_DIR, filename)
    with open(path, "w") as f:
        json.dump(note, f, indent=2)


def _get_review_files() -> list[str]:
    """Get sorted list of review queue filenames."""
    if not os.path.exists(REVIEW_DIR):
        return []
    return sorted(f for f in os.listdir(REVIEW_DIR) if f.endswith(".json"))


def _get_next_pending(current_filename: str) -> str | None:
    """Get the next pending note after the current one."""
    files = _get_review_files()
    current_idx = files.index(current_filename) if current_filename in files else -1

    # Search forward from current position
    for f in files[current_idx + 1:]:
        note = _load_note(f)
        if note and note.get("status") == "pending":
            return f

    # Wrap around
    for f in files[:current_idx]:
        note = _load_note(f)
        if note and note.get("status") == "pending":
            return f

    return None


def _approve_note(note: dict):
    """Write an approved note to the staging directory as a vault-ready markdown file."""
    os.makedirs(STAGING_DIR, exist_ok=True)

    title = note.get("title", "Untitled")
    safe_title = _sanitize(title)
    path = os.path.join(STAGING_DIR, f"{safe_title}.md")

    # Build markdown content
    lines = ["---"]
    fm = note.get("yaml_frontmatter", {})

    nexus = fm.get("nexus", "")
    if isinstance(nexus, list) and nexus:
        lines.append("nexus:")
        for n in nexus:
            lines.append(f"  - {n}")
    else:
        lines.append("nexus:")

    lines.append(f"type: {fm.get('type', 'working')}")

    tags = fm.get("tags", [])
    if isinstance(tags, list) and tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {t}")
    else:
        lines.append("tags:")

    subtype = note.get("subtype")
    if subtype:
        lines.append(f"subtype: {subtype}")

    rels = note.get("relationships", [])
    if rels:
        lines.append("relationships:")
        for rel in rels:
            if isinstance(rel, dict):
                lines.append(f"  - type: {rel.get('type', 'supports')}")
                lines.append(f"    target: \"{rel.get('target', '')}\"")
                lines.append(f"    confidence: {rel.get('confidence', 'medium')}")

    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(note.get("body", ""))

    source = note.get("source_file", "")
    if source:
        lines.append("")
        lines.append(f"**Source document:** {source}")

    counter = 1
    while os.path.exists(path):
        path = os.path.join(STAGING_DIR, f"{safe_title}-{counter}.md")
        counter += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _reject_note(filename: str, note: dict):
    """Move a rejected note to the rejected directory."""
    os.makedirs(REJECTED_DIR, exist_ok=True)
    dest = os.path.join(REJECTED_DIR, filename)
    with open(dest, "w") as f:
        json.dump(note, f, indent=2)


def _sanitize(title: str) -> str:
    """Sanitize a title for use as a filename."""
    import re
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()
    return safe[:200] if safe else "Untitled"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(REVIEW_DIR, exist_ok=True)
    os.makedirs(STAGING_DIR, exist_ok=True)

    print("Ora — Note Review Interface")
    print(f"  Review queue: {REVIEW_DIR}")
    print(f"  Staging dir:  {STAGING_DIR}")
    print(f"  Server:       http://localhost:5005")
    print()

    app.run(host="127.0.0.1", port=5005, debug=False)
