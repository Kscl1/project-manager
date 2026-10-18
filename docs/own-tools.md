# Make your own tools useful in a `.pm` project

Keep the MCP servers, plugins, skills and apps you already use. project-manager does not need to ship or own them. Installation makes a tool available; a short rule telling the lead **when to use it**, and a real smoke check, make it useful.

Start with `/pm-setup` (or your agent's equivalent). Its existing-tools step works for any tool, not just the examples below. Do one tool at a time, with permission before installing, changing configuration or calling a service that could receive private data.

## A small method, not another catalogue

For each tool, have the lead create/reuse a child task under the setup Epic and record:

1. **Job and trigger.** What project question does it answer? When should the lead reach for it, and when should it not? Prefer a concrete situation over “always use this tool.”
2. **What exists already.** Inspect the project's and agent's existing setup without opening credential stores. Is it project-local or user-global? Which agent can see it? The setup TUI's `similar` list is a starting point, not a complete inventory. Ask before scanning broader user configuration.
3. **Wiring and scope.** Use the vendor's official client instructions. MCP goes in the chosen client's configuration; a plugin in that client's plugin system; a skill in its supported skill directory; an external app can stay external with a documented handoff. Do not invent an MCP wrapper just to fit the tool into `.pm`.
4. **Permissions and cost.** Say what data leaves the machine, what can be read/written, what account/rate limit is involved and who approves side effects. Use the least privilege that answers the question. Keep credentials in the vendor-supported secret store or local environment, never in tasks, docs, shared config or feedback reports.
5. **One overlap decision.** Keep theirs, ours or both. Remove nothing automatically. Two copies can cost context, invoke a service twice or have different permissions/configuration; a duplicate is not automatically harmless. Name the preferred route for a given situation. A second task/issue app should not silently become a second authoritative tracker.
6. **Smoke check and fallback.** From the actual agent and project, list/inspect available tools, then run one approved low-risk query with a known answer. Record the exact tool/command, source/version, result and date, with secrets and private content omitted. A version check or a matching string in JSON is not an end-to-end check. “Configured, not tested” is an honest outcome. Say what to do when the service is absent or fails; do not quietly pretend it ran.
7. **Make it reachable.** After approval, add a row to the project's own “Which tool when” table in `AGENTS.md` (or its existing equivalent). Link longer setup instructions rather than duplicating them. Record the smoke-check evidence in the task, not a second live status page.

A useful row is small enough to read at session start:

| Situation | Reach for | Expected result | Boundary / fallback |
|---|---|---|---|
| Need current library/API setup for the installed version | Context7 via this agent's MCP connection | Library ID, version-aware docs and source links | No private code or secrets in queries; use official docs if unavailable and say so |
| Need to trace relationships already in the architecture model | LikeC4 MCP | Element/path/view references from the intended project | Read-only model query, not proof the code matches; inspect source/tests for behavior |
| Need an approved action in an external app | The user's existing app/plugin | A link or bounded result in the task | No sending, publishing or writes without explicit approval; manual handoff if unavailable |

These are examples to adapt, not extra default tools. The table describes routing; vendor documentation owns install syntax, and the setup task owns verification evidence. An unavailable optional tool should not make independent work stop.

## Where configuration belongs

- For a client that supports project `.mcp.json`, merge only the intended entry in `mcpServers`. Keep all other keys. Existing `.mcp.json` files are never rewritten by `pm_init`; the installer lists missing entries in `.pm/local/merge-by-hand.md` for review.
- Client support differs. Do not assume another coding agent reads `.mcp.json`, loads Claude plugins or discovers the same skills. Follow that agent's official instructions; do not copy one client's global config into a repo. If a worker will need the tool, check that actual worker client's connection and trust prompts as well. Lead access is not evidence of worker access.
- Put your own skills outside the shipped `pm-*` names. Those shipped skills are refreshed by `pm_init.py --upgrade`; custom changes there need a backup/reapply plan. A plugin may bundle hooks, skills and servers: inspect what it adds before enabling a second copy.
- A cloud app need not be an agent tool at all. Define what the user supplies (for example a public link or redacted export), what result returns to the Backlog task, and where the authoritative record lives. Link rather than mirror private records.
- Before a change, save the existing config privately, show a minimal diff, get approval and validate its syntax. Restart/reconnect only as the client requires. If the check fails, restore just that entry/plugin/version and retry the check; do not delete unrelated servers or reset the whole project.

## Tested example: Context7

**What it adds:** current library/API documentation, especially when the model's remembered API may be wrong. It does not test your code or replace the library's own release notes.

**Official setup:** [Context7 README](https://github.com/upstash/context7#readme) and [client-specific instructions](https://context7.com/docs/resources/all-clients). The package's core template already includes the remote endpoint below. This is a non-secret project configuration for clients that support this shape; merge it rather than replacing your whole file:

```json
{
  "mcpServers": {
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

Use the vendor's current authentication instructions if your connection needs a key/account; never paste the key into this shared example. The vendor currently also offers a CLI/skill route. Choose one preferred route rather than installing both without a reason.

**Workflow rule:** for a library question, resolve the exact library first, then ask for the required concept/version. Use returned documentation with source links. Check against the version the project actually uses; do not adopt the newest API just because it appears first. A tool catalogue or transport prefix may rename calls, so inspect the tools your client exposes instead of hard-coding an adapter-specific name.

**Smoke check:** ask `resolve-library-id` for a public library, then `query-docs` using the returned ID and a focused documentation question. Check that the answer has relevant official sources. Keep private requirements/code out of the request.

**Evidence (2026-10-18):** GPT-6.1 Sol (high), via 9router, used both calls from an existing MCP connection to retrieve Renovate regex-manager and custom-datasource docs, with upstream source links. This tests the workflow on that connection, not a fresh install, every client, or authenticated/private-library access. If it is rate-limited or unavailable, consult the library's official docs directly and label the fallback.

## Tested example: LikeC4

**What it adds:** queries over an existing architecture model. Its MCP answers model questions; the DSL skill teaches syntax. Neither proves implementation behavior.

**Official setup:** [LikeC4 MCP and skills](https://likec4.dev/tooling/mcp/). If you chose the package's Map layer, first use its generated server entry or merge-by-hand list instead of adding a duplicate. For an existing personal/editor server, verify its workspace points at **this project's model**, not whichever folder the server happened to start in. Do not install a second DSL skill on top of `pm-likec4-dsl` without an overlap choice.

**Workflow rule:** when asking what a component connects to, select the intended LikeC4 project, inspect the relevant model element/relationships and cite the model source. When editing syntax, use the DSL skill and validate with the CLI version selected by your release; when asking what the program really does, inspect code/tests.

**Smoke check:** list the available projects, verify the expected model is present, then read its summary or a known element. If the server points at another workspace, do not infer the current architecture from it. Correct the workspace under the vendor's instructions and repeat the check.

**Evidence (2026-10-18):** GPT-6.1 Sol (high), via 9router, successfully called `list-projects` on an existing MCP connection and checked its returned project/workspace information. This is a discovery-only smoke check, not a fresh install, model-validation or rendering test. Client-specific configuration and the user's own workspace still need their check.

## Finding install instructions, not blindly installing

A short source scan on 2026-10-18 (GPT-6.1 Sol, high; 9router) found existing discovery/install resources:

- [Official MCP Registry](https://registry.modelcontextprotocol.io/) ([scope and status](https://github.com/modelcontextprotocol/registry#readme)): server metadata/discovery, not a project-specific trust approval.
- [Claude Code plugin discovery](https://code.claude.com/docs/en/discover-plugins): a client's plugin installation/management, not a guarantee the plugin is appropriate for your workflow.
- [Agent Skills directory](https://www.skills.sh/): skill discovery. Review upstream source, licence and pin before adopting; a listing is not a security audit.

Use these rather than maintaining another broad installation catalogue here. The project-specific gap this guide addresses is **when to use a tool, which existing route wins and how to check that it helps**. This was a bounded scan, not proof no other resource covers that gap.

For a tool not covered here, apply the same seven steps and record “not tested” until its check is real. Suggest a new example through `/pm-feedback` or a contribution only with official links, a small reproducible check, overlap/permission boundaries and no private configuration. Installing a tool is never permission for it to publish, send messages, change your tracker or spawn helpers on its own.
