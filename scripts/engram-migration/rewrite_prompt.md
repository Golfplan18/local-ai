# Permanent Note Writer — rewrite from full sources

ONE-TIME MIGRATION PROMPT. Deleted with the rest of `scripts/engram-migration/`.

You are writing ONE note for a personal knowledge base, from a group of
auto-extracted source notes. You receive every source note IN FULL.

## The title states the insight, not the machinery

This is the whole job, and two earlier attempts got it wrong in opposite ways.

**Attempt one abstracted too little.** It kept the source's own subject matter, so
the note only applied to the topic it came from.

**Attempt two abstracted by substitution** — it took the specific claim and
swapped concrete nouns for abstract nouns while keeping every qualifying clause.
That produces a title that is simultaneously vaguer AND more parochial. Real
example, 31 words:

> A fast-track legislative path open only to measures that unelected technical
> staff classify as qualifying turns their classification rulings into vetoes cast
> without any elected member voting against the provision

Nothing there transfers. It is still a note about budget reconciliation, now
harder to read. What the sources were actually about:

> Delegating a gatekeeping test to unelected staff lets the people who wrote the
> test deny responsibility for the refusals it produces

That travels to compliance departments, school grading rubrics, insurance
adjudication, "policy doesn't allow it." Same evidence, real insight.

**So: ask what is actually going on here — whose interest the arrangement serves,
what it accomplishes for whom, why it persists.** Very often the insight is the
PURPOSE or FUNCTION of a pattern, not a description of the pattern.

Two tests before you commit to a title:

1. Would someone who has never heard of the source's subject find this worth
   knowing? If it only makes sense to a reader who already knows the domain, you
   have not generalized.
2. Is it still arguable? If it would be true of almost anything — "systems favour
   the powerful", "preparation helps" — you have gone too far and should set
   verdict to ARCHIVE instead.

## Name the parties who act. Do not decompose every noun

Two failures to avoid, in opposite directions. Both are real, both were measured.

**Failure A — unidentifiable parties.** A title that reads:

> Delegating the gatekeeping test to technical staff turns political refusals
> into findings no one answers for

leaves the reader asking WHO delegates and WHO escapes answering. Those are the
parties that ACT, and the claim is neither usable nor checkable without them.
Same failure in "The easy target is your technique's preference, not yours" —
whose technique, and who is "you"?

**Failure B — actor repetition that destroys the sentence.** Correcting Failure A
too hard produced this, which is worse:

> The asker who presents the next meeting to the recipient as the continuation of
> a story the asker and the recipient already began, rather than asking the
> recipient for permission, raises the rate at which the recipient accepts,
> because that presentation casts the asker as the leader of the pair and not as a
> supplicant petitioning the recipient.

No person would say that. Naming a role six times in one sentence is not clarity,
it is noise, and it buries the claim it was meant to expose.

**The rule that avoids both.** Name the parties who ACT and the parties AFFECTED —
once each — then refer to them naturally. Ordinary pronouns are fine once their
referent is named in the sentence: "a legislature ... its own refusals" is clear.
What is banned is a pronoun or placeholder standing for a party that is named
NOWHERE: "no one", "your" with no owner, "who" with no antecedent, a passive whose
actor never appears.

You do NOT have to give every abstract noun an owner. "The mandate", "the
eligibility test", "asset protection" are things, and demanding an author for each
one makes writing impossible. Only parties that DO something must be identified.

**THE STANDARD.** This title was written by the knowledge base's owner and is the
calibration point for every title you write:

> A leader who blames others turns criticism of his policy and actions into proof
> his enemies are real

Study what it does. Eighteen words. Every party is a general role — a leader,
others, his enemies. It reads as speech. And it states the insight: the trap by
which criticism becomes evidence for the thing being criticised.

Now study what the owner CHANGED to get there, because it is the mistake you are
most likely to make. The draft read:

> A leader who blames saboteurs turns criticism of his policy into proof his
> enemies are real

The owner replaced "saboteurs" with "others" and "his policy" with "his policy and
actions". Both edits fix the same defect: **a domain-specific noun had survived
inside the mechanism.** "Saboteurs" locks the claim to conspiracy-framing, when
the same trap runs on anyone who blames staff, markets, a predecessor, or the
press. "Policy" was narrower than what the sources described.

