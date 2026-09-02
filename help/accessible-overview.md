# Ora — An Accessible Overview

*A reader-facing explanation of what Ora is and why it exists. It derives entirely from [[Reference — Ora Technical Documentation]] and introduces no new claims — where you want the mechanism in full, that document has it. This one is for the door you walk through first: why any of this matters.*

> Most of this overview retains the technical documentation's installed-system pin at `7a5e8f40`. Its descriptions of the Knowledge Library, optional video feature, and Aside help are current to their landed Ora implementations. Where it says a thing works, it works on macOS on Apple Silicon — the platform Ora is actually tested on. See the closing section on honest limits.

---

## What Ora is

Ora makes AI reliable enough to trust with real work.

That is the whole point, and it is worth saying plainly before anything else, because it is not what most AI tools are for. Most tools are built to give you an answer fast. Ora is built to give you an answer far more trustworthy than any single model would hand you — one built to survive its own scrutiny — and it gets there by refusing to trust any single model, including the one it just ran. It does not remove you from the loop. The judgment about whether the answer is right, and the authority to act on it, stay with you; what Ora does is make the answer worth that judgment.

Here is the reframe the whole system rests on, and I will state it once and not soften it: this is **assisted human intelligence**, not artificial intelligence. The intelligence stays in your loop. Ora is the apparatus around the models — it supplies generation and, more importantly, it supplies pressure against that generation. You supply the problem, the judgment about what matters, and the authority to act. Think of a telescope. It extends how far you can see. It does not replace the eye, and it is useless pointed at nothing by nobody. Ora is that, for analytical work.

In short: Ora is a system that turns capable-but-unreliable models into a process you can lean on.

---

## The problem: you can't trust one model, and you can't fix that by asking nicely

Why does raw AI need all this machinery around it? Because a single model, left alone, fails in ways that are quiet and expensive.

It **makes things up.** Confidently, fluently, with citations that look real and aren't. It has no way to tell the difference between what it knows and what it is generating to fill a gap — and "I don't know" is not a natural place for it to stop, so it doesn't. Researchers call this hallucination.

It **tells you what you want to hear.** It agrees with your wrong premise. It finds things to like about your bad plan. That is sycophancy, and it is baked in from training — the model learned that agreeing pleased the people rating it.

It **drifts.** Over a long session it quietly swaps the problem you gave it for a nearby one, and by the time you notice, it has built a careful, thorough answer to a question you never asked.

And it **forgets.** Every request starts from zero. It does not remember the last thing you told it unless something puts that memory back in front of it.

Now here is the part that traps people. You cannot fix any of this by adding an instruction. Telling a model "be honest, don't agree with me, stay on task" helps a little and solves nothing — because the same model that produced the problem is the one you are asking to catch it. **You can't proofread your own thinking. Neither can an AI.** The blind spots are identical because it is the same mind doing both jobs.

Reliability, then, is the real bottleneck. Not raw capability — the models are already capable. The question is whether you can run a long piece of analytical work end to end and trust the result without babysitting it. Ora's answer is that this is not solvable inside the model. It is solvable in the system around the model. The rest of this overview is that system.

---

## The core move: two models, not one

What do you do when a mind can't check itself? You get a second mind in the room.

That is Ora's central mechanism, and everything else is built around it. For non-trivial work, Ora does not ask one model to answer and then grade its own homework. It runs an eight-step sequence in which one model produces, a **different** model — with no stake in the first answer — challenges it, a reviser folds in what survives the challenge, and a verifier checks the result before it reaches you. Two models. Same problem. No shared context. What they produce together is something neither would have reached alone.

The cost is real and Ora pays it on purpose: two models means roughly twice the work per hard question. It is worth it because the errors this catches — the confident fabrication, the flattering agreement, the quietly-wrong conclusion — are the most expensive ones, the ones you would otherwise have shipped.

In short: the check has to be independent to mean anything, so Ora makes it a separate model, not a second opinion from the same one.

---

## Not every question deserves the full machine

Here is a fair objection: if every answer runs two models through eight steps, simple questions become slow and expensive. Ora agrees, and handles it with **gears.**

A gear is just how much of the machinery a question gets. A quick lookup runs in a low gear — one model, straight through. A serious analytical question runs in a high gear — the full parallel adversarial sequence with independent research on each side. You do not choose the gear by hand each time; the kind of question picks it. The point is that the reliability machinery is there when the stakes justify it and out of the way when they don't.

