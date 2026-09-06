"""Lossless operations on the one authoritative Tasks section of a Matrix.

Lines remain source spans. Only explicitly selected lines and indentation move;
the parsed projection is never serialized back into the user's document.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from datetime import date
from pathlib import Path

try:
    from . import operation_matrix as om, matrix_classifier as classifier
except ImportError:  # top-level runtime imports
    import operation_matrix as om
    import matrix_classifier as classifier


class TaskError(Exception):
    def __init__(self, message, code="refused", status=400, saved=False):
        super().__init__(message)
        self.code, self.status, self.saved = code, status, saved


TASK = re.compile(r"^([ \t]*)([-+*])([ \t]+)\[([ xX])\]([ \t]+)([^\r\n]*)(\r?\n)?$")
HEADING = re.compile(r"^ {0,3}##[ \t]+(.+?)[ \t]*(?:[ \t]+#+[ \t]*)?$")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
MARKER = re.compile(r"^[ \t]*<!--[ \t]*MASTER_MATRIX_PROJECTION_(START|END)(.*?)-->[ \t]*$")
DATE = re.compile(r"[ \t]+✅[ \t]+(\d{4}-\d{2}-\d{2})([ \t]*)$")
FIELDS = {
    "add": {"destination", "position", "value"},
    "edit": {"target", "value"},
    "delete": {"target"},
    "reorder": {"target", "destination", "position"},
    "indent": {"target"}, "outdent": {"target"}, "promote": {"target"},
    "complete": {"target"}, "reopen": {"target"},
    "set-date": {"target", "value"}, "clear-date": {"target"},
}


def validate_request(body):
    if not isinstance(body, dict) or not isinstance(body.get("operation"), str):
        raise TaskError("Choose one named task operation.")
    op = body["operation"]
    if op not in FIELDS or set(body) != {"expected_digest", "operation"} | FIELDS[op]:
        raise TaskError("The task operation has missing or unsupported fields.")
    if not all(isinstance(value, str) for value in body.values()):
        raise TaskError("Task operation values and references must be text.")
    if not re.fullmatch(r"[0-9a-f]{64}", body["expected_digest"]):
        raise TaskError("A current Matrix digest is required.")
    if op in ("add", "edit") and (not body["value"].strip() or any(c in body["value"] for c in "\r\n\x00")):
        raise TaskError("Task text must be one nonempty line.")
    if op == "set-date":
        try:
            if date.fromisoformat(body["value"]).isoformat() != body["value"]:
                raise ValueError
        except ValueError:
            raise TaskError("Completion date must be a real date in YYYY-MM-DD form.")
    if op in ("add", "reorder") and body["position"] not in (
        ("root", "before", "after", "child") if op == "add" else ("before", "after")
    ):
        raise TaskError("Choose a supported task position.")


def _completion(label):
    match = DATE.search(label)
    valid = False
    if match:
        try:
            valid = date.fromisoformat(match[1]).isoformat() == match[1]
        except ValueError:
            pass
    ambiguous = "✅" in label and (label.count("✅") != 1 or not valid)
    return (match[1] if valid and not ambiguous else None), ambiguous, match


class Document:
    def __init__(self, text, digest, identity, classification):
        self.text, self.digest, self.identity = text, digest, identity
        self.lines = text.splitlines(keepends=True)
        self.root_ref = f"{identity}:{digest}:root"
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.section = None
        self.task_sections = []
        self.error = None
        self.tasks = []
        self.headings = []
        self.projection_end = None
        _, fm_end = om._split_frontmatter(text)
        offset = 0
        fence = None
        fence_start = None
        self.fences = []
        comment_start = None
        projection = False
        markers = []
        task_heads = []
        eligible = {}
        for index, line in enumerate(self.lines):
            plain = line.rstrip("\r\n")
            if offset < fm_end:
                offset += len(line)
                continue
            if comment_start is not None:
                if "-->" in plain:
                    self.fences.append((comment_start, index + 1))
                    comment_start = None
                offset += len(line)
                continue
            opening = FENCE.match(plain)
            if fence:
                if opening and opening[1][0] == fence[0] and len(opening[1]) >= fence[1] and not opening[2].strip():
                    self.fences.append((fence_start, index + 1))
                    fence = None
                offset += len(line)
                continue
            if opening and not (opening[1][0] == "`" and "`" in opening[2]):
                fence = (opening[1][0], len(opening[1]))
                fence_start = index
                offset += len(line)
                continue
            marker = MARKER.match(plain)
            if marker:
                kind = marker[1]
                markers.append(kind)
                if kind == "START":
                    if projection or len(markers) != 1:
                        self.error = "The strategic projection has duplicate or misplaced markers."
                    projection = True
                else:
                    if not projection or markers != ["START", "END"] or marker[2].strip():
                        self.error = "The strategic projection has an unmatched or malformed END marker."
                    projection = False
                    self.projection_end = index + 1
                offset += len(line)
                continue
            if plain.lstrip().startswith("<!--") and "MASTER_MATRIX_PROJECTION_" in plain:
                self.error = "The strategic projection contains a malformed delimiter."
            if plain.lstrip().startswith("<!--"):
                if "-->" not in plain:
                    comment_start = index
                offset += len(line)
                continue
            heading = HEADING.match(plain)
            if heading:
                name = re.sub(r"[ \t]+#+[ \t]*$", "", heading[1]).strip().lower()
                self.headings.append((index, name))
                if name == "tasks":
                    task_heads.append(index)
                    if projection:
                        self.error = "Tasks inside a strategic projection cannot be edited."
            if not projection:
                match = TASK.match(line)
                if match:
                    eligible[index] = (match, offset)
            if "<!--" in plain and "-->" not in plain[plain.index("<!--") + 4:]:
                comment_start = index
            offset += len(line)
        if projection:
            self.error = "The strategic projection has no valid END marker."
        self.open_fence = fence is not None or comment_start is not None
        if fence:
            self.fences.append((fence_start, len(self.lines)))
        if comment_start is not None:
            self.fences.append((comment_start, len(self.lines)))
        if len(task_heads) > 1:
            self.error = "There is more than one Tasks section; resolve the duplicate in the original Matrix."
        self.task_sections = [(head, next((i for i, _ in self.headings if i > head), len(self.lines))) for head in task_heads]
        if len(task_heads) == 1:
            head = task_heads[0]
            end = next((i for i, _ in self.headings if i > head), len(self.lines))
            self.section = (head + 1, end)
            if any(MARKER.match(line.rstrip("\r\n")) for line in self.lines[head + 1:end]):
                self.error = "The Tasks section crosses a strategic projection boundary."
            stack = []
            for index in range(head + 1, end):
                line = self.lines[index]
                if index not in eligible:
                    if line.strip():
                        while stack and not (line.startswith(stack[-1]["indent"] + " ") or line.startswith(stack[-1]["indent"] + "\t")):
                            stack.pop()
                    continue
                match, start = eligible[index]
                indent = match[1]
                while stack and len(stack[-1]["indent"].expandtabs(4)) >= len(indent.expandtabs(4)):
                    stack.pop()
                parent = stack[-1] if stack and indent.startswith(stack[-1]["indent"]) else None
                completed, ambiguous_date, _ = _completion(match[6])
                task = {"ref": f"{identity}:{digest}:{start}", "line": index,
                        "indent": indent, "match": match, "parent": parent,
                        "text": match[6], "done": match[4] != " ",
                        "depth": parent["depth"] + 1 if parent else 0,
                        "parent_ref": parent["ref"] if parent else None,
                        "completion_date": completed, "date_ambiguous": ambiguous_date,
                        "ambiguous": bool(indent and parent is None)}
                self.tasks.append(task)
                stack.append(task)
            for task in self.tasks:
                end_line = task["line"] + 1
                attached = False
                for i in range(end_line, end):
                    line = self.lines[i]
                    if not line.strip():
                        continue
                    if not line.startswith(task["indent"] + " ") and not line.startswith(task["indent"] + "\t"):
                        break
                    end_line = i + 1
                    if i not in eligible:
                        attached = True
                task["end"] = end_line
                task["attached"] = attached
                task["children"] = [child for child in self.tasks if child["parent"] is task]
                if any(a < end_line and b > task["line"] and not (task["line"] <= a and b <= end_line) for a, b in self.fences):
                    task["ambiguous"] = True
        anchors = {"mission", "objectives"}
        if classification == "operation":
            anchors |= {"active milestones", "aspirational milestones", "active milestones (recurring)", "aspirational milestones (maturity gates)"}
        elif classification == "passion":
            anchors |= {"practices", "directions of travel"}
        else:
            anchors.add("milestones")
        self.insertion = self.projection_end
        if self.insertion is None:
            strategic = [i for i, (_, heading) in enumerate(self.headings) if heading in anchors]
            last = strategic[-1] if strategic else None
            self.insertion = self.headings[last + 1][0] if last is not None and last + 1 < len(self.headings) else len(self.lines)
        if self.open_fence and self.section is None and self.insertion == len(self.lines):
            self.error = "Close the fenced example or comment before adding a Tasks section."

    def public_tasks(self):
        rows = []
        for task in self.tasks:
            row = {key: task[key] for key in ("ref", "text", "done", "depth", "parent_ref", "completion_date", "date_ambiguous")}
            limits = {}
            if task["children"] or task["attached"]:
                limits["delete"] = "Move or promote children first; edit attached notes in the original Markdown before deleting."
            if task["ambiguous"]:
                for op in ("reorder", "indent", "outdent", "promote"):
                    limits[op] = "This task's indentation has no unambiguous parent; edit its placement in the original Markdown."
            if task["parent"] is None:
                for op in ("outdent", "promote"):
                    limits.setdefault(op, "This task is already at the root.")
            if task["date_ambiguous"]:
                for op in ("complete", "reopen", "set-date", "clear-date"):
                    limits[op] = "Completion metadata is ambiguous; edit the complete task label explicitly first."
            row["limitations"] = limits
            rows.append(row)
        return rows


def _identity(nexus, folder, path):
    return hashlib.sha256(f"{nexus}\0{folder}\0{path.absolute()}".encode()).hexdigest()[:24]


def _authenticate(nexus, folder, path, raw, vault):
    root = (vault or om.vault_root()).absolute()
    mdir = root / "Matrix"
    if root.is_symlink() or mdir.is_symlink() or path.parent.absolute() != mdir:
        raise TaskError("Matrix storage is not an authorized regular directory.", "unavailable", 409)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o444 or not os.access(path, os.R_OK):
        raise TaskError("Matrix storage is not a readable regular file.", "unavailable", 409)
    om._folder_component(folder, vault=root)
    text = raw.decode("utf-8")
    if nexus.strip().lower() not in om._frontmatter_nexus(text):
        raise TaskError("Matrix identity changed. Refresh before editing.", "conflict", 409)
    return text, stat.S_IMODE(info.st_mode)


def unavailable_group(nexus, reason):
    return {"nexus": nexus, "state": "unavailable", "reason": str(reason), "editable": False,
            "digest": None, "identity": None, "root_ref": None, "tasks": [],
            "source_text": None, "counts": {"total": None, "completed": None, "incomplete": None},
            "actions": ["open_project"]}


def group_from_snapshot(nexus, folder, snapshot, *, vault=None):
    if isinstance(snapshot, Exception):
        return unavailable_group(nexus, snapshot)
    if snapshot is None:
        return unavailable_group(nexus, "No Matrix storage is available. Open the project to create or repair its Matrix.")
    path, raw = snapshot
    try:
        text, mode = _authenticate(nexus, folder, path, raw, vault)
    except (OSError, UnicodeError, om.MatrixError, TaskError) as exc:
        return unavailable_group(nexus, exc)
    fm, _ = om._split_frontmatter(text)
    reason = None
    classification = None
    try:
        classification, _ = classifier.classify_matrix(fm, str(path))
    except classifier.InvalidProjectTypeError:
        reason = "Matrix classification is invalid. Tasks remain readable; correct project_type in the original Matrix before editing."
    if not classifier.schema_valid(fm):
        reason = reason or "Tasks are read-only until the Matrix has a valid list-form project_type."
    if not mode & 0o222 or not os.access(path, os.W_OK) or not os.access(path.parent, os.W_OK):
        reason = "Matrix storage is read-only."
    digest = hashlib.sha256(raw).hexdigest()
    doc = Document(text, digest, _identity(nexus, folder, path), classification)
    reason = doc.error or reason
    rows = doc.public_tasks()
    source = ("".join(doc.lines[slice(*doc.section)]) if doc.section else
              "".join("".join(doc.lines[start:end]) for start, end in doc.task_sections))
    recognized = {task["line"] for task in doc.tasks}
    opaque = bool(doc.section and any(line.strip() and i not in recognized for i, line in enumerate(doc.lines) if doc.section[0] <= i < doc.section[1]))
    total = None if doc.error else len(rows)
    completed = sum(row["done"] for row in rows) if total is not None else None
    return {"nexus": nexus, "state": "read-only" if reason else "partial" if opaque else "ready" if rows else "empty",
            "reason": reason or ("Unfamiliar Markdown is preserved and available in source text." if opaque else None),
            "editable": not bool(reason), "digest": digest, "identity": doc.identity,
            "root_ref": doc.root_ref, "tasks": rows, "source_text": source,
            "counts": {"total": total, "completed": completed, "incomplete": total - completed if total is not None else None},
            "actions": ["open_project", "refresh_tasks"] + (["edit_tasks"] if not reason else [])}


def read_group(nexus, folder, *, vault=None):
    try:
        snapshots = om.resolve_matrix_snapshots({nexus: folder}, vault=vault)
        return group_from_snapshot(nexus, folder, snapshots[nexus], vault=vault)
    except (OSError, ValueError, om.MatrixError) as exc:
        return unavailable_group(nexus, exc)


def _apply(doc, body):
    if doc.error:
        raise TaskError(doc.error)
    op = body["operation"]
    by_ref = {task["ref"]: task for task in doc.tasks}
    def target(field):
        if body[field] not in by_ref:
            raise TaskError("The selected task no longer belongs to this snapshot. Refresh and select it again.", "conflict", 409)
        return by_ref[body[field]]
    selected = target("target") if "target" in body else None
    # Retain transient line correspondence; never write identities to Markdown.
    lines = [[line, None] for line in doc.lines]
    for task in doc.tasks:
        lines[task["line"]][1] = task["ref"]
    focus = selected["ref"] if selected else "added"
    if op in ("edit", "complete", "reopen", "set-date", "clear-date"):
        m = selected["match"]
        label, mark = selected["text"], m[4]
        if op == "edit":
            label = body["value"]
        else:
            if op == "complete" and selected["done"]:
                return lines, focus
            if op == "reopen" and not selected["done"] and "✅" not in label:
                return lines, focus
            existing, ambiguous, marker = _completion(label)
            if ambiguous:
                raise TaskError("Completion metadata is ambiguous; edit the complete task label explicitly first.")
            if op == "complete":
                mark = "x"
                if existing is None:
                    label += " ✅ " + date.today().isoformat()
            elif op == "reopen":
                mark = " "
                if marker:
                    label = label[:marker.start()] + marker[2]
            elif op == "clear-date":
                if marker:
                    label = label[:marker.start()] + marker[2]
            elif op == "set-date":
                if existing == body["value"]:
                    return lines, focus
                label = (label[:marker.start()] + " ✅ " + body["value"] + marker[2]) if marker else label + " ✅ " + body["value"]
        lines[selected["line"]][0] = f"{m[1]}{m[2]}{m[3]}[{mark}]{m[5]}{label}{m[7] or ''}"
    elif op == "delete":
        if selected["children"] or selected["attached"]:
            raise TaskError("Move or promote children first; edit attached notes in the original Markdown before deleting.")
        del lines[selected["line"]:selected["end"]]
        focus = None
    elif op == "add":
        position = body["position"]
        anchor = None
        if position == "root":
            if body["destination"] != doc.root_ref:
                raise TaskError("The Matrix identity changed. Refresh before adding a task.", "conflict", 409)
            if doc.section:
                if doc.open_fence and doc.section[1] == len(doc.lines):
                    raise TaskError("Close the fenced example before adding at the end of Tasks.")
                at = doc.section[1]
            else:
                at = doc.insertion
                prefix = "".join(line[0] for line in lines[:at])
                separator = "" if prefix.endswith(doc.newline * 2) or not prefix else doc.newline if prefix.endswith(doc.newline) else doc.newline * 2
                lines[at:at] = [[separator + "## Tasks" + doc.newline * 2, None]]
                at += 1
            indent = ""
        else:
            anchor = target("destination")
            if anchor["ambiguous"]:
                raise TaskError("This destination has ambiguous indentation; choose a root position.")
            at = anchor["line"] if position == "before" else anchor["end"]
            indent = anchor["indent"] + _indent_unit(anchor, doc) if position == "child" else anchor["indent"]
        peers = [t for t in doc.tasks if t["indent"] == indent]
        styles = {(t["match"][2], t["match"][3], t["match"][5]) for t in peers}
        bullet, gap, label_gap = next(iter(styles)) if len(styles) == 1 else ("-", " ", " ")
        if at and not lines[at - 1][0].endswith("\n"):
            lines[at - 1][0] += doc.newline
        lines.insert(at, [f"{indent}{bullet}{gap}[ ]{label_gap}{body['value']}{doc.newline}", "added"])
        if doc.section is None:
            lines.insert(at + 1, [doc.newline, None])
    else:
        if selected["ambiguous"]:
            raise TaskError("This task has ambiguous indentation; edit its placement in the original Markdown.")
        parent = selected["parent"]
        siblings = [t for t in doc.tasks if t["parent"] is parent and t["indent"] == selected["indent"]]
        if op == "reorder":
            anchor = target("destination")
            if anchor not in siblings:
                raise TaskError("Reorder only moves a whole task block among siblings under the same parent.")
            if anchor is selected:
                return lines, focus
            at = anchor["line"] if body["position"] == "before" else anchor["end"]
            indent = selected["indent"]
        elif op == "indent":
            index = siblings.index(selected)
            if index == 0:
                raise TaskError("The first sibling has no preceding task to indent under.")
            anchor = siblings[index - 1]
            at = selected["line"]
            indent = anchor["indent"] + _indent_unit(anchor, doc)
            if "".join(doc.lines[anchor["end"]:selected["line"]]).strip():
                raise TaskError("Unattached source text separates these tasks; move it deliberately in the original Markdown.")
        else:
            if parent is None:
                raise TaskError("This task is already at the root.")
            anchor = parent
            if op == "promote":
                while anchor["parent"] is not None:
                    anchor = anchor["parent"]
            at = anchor["end"]
            indent = anchor["indent"]
        start, end = selected["line"], selected["end"]
        low, high = min(start, at), max(end, at)
        covered = {i for task in doc.tasks for i in range(task["line"], task["end"])}
        if any(doc.lines[i].strip() and i not in covered for i in range(low, high)):
            raise TaskError("Unattached source text prevents this move. Edit that placement in the original Markdown.")
        block = lines[start:end]
        for line in block:
            if line[0].strip():
                if not line[0].startswith(selected["indent"]):
                    raise TaskError("Task continuation ownership is ambiguous.")
                line[0] = indent + line[0][len(selected["indent"]):]
        del lines[start:end]
        if at > start:
            at -= end - start
        if at < len(lines) and block and not block[-1][0].endswith("\n"):
            block[-1][0] += doc.newline
        if at and not lines[at - 1][0].endswith("\n"):
            lines[at - 1][0] += doc.newline
        lines[at:at] = block
    return lines, focus


def _indent_unit(task, doc):
    units = {child["indent"][len(task["indent"]):] for child in task["children"]}
    return next(iter(units)) if len(units) == 1 else "  "


def _stamp(text):
    _, end = om._split_frontmatter(text)
    if not end:
        return text
    head = text[:end]
    newline = "\r\n" if "\r\n" in head else "\n"
    field = "date modified: " + date.today().isoformat()
    if re.search(r"^date modified:[^\r\n]*", head, re.MULTILINE):
        head = re.sub(r"^date modified:[^\r\n]*", field, head, count=1, flags=re.MULTILINE)
    else:
        closing = head.rfind("---")
        head = head[:closing] + field + newline + head[closing:]
    return head + text[end:]


def write_group(nexus, folder, body, *, vault=None, identity_check=None):
    validate_request(body)
    try:
        from runtime_hygiene import mutation_path_locks
    except ImportError:  # pragma: no cover
        from orchestrator.runtime_hygiene import mutation_path_locks
    initial = om.resolve_matrix_path(nexus, folder, vault=vault)
    if initial is None:
        raise TaskError("No Matrix storage is available. Open the project to create or repair it.", "unavailable", 404)
    with mutation_path_locks([initial]):
        def current_snapshot():
            if identity_check is not None and not identity_check():
                raise TaskError("Project storage identity changed. Refresh before editing.", "conflict", 409)
            snapshot = om.resolve_matrix_snapshots({nexus: folder}, vault=vault)[nexus]
            if isinstance(snapshot, Exception) or not snapshot or snapshot[0] != initial:
                raise TaskError("Matrix identity changed. Refresh before editing.", "conflict", 409)
            return snapshot
        snapshot = current_snapshot()
        text, mode = _authenticate(nexus, folder, *snapshot, vault)
        group = group_from_snapshot(nexus, folder, snapshot, vault=vault)
        if group["digest"] != body["expected_digest"]:
            raise TaskError("The Matrix changed after this snapshot. Refresh and select the task again.", "conflict", 409)
        if not group["editable"]:
            raise TaskError(group["reason"], "refused", 403)
        fm, _ = om._split_frontmatter(text)
        classification, _ = classifier.classify_matrix(fm, str(initial))
        doc = Document(text, group["digest"], group["identity"], classification)
        lines, focus = _apply(doc, body)
        replacement = "".join(line[0] for line in lines)
        if replacement == text:
            return {"ok": True, "saved": False, "changed": False, "group": group,
                    "correspondence": {task["ref"]: task["ref"] for task in doc.tasks}, "focus_ref": focus}
        replacement = _stamp(replacement)
        verified = Document(replacement, group["digest"], group["identity"], classification)
        tokens = [token for _, token in lines if token is not None]
        if verified.error or len(verified.tasks) != len(tokens):
            raise TaskError(verified.error or "This placement would hide or split task content; choose another position.")
        latest = current_snapshot()
        _authenticate(nexus, folder, *latest, vault)
        if latest[1] != snapshot[1]:
            raise TaskError("The Matrix changed before replacement. Refresh before editing.", "conflict", 409)
        try:
            om._rp.atomic_write_bytes(initial, replacement.encode("utf-8"), mode=mode)
        except OSError as exc:
            # An atomic helper can fail after replacement (for example cleanup).
            try:
                unchanged = current_snapshot()[1] == snapshot[1]
            except Exception:
                unchanged = False
            raise TaskError("The task could not be saved." if unchanged else "The save outcome could not be confirmed. Refresh before another action.",
                            "unavailable" if unchanged else "unknown-outcome", 500, False if unchanged else None) from exc
        try:
            actual = current_snapshot()
            actual_group = group_from_snapshot(nexus, folder, actual, vault=vault)
            if actual[1] != replacement.encode("utf-8") or actual_group["digest"] is None:
                raise ValueError("Matrix changed after replacement")
            old_order = [token for _, token in lines if token is not None]
            if len(old_order) != len(actual_group["tasks"]):
                raise ValueError("Task correspondence changed")
            correspondence = {old: task["ref"] for old, task in zip(old_order, actual_group["tasks"])}
        except Exception as exc:
            raise TaskError("The save may have landed, but its result could not be confirmed. Refresh before another action.",
                            "unknown-outcome", 500, None) from exc
        return {"ok": True, "saved": True, "changed": True, "group": actual_group,
                "correspondence": correspondence, "focus_ref": correspondence.get(focus)}
