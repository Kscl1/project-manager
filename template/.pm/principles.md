# Principles

Five rules. Name the one that shaped a decision when you explain it. Adapted from [pstack](https://github.com/cursor/plugins/tree/main/pstack) (MIT).

1. **Smallest change.** Prefer deleting to adding. Add no layer, file type or dependency without a reason.
2. **Subtract before you add.** Remove dead code and duplicate helpers before extending a system.
3. **Minimize reader load.** Collapse needless indirection; a reviewer should understand the change in two minutes.
4. **Prove it works.** Run the command or inspect the real output; neither a passing type check nor an agent's claim is proof by itself.
5. **Guard the context window.** Give bulk reading to a scoped researcher; keep evidence and conclusions in the main thread. A short brief beats a transcript dump.

Keep a task's next step and evidence in its live block, not in a second handoff file. A new session checks that block against git and the filesystem before trusting it.
