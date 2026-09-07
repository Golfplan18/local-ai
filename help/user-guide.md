# Using Ora — Operator Guide

*Task-indexed guide for installing, running, and operating an installed Ora system. It derives from [[Reference — Ora Technical Documentation]] and adds no new claims. Find your task, do the steps.*

**Documentation baseline.** Install and general-operation guidance retains its established platform pins except for the scoped current Windows-launch correction below. The Knowledge Library guidance describes the current unified List/Visual workspace with safe Markdown Read and CodeMirror Edit, while the Overview guidance describes the separate full-screen shell with Daily Note Read in Ora, external-open actions and P3 Matrix Tasks source behavior. This scoped Tasks update does not establish live activation or native-display acceptance. The Scheduled section describes the separate current Trigger surface; the Programming section describes the current explicit standalone implementation and its Documentation-Code Parity review contract. Aside help and the optional video feature describe the current landed behavior. The vault guide remains canonical; synchronize body-only to `help/user-guide.md`.

**Platform labels.** Every command is labeled. `[macOS]` is the tested path (Apple Silicon). `[Linux server]` is the supported headless path. `[Windows-native]` and `[WSL]` are labeled where they differ; **`[Windows-native]` is intended but untested** — treat it as best-effort until a clean-room Windows install has been verified. If a command carries no label, it applies everywhere Ora runs.

**What things are called.** A working session with Ora is a **Dialogue**. You type into the **Inquiry** pane, read results in the **Findings** pane, and see diagrams in the **Exhibits** pane (the canvas beside the text). The small side-model chat panes in the upper right are the **Aside**, and the browse window for your Dialogues, engrams, and files — opened from the sidebar — is the **Library**. **Overview** is the separate full-screen arrival surface opened and closed from the dedicated mid-height control on the permanent left rail. It preserves the workspace beneath it and restores that exact state when closed. Its five fixed cards show Project priority, Oversight, Triggers, the previous day's Daily Note, and Tasks: read each card's state together with its freshness or error, and use an action only when the item offers one. Missing or unreadable content is not a successful zero.

Overview arranges active projects around its central O and spine in your canonical priority order. Activity is labelled without moving projects. Equal-priority and unranked projects use their stable project identifiers, so reopening or renaming a project does not rearrange the ring. Change priority through existing project management; Overview uses the new order on its next opening. At narrow widths or with many projects, the same controls wrap and scroll. Every project stays reachable, and its full name remains available.

Each project has four labelled destinations. **Overview** opens that project's Overview tab. **Files**, **Dialogues**, and **Knowledge** open its corresponding Library collection with the previous search, filters, provenance, pin and preview cleared; your List/Visual preference and compatible sort remain. This also starts clean when you return to the same collection. Opening Library from the Sidebar instead preserves its prior browsing state. If a destination is unavailable, Overview explains that locally and stays open. Known-project counts retain any partial or unavailable qualification; collection totals and content come from Library after you enter it.

Use Tab or Shift-Tab to move among Overview's visible controls, including in Daily Note Read. Focus stays inside the open dialog; Close or Escape restores your prior workspace focus. The O/spine is decorative here. Project names, order, activity and actions remain available as text, and the layout settles without requiring motion or ignoring reduced-motion preferences.

**Manage Matrix Tasks.** Expand a project in Tasks to see its incomplete and completed tasks. Groups use the same active-project priority order as the ring. Tasks come only from that project's real `## Tasks` section in its original Matrix Markdown; checkboxes elsewhere in the vault are not included. Project, Operation and Passion matrices keep their own strategic layout. A missing Tasks section is empty and is created only by the first successful Add. A missing Matrix cannot be created here: use the group's project-opening action and its storage explanation.

Choose **Add task**, choose its position at the root, beside a task or beneath it, enter its text and choose **Save new task**. To edit, select the task and change its full checkbox-line label in the text control; use **Save text** to commit or **Cancel draft** to discard unsaved edits. Embedded line breaks are refused. Existing inline syntax is part of that label, so keep any notation you want preserved.

**Move earlier** and **Move later** reorder a task and its children among siblings. **Indent** puts that block under its preceding sibling; **Outdent** raises it one level; **Promote to root** takes it to the root. The displayed nesting level also expresses hierarchy in words. The first sibling cannot be indented and a root cannot be outdented. Unclear ownership of nearby text can prevent a move while leaving safe text or completion edits available.

**Delete task** is limited to a leaf with no attached unfamiliar content. Move or promote children first; deliberately edit attached notes in the original Markdown before deleting their task. **View original Tasks Markdown** exposes the source as literal text, including fenced examples, which are never silently discarded.

**Complete task** marks only the selected task and adds today's local completion date when it has none; an existing clear completion date stays. **Reopen task** clears its checkbox and recognized completion marker, without changing children. Enter a real calendar date and choose **Save completion date**, or use **Clear completion date**; neither changes completion state. This is a completion date, not a due date. If completion notation conflicts or is ambiguous, Ora explains which date-related action it cannot safely perform and preserves that notation.

An empty group means its authenticated Matrix has no recognized tasks. Read-only means saving is blocked for the stated reason; tasks and source remain inspectable where Ora can establish their section. Partial means only known counts can be reported. Unavailable means Ora could not establish the source; it does not mean zero tasks. One affected Matrix leaves healthy project groups and unrelated cards usable.

Every deliberate action sends one save request. A successful save refreshes only that project group and returns focus to the corresponding task or a nearby group control. Other groups and drafts stay in place. If the Matrix changed outside Ora, the save reports a conflict. Keep the draft, explicitly refresh the group, inspect current source, and select the intended task again before saving. Identical labels do not identify the same task.

A lost response may mean a write landed. Ora reports the uncertainty and requires refresh before another mutation; it never automatically repeats the action. Text and date drafts survive a refusal, conflict, refresh, and closing/reopening Overview in memory until Save, Cancel or page teardown. Reopening reads current authority and does not silently attach an old draft to a new task. Back from Daily Note Read restores the mounted Tasks state; Escape closes without saving. There is no background polling or promise of live synchronization with Obsidian.

On a Trigger row, **Open in Scheduled** closes Overview, restores the exact prior workspace, then has Oversight's existing Scheduled panel refetch, open, expand, and focus that exact stable Trigger card. Run, review, activate, pause, resume, and retire stay there; Overview never calls or copies them.

When the exact previous-day Daily Note is available, its row offers **Read in Ora** and **Open externally**. Both send only the dated identity. **Read in Ora** opens the note's body in Overview without entering Edit. Ora checks that it is still the prior day's own valid Daily Note before returning its text. **Back to Overview** returns to the same ring, cards and action; Close or Escape returns to your prior workspace and focus. A failed read leaves the cards usable. If the source exceeds the 4 MiB reading bound, the card preview and Open externally remain available.

For **Open externally**, the server confirms that it is still the completed previous local day and resolves the canonical file again. A missing, stale, unsafe, or non-regular note is not replaced with another. The action does not read, change, create, or regenerate it.

On the local Mac, Ora asks Obsidian first. Only a definite refusal leads to one recheck and the system's default Markdown application. A timeout is uncertain, so Ora names that uncertainty and tries no other application that could duplicate the open. Missing, unsafe, unsupported, launch, and fallback failures stay visible. Success means the request was sent, not that the note appeared.

After confirmed dispatch, Overview closes, leaves the message visible, and restores the prior Dialogue, draft, panes, workspace, and focus. Failure or uncertainty keeps the cards usable, restores only the pending button, and starts no retry. The ring, navigation and Tasks describe source implementation; live activation and native-display acceptance remain separate. Saved layout, widget configuration and quick links remain future work. Tasks adds no due dates, recurrence, dependencies, assignments, connectors, priority editor, remote or wake controls. Internal names — such as the `conversations` folder where Dialogues are stored — remain unchanged.

---

## Start a Dialogue without duplicating prior work

1. Choose **New Dialogue** from the sidebar, the spine `+`, or the New Dialogue keyboard shortcut. Standard, Private, and Stealth creation all use the same review flow; the privacy choice remains visible in the heading.
2. Give the Dialogue a short title and an expanded description of what you want to explore or accomplish. The description must contain at least 20 characters and three terms so retrieval has enough subject matter to work with.
3. Choose **Find related material**. Ora searches both prior Dialogues and atomic notes. Nothing is created at this point.
4. Review the surfaced set. For each item you may:
   - **Add contributor** — include that source as read-only reference material in the new Dialogue without making it an ancestor.
   - **Continue** — return to an existing live Dialogue.
   - **Fork** — create a true child branch of an existing live Dialogue.
