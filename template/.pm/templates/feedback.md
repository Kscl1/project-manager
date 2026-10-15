# Package feedback report

For a problem with the `.pm/` package itself (a tool, hook, rule or template), not with this project's code. The report carries only the diagnosis: which versions, which package command failed, and a short error excerpt. Nothing about this project travels with it.

Write it with the `pm-feedback` skill, or run `python .pm/tools/pm_feedback.py --command "<failed command>" --error-file <file>`. The tool fills the fields, redacts them and saves the report as `.pm/local/feedback/<date>-feedback.md` (git-ignored). It is sent only when the owner reads it and says yes; then it becomes an issue in the package's home repo. Do not change `.pm/` package files here.

```text
TITLE           one line: which package command failed and how
PACKAGE         contents of .pm/VERSION
HARNESS         harness, model and thinking level that hit it
TOOLS           python, OS, git, gh, backlog, node, herdr, pi versions
FAILED COMMAND  the command, with project paths and quoted text replaced
ERROR EXCERPT   the last 20 lines of its output at most, redacted
```

Never add: project paths or file names, the project's or anyone's name, task or decision titles, prompts, code, or excerpts from project files. If the problem cannot be shown without them, say so in the title and let the owner explain in person.
