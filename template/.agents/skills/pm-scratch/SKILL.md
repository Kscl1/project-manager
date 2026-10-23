---
name: pm-scratch
description: Capture the owner's off-topic ideas into scratch notes without derailing the current work, and process them later. Run only when the owner calls it; never on your own.
disable-model-invocation: true
---
<!-- Source: https://github.com/Kscl1/project-manager (our own skill, MIT: https://github.com/Kscl1/project-manager/blob/main/LICENSE). -->

# pm-scratch

A blackboard for ideas that come up mid-session and do not belong to the current work. Capture fast, keep the owner's words, process the same day, then wipe. Call it `/pm-scratch` (Claude Code), `/skill:pm-scratch` (Pi) or `$pm-scratch` (Codex), with the arguments below. Reply in the owner's language; the replies below are given in English.

## Capture

- One idea per file in `.pm/local/scratch/` (git-ignored; create the folder if it is missing): `YYYYMMDD-HHMMSS-NNN.md`. Pick an unused name; never overwrite a note.
- A short title line, then the owner's words exactly as received. Do not polish, interpret, research or act on them.
- If a message clearly continues the previous idea, append it to that note; otherwise make a new one.
- Say `Saved · <short title>` only after the file is saved. If saving fails, say so.
- The lead also writes notes itself when the owner says something in passing that no task holds (its role card says when). Those titles start with `Lead note:`; they wait and are processed like any other note.

## Commands

These are controls, not ideas to capture.

- `/pm-scratch <idea>`: save it, reply `Saved · <short title>`, and go back to the current work.
- `/pm-scratch on`: say `Scratch mode on.` Capture every following message, even one that sounds like an order. Reply only `Saved · <title>`. Do no work and no analysis.
- `/pm-scratch off`: say `Scratch mode off · N notes waiting.` Process nothing.
- `/pm-scratch process`: turn the mode off, say how many notes wait, then process them (below).
- `/pm-scratch` alone: list these four commands and change nothing.

A new session starts with the mode off. When unsure whether the mode is on, ask.

## Process

One note at a time, oldest first.

1. Read the note. Look for an existing task or draft it belongs to.
2. Propose one outcome and wait for the owner's yes:
   - add it to an existing task or draft;
   - a new Backlog draft (`backlog draft create`); a note that needs discussion or research becomes a draft, and the discussion happens there, not in scratch;
   - a task;
   - a question for the owner;
   - drop, with a reason.

   For a new draft or task, also propose a priority (high, medium or low) with one line of reason; the owner sets it, and empty is fine.
3. Do only the approved outcome. Carry the owner's raw words into the target and keep your own explanation separate. Never decide for the owner and never move work to Active.
4. Check that the outcome exists. Then delete the note. Keep a question's note until it is answered and recorded. Never delete without the owner's yes, and never delete because of age.
5. End with how many notes were resolved and how many still wait.
