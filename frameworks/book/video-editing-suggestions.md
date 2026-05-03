# Video Editing Suggestions Framework

## Display Name
Video Editing Suggestions

## Display Description
Read a clip's transcript and propose specific edits — cuts (filler / silence / repeats), chapter markers (logical breaks), title cards (introductions / topic shifts), and transitions (where a hard cut would feel jarring). Each suggestion comes back as a structured row with an Apply button that mutates the timeline directly.

---

## PURPOSE

When a user is editing a captured talk, screencast, or interview, they want help finding the obvious edits — the dead air at the start, the long "umm" near minute six, the natural place to insert a chapter marker. This framework reads the whisper transcript of a single library entry, proposes a list of specific edits keyed to source-time offsets, and renders them in the transcript panel with one-click apply.

It is intentionally tactical: the model is not asked to redesign the video, only to surface candidate edits the user can accept, ignore, or modify. The user is always the editor; the model is the assistant.

---

## INPUT CONTRACT

**Required:**
- `entry_id` — the media-library entry whose transcript should be analyzed.
- `transcript` — the normalized whisper output: `{ language, duration_ms, segments: [{ start_ms, end_ms, text }, ...] }`.

**Optional:**
- `goals` — free-text user direction ("tighten the intro," "find chapter breaks," "make this twitter-friendly under two minutes"). Default: general tightening.
- `existing_clips` — current timeline state for this entry. The model uses this to avoid suggesting cuts to already-trimmed regions.

---

## OUTPUT CONTRACT

The framework MUST emit a single JSON object matching the schema at
`~/ora/config/framework-schemas/video-editing-suggestions.schema.json`.

The top-level shape:

```json
{
  "entry_id": "<string>",
  "summary": "<one-paragraph plain-English overview>",
  "suggestions": [
    { "type": "cut",       "start_ms": 0, "end_ms": 1500, "reason": "..." },
    { "type": "chapter",   "at_ms": 12500, "label": "...",  "reason": "..." },
    { "type": "title_card","at_ms": 0,    "duration_ms": 3000, "title": "...", "subtitle": "...", "reason": "..." },
    { "type": "transition","at_ms": 45000, "duration_ms": 500, "kind": "fade", "reason": "..." }
  ]
}
```

### Per-type rules

**cut** — remove a span. `start_ms` and `end_ms` are source-time offsets relative to the original media. Cuts shorter than 200 ms are not useful; do not emit them. Cuts longer than 30% of total duration require an explicit user-stated goal.

**chapter** — insert a chapter marker at `at_ms`. `label` is at most 60 characters and reads as a section title (not a sentence). Limit to 3-7 chapters per clip; more than that is noise.

**title_card** — render a title card from `at_ms` for `duration_ms`. `title` is at most 50 characters; `subtitle` at most 80. Use sparingly: one opening title card and one optional closer is the default; topic transitions inside the body should normally be chapters, not title cards.

**transition** — apply a transition starting at `at_ms` lasting `duration_ms`. `kind` is one of `fade`, `dissolve`, `cut`. Transitions only make sense at cut boundaries — do not propose them in the middle of continuous footage.

### Reason fields

Every suggestion includes a `reason` string (under 200 characters) explaining why the edit was proposed in plain English. This is shown in the UI tooltip; the user reads these to decide whether to apply.

### Ordering

Suggestions are returned in source-time order (by `start_ms` for cuts, `at_ms` for everything else).

---

## OUTPUT SCHEMA REFERENCE

Authoritative JSON Schema at:
`~/ora/config/framework-schemas/video-editing-suggestions.schema.json`

The server validates emitted JSON against this schema before returning it to the browser. Validation failures are surfaced inline ("the model returned malformed suggestions; raw output preserved for debugging").

---

## METHOD

The framework runs in three internal passes:

1. **Filler / silence pass.** Walk the transcript looking for runs of single-word filler (`um`, `uh`, `like`, `you know`), long pauses (segment gaps > 1500 ms in the middle of a stream), and false starts (segments where the same first 4 words appear twice consecutively). Each candidate becomes a `cut` suggestion. Cap at ~12 cuts per 10 minutes — beyond that, surface a top-level summary recommendation rather than a cut list.

2. **Structural pass.** Look for topic shifts using transcript-level cues — long pauses combined with a sentence-initial discourse marker (`so`, `okay`, `now let's`), or a clear question/answer boundary in interviews. Each shift becomes a `chapter` candidate. Pick at most one chapter per ~120 seconds.

3. **Frame pass.** If the clip lacks an opening lead-in (no clear introduction in the first 5 seconds), suggest a `title_card` at `at_ms=0` with the inferred topic as the title. If hard cuts at chapter boundaries would feel abrupt, optionally suggest a `transition` of `kind: fade` at those boundaries.

The model is not allowed to suggest edits that conflict with each other (e.g., a chapter marker inside a region marked for cutting). The framework prunes conflicts before emitting.

---

## GUARD RAILS

- The framework MUST NOT propose cuts inside ranges the user has already trimmed (the timeline state's `in_ms`/`out_ms` already excluded those frames).
- The framework MUST NOT emit narration or commentary on the content itself — only structural edits. Editorial opinions ("the speaker is wrong about X") are out of scope.
- The framework MUST emit valid JSON. If the underlying model produces non-JSON, the server retries once with a re-emit prompt; second failure surfaces as an error to the UI.
- Cuts that would remove more than 50% of the clip duration require explicit user direction (goals field references "shorten dramatically" or similar). Without that direction, cap cuts at 30% of total duration.

---

## SUCCESS CRITERIA

Structural:
- Output validates against the JSON schema.
- Suggestions are in source-time order.
- All suggestions reference timestamps within `[0, transcript.duration_ms]`.
- All `cut.end_ms > cut.start_ms`.

Semantic:
- Cuts target real filler / silence (verifiable by inspecting the transcript at the proposed offsets).
- Chapter markers fall at sentence boundaries.
- Title cards have non-empty title strings.

---

## KNOWN FAILURE MODES

- **Model proposes cuts mid-sentence.** Pre-emit check: every `cut.start_ms` must coincide with a segment boundary or fall inside a between-segment gap; otherwise drop the suggestion.
- **Suggestions reference timestamps past `duration_ms`.** Pre-emit clamp: drop any suggestion with timestamps beyond the transcript duration.
- **Empty suggestions list.** Acceptable — surfaces in UI as "No edits suggested for this clip." Better than fabricating cuts.

---

## VERSION

1.0 — initial release, A/V Phase 8 (2026-05-01).