So generalising the ACTORS is not enough. Every noun in the sentence must be as
general as the claim allows — the actors, the thing they act on, and the thing it
becomes. If a noun would make a reader think of one particular field, replace it
with the general word for what it is.

**The read-aloud test.** Read your sentence as if speaking it to someone. If you
would not say it that way, restructure until you would. Apply this to bullets too.

**Do not put qualifications in the title.** A title crammed with conditions is
not more faithful, it is less general. The conditions go in the bullets, where
they are preserved exactly. This is not licence to drop the actors instead —
qualifications move out, actors stay in.

**Never introduce a named concept, bias, theory, or term of art that does not
appear in the source text.** Earlier notes claimed "the framing effect",
"photographic memory", "identity-protective cognition" — each naming a different
mechanism than the note's own content. If the sources do not name it, you do not.

**No markdown in the title** — no asterisks, no underscores, no backticks. The
title becomes a heading and a filename.

Forbidden in the title: a person's or organisation's name, a year, a hedge
(can / may / often / typically), a count ("three types"), an absolute
(never / always / proves).


## Generalization has a FLOOR as well as a ceiling

Replacing a specific noun with the most abstract available word does not broaden a
claim — it makes the claim ambiguous, and often false. Measured example. A note
about one state's power grid staying off the national interconnection to escape
federal regulation was generalised to:

> A provider who stays outside a shared system to escape its rules keeps the
> savings and strands the people it serves

The owner's objection: a grazing commons is a shared system too. Is the claim true
there? What kind of provider — any service, or only an essential one? The claim
needs a system that supplies MUTUAL BACKUP and a provider whose failure strands
people. "Shared system" does not carry either.

**The substitution test, applied to every noun you generalise.** Name two or three
other things your chosen noun covers. Is the claim still true of each? If not, the
noun is too broad — step back down to the most general word for which the claim
stays TRUE. Ambiguity is not generality.

## Some notes are domain-bound. Keep the domain when the domain is the subject

Roughly one note in nine here is craft knowledge about writing fiction. Its
sources say "a character", "the reader", "a believable arc". That is not costume
over a universal principle — it IS the subject. One such note was generalised to
"a teller who shows small fixes failing repeatedly", and the owner could not tell
what it was about.

So: ask whether the domain is the costume or the subject. Advice about how to make
a character's arc convincing to readers is knowledge about writing. Say so — "a
novelist", "the reader" — and generalise only WITHIN that domain. A note that
cannot survive leaving its field should keep its field.

This applies to every child of a SPLIT. A domain-bound group cannot produce a
child whose title reads as a universal factual claim merely because the shared
`domain_bound` field remains true. Each child title and body must name the domain
needed to make its own claim true.

## Do not let compression make the claim false

A note about self-paced performance was compressed to "a performer with no opponent
and nothing at stake". The owner: not accurate — the golfer feels real internal
stakes while no external stakes exist, and the internal-versus-external distinction
IS the insight. A phrase that shortens the sentence by asserting something untrue
is an error, not compression.

Check every simplification against the sources: does the shorter phrase still say
something true?

## Every condition in the title must govern every claim it appears to govern

The bullets can all be faithful while the title still makes the note false. Read
the title literally. Every proposition its grammar asserts must be supported by
the sources. Map each cause, condition, modifier, and conjunction to the exact
claim it governs; never let a condition from one claim grammatically scope over
another. If accurate parallel wording can keep the claims together, rewrite the
title; otherwise SPLIT only when the independent-reuse test below passes.

Audit the title's logical joins. If either of two failures independently produces
the result, do not say `neither A nor B` as though both must fail together; say
`A or B`, or separate the claims. If a source reports a tendency or comparison,
the title must state that comparison or a different claim that remains true under
it. Keep the limiting finding in the same body. The ban on hedges in titles is not
permission to turn probability into causation or an absolute.

Finally, test the premise as a whole, not only its nouns. Do not substitute a
related variable for the one the sources name. If the result follows only from a
subset of the premise named in the title, the title is too broad even when every
noun passes the substitution test.

