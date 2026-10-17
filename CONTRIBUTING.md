# Contributing

project-manager is an alpha maintained by one person. Issues and pull requests are welcome; support is best effort, with no promised response time (see [Status](README.md#status)).

## Issues

- **A `.pm` tool, hook, rule or template failed:** run `/pm-feedback` in your project, or open the **Package problem** form. Both send only a diagnosis: versions, the failed command and a short error excerpt.
- **Anything else** (an idea, a question, a doc that misled you): open a blank issue and say what you tried and what you expected.
- **Security problems:** never in a public issue; see [SECURITY.md](SECURITY.md).

Leave out private project content: paths, names, prompts and code from your own project.

## Pull requests

- Small fixes (a typo, a broken link, a clear bug with a test) can go straight to a pull request.
- For anything larger, open an issue first so we agree on the change before you spend time on it.
- One idea per pull request. Fill in the [pull request template](.github/pull_request_template.md).
- Run the checks CI runs, before you push:

  ```bash
  python -m pip install -r tools/dev-tools.txt
  ruff check . && ruff format --check .
  python tools/check_ids.py
  python -m unittest discover -s template/.pm/tests
  python -m unittest discover -s template/.pm/swarm
  python -m unittest discover -s tests
  ```

- Commit titles follow Conventional Commits: `type(scope): subject`, with the types feat, fix, docs, refactor, test and chore. End the message with `Refs: #<issue>` (or `Refs: none`), then one line naming the model that helped, e.g. `Assisted-by: <model> (<thinking level>)`, or `Assisted-by: none (human)`; never `Co-authored-by`. The repo's own hooks check this: `git config core.hooksPath .githooks`.
- CI runs on your pull request once the maintainer approves it (GitHub asks for this on a first contribution).

By contributing you agree that your work is released under the repository's [MIT licence](LICENSE).