---

## Memory that survives you leaving

Come back to a project after two weeks and you will have forgotten half the discussion. The model has forgotten all of it: each request is still a new call.

Ora makes continuity a server responsibility. It keeps each Dialogue's raw user-and-assistant exchanges, reconstructs the history the current branch is actually allowed to see, and supplies that history to every processing path — from prompt cleanup and a direct answer through the higher analytical gears. The exchanges remain authoritative. Ora does not invent a separate store of “accepted decisions,” and it does not turn a model's guess about what you agreed to into memory.

Forking a Dialogue creates a real branch. The child starts with no copied messages and its own turn numbering; when Ora reads it, the server reconstructs only the parent prefix that existed at the fork point. Later turns in the parent cannot leak into the child, and the parent is unchanged.

You can also name **contributors**: other Dialogues or indexed atomic notes that should inform the work. Their order is preserved, duplicates are removed, and there is no arbitrary contributor-count cap. A contributed Dialogue brings only the recursively permitted part of its own ancestry; a contributed note brings its indexed whole-content chunks. Missing, privacy-withheld, or budget-deferred references stay accounted for instead of disappearing silently.

Ora then packs complete conversational turns and note chunks into the model's safe request size. The Dialogue maximum is 200,000 tokens, but the usable amount can be smaller once the selected endpoint's required payload, output allowance, retries, images, provider rules, and safety reserve are counted. Recent local context and the fork frontier come first, then eligible contributors, older history, and finally lower-priority background retrieval. Nothing is cut in the middle of a turn merely to make it fit.

Privacy belongs to each complete Inquiry-and-Findings pair. Ordinary history requires only matching valid privacy on its adjacent halves; the canonical envelope supplies the Dialogue and Ora reconstructs local order, so old halves need not repeat matching turn or chunk fields. A Dialogue may mix Standard and Private turns. Standard may use Standard; Private may also use Private; Stealth may use all three. Missing or conflicting privacy is withheld without guessing from the current Dialogue setting, often without a visible notice. Contributor status is also internal, so ordinary output may omit an unavailable contributor.

Library and word/meaning search apply surface-specific privacy or ownership checks before title, snippet, body, or distance. An archived Dialogue contributes only complete, cutoff-safe pairs with matching permitted privacy; archived notes and global-search rows stay excluded. Fork creation adds the stricter inherited-prefix check of canonical Dialogue/turn owner and saved chunk/privacy. Ora-managed runtime derivatives likewise require a complete owner tuple. Withholding preserves forks, projects, recovery data, canonical content, and source identity. Phase 4 automatic semantic recall remains unimplemented.

Ora now contains a narrow operator-only way to prepare a repaired copy of the current conversation index without changing the active one. For the 40,177 surviving exchanges, the owner has chosen 4,107 Private and 36,070 Standard, including 16,534 exchanges that old whole-Dialogue propagation had made Private and the owner has classified as Standard. The preparation keeps every surviving exchange, its stored search vector, and other metadata; it preserves 698 turns with one intentionally empty side and leaves out 884 recovery-only rows. It changes only the privacy labels in a fresh inactive copy. No live copy, source-envelope backfill, switchover, or deployment has happened.

After a new non-Stealth answer is safely stored, background extraction rereads and authenticates that current complete exchange and processes only it, not the preceding Dialogue as a substitute. Notes sent for human review keep the same exact owner and privacy; Stealth is never sent to this extraction path. If you make a displayed Standard turn Private, Ora tightens only the copies and Daily Note summary it can prove belong to that exact turn; missing, edited, conflicting, or ambiguous material is left alone and reported as incomplete. Making it Standard also reports any copy it could not reconcile. Stealth turns cannot be retagged, and approval cannot race a retag because both wait on the same Dialogue lifecycle lock.

Exports use the same rule. **Save output to Vault** ignores the browser's rendered title and text, rereads the canonical displayed exchange, and keeps Private output visibly labelled and tagged. An explicit Stealth output carries no privacy marker or source identity. **Save full Dialogue** authenticates every effective exchange while its owners are held stable: a Standard or Private target refuses a Stealth-owned turn, while a Stealth target may include eligible Standard or Private ancestry inherited through a real fork. If a safe title cannot be derived, the Stealth export uses a neutral name rather than leaking its source.