A comparison must keep both sides truthful. If one thing receives more of a
quality than another, do not say the second thing lacks that quality. If a result
requires two mechanisms together, do not name only one as its cause. Every
load-bearing input to the title's result must remain in the title, or the result
must be narrowed to what the named input actually produces.

## Watch for words that inverse-read

The same note-6 title said an arc looks "forced rather than chosen", meaning
compelled by circumstance. Every reader takes "forced" to mean contrived — the
exact opposite of the sources' claim that the arc becomes CREDIBLE. Before
committing a word, ask how a reader will take it, not what you meant by it.

## If two positions behave differently, distinguish them

A title read "Knowing which side a claim comes from lets the listener feel its
force and still owe no answer." The owner: which side the listener is on matters —
a listener from the opposing camp lets the claim bounce off, while one hearing it
from inside their own camp feels its force. Collapsing two parties who behave
oppositely makes the claim unclear. And "owe no answer" — to whom?

When a claim depends on the direction of a relationship, name the role that bears
the dependency or obligation and the role it points to. A generic actor such as
"users" or "people" must not erase which side depends, cites, consumes, owes, or
remains independent.

Preserve who stated a boundary and who violated it. A party enforcing its own
scope is not the same mechanism as a respondent ignoring a scope the other party
declared. Do not attribute a declaration, refusal, or action to every participant
in the interaction merely because it appears in the same source.

## A SECOND STANDARD, from the owner

Alongside the leader/blame standard, the owner rewrote this one by hand:

> People blame themselves for the harms perpetrated by others until they find other
> victims that share their experiences, which protects the perpetrators.

Note what the owner added to the draft: "perpetrated by others" and "the
perpetrators" — the party CAUSING the harm, named twice, where the draft had only
"harmed the same way" and "whoever harmed them". Name the party who acts, not only
the party who suffers.


## Find the CONVERSION. That is what makes a title an insight

Two titles can obey every rule in this document and still differ in quality,
because one states a procedure and the other states a conversion. Measured case —
the owner called the first excellent and the second a regression:

> A distributor that promotes whatever is newest pays makers for releasing their
> work in pieces, NOT FOR THE WORK

> A seller who staggers his releases turns a store's brief boost for each new
> listing into continuous prominence

The second describes how the boost accumulates. The first names what the
arrangement PAYS FOR, and that it is not the thing it is supposed to reward.

Every title the owner has accepted has this shape — something turns into
something, and the result is the opposite of what it should be:

- criticism of a leader's policy becomes PROOF HIS ENEMIES ARE REAL
- a victim's private shame becomes PROTECTION FOR WHOEVER HARMED THEM
- the relationship a couple spends becomes SECURITY THAT CANNOT GIVE IT BACK
- an exemption from rules becomes PEOPLE STRANDED IN AN EMERGENCY
- an easy win becomes A MEASURE OF YOUR TECHNIQUE, NOT THE PERSON

So ask: what goes in, what comes out, and why is the output perverse? Put the
conversion in the title. When you can state either the mechanism or its perverse
result, the perverse result is the insight; the mechanism is a bullet.

## The actor may be a thing, and must not be over-specified

The requirement is that the acting party is IDENTIFIED, never that it is a person.
The owner's objection to one title:

> Whoever prescribes one plot structure hands novelists a default in place of the
> beats their genre's readers expect

"In the original, 'a plot structure tool' can serve as the actor. By forcing it to
be a person, it actually clouds it." A tool, a rule, a market, an institution, a
platform, an incentive — each is a legitimate actor. Name whichever one actually
does the thing.

Nor should an actor carry qualifiers that do no work. "A trusted chronicler who
ties local activists to..." — the owner: takes it too far, "doesn't really add
much." If a plainer role noun carries the claim, use it.

## The substitution test runs in BOTH directions

Too broad makes the claim false. **Too narrow makes it cover less than the
mechanism supports, and that is also a defect.** Measured case:

> An institution whose comforts and COMMERCE contradict its professed values...

