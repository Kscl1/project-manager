# Models

Which model fills which role in this project. This file names roles and what each role needs, plus the models you have measured. It does not prescribe a provider: each person binds the roles to their own models in their own place, outside this file. Model identity comes from the harness or run record, **not** a worker's self-reported name.

## Roles and what they need

| Role | Needs |
|---|---|
| lead | Strong planning and review; reads large context; writes briefs, integrates; may write code itself when that is cheaper. |
| peer lead | Equal to the lead and from a different model family: takes its own job or package, runs its own helpers, cross-reviews; disagreements go to the owner. |
| worker (scoped, cheap) | Reliable tool calling on a small brief; low cost per run; follows the stop condition in the brief. |
| worker (hard or subtle) | Deeper reasoning at a higher thinking level; used when a cheap worker failed or the leaf is tricky. |
| researcher | Reads and cites sources; marks unverified claims. |
| reviewer | Always a different family from the author. |
| test-writer | Works in parallel with the coder; no family rule. |

Which data may go to which provider is a separate project decision; record it in `decisions.md`.

## Measured models (evidence, not a default)

Add a row after each measured run. A result tells you how a model did on that brief; it does not prove fit on other code.

| Model | Measured as | Measured on | Evidence (`eval:` your measurement, `baseline:` vendor claim) | Date |
|---|---|---|---|---|
| `<model and thinking level>` | `<role>` | `<provider or harness>` | `candidate` until measured | — |

Do not set a repeated-command or token budget from a model name alone; the brief must specify the stop condition.

## Adding a measurement or changing a role's needs

1. Record the model, harness, provider, actual thinking level and dated evidence. Label unrun candidates as such.
2. Run candidates on the same scoped brief, acceptance checks and timebox. Compare pass rate, cost and rework.
3. Add the row only after reviewing results. The lead chooses the worker; the reviewer must be from another family.
