---
title: Upgrade and roll back
description: Upgrade an installed project one layer at a time, and roll back package files without losing tasks or decisions.
---

A project has several independent layers. Words such as commit, branch or layer are in the [glossary](glossary.md). Updating the project-manager checkout does **not** update an installed project, your global tools or your own plugins. Update one layer at a time, keep the previous version, then check it before moving on.

## Before changing anything

1. Finish or stop active workers. In your project, save a commit or a private external backup. Include tasks, decisions, worklog, charter, specs, root instructions and configuration. Also copy ignored `.pm/local/` somewhere safe: it holds local setup records and package backups, and Git does not save it.
2. Record `git status --short`, the project-manager source tag/commit (`git describe --tags --always`), your project's `.pm/VERSION`, selected layers and the tools' version output. Keep a copy of the old release's `tools/setup/bom.toml`.
3. Read the new [release notes](https://github.com/Kscl1/project-manager/releases). Alpha releases can change formats: an old checker may not understand records written with a newer package. Do not rewrite or delete records to silence it.

## 1. Choose a source release

These commands run **in the project-manager source clone**, not in your project. The getting-started guide installs `v0.1.0-alpha.6`. For an upgrade, replace `<new-tag>` below with a real, newer release tag.

```bash
git status --short
git fetch --tags origin
git checkout --detach <new-tag>
git describe --tags --always
```

If the source has local changes, stop and save them first. A detached HEAD is normal for a release checkout. `git pull` is not the release upgrade path. Use published tags for normal use; `git fetch origin` and `git checkout --detach origin/main` select unreleased code only when you deliberately want to test it. Note the exact commit if you do.

## 2. Upgrade the installed `.pm` package

From that source clone, use its installer against your project. The following example keeps both optional layers; omit `--map` / `--swarm` if you do not want to add them. Already installed optional layers continue to be upgraded even without the flags. Flags are additive, not uninstall switches.

```bash
python template/.pm/tools/pm_init.py ../my-project --upgrade --dry-run --map --swarm
python template/.pm/tools/pm_init.py ../my-project --upgrade --map --swarm
```

Read the dry run first. It reports new/removed files, local edits and files changed on both sides. It writes nothing. The real upgrade:

- Replaces `.pm/tools`, `tests`, `hooks`, `roles`, `templates` and the installed swarm layer. Removed package files disappear from those managed folders.
- Replaces shipped `pm-*` skills in `.agents/skills/` and refreshes their Claude Code pointers. **Local edits inside managed folders are overwritten.** Their old folders go to `.pm/local/backup/<timestamp>/` (a folder that already matches the package is kept and gets no backup); use them to reapply intentional edits, not to overwrite the entire new package blindly. Backups use second-resolution timestamps: wait until the next second before another real upgrade.
- Leaves project tasks, decisions, worklog, specs, charter and seed files such as `.pm/models.md` alone. Your own skills outside the shipped `pm-*` names are not touched; do not give a personal skill a shipped name.
- Keeps existing root instructions, Backlog config, `.claude/settings.json` and `.mcp.json`; missing integrations go into `.pm/local/merge-by-hand.md`. It may append package rules to `.gitignore` / `.gitattributes` / `.ignore` and activate/stage package hooks when the project has no hooks of its own.

Review the diff and merge list. Compare kept root/seed files with the new templates when the release notes call for changes; `--upgrade` intentionally does not synchronize them. From **your project**, run:

```bash
python .pm/tools/pm_check.py
python -m unittest discover -s .pm/tests
python .pm/tools/pm_board.py --resume
```

If you installed swarm, also run `python -m unittest discover -s .pm/swarm`; the upgrade prints these checks as its next steps. Inspect `.pm/VERSION`: it names the last package commit and, on a release checkout, the tag. Then try a normal task/resume flow. A consistency check is not a compatibility certification. Review before committing the upgrade in your project, and keep the ignored backups until you are satisfied.

## 3. Upgrade tools separately

The release's [bill of materials](https://github.com/Kscl1/project-manager/blob/main/tools/setup/bom.toml) is the command source. `min` is a support floor, `tested` is evidence from human-run checks, and `install.*` contains the actual pin where the installer supports one. They need not be equal. An installed version above `tested` is **not tested yet**, not automatically broken.

The upgrade in step 2 ends with a short list, "Programs on this machine against this release": each program that is missing or below `min` (needed), older than a pinned `tested` version (optional) or newer than it (keep it unless something breaks), with its command. Nothing is installed. Your agent reads the list, explains each line and runs a command only after you say yes. To see it again: `python tools/setup/bom.py --updates --layers core,map,swarm`.

To hear about new releases, open the repository on GitHub and choose **Watch → Custom → Releases**.

Use the setup TUI or its read-only inventory after switching releases:

```bash
python tools/setup/bom.py --project ../my-project --layers core,map,swarm
```

Add `evren` only if you use that optional layer. Exit 1 can mean remaining steps or warnings; read the table. The TUI does not force every installed tool to the new command pin: when intentionally upgrading, review and run the release's matching `install.*` / `upgrade.*` command yourself, then recheck. Install the TUI requirements into its separate virtual environment again if they changed.

| Tool group | Upgrade path | Rollback preparation |
|---|---|---|
| Backlog.md, Pi | Run the release's pinned `npm i -g package@version` command. | Save the old version; reinstall the exact previous npm version if needed. |
| Pi extensions | Run the release's `pi install npm:package@version`. | Record the old package versions and restore them with the same pinned install form. Restart Pi and verify its actual package list. |
| LikeC4 CLI | Run the release's pinned `npx likec4@version ...` command. Nothing global is upgraded by this. | Use the earlier pin again; keep the model files. Review the project's MCP command separately if it pins another package/version. |
| Herdr | Review its official installer/update instructions and the release manifest before accepting upstream latest. | Save the old binary and its provenance/checksum before replacing it. If no supported older release can be restored, do not upgrade without another recovery path. The latest installer is not a rollback command. |
| Python, Git, Node.js, Claude Code | Follow the OS/vendor's supported upgrade path; these commands are not all version-pinned. | Keep the vendor-supported previous installer/runtime and configuration backup. Do not remove an interpreter your tools still need. Auto-updating tools may need vendor-specific controls. |
| Optional bridge/app clones | Follow that tool's own release instructions; record the old commit and dependency environment. | Restore that clone's previous supported ref/environment without touching project records. A moving `git pull` is not a reproducible release pin. |

For Herdr, discovery of a new release is **not** proof it works with the runner. Before moving the `tested` value, run a small visible worker with **Pi and Claude Code separately**, verify pane/status/output/evidence and retain results. Do not use this guide's automated package tests as a substitute. No agent workers are launched by the inventory command.

## Your own third-party skills

For your **own** third-party skill, use its upstream installer/version pin and keep its previous copy. It is not managed by `.pm`; see [your own tools](own-tools.md).

## Maintainers

Vendored skills, the Renovate policy and the `pi-mcp-adapter` 5.x to 7.0 change are notes for people who maintain the package or watch its dependencies. They live in the contributing guide: [Maintainers](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md#maintainers).

## Roll back without losing records

**Do not reset your entire project to an old commit or replace its whole `.pm` directory.** That would discard tasks and decisions written since upgrading. A rollback changes managed package files only; keep the latest project data.

1. Stop workers and back up the current state, including ignored backups. Record the failing version and symptoms.
2. In the **source clone**, select the previous known-good release, for example:

   ```bash
   git fetch --tags origin
   git checkout --detach v0.1.0-alpha.1
   python template/.pm/tools/pm_init.py ../my-project --upgrade --dry-run --map --swarm
   python template/.pm/tools/pm_init.py ../my-project --upgrade --map --swarm
   ```

3. In your project, check `.pm/VERSION`, the diff and merge list. Restore any intentional local package edits from the right timestamped backup only after comparing them with the old release. Review root/config changes made manually during the upgrade separately: the installer keeps them rather than reverting them. Newer-only skill directories or optional layers may need manual review; an old installer cannot know future package names. Never delete a directory until you have confirmed it contains only package files, not records.
4. Roll back changed global tools one at a time, using the recorded old pins/installers. Rolling back `.pm` does not downgrade Herdr, Pi, extensions, apps or MCP servers.
5. Repeat package checks and a normal workflow. Confirm records created **after** the upgrade are still present. If the older version cannot read a newer record format, stop and use the backup to plan a format-specific migration; do not delete those records.

### What was rehearsed

A developer rehearsal on 2026-10-18 covered a local install from `v0.1.0-alpha.1`, upgrade to main at `185f9ca`, and rollback to the tag with Map and Swarm enabled. The rehearsal checked managed files, a deliberately edited package tool and preservation of project records including a task added after the upgrade. This is a developer rehearsal, not an independent user's acceptance test or evidence that global tools have been upgraded. No release or tool compatibility is certified by it.