5. If you still want a new Dialogue, select any contributors, confirm that you reviewed the suggestions, and choose **Create Dialogue**. Editing the description invalidates the prior review and requires another search.

The confirmation asks Ora to issue a server-side creation contract bound to the exact title, description, selected contributors, privacy target, and active project you reviewed. Changing any of those inputs invalidates that confirmation. The new Dialogue is persisted only after the final Create action; concurrent delivery or a network retry returns the same Dialogue instead of creating another one.

Its description then appears in Inquiry as an **unsent draft**; review or edit it before submitting the first turn. Continue and Fork use the same rule, carrying the description as an unsent draft rather than sending it automatically.

A Dialogue may have one parent and any number of explicit contributors. Ora preserves contributor order, removes duplicates, and resolves each reference on every turn. A Dialogue contributor brings only its recursively cutoff-safe history. An atomic-note contributor brings indexed whole-content chunks. Missing, privacy-withheld, and budget-deferred references remain accounted for; they are not silently dropped.

Fork ancestry and contributors do different jobs. A new fork stores the direct parent and the parent's immutable local-message count at the fork point, but starts with `messages=[]`; its first new exchange is local turn 1. When you return, Ora recursively reconstructs only the permitted prefix at every ancestry edge. Later ancestor turns never leak into the child, and forking never changes the parent. The older `fork_point_chunk_id` field is compatibility metadata, not the current history boundary.

Every processing path receives server-authoritative history, including Phase A cleanup, Direct, G1–G4, and special consumers. Ora packs complete turn and note units into the selected endpoint's safe request size. The Dialogue maximum is 200,000 tokens, but the effective budget can be smaller after required payload, output, retry, image, provider, and safety allowances. Recent local context and the fork frontier come first, followed by eligible contributors, older history, and lower-priority global retrieval. Ora does not cut a turn in half or infer a durable “accepted decision” from model prose; the raw exchanges remain authoritative.

Privacy applies to each complete Inquiry/Findings exchange. A Dialogue can contain both Standard and Private turns: use **Compose next as Standard** or **Compose next as Private** to choose the next exchange without changing earlier ones. Ora saves the same Dialogue owner, local turn, chunk, and privacy on both halves of the exchange. A Dialogue's current composer setting never fills in missing privacy on an old turn.

Access is cumulative once adjacent halves share valid privacy: Standard may use Standard; Private may also use Private; Stealth may use all three, but Standard cannot use Private. The canonical envelope supplies Dialogue identity and local order, so ordinary history need not match saved turn or chunk fields. Missing, conflicting, or too-private pairs are omitted without guessing, often silently; contributor status is internal too.

History and Dialogue contributors apply that pair-privacy rule before model use; Library and search use surface-specific row/path checks before content or relevance. An archived contributor uses only complete, cutoff-safe pairs with matching permitted privacy. Fork creation adds the full inherited-prefix check: canonical Dialogue/turn owner plus saved chunk/privacy. Archived notes and global rows stay excluded, and global retrieval excludes current, ancestor, and contributor sources. Phase 4 automatic semantic retrieval is not active.

For protected-index repair, an operator can invoke `python3 -m orchestrator.tools.chroma_source_rebuild protected-inactive-copy` with `--chroma-path` and `--authority-plan`. The plan must name distinct source and fresh inactive target collections and contain `private` and `standard` objects, each with a complete `ids` array, exact `expected_count`, and sorted-ID `expected_id_sha256`. It must account for every source ID. The command copies only those surviving source rows into the new same-store target, preserving documents, stored vectors, collection metadata, and every nonprivacy field while changing only `turn_privacy`, `tag`, and `tag_private`.

Treat this as preparation, not activation. It refuses missing, unknown, overlapping, omitted, extra, drifted, conflicting, malformed, or colliding input; audits payloads exactly and stored vectors within the existing one-float32-ULP Chroma copy boundary; and removes only the identity-matched target it created if a later check fails. It does not embed, replay, use the network, read or change Ora's configuration, stop the service, backfill source envelopes, or switch the active collection. The present owner disposition covers all 40,177 surviving rows—4,107 Private and 36,070 Standard, with 16,534 propagation-only Private rows classified Standard; the 698 empty-sided turns stay exact and the 884 recovery-only rows stay excluded. No live copy, backfill, cutover, or deployment has been performed or authorized by this documentation.

Withholding does not rewrite the source. Fork ancestry, project membership, raw recovery material, canonical content, contributor order, and source identity remain intact. Ora-managed extracted notes must prove the same complete owner tuple; a stray source label or false metadata cannot make missing material public or turn an owned derivative into an ordinary Standard note.

Use **Library** in the Dialogue sidebar when you want to inspect retained knowledge without disturbing the work you have staged. It replaces the upper Inquiry and Aside area while it is open, but it does not delete or reset either one: your draft, attachments, Framework or Analysis choice, and Aside state return exactly when you close it. Findings and Exhibits remain visible below. Pinning a result uses temporary previews there without changing the active Dialogue.

Start without a search term. In **Sources**, choose Dialogues, Engrams, Files or any combination; all three start on. Turning all off is an explicit empty view. Choose a project separately: **Commons** means everything you are allowed to browse, while a named project means exact membership. Commons is not another project assignment. A Dialogue with no project belongs to the Commons group; one with several projects can appear in several groups, but totals and checked actions count it once.

Use the available filter controls to narrow the whole result, then remove an individual chip to undo that choice. Depending on the selected corpus, these include tags, dates, lifecycle, privacy, recorded relationship kind/family, extraction source, epistemic kind, extraction date, folder, content type, canonical File type and configured category. Required tags all have to match; date limits include their boundary days. An unavailable field says so beside the control rather than inventing a value. In particular, local restriction is not guessed from privacy. Missing metadata remains visible in ordinary browse but cannot satisfy a specific filter.

Choose one **Group** axis at a time. File Folder uses the file's folder within its project and labels top-level files **Project root**. Content type uses known metadata and labels missing values **Unavailable**. **Item type** means Dialogue, Engram or File; the File's own YAML **type** is a separate refinement. Choices needing every result wait for **Load all**. If a grouping becomes ineligible after a source change, only Group repairs to **None**; your search, filters and sort remain.

**List** and **Visual** share the same results, filters, checked items, pin and paging. Use the check control in either view for bulk actions; pinning is separate. Switching views does not search again. Ora remembers only your last List/Visual preference across a reload. Filters and grouping survive closing/reopening Library in the same page session, not a new page. If preference storage is unavailable or invalid, Ora explains the fallback; it saves no content or browsing history.

Changing the project scope immediately clears the old identity-bound rows, pin, checks, relationship detail, preview and actions before requesting the new scope. Your source/search/filter/group/sort choices remain. A same-scope refresh keeps accepted state until replacement. Closing Library restores the original workspace, not a newly constructed copy.

The top field searches readable Dialogue bodies and exact/fuzzy indexed Engram text, not meaning-based semantic similarity. Scope, source choices and requested filters apply before counts and pages. Files have no body search: Ora names that unsupported part while showing eligible Dialogue/Engram matches. A metadata-only Dialogue stays in queryless browse but cannot match unreadable text. Complete-result grouping and title sorting wait until all qualified pages are loaded.

Results arrive in stages through the same search. Pending or failed sources and provisional counts stay labelled; **Load more** and **Load all** wait for final accounting. An interrupted or incomplete response leaves safe results visible with an explanation and retry, not a false complete empty view. Changing search/scope or closing Library cancels the old request; a late response cannot replace the newer one. An early stage also cannot drop your pin simply because its source has not finished.

For Engrams, start in **Browse** to group by a proven source Dialogue or document. Refine by project, epistemic kind or extraction date when known. Missing or conflicting provenance stays in a labelled unresolved group; Ora never guesses a likely source. **Show derived Engrams** on an admitted Dialogue or File opens Engrams with that source already selected, clearing incompatible filters. It changes no active Dialogue, creates no Engram and shows an honest empty state if the index has no admitted derivation.

Choose **Trace** for the selected Engram's recorded neighbors. Read each connection's kind, incoming/outgoing direction and confidence in the relationship list; patterns, arrowheads and labels supplement color in Visual. Families collect evidence/argument, building/evolution, causal/logical and hierarchy/abstraction relationships. Unrecognized stored kinds remain inspectable under their own labels. Similarity suggestions are separate and never masquerade as recorded connections.