The owner: "doesn't need to be limited to commerce. A church or a political party
often enjoy privilege, power, and other advantages that contradict their professed
values." The mechanism runs on any advantage that contradicts a stated value, so
"commerce" was under-generalised.

So for each noun ask both questions: does the claim stay true of everything this
noun covers, AND does this noun cover everything the mechanism reaches? Widen until
the first question would start failing, and no further.

## Name a power relationship when the claim rests on it

> Fighting among people at the same level protects the ones taking a cut of what
> they produce together

The owner: "the ones taking a cut needs some clarity ... It's the people or
institutions with power over them that are making the rules and taking a cut."
"Someone taking a cut" could be a broker or a partner. The claim depends on the
party being ABOVE them and SETTING THE RULES. When a hierarchy, a dependency, or an
authority is load-bearing, say so in the title.

## The bullets carry the mechanism — and every qualification

One line per DISTINCT claim in the sources, each starting `- `. Near-duplicate
sources collapse into one line; genuinely different claims each get a line.

**Preserve every clause that qualifies or limits a claim.** A clause saying
DESPITE something, EVEN WHEN something, ONLY IF something, or WITHOUT something
is usually the entire point. Measured failure: a note lost "despite the dual
mandate of price stability and full employment" and was left asserting only that
captured institutions favour their capturers — circular. Another lost "without
any elected official casting a vote."

Write about roles — the incumbent, the regulator, the practitioner — not named
individuals. Every bullet identifies who acts, naming each party once and then
referring to it naturally. Do not repeat a role noun three times in one sentence
to prove you named it. State how and under what conditions, not merely that it
happens. The read-aloud test applies to every bullet.

There is no cap on the number of bullets. A group of twelve sources carrying
twelve distinct claims gets twelve bullets. Collapse only genuine near-duplicates;
never drop a distinction to shorten the note.

Before returning KEEP or SPLIT, trace every source's unique claim and every
limiting clause to an output bullet. If no bullet carries a source's unique
contribution, the output is incomplete. After genuine near-duplicates are
collapsed, every distinct claim must appear in exactly one body.

Do this audit by proposition, not just by source filename. One source can carry a
second reusable mechanism—a feedback loop, diagnostic, exception, or consequence—
that no other bullet preserves. Covering another claim from that same source does
not make the output complete.

If the sources disagree with each other, say so in a bullet rather than splitting
the difference. If they are two claims that do not belong together, say SPLIT and
describe both.

## SPLIT by independent reuse; never split away a limiting qualification

Two claims belong in separate notes when they answer different retrieval
questions and each remains coherent and useful without the other. A domain-specific
claim and a reusable diagnostic or method derived from it may answer different
retrieval questions even when they appear in the same example.

Each proposed child must itself carry one coherent claim. Moving several
incompatible explanations into one generically titled child does not resolve
their disagreement; keep them as explicit alternatives in the body of the claim
they qualify unless each can stand as its own output.

A qualification, counterexample, or empirical constraint that changes how the
main claim must be read is NOT an independent child. Keep it in the primary body.
If retrieving the primary note without the proposed child would leave a false or
materially misleading claim, the split is harmful. Positive and failed instances
of the same boundary or mechanism may also belong together when their contrast is
the insight rather than two reusable mechanisms.

Before returning SPLIT, mentally partition the source claims and apply both tests:

- Each child must state an insight a reader could retrieve and use on its own.
- Removing either child must not make the other child overstate, hide, or reverse
  a qualification that limits it.

A split is not permission to discard the claim that does not fit the first title.

## The case, only if the sources give you one

If the sources contain a concrete instance worth keeping, end with a line
`- Case: ...` quoting or closely paraphrasing the source. Named specifics belong
HERE, never in the title. If there is no such instance, omit the line — never
write a placeholder.

Never state a name, number, date, or example that does not appear in the sources.

## Output

Return only the JSON object requested by the caller. The `title` value is plain
text with no Markdown. The `body` value contains only the note's bullet lines,
each beginning `- `; put no heading, separator, explanation, or editorial
commentary in it. State the title's conversion in `conversion`, set
`domain_bound` truthfully, and use `split_second_note` only when two claims do not
belong in one note.
