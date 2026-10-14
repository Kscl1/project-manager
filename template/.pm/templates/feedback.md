# Package feedback report

For a problem with the `.pm/` package itself, found while working in this project. The agent writes it, the owner reads it, and the package's home project triages it by path. Keep it to one page and make it readable without this project's chat or code.

Save as `.pm/local/feedback/<yyyy-mm-dd>-<short-name>.md` (git-ignored). Do not change `.pm/` package files here.

```text
TITLE         one line: what went wrong
PACKAGE       contents of .pm/VERSION
HARNESS       harness, model and thinking level that hit it
EXPECTED      what the package's docs or tool promised (quote file:line)
OBSERVED      what happened instead (exact command and output, trimmed)
REPRODUCE     the smallest steps that show it, or "not reproduced" and why
IDS           every task/decision ID mentioned, each with its meaning in a few words
EVIDENCE      paths in this project and a short excerpt; no secrets, no private data
WORKAROUND    what was done here meanwhile, or "none"
KIND GUESS    package bug | installed version or config | rule not followed | task underspecified
DISCLOSURE    what the owner must check before this leaves the project (names, code, data)
```
