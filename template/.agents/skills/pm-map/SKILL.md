---
name: pm-map
description: Use when you add, change or review a LikeC4 map in a PM project, or when the map is hard to read. Teaches PM's map standard: three levels, short box text with detail in the details panel, one shared vocabulary of box kinds, tags and arrow kinds, flows, layout fixes and a review checklist. For exact DSL syntax use pm-likec4-dsl.
---

# PM map standard

A good PM map reads in one glance and opens in layers: the first view tells the whole story in a
few boxes; each click goes one level deeper; the long text waits in the details panel. Syntax lives
in `pm-likec4-dsl`; this skill says **what** to draw and **how to write it**. Write the map's text
in the project's language (the `Language:` line in AGENTS.md); identifiers and comments stay English.

## 1. Read the truth first

Draw what exists today, not what an old map says. Read `git log`, the code or manifest, and the
decisions the part depends on. A clean `likec4 validate` proves syntax, not truth.

## 2. Start a map

If the map folder has no `.c4` file yet, copy `references/starter-spec.c4` into it as `spec.c4`,
then add `model.c4` and `views.c4`. From then on `spec.c4` is the project's own file: change its
tags and kinds to fit the project, and nothing will overwrite it. The map folder is the folder after
`start` in the `map` entry of `.claude/launch.json`, or the project root; it already holds
`likec4.config.json`, whose `name` you never change (pm_open knows the running map by it).

## 3. Three levels

| Sidebar folder | View | Boxes | Answers |
|---|---|---|---|
| `1 Start` | one view, `index` | at most 7 | What is this system, who uses it, how does work move? |
| `2 Inside` | `view x of <element>` per big box | at most 12, in groups | What is inside this box? |
| `3 Flows` | `dynamic view`, usually `variant sequence` | at most 10 steps | What happens, in order, when X? |
| `9 Personal` | deployment view, only in a personal, untracked or ignored folder | as needed | Where does each thing run? |

- A `/` in a title makes a sidebar folder: `title '2 Inside / The package'`; `order` sorts inside it.
  Never put another `/` in a title.
- Every title asks or names one question; every description says in one or two sentences what the
  reader sees and names the parent view.
- Going down: a scoped view becomes its element's default, so the box gets a drill-down button.
  Link a box to a flow with `include x with { navigateTo flowId }`; link a flow step to a sub-flow
  with `navigateTo` inside the step (dynamic views only).
- A view filtered by tag (`include * where tag is #optional`) answers "what does this layer bring?"
  without a hand-kept list.

## 4. Writing rules

| Field | Rule |
|---|---|
| `title` | 1-4 words, the thing's real name |
| `summary` | at most 8 words (hard limit 10), a verb phrase; the only text on the box |
| `description` | Markdown in triple quotes (`'''`), 2-4 sentences: what it does, what it does not do |
| `technology` | short: `Python`, `GitHub Actions`; no versions or paths |
| `metadata` | `file` (path from the repo root), `decision` (D-n), `task` (task ID); one set of keys per project |
| `link` | the source file, the decision file; relative to the `.c4` file |
| tags | 1-3 per box, from the project's `spec.c4` |
| arrow label | 1-4 words, a verb: "writes the report", "opens a pane" |

Never copy a decision's reasoning into the map: give its ID and a link. Never copy task status.

Before and after:

```likec4
// before: the box shows 40 words
pmRun = component 'pm_run' {
  description 'Runs jobs in Herdr with Pi or Claude Code; Herdr does not decide whether a job is done, its own evidence does: output written in this attempt, done marker and word count, closed agent, the job check.'
}
// after: the box shows 6 words; the rest opens on click
runner = tool 'pm_run' {
  #optional
  summary 'Starts a worker, proves it finished'
  technology 'Python · Herdr CLI'
  description '''
    The swarm layer's runner. It starts each job in a visible Herdr pane and counts a job
    as **verified** only when four pieces of evidence pass together.
  '''
  metadata { file '.pm/swarm/pm_run.py'; decision 'D-01' }
  link ../../.pm/swarm/pm_run.py 'pm_run'
}
```

## 5. One vocabulary

The starter `spec.c4` defines:

- **Box kinds**, told apart by shape + icon + colour: person, agent, system, tool, gate, record,
  viewer, external; places for deployment views: computer, cloud, zone.
- **Tags**, each with an explicit colour: `#core`, `#optional`, `#personal`, `#planned`. An
  uncoloured tag is coloured by alphabetical order, so a new tag without a colour recolours others.
- **Arrow kinds**, told apart by colour + line + head, so they read without colour too: `directs`,
  `runs`, `writes`, `reads`, `checks`, `ships`. Every kind has a `notation` name.

Add a kind only when no existing one fits, and give it a `notation` and its own line or head.

## 6. Which way an arrow points

**An arrow goes from the one who acts to what it acts on.** "The lead reads the report" is
`lead -[reads]-> report`, even though the data moves the other way; say that in the label if it
matters. In a flow, draw a dashed return (`a <- b 'answer'`) only when `b` really answers, as a
program or a person does; a file never answers.

## 7. Flows

- `variant sequence` for most flows; the reader can switch to the diagram and press **Start**.
- `parallel` only for work that really runs at the same time; `alt` for either-or; `opt` for a step
  that may be skipped; `loop` for a retry. Never use a block to decorate.
- Long detail goes into the step's `notes`, not its label.

## 8. Layout

LikeC4 lays each view out with Graphviz from scratch; one new box or arrow can move others. Fix in
this order: drop boxes and arrows the question does not need → shorten summaries → split the view →
pick `autoLayout TopBottom` (structure) or `LeftRight` (many side-by-side groups) → group related
boxes → `rank source|sink` for entry and exit (`rank same` only for siblings with one parent) →
spacing. Save a manual layout (the **Edit** button) only for the `1 Start` view, after its content
settles, and commit the `.likec4/` folder with it.

## 9. Known limits (LikeC4 1.60.0)

- Several relations between the same two boxes merge into one grey `[...]` arrow. Name it in the
  view: `include a -> b with { title '…'; color …; line …; head … }`. Deployment views cannot do this.
- A flow step between two such boxes loses its kind's style: write `color`, `line`, `head` in the step.
- Boxes included before a `group` stay outside it: include them inside the group.
- The UI upper-cases group titles with English rules (Turkish `i` becomes `I`): write group titles in
  capitals yourself.
- Markdown renders only in triple-quoted text.
- `navigateTo` is not an element property: put it on a view's `include … with { }` or on a flow step.
- Double-click highlights neighbours; the box's drill-down button goes inside.
- Add `"inferTechnologyFromIcon": false` to `likec4.config.json`, or bundled icons fill `technology`
  in English.
- A folder brought in by `include` in `likec4.config.json` does not reload live: restart the map.

## 10. Review checklist

- [ ] Each view answers one question; its boxes are at the same distance from the reader.
- [ ] Every box rests on something that exists today; nothing retired is drawn as live.
- [ ] Every box has a `summary` of at most 8 words; no paragraph sits on a box.
- [ ] Every arrow has a kind; no grey `[...]` arrow is left unnamed (except in deployment views).
- [ ] The map reads without colour: shapes, lines and arrow heads differ.
- [ ] Every box in `1 Start` with more inside can be opened; every flow names its parent view.
- [ ] Decisions and files are one click away (`metadata`, `link`), not copied.
- [ ] Personal parts (machines, keys, model routes) stay out of the shared map.
- [ ] `npx --no-install likec4@1.60.0 validate <map folder>` passes, and every changed view was
      opened in the browser.