Trace includes all neighbors through **50 distinct Engrams**, not fifty lines. When there are more, it balances the families and ranks by confidence, then names exactly **N more** admitted neighbors; expand in batches of fifty. Several relationship types between the same nodes do not consume extra places. Selecting a neighbor reads it below without moving the existing neighborhood; **Trace from this Engram** explicitly begins a different one. A pin or late relationship update changes emphasis, not node positions. On a small screen, Visual states how many fit and the expandable relationship list retains every advertised neighbor and action.

Files use the project's own folder inventory. Known nexus, type, tags and subtype come from their Markdown metadata, including readable files that cannot be edited. Where an existing project record supplies categories, choose that project's category as a refinement. Categories use exact values: all required list members must be present, and every configured field must match. There is no category-authoring editor in Library. Missing configuration means no category choices; a malformed entry warns without hiding the files. File relationships distinguish folder/project membership, explicit metadata links and extracted Engram provenance instead of presenting them as one kind of connection.

**Show archived** is off by default. Turn it on to inspect retired Engrams and the distinct indexed-Dialogue archive. It does not mean Close/Restore for a retained Dialogue. Readable historical items stay read-only. An indexed Dialogue is readable only where complete, unambiguous exchanges have current privacy authority; missing, private or ambiguous material remains unavailable rather than reconstructed into guessed speaker text. Retained Dialogues are not duplicated by their indexed copies.

Relationship freshness reports the last successful completion and any current incomplete reason. Existing file events update the graph; startup catches changes missed while Ora was stopped. Unchanged Markdown is not repeatedly parsed, and opening Library never repairs the database. The files remain authoritative. A missed edit that preserves every observed file-state value may need a later event or explicit operator rebuild to be detected. Stale or failed relationship information leaves the usable inventory available; a relationship filter that cannot be answered says unavailable instead of hiding everything.

Pin a readable Dialogue to read its permitted complete exchanges below, with a fixed speaker label outside each turn’s Markdown. This does not activate it, update last access, replace your draft or make it editable. Nested-fork cutoffs and current per-turn privacy still apply. Then use **Actions → Continue Dialogue** to enter its normal reader, **Fork Dialogue**, start a new Dialogue with it as a contributor, change its lifecycle, or add selected Dialogues to the active named project. To ground a new Dialogue in several items, check the readable Dialogues and atomic Engrams you want and choose **New Dialogue with checked context**. Ora puts every eligible item into the existing repeatable contributor review before creation. When checked context comes from a named Library scope, contributor discovery stays inside that project; Commons sends no project filter. Opening any other creation path clears that temporary discovery scope, and the new Dialogue's stored project membership still follows the ordinary creation rule. Checked Files and metadata-only Dialogues are named as unsupported instead of disappearing, and the strictest selected privacy boundary becomes the new Dialogue's starting boundary. The raised O becomes the selected-item anchor while Library is open; activating it moves focus to relationship details, and activating a relationship node moves focus to the matching typed text entry. A metadata-only Dialogue remains visible under a generic name but cannot be read or acted on and does not request Related details. Pinning a currently readable text Engram or File sends its stable Library ID, never its displayed path, through a fresh current-authority check and shows the authorized Markdown in temporary Findings through **Read**, retaining the source's supplied frontmatter. A supported bounded image File follows the same stable-ID/current-authority boundary and appears only in temporary Exhibits while Findings keeps its metadata and relationships. Project File rows also offer **Actions → Reveal in Finder**. This operation is macOS-only: Ora uses only the current provider row's file location, asks the existing reveal route to check the allowed folders and current existence, and shows success or the route's refusal/failure in the existing notice. Reveal does not open, read, write, or download the file, and it changes no scope, search, filter, paging, selection, pin, preview, active Dialogue or draft, or lower-pane ownership. When a current File row also carries a server-issued `obsidian://open` locator, **Actions → Open in Obsidian** appears. Its native anchor uses the exact returned URI, so the browser and operating system perform the handoff; Ora cannot tell whether Obsidian accepted it and does not report that it did. The action is absent for Dialogues, Engrams, and Files without the locator. **Reveal in Finder** remains a separate action with its own checks. Using Open in Obsidian leaves every Library choice and result, the active Dialogue and composer draft, and the Inquiry, Aside, Findings, and Exhibits pane state and ownership unchanged. Repinning or closing aborts the preview, and a late result is discarded; the active Dialogue, draft, pin, selection, and underlying pane owners remain intact. The separate image preview grants no Markdown editing authority.

The browse-time edit offer for a Markdown project File or uniquely direct Standard Engram is provisional. **Edit** rechecks the current source and loads its complete Markdown and fingerprint into CodeMirror 6, the editor bundled with Ora. Use its line numbers, wrapping, standard editing keys, folding, and undo while keeping Save and Cancel explicit. Save rechecks the same Library identity and fingerprint; an external-change conflict writes nothing and leaves the full draft, selection, and undo history in place. An accepted save preserves the file's uniform line endings and mode, while an Engram reports content saved separately if its knowledge-index refresh fails. A failed connection or malformed reply leaves the draft intact and reports uncertainty about whether the save completed. While Save is pending, editing and another Save are disabled. An accepted save returns to Read. Cancel discards only your unsaved draft and reloads the current source.

Relationship loading and status changes keep the same editor and your place in it. Repinning, changing source/project scope, losing the pinned item, or closing Library ends that edit session; these do not save the draft. A late reply cannot replace the newer surface. A File declaring `type: engram` is read-only and must be edited through an eligible Engrams row; folded aliases, symlink-only, ambiguous, incomplete, malformed, privacy-changing, non-Markdown, missing, unwritable, mixed-ending, and lone-CR cases stay read-only. Browse still carries no bodies and File-body search remains unavailable. File links require exact admitted endpoints; optional missing metadata never creates a connection. SVG, PDF, animated-image, and other-media preview, plus image/media editing and download, remain unavailable. Close Library to restore the O's normal Submit operation and the exact upper/lower work state.

Read formats ordinary Markdown headings, lists, quotes, code, emphasis, tables, and separators. Raw HTML stays text. Explicit web and email links can be opened; images, embeds, wikilinks, relative paths, fragments, and application/file links remain readable but inactive and do not fetch anything. Use the separate offered source actions when you need an external application.

If the reader bundle fails or authorized Library text exceeds 4 MiB, Ora shows the original literal text with an explanation. For a Dialogue the bound covers all displayed turns together, and literal fallback keeps the separate speaker labels. A bundle or rendering failure makes Edit visibly unavailable. The size bound limits formatted reading; it does not grant or remove source write permission. Daily Notes and Dialogues remain read-only, and Ora adds no autosave or saved local draft store.

Use the lifecycle controls literally:

- The ordinary sidebar shows the current project's non-Stealth Dialogues and only the active Stealth Dialogue. Closed Dialogues live in **Manage**.
- **Close** on Standard or Private sets a retained hidden state. Restore it from Manage; its transcript and descendants remain available.
- **Make displayed turn Private/Standard** changes one complete non-Stealth exchange, not the whole Dialogue. Making a turn Private tightens every representation Ora can prove belongs to that exact turn, including its conversation/index records, extracted or review notes, and managed Daily Note summary. Missing, edited, conflicting, or ambiguous copies stay untouched. If Ora reports that propagation or reconciliation is incomplete, treat the turn as not fully retagged; do not infer success from the heading. Approval of a pending extracted note waits on the same Dialogue lifecycle lock, so it cannot publish across that privacy change.
- **Exit Stealth** is navigation only. Ora returns to the latest readable direct parent, even if that parent is Stealth, or opens a fresh Standard Dialogue when no readable parent exists. It does not close or delete anything.
- **Delete Forever** is the protected Stealth purge, even when descendants exist. Children detach and keep only their local turns. Ora strips a legacy copied-parent prefix only when an exact match proves what was copied; ambiguous content is preserved. Explicit exports and copies held by providers, Git, backups, or other external systems remain outside Ora's managed purge boundary.

Use the **Export** menu at the lower right of Findings for a durable copy. **Save output to Vault** saves the displayed assistant answer only; Word and PDF do the same when their converters are available. The browser sends the owner Ora attached to that exchange, not its rendered title or text. The server rereads the effective Dialogue and the canonical local turn, and refuses a stale, incomplete, or mismatched owner instead of exporting what happens to be on screen.

A Private current-output export stays visibly labelled Private and its Markdown remains Private-tagged. An explicit Stealth output omits privacy markers and source identity. Those presentation rules do not weaken the source exchange: Ora authenticates it first, then produces the destination-appropriate copy.