Dialogue lifecycle is equally literal. **Close** on Standard or Private hides the Dialogue from the ordinary sidebar while retaining it for restoration in Manage. The sidebar shows the current project's non-Stealth Dialogues plus only the active Stealth Dialogue. **Exit Stealth** merely navigates to the latest readable direct parent — even a Stealth parent — or opens a fresh Standard Dialogue; it closes or deletes nothing. **Delete Forever** is the protected Stealth purge. Descendants survive as detached branches with their own local turns, while explicit exports and copies already held by a provider, Git, or backups remain outside Ora's managed purge boundary.

So the model is not remembering. It is receiving a fresh, bounded, privacy-aware briefing whose provenance remains in the raw exchanges and source notes.

---

## A Library that shows what it knows—and what it does not

Long-lived work ends up in different places: Dialogues, refined Engrams, and ordinary project files. Ora's Knowledge Library gives those three stores one place to inspect without pretending they have become one database. Open it from the Dialogue sidebar and the upper Inquiry and Aside area becomes a single List/Visual workspace. The work you were composing is not thrown away. Your draft, attachments, selected Framework or Analysis, and Aside state are still there when you close it, while Findings and Exhibits stay visible below throughout.

The source choices are genuinely independent. You can see Dialogues alone, Files alone, Dialogues with Engrams, or any other subset. Project scope is separate and mutually exclusive: Commons is the universal eligible view, or one named project means exact membership. Changing project scope immediately removes the old rows, pin, checked selection, relationship details, preview, and actions before the replacement is requested, while leaving your source, search, filter, grouping, and sort choices in place. Refreshing the same scope keeps the old view until its replacement arrives together. List and Visual are two views of the same result state rather than separate searches. Pinning an item shows its known metadata and relationship summary below; it does not quietly replace the active Dialogue. A readable Dialogue moves into the normal reader only when you deliberately choose Continue. A Dialogue with no privacy-admitted exchange can remain visible as an anonymous metadata record while its title and content stay unreadable.

The top field is intentionally bounded. It performs ordinary keyword search over readable Dialogue bodies and exact or fuzzy indexed Engram text after project and source scope, then computes the counts and pages. It does not run semantic search or filter one page and call that a complete answer. Files do not support body keyword search, so Ora keeps matching Dialogues and Engrams while naming the missing File part. Metadata-only Dialogues remain visible without a query but cannot match body text. Files and Engrams still show previews as unavailable rather than turning an internal filesystem path into a browser link.

Checked readable Dialogues and atomic Engrams can ground a new Dialogue through Ora's existing contributor review. If checked context came from a named Library scope, only the contributor search is limited to that project; Commons sends no project filter. Each new creation opening resets that temporary search scope, and the new Dialogue's stored project membership still follows the usual creation rule. Files and metadata-only Dialogues are named as unsupported instead of quietly disappearing, and nothing is created until you complete the normal review and confirmation.

Visual mode follows the same honesty rule. Items are real keyboard-focusable controls arranged around Ora's existing raised O, which becomes the selected-item anchor while the Library is open. If a dense result cannot fit the measured arc without collisions, Visual states its capacity while every row remains in List. Relationship details are also available as ordinary readable text. Inventory summaries that merely say “two supporting relationships” never invent two neighbors. For a pinned readable Dialogue or compatible Engram, Ora can separately ask its existing Related view for named endpoints; it draws an O-centred line only when the returned item also carries a supported stored relationship kind. Similarity suggestions, metadata-only Dialogues, Files, and unavailable authority stay connector-free and say why. Activating a relationship node moves focus to its typed text equivalent, so the picture is never the only disclosure.

---

## Describe the work once, and it runs itself

The most surprising thing Ora does is let you hand it not just a question but a **procedure.**

A framework is a written specification of how to do a kind of work — how to evolve a fuzzy problem into a sharp one, how to turn a messy process into a repeatable one, how to formalize a pile of source material, how to shape an output. You describe what you want done, and the system runs it as a sequence of steps, the same way every time, through the same reliability machinery. Your expertise, encoded. Your process, running without you re-explaining it.

You describe what you want; it builds you the thing that produces it. There is a fixed, closed set of these — six frameworks covering the space of specifiable cognitive work: Problem Evolution, Process Inference, Process Formalization, Corpus Formalization, Output Formalization, and Decision Clarity Analysis. Closed means closed — there is no seventh waiting to be discovered; the six cover the regions.

