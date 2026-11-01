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
npm run test:site # checks the built pages, the menu, Turkish pages, local links and assets
npm run preview   # preview the built site
```

`docs/` is the single content source, loaded directly by `src/content.config.ts`; do not create a second copy in `src/content/docs/`. English pages live at `docs/<slug>.md`, translations at `docs/tr/<same-slug>.md`; subdirectories work too. Each page needs YAML frontmatter with a `title`; `description` is optional. Files whose names begin with `_` are not loaded. The menu is the `sidebar` list in `astro.config.mjs`, one slug per page in reading order; add a new page there (the site test fails when a page is missing from the menu).

English is the source language, and every page has a Turkish version; `npm run test:site` fails when one is missing. A new page or a change to a page updates both versions in the same PR. The test detects missing files, not stale translations.

Link between pages with the relative Markdown file, for example `getting-started.md` or, from `docs/tr/`, `../how-it-works.md`. GitHub follows these links as they are, and the site build turns them into page URLs (`src/md-links.mjs`). Use explicit GitHub URLs for files outside `docs/`. A Mermaid code fence renders as a diagram in the browser; keep a prose explanation alongside it.

Pull requests build and test the site but never deploy it. Publishing is manual: after reading and merging the change, the maintainer sets the repository's **Settings → Pages → Source** to **GitHub Actions**, then runs **Documentation site → Run workflow** on `main`. The workflow does not enable Pages itself, and neither pushes nor pull requests can deploy. The configured project URL is `https://kscl1.github.io/project-manager/`.

## Maintainers

### Vendored skills

Shipped third-party skills are versioned as package files. Their `SKILL.md` source note identifies the actual upstream commit, licence and changes made here. A project's normal update is the reviewed release's `pm_init.py --upgrade`, not a skills installer writing over `.agents/skills/pm-*`.

Reviewing an upstream candidate:

1. Compare the old source commit to the proposed commit, including referenced files and the licence.
2. Copy the intended changes, reapply the documented local changes, retain the licence and update the source note and BOM `ref` to describe the files actually shipped. Candidate fields alone are not provenance.
3. Run the relevant syntax/CLI checks for a changed skill and review the results before releasing. The [selection test](https://github.com/Kscl1/project-manager/blob/main/tests/selection/README.md) is not rerun for each update; it runs right before a stage change, such as the first beta.

### pi-mcp-adapter 5.x to 7.0

Two major releases change the adapter's own settings; the project's `.mcp.json` works as before. Check your own Pi config (`~/.pi/agent/mcp.json`, a project's `.pi/mcp.json`) only if you set these yourself: `mcpScript` and its `settings.scriptMode`, `scriptSkill` and `settings.jev` budget keys are gone (use Pi's `codemode` instead); `settings.jev` becomes `settings.semanticSearch`, and `settings.jev: false` no longer turns semantic search off (set `settings.semanticSearch` to `false`); a System One key does nothing, semantic search uses Pi's own logins. An old key loads with a notice that names the file. The upstream changelog has the details.

### Renovate: discovery, then human review

[renovate.json](https://github.com/Kscl1/project-manager/blob/main/renovate.json) does nothing by itself. It stays inert until a maintainer installs/enables the Renovate app (or explicitly runs Renovate elsewhere). Automerge is off. Only the regex managers for the BOM are enabled:

- Actual npm pins in setup commands: Backlog.md, Pi, LikeC4 and Pi extensions.
- Herdr's `upstream_version` candidate, from its public latest-release manifest. This is not an install pin and cannot move `tested` or `min`.
- `upstream_version` candidates for the vendored grilling skills, from the upstream repository's published releases. These notify of a new release; they do not replace skill files, source notes or the actual BOM `ref`.

Every watch follows published releases, never branch commits, so a proposed update means upstream shipped a version.

Renovate opens pull requests only on Saturdays (UTC), so they are ready for a weekly review. Every minor and patch update arrives in one grouped pull request; a major version gets its own, because it may break something. Each Saturday's pull request brings the newest release that is at least three days old: npm can no longer unpublish it, and security scanners have had time to check it. Herdr's manifest has no release date, so its candidate is not held. Renovate's own security updates ignore the schedule and the limits.

A proposed update **discovers changes; it does not certify them**. Review the real upstream diff, synchronize relevant docs/runtime pins, run relevant smoke/selection checks and then consciously promote compatibility evidence and publish a release. The minimum/tested fields are outside the regex matches. Other dependencies, unpinned servers and user-owned tools are not watched by this scoped configuration. The LikeC4 version written outside the BOM is not watched either: the MCP server args in `template/.pm/templates/root/mcp-map.json` (`@likec4/mcp@1.60.0`), the `npx likec4@1.60.0 validate` line in the `pm-setup` skill, and the `npx likec4@1.60.0 start` examples in the README and on the optional layers page, in English and in Turkish (`docs/tr/optional-layers.md`). When a Renovate update changes the LikeC4 pin in `tools/setup/bom.toml`, change these by hand in the same pull request, and update the vendored `pm-likec4-dsl` skill from that release (see Vendored skills above). The skill has no watch of its own: LikeC4's main branch documents features before they are released.

Validate config changes with `npx --yes --package renovate -- renovate-config-validator`. The [regex boundary tests](https://github.com/Kscl1/project-manager/blob/main/tests/test_renovate.py) additionally protect compatibility/provenance fields. See Renovate's [regex manager](https://docs.renovatebot.com/modules/manager/regex/) and [custom datasource](https://docs.renovatebot.com/modules/datasource/custom/) docs.

By contributing you agree that your work is released under the repository's [MIT licence](LICENSE).