Choose **Save full Dialogue** when you need the effective branch rather than one answer. Ora holds every ancestral owner stable and authenticates every complete exchange against its canonical Dialogue, turn, chunk, privacy, and content. A Standard or Private target refuses any Stealth-owned turn. A Stealth target may include eligible Standard or Private ancestry inherited through a real fork, but the exported artifact remains source-free and uses a neutral fallback name when a safe canonical title is unavailable.

Both Markdown saves check the document's metadata before creating supporting output. A metadata refusal names the field that needs attention and does not mean a file was saved. A missing optional description instead permits the save and appears as a warning in the existing saved-result status; Reveal remains available after success. Titles with punctuation, the source prose and privacy presentation keep their meaning. Word/PDF, Print and Trace are unchanged. These checks describe the P4 source implementation, not a claim that this machine's running Ora has been updated.

---

## Ask Aside for help

Use **Aside**, the narrow column in the upper right, for a quick answer that
should not become part of the Dialogue. Its header says **Quick answers · system
help · not saved**.

1. Type a question in the Aside input. For example: “How do I open the video
   editor?”, “Where are Ora plugins?”, or “How do I recover a failed install?”
2. Press Enter or use the O submit control.
3. Read the answer in the Aside output above the input. Minimize or restore the
   column with its header control when you need more room.

Aside can answer ordinary quick questions, and it searches a small public help
library when the wording matches an Ora operating question. That library contains
only five tracked files from the installed checkout:

- this operator guide;
- the accessible overview;
- the install guide;
- the manual install procedure; and
- install recovery.

It does **not** search your vault, private notes, Dialogue history, or other Ora
documentation. Help search is therefore isolated from personal material. Ora may
use an indexed copy of those same five files for speed, but a local lexical search
over the files remains available when the index or embedding service is not.

Aside remembers at most the five most recent exchanges in the Ora server
process so a follow-up can make sense. Reloading the page clears the visible
Aside pane but does not clear that server-held window. Restarting the server
clears the stored window. The prompt, answer, and
temporary help excerpts are not written to a Dialogue, the vault, or the help
index. Aside is informational: it cannot start a Run, change the current
Dialogue, or make an authoritative decision for Ora.

If help lookup fails, Aside still tries to answer without the excerpts and Ora
records the lookup problem in its server log. For work that must be saved,
retrieved later, or used by the main reasoning pipeline, ask in Inquiry instead.

---

## Use Audio & Video

Ora has two related capabilities with different availability.

**Audio/video transcription is core.** Drop a supported audio or video file into
the **Inquiry** pane. Ora uploads it through the ordinary conversation boundary,
transcribes it, and makes the transcript available to the Dialogue. This works
even when the optional video feature is not installed.

**The editor is an optional first-party feature plugin.** When the bundled
`plugins/video` package is present and valid at server startup, Ora adds the video
editor, Dialogue media library, capture and rendering controls, a **Video**
settings section, and the `/video` command. To use it:

1. Open or create the Dialogue that should own the media.
2. Choose **Video editor** in the Exhibits controls, or type `/video` to toggle
   the editor. The editor takes over Exhibits until you close or toggle it.
3. Choose **Browse Dialogue media** to see that Dialogue's clips. Captured media
   appears there automatically. You can also import a supported URL, add local
   media through the available upload/drop surface, or choose **Send canvas image
   to media library** for the current Exhibit.
4. Drag media onto the timeline. Move or trim clips, adjust audio and fades, use
   the preview and transcript panels, and apply suggestions only after reviewing
   the proposed timeline change.
5. Use the render controls to export the timeline. The video plugin starts
   FFmpeg in its own background render worker, and the editor reports its state.
   Ora's shared background job queue remains part of core, but it does not run
   the FFmpeg export.

Open **Settings → Video** to choose the screen-recording directory and frame rate,
microphone or loopback device, webcam picture-in-picture, export directory and
preset, background-render threshold, and preferred or fallback video-generation
model. A loopback audio device is required when you want a screen recording to
include system audio. Capture, preview, waveform, and rendering also depend on
the media tools available on the host; Ora shows an unavailable capability rather
than pretending it can run.

Closing a Standard or Private Dialogue is reversible. It releases finished video
records and caches but does not delete its media or kill active work. **Delete
Forever** is different: Ora first stops or tombstones video work which could still
write to the Dialogue, performs the protected purge, and then clears remaining
plugin state.

If the video package is absent, Ora starts normally; the video controls, settings,
browser overlay, assets, and routes do not appear. A broken package is logged and
its browser surface is suppressed. Repairing or removing it and restarting gives
the guaranteed clean state. Core transcription and Inquiry audio/video drop
remain. There is no install or enable button in Settings. A checkout owner adds,
removes, or restores the first-party package and restarts Ora. See
[[Reference — Ora Feature Plugin Architecture]] for the technical boundary.

---

## Before you start

You need:

- Git
- Python 3.11 or newer
- Node.js and npm (the installer sets up Ora's three pinned MCP servers and their browser, and stops if these are missing)
- At least 5 GB free disk for a source install
- Internet access to GitHub, PyPI, the npm registry, and Playwright's browser CDN — the installer fetches the pinned MCP servers and their exact Chromium from the last two, and stops if either is unreachable. The model-catalog sources are wanted but not required: if OpenRouter is unreachable the install falls back to the catalog packaged with the checkout.

You do not need an existing vault, and you do not need Pandoc or Typst. The installer creates the vault when there is none, and downloads the two converters Word and PDF export need when the machine has none.

Optional but useful: an OpenRouter API key (broad cloud-model access), a Tavily key (web search), an Artificial Analysis key (better model-selector data). None are required to finish the install — you add them later.

There is no packaged one-click installer. The install is a source install: you clone the repository and run a script.

---

## Install Ora

### macOS desktop `[macOS]`

1. Clone the repository and enter it:
   ```bash
   git clone https://github.com/ora-commons/ora.git ~/ora
   cd ~/ora
   ```
2. Run the installer for the Solo profile:
   ```bash
   python3 scripts/install.py --profile solo
   ```
   The installer runs nine steps (pre-flight, which also creates the vault → Python dependencies → Word/PDF converters → profile → catalog refresh → registry sync → user pipeline and the four model presets → smoke test → API orientation). It is safe to re-run.
3. Install the recommended per-user supervised service:
   ```bash
   ./scripts/ora-launchd.sh install
   ```
   The installer starts Ora immediately and configures macOS `launchd` to keep it available across logins. It also verifies that the responding server belongs to this checkout and updates an existing Ora.app launcher to delegate to the same service.
4. Open the exact `Health:` URL printed by the command. Ora normally uses port 5000 but may select the first available port through 5010. Check the installed service at any time with `./scripts/ora-launchd.sh status`.

Solo is the only supported profile today. Hybrid and Organization are reserved — the installer refuses them with a clear message.

### Windows — native `[Windows-native — untested]`

1. Clone and enter the repo:
   ```powershell
   git clone https://github.com/ora-commons/ora.git $env:USERPROFILE\ora
   cd $env:USERPROFILE\ora
   ```
2. Run the installer with the Python launcher:
   ```powershell
   py -3 scripts\install.py --profile solo
   ```
3. Start the server with `start.bat`. Oversight is enabled by default. For a one-off diagnostic launch without the Oversight event/deadline lanes, use `start.bat --no-oversight`.

The native Windows path has not passed a clean-install test. The current launcher does honor `ORA_HOME`, prefer the checkout's virtual environment before `py -3`/`python`, validate an explicit `PORT`, forward arguments safely, stop only the server owned by this checkout, and verify that the responding server reports this checkout before opening the browser. Those improvements do not give it the same feature defaults as the POSIX foreground launcher: `start.bat` enables the Execution Review loop but does not itself enable the POSIX defaults for RAG selection and fit-gate slot, web extraction, runtime engram promotion and auto-commit, deliverable scrubbing, or OR statistics. Unless you set those environment variables separately, Windows may run a reduced or differently configured pipeline even though Oversight is on.

Quoted native paths in slash commands now retain their backslashes and lose only their balanced wrapper quotes. That fixes the shared parser; it does not prove every downstream tool against every Windows path. Native process handling, keyring behavior, Bash-dependent maintenance helpers, MLX alternatives, and the complete browser/server lifecycle remain untested. Treat both Windows-native and WSL as unverified desktop paths; the supported non-Mac target remains the Linux server profile.

### Windows — WSL `[WSL]`

Install Ubuntu under WSL, then run the desktop install steps inside it — but treat this as **untested**. The technical documentation labels the desktop installer and `start.sh` as untested on WSL and Linux; WSL behaves like a Linux desktop, which is a best-effort path, not a verified one. WSL makes the Python tooling behave like Linux; browser and file integration feel less native than a Windows-native install. If you need a supported non-Mac path, use the Linux server install below.

### Linux server (headless, API-only) `[Linux server]`

1. Clone and enter the repo:
   ```bash
   git clone https://github.com/ora-commons/ora.git ~/ora
   cd ~/ora
   ```
2. Run the server installer:
   ```bash
   ./scripts/install-server.sh
   ```

This path builds a Linux Python environment, routes every model call to cloud APIs (no local models), stores keys in `~/.config/ora-server.env`, and runs a smoke test. It does not expose the browser UI publicly.

### Add local models (optional) `[macOS]`

The core install does not download model weights. To add local models later:

```bash
python3 scripts/install.py models
```

The flow detects your RAM, recommends matching options, and asks before downloading. Expect tens of gigabytes per model. Local models run on Apple Silicon (MLX) — on any other platform, Ora routes model calls to the cloud instead.

---

## Start and stop the server

**Recommended supervised setup** `[macOS]` (run once):
```bash
./scripts/ora-launchd.sh install
```
The command starts Ora immediately, installs a per-user `launchd` service with `RunAtLoad` and `KeepAlive`, verifies the expected checkout, and prints the exact `Health:` URL. Use that reported URL: the server binds the first free port in 5000–5010.

After supervision is installed, `./start.sh` starts the service if needed and opens Ora at its reported port. `./stop.sh` stops the service but keeps it installed. For explicit service control:

```bash
./scripts/ora-launchd.sh status
./scripts/ora-launchd.sh restart
./scripts/ora-launchd.sh uninstall
```

For a one-session, unsupervised macOS launch, run `./start.sh` before installing the service. If an unmanaged server is already running when you decide to install supervision, stop it with `./stop.sh` first, then run the install command above.

**Start** `[WSL]` `[Linux-desktop — untested/best-effort]`:
```bash
./start.sh
```
Open the exact URL that `start.sh` prints. The script is verified on macOS only; on WSL and Linux desktop it is untested.

**Start** `[Windows-native]`: run `start.bat`. Oversight and the Execution Review loop are on by default; `start.bat --no-oversight` is the explicit diagnostic opt-out. Use the exact URL the launcher reports. The launcher does not set the additional POSIX feature defaults named above, so supply them explicitly if you need equivalent behavior.

**Stop** `[macOS]` `[WSL]` `[Linux]`:
```bash
~/ora/stop.sh
```
On macOS this delegates to the installed service when present; otherwise it stops only the Ora process belonging to this checkout. Use `./stop.sh` on every POSIX platform: `start.sh` backgrounds the unsupervised server, so closing the terminal is not a reliable stop.

**Stop** `[Windows-native]`: run `stop.bat`.

---

## Add your API keys

You need at least one working model endpoint before Ora can answer. The core install completes without keys, so this is usually your first step after installing.

1. Open the interface at the exact URL printed by the launchd install, or rerun `./start.sh` to print and open the current URL (port 5000–5010). The `status` action inspects service state; it does not report the health URL.
2. Open **Settings → External APIs**.
3. Add a key. OpenRouter is the broadest single choice; direct provider keys (Anthropic, OpenAI, Google, and others) skip OpenRouter's gateway markup for those providers' own models.
4. Save. On macOS desktop, keys go into the system keychain, not a plaintext file.

For a conversational walkthrough of provider choices and key-safety guidance, see
the retained **API Key Setup** guidance document. Key entry itself remains in
**Settings → External APIs**.

On the Linux server path, keys live in the plaintext file `~/.config/ora-server.env` (permissions `600`), not the keychain — that is by design for a headless host.

---

## Choose and switch models

Ora assigns models to named roles (the analyst, the reviewer, the fast helper, and so on) rather than tying you to one model. You set this in the interface.

**Pick a configuration.** Open **Settings → Models**. Four presets are always available — Free, Budget, Speed, Premium — plus any custom configurations you save. Picking one sets which models fill which roles.

**Edit a single role.** In the same Models pane, change which model fills a given slot; the interface writes the change into your active configuration's routing. (Edit routing through the Models pane, not by hand-editing config files.)

**Delete a custom Model Profile.** Click **Delete** on its card and confirm. Because deletion is protected, Ora pauses it for approval instead of removing the profile immediately. In **Review Queue → Paused**, approve the request, then return to **Settings → Models** and click **Delete** again (and confirm again) to complete the deletion.

If you pick Free, expect the trade-off up front: free models are rate-limited and sometimes unavailable. Add OpenRouter credits or a direct provider key for daily use.

---

## Choose Persona, Output Style, and values

Ora keeps three controls separate. **Persona** is the speaking identity — who is answering. **Output Style** controls delivery and form, such as tone, arrangement, diction, and genre. **`mind.md`** supplies your values and personal context; it does not choose the Persona or Output Style.

For ordinary work, Persona resolution follows this order: the active project's Persona, then your global default, then packaged Ora.

Scheduled email drafts are the exception. They use the global default Persona unless you explicitly choose another available Persona, and the saved draft records and displays the resolved identity. If that explicit choice is unavailable, Ora refuses to create the draft rather than substitute another identity. Creating a draft does not activate or approve a Trigger, contact an email provider, send email, or grant permission to send.

---

## Do work

1. Open Ora at the exact reported URL (port 5000–5010), type your question or task in the Inquiry pane, and submit.
2. Wait. Ora is async by design — for serious work it runs the full pipeline server-side and does not stream a live progress bar. Submit, leave, come back. The interface reconciles what finished while you were gone.
3. Read the result in the Findings pane — the response side of the Dialogue. When Ora produces a diagram, it appears in the Exhibits pane, the canvas beside the text.

**Run a framework** (a whole procedure, not a single answer):
```
/framework <name> <your input>
```
Invoke a framework with no input to have Ora walk you through it one question at a time.

**Use tools without leaving the loop.** Do your tool-using work at the exact local Ora URL reported by the launcher, not at claude.ai or ChatGPT directly. The reason is mechanical: tools (web search, file access, knowledge search) run in the Python server between you and the model. A direct commercial chat interface has no Python in the loop, so the tools do not run.

---

## Schedule exact work with Triggers

Use a Trigger when an already registered unit of work should run on one explicit cause: your manual request, a file change, a named-timezone calendar occurrence, or successful completion of another Trigger. This is separate from Programming. A Trigger can invoke a registered project tool or a user-invocable framework; the narrow email action is manual-only. You cannot paste an arbitrary shell command into this surface.

### Create and activate a Trigger

1. Open **Oversight → Scheduled** and click **+**.
2. Name the Trigger, choose its cause, and choose the registered action. For a file change, choose a path under a root Ora is actually watching. For a calendar cause, choose the local schedule and explain why time itself—rather than an available runtime event—is the cause.
3. Save the draft. You may use **Run now** before activation to verify what the action does; a draft or paused project-tool Trigger first places that exact manual run in Paused review and consumes its one-shot approval when you retry it. This test run does not activate the Trigger. Retired Triggers cannot run.
4. Choose **Review and activate…**. Read the cause and the material action that will run—including its exact arguments, stdin, or framework input together with the resolved Project nexus and profile when present—alongside the specification digest, bound program identity, and any calendar/intermittency notice. **Approve and activate** accepts only that exact version; if the draft or registered program changes, review it again.

An active card shows status, next due time when relevant, and recent firing history. For a project-tool Trigger, exact activation is standing permission for that specification and Project binding—including the registered project folder used as its working directory—so each occurrence can run without another project-tool prompt while the Trigger remains active. Expand the card to inspect its bound message, run once, pause, resume, or retire it. Pausing or retiring revokes permission for new firings; resuming creates a new admission identity, and editing returns the Trigger to draft. Work already claimed keeps the reviewed action snapshot, so an edit cannot replace it mid-run and an older file, calendar, or completion event cannot run a later version. Retiring removes it from the default Scheduled list; the default list shows draft, active, and paused Triggers, not retired ones. Email keeps its own exact send approval: an approved email can be cancelled and retired only before provider contact, and Ora cannot recall a message after it reaches the provider.

### Understand availability and failure

Triggers act only while Ora is running. There is no cron, launchd, sweep, interval scan, or promise of 24/7 execution while the computer is off. An expanded Scheduled card and **Review and activate…** show the routine facts supplied by the server: the action runs locally; remote execution is unavailable; idle-sleep protection is offered only on a supported host, only during an active action, and ends with that action; and Ora cannot wake a sleeping Mac. These labels describe the existing runner rather than adding a capability, and they do not change the Trigger lifecycle, firing receipts, or error handling. A calendar Trigger follows its declared missed-occurrence policy when Ora returns. A file change that happens entirely while its event lane is unavailable is not reconstructed from a later scan.

After an upgrade, the first delivery from a calendar deadline armed before authenticated admission identities existed is reported as stale. Ora runs no action from that legacy payload and arms the next occurrence in the current authenticated format.

The Scheduled group shows warnings only for lane availability or repeated lane restarts, and separately reports the internal maintenance deadlines Ora arms for itself. Firing-evidence or telemetry degradation appears through general Oversight health, not as a Scheduled-card warning. A Trigger firing is claimed durably before work begins. Project-tool firings recheck the reviewed Project folder, manifest, executable, script, interface, and exact arguments or stdin before the subprocess starts; the exact authenticated absolute executable is the child argv's first element, and each protected effect has authenticated start and success/failure receipts. Action work has a whole-firing deadline. On POSIX, a post-start timeout terminates and verifies the known action process group, but a descendant may have created a new session and escaped it. Ora therefore leaves that firing and its protected start nonterminal, keeps the overlap guard through restart, and blocks another firing even when the recorded wrapper and group are gone. On Windows, Ora first assigns the held wrapper to a uniquely and globally named, non-breakaway Job Object whose noninherited sole ownership handle kills every member when it closes; failure to create that global name, including a collision, refuses before action work begins. Ora saves the root process's PID and Windows creation time, current and observed member identities and counts, and the Job's containment facts before allowing action work to begin. The Job continues to contain late children even after an intermediate process exits. The existing duplex hold remains through every result, error, transfer failure, and cleanup path; Ora releases a completed wrapper and terminates the Job, while timeout or cleanup terminates the still-held Job directly. It marks terminal evidence and releases the overlap guard only after the original owner handle reports zero active processes, that observation is durably saved, and the wrapper is dead. After restart, that saved owner-zero fact is conclusive. Without it, reopening the same Job name—even when the reopened object looks empty or matching—cannot authenticate the original object and leaves the firing unfinished; Ora does not terminate the reopened object. A true not-found result may release only when the saved global-name, assignment, containment, kill-on-close, non-breakaway, noninheritance, and sole-owner facts all validate; every other open, setup, membership, termination, persistence, handle-close, or recovery uncertainty keeps later firings blocked. A successful source Trigger stages exact dependent-admission deliveries durably and unfinished deliveries replay on startup. The dependent card shows a **completion pending** badge and explains the delivery when expanded; `/trigger list` and `/trigger show` place the same information in a separate **Pending completions** section rather than mixing it into firing history. If the dependent Trigger changed or was reactivated after source completion, the badge says the delivery is blocked because it targeted an earlier approved version. Ora does not run the current action, and the old delivery stays pending visibly.

The `/trigger` and `/triggers` slash commands expose the same Trigger service when a keyboard path is preferable. `/trigger rollback` is only the pre-provider cancellation for an email Trigger. To restore an EventLedger mutation's authenticated before-bytes and permission mode, use `/maintenance rollback <event-id>`; Ora refuses if the recorded after-bytes or mode have since changed, or if a backup's mode no longer matches its bound manifest value. Authenticated rollback is available only when the manifest digest and mode-bearing identities were independently bound during preparation. Older mode-less or malformed material fails closed; Ora does not infer permissions from the current backup. At startup, that refusal remains a separate diagnostic instead of being reported as a restoration, and a later independent event can still recover. If interruption occurs after restoration starts, the same authenticated rollback resumes at startup and refuses any path that is no longer one of its bound before/after byte-and-mode states.

---

## Programming

Use Programming when you want Ora to change and verify a real Git repository. Use ordinary Inquiry for answers, explanations, comparisons, drafts, and framework-guided thinking.

Programming begins only from the **Programming** toolbar action. Ora never classifies ordinary conversation into Programming and does not add Programming to the framework picker.

### Plan repository work

1. Open **Programming**.
2. Enter the repository's short name, such as `ora`, `vault`, or `mainstreetindependent`, or enter its Git worktree path.
3. Describe what should change in ordinary language and submit the Inquiry input.
4. Wait while Ora inspects repository instructions, implementation, tests, Git state, and visible automation.
5. Answer only material questions Ora cannot responsibly resolve from inspection. Ora asks no more than three questions per round and no more than two rounds.
6. Read the one proposed plan. It identifies the outcome, component scope, non-goals, protected work, milestones, checks, authorized effects, and Git finish line. Ora rejects a plan whose displayed finish line disagrees with its runtime authority. The tracked root instructions determine whether Documentation-Code Parity applies, so Ora rejects a planner attempt to turn it on or off.
7. Choose **Approve and run** only if that complete boundary is right. Cancel leaves the repository unchanged.

Planning is read-only. Ora rechecks the Git baseline before creating a task branch. Safely separable unrelated work is protected and left uncommitted while Programming continues; Ora stops only when task work and user work cannot be separated safely.

### Follow execution and review

After approval, the Programming panel shows the current milestone, progress, accepted commit, and reviewer outcome. Ora's executor changes the real task repository and runs only the checks scheduled by the approved plan. A separate fresh model call then inspects the raw diff, repository, and authorized check results without receiving or trusting the executor's transcript.

When the plan declares Documentation-Code Parity impact, milestone reviews do not use a packet that later commits would make stale. After all milestone commits, Programming pauses at **Final documentation evidence required**. Generate the complete five-repository packet from those current heads, paste the JSON into the panel, and choose **Resume final review**. The pasted text passes through the same Standard/Private/Stealth privacy check as other Programming text. The packet identifies each exact root, base, `codex/` or `ora/` task branch, and head. Its plan, packet, documentation dispositions, and later reviewer verdicts must all cover the stable unique set from the passing gate's one `affected surfaces:` line. Programming rejects invalid JSON, missing evidence, a default/other branch, dirty or detached worktrees, any head that no longer equals the verbose gate, or any supplied cumulative diff that is not byte-for-byte identical to its raw live gated base-to-head diff, including trailing spaces and newlines. Use `[no changes]` only for a genuinely empty diff.

Reviewer outcomes mean:

| Outcome | Meaning |
|---|---|
| **CONTINUE** | The current slice is sound and approved work remains. |
| **FIX** | A substantive defect can be corrected within the approved plan; at DCP final review, the five-repository coordinator receives it instead of the single-repository executor. |
| **DONE** | Final cumulative review proves the approved outcome complete. |
| **ASK USER** | Safe continuation requires changed scope or authority, a human-only decision, separation of user work, or a spend decision. |

Ora commits each accepted slice before continuing. Those commits are the rollback and resume points. Programming creates no separate Run record, Process Library, Trigger, lifecycle store, or background Programming daemon. The user-authored Scheduled Triggers above are a separate Oversight facility and do not wrap Programming work.

### Understand evidence and completion

The reviewer independently obtains evidence that matters to the plan. It may run local checks, inspect the implementation, fetch an authoritative outside source, or directly inspect an image or rendered PDF. An executor's statement that a test passed, a page says something, or an image looks correct is not evidence.

A required criterion remains unverified when its source or artifact cannot be inspected. Ora corrects it when possible inside scope and asks only when verification needs new authority, credentials, production effects, or human-only access.

Completion requires final **DONE**, clean accepted-slice commits, and the approved finish line:

- **local commits** — stop with the task branch ready locally;
- **push** — push that branch;
- **pull request** — push and open a pull request; or
- **merge** — perform the explicitly approved merge path; or
- **coordinated DCP** — return five reviewed local branches for the approved coordinator landing.

For a documentation-impacting plan, **local commits** stops with all five reviewed branches local; the alternative **coordinated DCP** finish authorizes the five-repository coordinator to land only those exact reviewed heads. Ordinary single-repository push, pull-request, and merge finishes are not valid for DCP work. Programming reports the approved finish with the five reviewed roots, bases, branches, and heads, and never lands only the current repository. If final review returns **FIX**, or returns **CONTINUE** without completing the task, the panel changes to **Coordinated documentation correction required** and keeps the full consolidated defect. Programming clears the submitted packet, does not run the current repository's executor, and does not create a correction or empty commit. The five-repository coordinator corrects the participating task branches. Then recover the task and submit a fresh current gate and packet for final review.

If a newly discovered finish-line effect would deploy, publish, message, use credentials, or mutate another system without plan authority, Ora returns **ASK USER**.

### Keep documentation and code together

For code-changing work in the vault, Ora, ora-ai-app, ora-ai-org, or MSI, the plan identifies the documentation surface each changed path belongs to. If behavior, a user or operator promise, configuration, route, output, or material failure mode changes, update the owning vault canonical in the same task. When the ownership map names a section, changing some other part of that file does not count. If the change truly has no documentation effect, the final task commit records exactly one `Documentation-No-Impact: <surface-id>` line for that surface and the independent reviewer confirms it. Extra, duplicate, or unrelated no-impact lines are rejected. An unfamiliar production path receives its repository's conservative owner rather than escaping the decision.

Regenerate registered Ora mirrors and public-site derivatives from their vault canonicals before final verification. Technical Documentation, Accessible Overview, Using Ora, and the Thinking Tools singleton use the body-only rule: remove the vault YAML and its one following blank line, then keep every remaining byte identical. The authoritative check is Ora's focused `documentation-integrity --verbose` verifier with explicit roots and base commits for all five task worktrees. It refuses a pre-activation vault base and checks declared ownership, named-section changes, references, lifecycle state, task dispositions, accepted-finding boundaries, and exact derivative parity. It does not determine whether ordinary prose is semantically true.

At the final evidence boundary, the independent reviewer receives all five exact live cumulative diffs and task-branch states, global/Programming-skill instruction changes, the authoritative affected-surface set printed once by the passing gate, exact canonical-section changes, every no-impact declaration with its rationale, propagation results, the verbose gate output, and the authorized focused-test output. It compares behavior with each canonical section or explicitly accepts the no-impact rationale, then gives one verdict per gate-affected surface. Missing, mismatched, or stale evidence is not acceptance.

Seven managed local hooks are installed and verified: one blocking pre-push hook in each of the five repositories, plus fail-open post-commit framework-pair audit hooks in Ora and the vault. An owned-code push blocks when the coordinator's complete five-root task context is missing. The audit labels only the exact accepted E-093 and Video/D35 states as accepted external findings; new, changed, verifier, and queue-write failures remain visible. These hooks are bypassable and do not create remote enforcement or an atomic five-repository commit, so the coordinator holds all participating merges until both the combined check and semantic review pass.

When **coordinated DCP** was approved, the coordinator confirms after review that every clean branch head still equals the head printed by the gate. Only those exact reviewed heads may use `--no-verify`, solely to avoid repeating the same DCP pre-push hook; the exception does not bypass another protection. All remote task branches and pull requests must be ready before the first merge. Recovery is Git revert in reverse landing order.

Vault auto-sync is the separate backup-transport case. It may bypass the local DCP hook so ordinary vault edits still reach the remote backup, but that push is not task certification and does not authorize a person to bypass the coordinated workflow. A later code task still evaluates any canonical state it touches.

> **Testing is evidence for the changed behavior, not a second project. The task scope lock's named check list is the exact testing ceiling: run every named check and nothing additional. Do not run a full suite, full build, benchmark, broad audit, `--check all`, or an extra reassurance check. If a newly discovered material risk cannot be judged by that list, stop and revise the scope with the user before running another check. Stop when the named checks pass and material review is satisfied. The completion report must list every check actually run.**

### Leave, resume, cancel, or recover

Closing the Programming panel restores ordinary Inquiry; it does not create a persistent browser workflow. Before approval, cancel simply discards the proposal. During or after execution, the plan, task branch, commits, current diff, and checks are the recovery record.

To continue later, return to that repository and branch. Do not look for a Programming Run Inspector, process review queue, process-bound Trigger Manager, Process Library, activation control, or generic reopen action; standalone Programming does not create those objects. The separate **Oversight → Scheduled** Trigger surface is for exact event/deadline work, not Programming recovery.

### Troubleshoot Programming

| Symptom | Meaning | What to do |
|---|---|---|
| Repository required | No repository name or Git worktree path was supplied | Enter a short name or the worktree root |
| Planning stopped | Inspection or the configured planner failed | Read the visible error, correct repository/model access, and submit again |
| Baseline changed | Git state differs from the inspected plan baseline | Preserve or finish the unrelated work, then request a new plan |
| **FIX** repeats without progress | The same substantive defect survived three ordinary non-DCP cycles without a changed task diff | Review Ora's consolidated **ASK USER** blocker |
| Required evidence is unavailable | The reviewer could not directly inspect a source or artifact | Grant only the exact authority/access needed or revise the plan |
| Documentation review cannot accept | A five-repository packet item, disposition, propagation result, gate result, test output, or per-surface semantic verdict is missing or contradictory | Complete or correct the exact evidence shown; do not substitute a broad test or an extra no-impact line |
| Final documentation evidence required | Milestones changed the branch or a prior packet is stale | Generate the focused five-root gate and complete packet from the current clean branches, paste that JSON, and resume final review |
| Coordinated documentation correction required | Final DCP review found a defect that may span the five repositories | Give the displayed consolidated defect to the five-repository coordinator, correct the participating branches, recover the task, then paste a fresh current packet |
| Programming needs a decision | Ora cannot continue responsibly inside the approved boundary | Decide the specific scope, authority, access, or spend question shown |
| Work is complete locally | The approved finish line was local commits | Inspect or continue from the task branch; push only when intended |


## Diagnose a problematic result with Trace Walk

**Current-feature note (2026-07-16, post-pin).** Trace Walk landed in Ora PR #269 (merge commit `241a31c0`, implementation commit `99638ef3`). This section is a scoped description of that shipped feature; it does not re-pin the rest of this guide from its installed-system baseline at `7a5e8f40`.

Tracing is automatic and on by default. There is no `/trace` slash command and no setup command to run. Each eligible turn records what actually happened under `~/ora/data/pipeline-traces/<dialogue-id>/<turn>/`. Setting `ORA_PIPELINE_TRACE=off` (also `false`, `0`, `no`, or `disabled`) disables new traces globally. A Stealth Dialogue never creates a trace.

### Open and read a trace

1. Go to the problematic turn in its Dialogue.
2. Hover over the lower-right edge of the Findings pane. The output toolbar appears.
3. Click **Trace** (tooltip: **How this was made**). The button is enabled only when that turn carries a trace reference.
4. Read the overview badges first: trace kind, terminal status, effective Gear, and retention state. If a Gear 4 attempt fell back to Gear 3, the Gear badge reports the Gear that actually completed.
5. Check the stage categories, then choose a recorded step in the left-hand map. Trace Walk shows a redacted structural projection: stage identity, endpoint/slot and health fields when recorded, retry or contingency markers, verdicts, routing/persistence state, and lengths/hashes instead of raw prompt or output text.

The manifest categories have literal meanings:

| Category | Meaning |
|---|---|
| Actual | A real `step*.json` artifact exists on disk. |
| Derived | A computed artifact such as step health or cost summary exists; it is not itself a production stage. |
| Missing expected | A normally required stage is absent from a completed turn. This deserves investigation. |
| Skipped | An optional stage did not run, or an exceptional exit prevented a required stage from being reached. |
| Replaced | A fallback or short path displaced normally expected work; the manifest retains the original expectation rather than rewriting history. |
| Contingency | A recorded retry, fallback, no-endpoint, or other exceptional production path actually ran. |
| Unexpected | A real stage ran but belongs to none of the expected, optional, replacement, or contingency sets. |

Use the evidence this way:

| Symptom | Inspect first |
|---|---|
| Wrong model, mode, or routing | `step1-pre-routing`, model-call configuration records, endpoint/slot fields, and the effective Gear badge |
| Sources or retrieved context seem absent | Step 2 context assembly, supplemental-RAG, and web-consultation stages; distinguish **skipped** from **missing expected** |
| Answer looks degraded or fell back | Step health plus **contingency**, **replaced**, and **skipped** stages |
| Findings differ from what the pipeline produced | `step-terminal-output`; its local artifact records the exact value only after output routing/delivery, including persistence state |
| A factual claim or verification seems unsupported | Claim-evidence assembly, verifier, quality-gate, and retry/fallback stages |

### Preserve, investigate, or export

- Click **Pin trace** before an important investigation. Unpinned traces are normally swept after 30 days; pinned traces are exempt. The same control becomes **Unpin trace**.
- Select the most suspicious step and click **Investigate**. Add the symptom when prompted. Ora creates a separate P-Debug diagnostic turn in the same Dialogue; it does not rerun, replay, approve, or modify the original trace.
- Click **Export HTML** for a portable report. Browser views and exports recursively redact raw strings and bytes to structural metadata, lengths, and SHA-256 hashes. A Private trace is labeled private and its raw content is omitted from the export. Investigation stays in the originating Dialogue and keeps its privacy tag. Stealth produces no trace at all.

The raw local trace files are more sensitive than the Trace Walk view: they can contain exact prompts, model responses, and terminal values. Treat `~/ora/data/pipeline-traces/` as private local diagnostic data and do not share a raw turn directory without reviewing it.

### Reproduce a problem from the command line `[macOS]`

Use the exact URL reported by the Ora launcher; do not assume port 5000 when the launcher selected another port.

```bash
cd ~/ora
export ORA_URL="http://127.0.0.1:5000"  # replace with the reported URL

./scripts/ora-test --list-configs
./scripts/ora-test --list-modes
./scripts/ora-test --server "$ORA_URL" \
  --id trace-repro-001 \
  "Describe the problem you need to reproduce"
```

Add `--config NAME` to use a saved configuration without changing the server's active configuration, or `--mode MODE` to pin a mode. The command prints the Dialogue id, pipeline stages, final trace directory, and a cost summary when available. `--no-wait` submits in the background; it is POSIX-only and gives you a directory pattern rather than a completed trace immediately.

A trace reference is the final two path components, `<dialogue-id>/<turn>`. From `~/ora`, inspect or preserve it without opening the browser:

```bash
python3 -m orchestrator.pipeline_trace status '<dialogue-id>/<turn>'
python3 -m orchestrator.pipeline_trace pin '<dialogue-id>/<turn>'
python3 -m orchestrator.pipeline_trace unpin '<dialogue-id>/<turn>'
```

For automation or remote diagnostics, the server exposes safe read-side projections. Replace the placeholders with the Dialogue id and turn timestamp from the trace reference:

```bash
curl -s "$ORA_URL/api/trace/list/<dialogue-id>"
curl -s "$ORA_URL/api/trace/manifest/<dialogue-id>/<turn>"
curl -s "$ORA_URL/api/trace/step/<dialogue-id>/<turn>/<step-name>"
curl -o ora-trace.html "$ORA_URL/api/trace/export/<dialogue-id>/<turn>"
```

If **Trace** is disabled or absent, the turn has no trace reference. Common causes are a turn created before Trace Walk was installed, a globally disabled trace layer, a Stealth Dialogue, an incomplete/current turn, or a fail-open trace-write error. Tracing is observational: a trace-write failure must not change the answer or crash the pipeline, so server logs are the next place to check.

---

## Where your things live

- **Vault** — `~/Documents/vault/`. Put files here that you want Ora to search: notes, documents, project files.
- **Dialogues** — `~/Documents/conversations/`. Raw session logs are saved automatically here. Lifecycle envelopes and retrieval caches are Ora-managed companions; use the interface rather than editing any of them by hand.
- **System prompt** — `~/ora/boot/boot.md`. Ora reads this as its operating instructions.
- **Your values and context** — `~/ora/mind.md`. Customize this separate values layer from **Settings → Output Styles**.
- **Model configuration** — `~/ora/config/routing-config.json` (routing and slots) and `~/ora/config/model-registry.json` (model inventory). Edit these through the Models pane, not by hand.

On Windows, read `~/...` as `%USERPROFILE%\...`.

**Check a project's metadata without changing it.** In an Ora source checkout, run `python -m orchestrator.project_documents check --ora-root <existing-ora-root> --vault <existing-vault-root> --project <nexus>`, substituting the actual roots and persisted project identifier. For one note, replace `--project <nexus>` with `--file <vault-relative-markdown-path> --owner <ordinary|matrix|output|chat>`. Choosing an owner does not prove the file belongs to it. The result lists each selected document's metadata errors, optional-description warnings and completeness. Exit 0 means a complete check without errors, 1 means document errors, and 2 means some selection or authority could not be checked. The command makes no repairs, date changes or index updates; inspect the named source before deciding how to correct it.

**Preview the folder map.** From the same checkout, `python -m orchestrator.project_orientation --ora-root <existing-ora-root> --vault <existing-vault-root>` prints the proposed shallow map. It lists immediate folders and registered project folders, not every file. Descriptions come only from existing folder guidance or explicit Matrix metadata; missing descriptions and unavailable Matrices remain visible. Read the generation time and completeness notice rather than assuming a continuously current inventory.

Add `--write` only when you want to save that preview's kind of output as root `Directory Map.md`. The command generates a fresh snapshot on each invocation. It refuses unsafe destinations and an existing file it cannot recognize as its generated output; do not delete or rename a colliding user file to work around the refusal. A failed atomic replacement preserves the previous map. No timer or startup refresh is installed. The Registry remains the separate explanation of important documents. The map inherits source privacy, so a pointer to it is not permission to send its names or descriptions to a provider. P4 source acceptance uses synthetic examples; generating your real map is a separate deliberate local action.

---

## Update Ora

There is no packaged updater and no documented update procedure. Updating an existing install is open work in the system as documented — so this guide does not give you an update command, because the technical documentation does not yet authorize one. If you need the current state of the update story, check the repository and the technical documentation before changing a working install; do not treat any informal source-pull-and-reinstall sequence as a supported upgrade path.

---

## Recover from a failed install

The installer keeps state, so you can retry without starting over. The commands below use `python3` and POSIX paths `[macOS]` `[WSL]` `[Linux]`; on `[Windows-native — untested]` substitute `py -3` for `python3` and `%USERPROFILE%\ora\...` for `~/ora/...`.

1. See what happened: read `~/ora/install.log` `[macOS/WSL/Linux]` (`%USERPROFILE%\ora\install.log` on `[Windows-native]`).
2. Preview without changing anything:
   ```bash
   python3 scripts/install.py --dry-run
   ```
3. Continue a halted run:
   ```bash
   python3 scripts/install.py --resume
   ```
4. Start the install state over (this clears installer state only — it does **not** delete your vault, Dialogues, or downloaded models):
   ```bash
   python3 scripts/install.py --reset
   ```

For a script that is broken at the source level, `help/install-manual.md` reproduces the install by hand. For per-step failure fixes, see `help/install-recovery.md`.

---

## Troubleshoot

| What you see | What it means | What to do |
|---|---|---|
| Browser: "connection refused" | The server isn't running | On macOS install supervision with `./scripts/ora-launchd.sh install`, or run `./start.sh`; use the exact URL either command reports. On Windows-native, run `start.bat` `[implemented, untested]`; oversight is on by default and `--no-oversight` is the diagnostic opt-out, but the additional POSIX feature defaults are not supplied by that launcher |
| "No AI endpoints configured" | No working model key | Start the server, open its reported local URL, then add a key in **Settings → External APIs** |
| `<tool_call>` tags in the response | You're connected to a commercial AI directly, not to Ora's local server | Use the exact local URL Ora reports, not claude.ai / ChatGPT |
| Health passes, but Ora cannot read `~/Documents` | macOS privacy controls denied the supervised process access | Inspect `logs/ora-server.stderr.log`. In **System Settings → Privacy & Security**, grant the selected Python/Ora process **Files & Folders** access or **Full Disk Access**, then restart the service |
| Garbled output from a local model | The chat template needs a re-check | Switch models, or re-run the model setup |
| Output repeats itself | Repetition alone does not prove the Dialogue is too long; it may be a model, prompt, or coverage problem | Retry once, then inspect the Trace and numeric context coverage. Fork or start a new Dialogue only when you actually want a new branch or scope |
| Free model unavailable or rate-limited | Expected on the Free configuration | Add OpenRouter credits or a direct provider key |

If a command in this guide fails on Windows or Linux, that is consistent with the platform status: macOS is the tested target. Check the platform label on the step before assuming a defect.

On macOS, supervised stdout and stderr are written to `logs/ora-server.stdout.log` and `logs/ora-server.stderr.log`. An unsupervised `start.sh` launch uses the root `server.log`. Both log families are retention-bounded and rotated by Ora's retention sweeper.

---

## Try this now

- Install on macOS, run `./scripts/ora-launchd.sh install`, open the exact `Health:` URL it prints, add one OpenRouter key in **Settings → External APIs**, and submit a real question you have been putting off.
- Compare what comes back to what you would have written yourself in the same fifteen minutes.

---

## Cross-references

- (For why Ora runs two models instead of one, and why it makes AI reliable, see [[Reference — Ora Accessible Overview]].)
- (For how any of this works under the hood — the pipeline, the vault, the model routing, the platform matrix — see [[Reference — Ora Technical Documentation]].)
- (For the full install matrix and recovery detail, see `~/ora/help/install-guide.md`, `help/install-recovery.md`, and `help/install-manual.md`.)