And this is the right place to retire a piece of industry vocabulary. When people say "agent," they usually mean something mystified — an autonomous digital worker. Strip the mystique and an agent is just a framework that can run in the **background** instead of the **foreground**. Foreground work finishes while you watch. Background work runs on its own after you have submitted and moved on, and reports what it did. Same machinery, two modes. Ora is async by design: you submit serious work and come back to it, the way you would hand a task to a capable colleague rather than standing over their shoulder.

---

## What keeps a long job honest at 3 a.m.

So a framework is running in the background, on its own, while you sleep. What stops it from drifting off the goal and building the wrong thing beautifully?

A supervision layer whose only job is to watch the work against what it was supposed to be. At the points where a long job could go astray — a hand-off between steps, a claim that a milestone is finished — the supervisor is positioned to check the work against the original mission and the boundaries you set — not whether the system is busy, but whether it is still right. Be precise about how much of this is live in the installed system, though: by default the apparatus *watches*. It detects the hand-offs and milestone claims, assembles the context a verdict would need, and records what it sees. The step where a model actually renders a proceed/revise/escalate verdict and acts on it is deliberately held back — switched off unless you turn it on. So out of the box it is an observer that keeps a record, and the acting-on-verdicts loop is a capability you enable, not a default.

---

## Seeing, not just saying

Some things are clearer as a picture than a paragraph — a feedback loop, a decision tree, the structure of a risk. Ora can produce these, and it produces them honestly.

That last word matters. Left alone, models draw charts that mislead — truncated axes, decoration that distorts the data. Ora runs every diagram it generates through a check for exactly that kind of dishonesty before you see it, and it builds in a spoken-word description of each figure so the picture is not the only way in. The result shows up beside the Dialogue, in the Exhibits pane — a canvas you can also draw on and hand back to the system. The idea is simple: your mind has always worked partly in pictures, and the system finally meets you there.

---

## Quick help that does not become memory

The narrow **Aside** in the upper right is the place for a quick question you do
not want folded into the Dialogue. When you ask how to install Ora, recover an
install, use a feature, or work with video, Aside can search a deliberately small
help shelf: five public files shipped in Ora's `help` folder. It does not search
your vault, private notes, or Dialogue history.

That separation is the point. The useful paragraph is placed in the model's
prompt for that answer and then discarded. Aside remembers only a five-exchange
window in memory so you can ask a follow-up; it saves neither your question nor
the answer, and it cannot take action for you. If the faster help index is not
available, Ora reads and ranks the same five files locally. A help-search failure
does not prevent an ordinary Aside answer.

---

## Video is removable; transcription is not

Ora's video editor is the first **feature plugin**: trusted first-party code in
one optional folder. When it is present, Exhibits gains a video editor and a
Dialogue media browser, Settings gains a Video section, and Ora can capture,
arrange, preview, suggest edits for, and render media. The feature participates
in Dialogue cleanup, so Delete Forever stops anything which could still write to
the Dialogue before the purge proceeds.

Remove that folder and restart Ora, and the video editor, routes, settings, and
browser files simply do not load. Ora itself still starts. Dropping an audio or
video file into Inquiry for transcription continues to work because transcription
and the shared background job queue remain part of the core. This is a modest
plugin boundary, not an app store or a way to install arbitrary third-party code.

---

## The honesty layer you never see

Underneath all of it sits a quieter guarantee. Before Ora reaches for a tool — reads a file, runs a command, touches the web — a gate decides whether the request is well-formed and safe enough to proceed, and it fails closed: when in doubt, it refuses rather than runs. This is the brake that stays on for the one class of action where a brake matters most — the irreversible one, the one that touches a secret. It runs before the action, and it does not care what convenience setting you have flipped.

Documentation has its own, narrower honesty check. When a task changes code in the vault, Ora, either Ora site, or MSI, the task must identify the vault document responsible for that behavior. It updates that document before the task finishes, or records that the change truly has no documentation effect and asks the independent reviewer to confirm the judgment. Registered help copies and public pages are then regenerated from the vault source.

