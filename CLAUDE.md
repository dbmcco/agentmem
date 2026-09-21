<!-- workgraph-managed -->
# Workgraph

Use workgraph for task management.

**At the start of each session, run `wg quickstart` in your terminal to orient yourself.**
Use `wg service start` to dispatch work — do not manually claim tasks.

## For All Agents (Including the Orchestrating Agent)

CRITICAL: Do NOT use built-in TaskCreate/TaskUpdate/TaskList/TaskGet tools.
These are a separate system that does NOT interact with workgraph.
Always use `wg` CLI commands for all task management.

CRITICAL: Do NOT use the built-in **Task tool** (subagents). NEVER spawn Explore, Plan,
general-purpose, or any other subagent type. The Task tool creates processes outside
workgraph, which defeats the entire system. If you need research, exploration, or planning
done — create a `wg add` task and let the coordinator dispatch it.

ALL tasks — including research, exploration, and planning — should be workgraph tasks.

### Orchestrating agent role

The orchestrating agent (the one the user interacts with directly) does ONLY:
- **Conversation** with the user
- **Inspection** via `wg show`, `wg viz`, `wg list`, `wg status`, and reading files
- **Task creation** via `wg add` with descriptions, dependencies, and context
- **Monitoring** via `wg agents`, `wg service status`, `wg watch`

It NEVER writes code, implements features, or does research itself.
Everything gets dispatched through `wg add` and `wg service start`.

<!-- driftdriver-claude:start -->
## Speedrift Ecosystem

**Speedrift** is the development quality system across this workspace. It combines
[Workgraph](https://github.com/graphwork/workgraph) (task spine) with
[Driftdriver](https://github.com/dbmcco/driftdriver) (drift orchestrator) to keep
code, specs, and intent in sync without hard-blocking work.

Use `/speedrift` (or `/rifts`) to invoke the full protocol skill.

### Quick Reference

```bash
# Drift-check a task (run at start + before completion)
./.workgraph/drifts check --task <id> --write-log --create-followups

# Ecosystem dashboard (40+ repos, pressure scores, action queue)
# Local:     http://127.0.0.1:8777/
# Tailscale: http://100.77.214.44:8777/

# Create tasks with current wg flags (add creates a draft; publish activates it)
wg add "Title" --after <dep-id> -d "## Validation
- [ ] test command passes"
wg publish <task-id> --only

# Attractor loop — check convergence status or run convergence
driftdriver attractor status --json
driftdriver attractor run --json
```

### Runtime Authority
- Workgraph is the task/dependency source of truth. `speedriftd` is the repo-local supervisor.
- Sessions default to `observe`. Do not use `wg service start` as a generic kickoff.
- Refresh state: `driftdriver --dir "$PWD" --json speedriftd status --refresh`
- Arm repo: `driftdriver --dir "$PWD" speedriftd status --set-mode supervise --lease-owner <agent> --reason "reason"`
- Disarm: `driftdriver --dir "$PWD" speedriftd status --set-mode observe --release-lease --reason "done"`

### Attractor Loop (Convergence Engine)
- Each repo declares a target attractor in `drift-policy.toml`: `onboarded` → `production-ready` → `hardened`
- The loop runs diagnose → plan → execute → re-diagnose until convergence or circuit breaker
- Circuit breakers: max 3 passes, plateau detection (2 consecutive no-improvement), task budget cap (30)
- Bundles (reusable fix templates) are matched to findings automatically; unmatched findings escalate
- Check status: `driftdriver attractor status --json`
- Run convergence: `driftdriver attractor run --json`

### What Happens Automatically
- **Drift task guard**: follow-up tasks are deduped + capped at 3 per lane per repo
- **Attractor convergence**: repos are driven toward their declared target state via the attractor loop
- **Notifications**: significant findings alert via terminal/webhook/wg-notify
- **Prompt evolution**: recurring drift patterns trigger `wg evolve` to teach agents
- **Outcome learning**: resolution rates feed back into notification significance scoring
<!-- driftdriver-claude:end -->
