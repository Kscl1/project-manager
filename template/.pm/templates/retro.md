# Retro

A look back at a stretch of work, weekly by default. `pm_board --resume` says when one is due: no task whose title begins with the word "Retro" was closed in the last seven days. The owner may put it off; the line stays in the resume and says when the last one was held.

The retro is a task. Create it with the title `Retro: <from> to <to>`, write the two parts below into its notes, and close it with the usual final summary. Nothing is fixed inside the retro: a finding that needs work becomes its own task, and the owner sets the order.

A long read goes to a worker, as in `roles/lead.md`. The lead checks each finding at its source before the owner sees it.

## Part 1: the work

Read-only, from the records of the period:

- The tasks closed and their closing summaries: what was built, what was dropped, what took more rounds than planned.
- The `Decided alone:` lines in task notes: which choices the owner later reversed. That kind of choice joins the ask-first list.
- `.pm/lessons.md`: proposals still waiting, and rules marked applied that were broken again.
- Rules in `AGENTS.md` and the role cards that answer a mistake no longer seen: propose removing them. A rule written for one model's habit goes stale when the model changes.

## Part 2: the chats

The records cannot show what the owner had to say twice. The chats can.

- Read the period's chat transcripts where the harness keeps them. Ask the owner where they are; they are private and stay on the machine. With no transcripts, ask the owner what they remember.
- Count, each with a short quote and its date: what the owner repeated, asked to have written down, corrected, or had to start by hand.
- Sort each one: the package lacks it, this project's setup lacks it, or it is normal for this project.

## The fix for each finding

<!-- The order below is adapted from the `retro` skill in Matt Pocock's skills, https://github.com/mattpocock/skills/blob/a7d038f6bf7f01b516408e95e2fb56e0b338fa6f/skills/engineering/retro/SKILL.md (MIT). His looks at one coding session and the agent's environment; this template keeps his way of sorting a finding by the kind of fix. -->

Name the cheapest fix that lasts, trying these in order:

1. **A check.** A mistake a check could have caught gets the check: a `pm_check` rule, a hook, a test. Look first for a check that exists and is not wired up or is broken. Prefer the check to a written rule.
2. **A pointer.** When a session took long to find something, add a line where it looked first that says where the thing is.
3. **Access.** When something the agent needed was out of reach (a log, a read-only view of a service), give that access.
4. **A rule for the reviewer.** A judgement call that no check can make goes into `roles/reviewer.md`. The reviewer reads only the diff and has room for it; the one who builds does not.
5. **A sentence in a role card or the root `AGENTS.md`.** Last, because every session pays to read it.

Then look for what to take out: an instruction that changed nothing in the period, a line in the root `AGENTS.md` that a check or a role card now carries, and a tool call that costs much and returns little.

## Output

In the task's notes:

- The findings as a numbered table: what, the evidence, the kind, the fix.
- Two counts from part 2: how often the lead proposed a lasting record by itself, and how often the owner had to ask for one.
- The owner's order for what follows.

A fault of the package itself goes into a feedback report (`.pm/templates/feedback.md`), not into the project's tasks.