One focused check reads all five task worktrees together and confirms that the declared owners, references, lifecycle labels, and generated copies agree. This check cannot decide whether an explanation is actually true; the independent reviewer still compares the prose with the behavior. Seven managed local hooks are installed and verified: one blocking pre-push hook in each repository, plus fail-open post-commit framework-pair audit hooks in Ora and the vault. They require the coordinator's complete five-root task context for owned-code pushes, but they can be bypassed and are not a remote or atomic guarantee. The coordinator therefore still holds every participating merge until the combined check passes. If the coordinated landing must be undone, recovery is ordinary Git reversion in reverse order.

---

## Who it's for, and what it runs on

Ora runs on your own machine. A small server sits on your computer, your browser opens to it, and Python stays in the loop between you and the models — which is the whole reason the tools and the memory and the checking work at all. The models themselves can be local (running on your own hardware) or reached over the internet, and you can move any model into any role. You are never locked to one provider or one price.

The person Ora is built for is not a machine-learning researcher. It is someone with real expertise in their own field who has used AI, felt there was something more there, and wants the model to be a reliable instrument rather than a confident stranger. You bring the domain knowledge and the judgment. Ora brings the reliability. Neither works without the other — which is the point of calling it assisted human intelligence and meaning it.

---

## Honest limits

I will not oversell this, because the reader of a reliability system deserves to know where the reliability stops.

Ora is tested on macOS on Apple Silicon. That is the platform it actually runs on. Windows and Linux are somewhere between intended and untested — the groundwork is there, but a fresh install on a non-Mac machine is not something the system can yet promise, and this overview does not pretend otherwise. The technical documentation labels every command and path by platform for exactly this reason.

Some pieces are built but not yet finished, and the system says so rather than blurring the line: the landed Programming workflow can independently inspect evidence for repository work, but it does not turn every ordinary answer into a proved fact; multi-machine setups and a packaged one-click installer are planned, not done. And the deepest honesty of all is the one the reliability machinery is built to enforce on itself — a clean run means nothing you knew to check broke. It does not mean the right problem was solved. That judgment is still yours. It was always going to be.

In short: Ora is a working demonstration that reliability is a system problem, not a model problem — and a working system, on the platform it is built for, with the honesty to tell you where it isn't finished.

---

---

## Changelog

- **2026-08-29** — Added the implemented five-repository documentation-integrity contract and recorded the verified five-pre-push/two-post-commit local hook installation, with its semantic, bypassability, remote-enforcement, atomicity, and recovery limits.
- **2026-08-24** — Added current reader-level explanations of isolated Aside help and the removable first-party video feature; corrected the stale pre-merge evidence-layer limit. The rest of the overview retains its existing installed-system pin.
- **2026-08-11** — Rewrote the "Memory that survives you leaving" section for clarity. In the same pass the pin banner and this changelog were dropped from the document; both were restored on 2026-08-16 with no body change. Terminology and prose only — content remains pinned to ora commit `7a5e8f40`.
- **2026-07-12** — Closure currency note: Commons is the universal all-Dialogue view (it includes both empty-membership and explicitly project-assigned material); its canonical runtime sentinel is `commons`, while legacy `general` remains accepted. Commons saves now land at the vault root, and the live V3 interface is one fixed resizable Inquiry/Findings/Aside/Exhibits workspace rather than selectable layout presets. The body remains pinned to `7a5e8f40`.
- **2026-07-11** — Commons rename pass: the default project (where work lands when no project is selected) is now **Commons** in user-facing language, formerly General; its internal id is still `general` (code rename pending). Audited this overview — it contains no references to the default project, so no body text changed. Terminology only; content remains pinned to ora commit `7a5e8f40`.
- **2026-07-11** — User-facing nomenclature pass: Dialogues (conversations), Exhibits pane (visual canvas). Terminology only — content remains pinned to ora commit `7a5e8f40`; this is not a re-pin and the parity audit was not re-run.
- **2026-07-11** — Code-level rename landed (ora PR #218, commit `062b67a7`, well after this document's `7a5e8f40` pin): the default project's internal nexus id is now `commons`, with the legacy id `general` still recognized everywhere, permanently — not a one-time migration. This overview names no internal ids, so no body text changed. A currency note only; this document's pinned content is not re-audited against `062b67a7`.
- **2026-07-04** — Initial version (Documentation-Code Parity closeout, pinned to `7a5e8f40`).

*Companion documents: [[Reference — Ora Technical Documentation]] (the full mechanism, for engineers and evaluators) and [[Guide — Using Ora]] (how to install, run, and operate it).*
