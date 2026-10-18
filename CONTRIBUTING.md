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

## Documentation site

The site uses Astro and Starlight. From the repository root, with Node.js 24.14.0 or newer:

```bash
npm ci
npm run dev       # http://localhost:4321/project-manager/
npm run build
npm run test:site # checks the built pages, fallback notice, local links and assets
npm run preview   # preview the built site
```

`docs/` is the single content source, loaded directly by `src/content.config.ts`; do not create a second copy in `src/content/docs/`. English pages live at `docs/<slug>.md`, translations at `docs/tr/<same-slug>.md`; subdirectories work too. Each page needs YAML frontmatter with a `title`; `description` and `sidebar.order` are optional. Names beginning `_` are not loaded. Navigation includes new pages automatically.

English is the source language. The introduction and getting-started guide have Turkish versions; other pages fall back to English with Starlight's missing-translation notice. When changing a translated page, update both versions in the same PR, or remove the outdated translation so the notice appears. The notice detects missing files, not stale translations.

For links between site pages, use relative directory-style URLs: `./getting-started/` from the index, `../getting-started/` from another top-level page. Use explicit GitHub URLs for files outside `docs/`. A Mermaid code fence renders as a diagram in the browser; keep a prose explanation alongside it.

Pull requests build and test the site but never deploy it. Publishing is manual: after reading and merging the change, the maintainer sets the repository's **Settings → Pages → Source** to **GitHub Actions**, then runs **Documentation site → Run workflow** on `main`. The workflow does not enable Pages itself, and neither pushes nor pull requests can deploy. The configured project URL is `https://kscl1.github.io/project-manager/`.

By contributing you agree that your work is released under the repository's [MIT licence](LICENSE).
