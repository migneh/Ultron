# Using Claude Code on Ultron

This is an operating guide, not a persona prompt. Research reviewed 2026-11-23;
see [sources and attribution](SOURCES.md). Tool commands/defaults evolve: check
`claude --version`, `claude --help` and in-session `/help` on your installation.

## What is installed in this repository

- `CLAUDE.md`: concise shared project context, loaded by Claude Code.
- `PROJECT_MAP.md`: architecture navigation, read when needed—not force-loaded.
- `.claude/skills/ultron-check/SKILL.md`: reusable, user-invoked `/ultron-check`.
- This guide and `SOURCES.md`: human instructions and the evidence behind them.

No Claude settings, hooks, permissions, MCP servers, dependency installations or
remote integrations were enabled. Markdown does not grant or restrict tool access.

## First session

1. Install Claude Code using its official setup documentation on your own machine;
   authenticate through its supported flow, never through repository files/chat.
2. Open a terminal in the Ultron checkout and run `claude`.
3. Review workspace trust and tool permissions. Do not choose blanket permission
   bypass. Confirm loaded instructions using `/context` (or the memory listing your
   installed version provides). `/init` is optional; review any proposed changes
   rather than replacing the curated instructions blindly.
4. Ask for a bounded onboarding: read the map, inspect current branch/status, find
   the relevant test command, run safe baseline checks if dependencies exist, then
   summarize risks. Do not supply secret configuration to “help it understand.”
5. For an unfamiliar or cross-cutting task, use Plan mode through the supported UI
   or CLI option shown by your version. Agree scope and checks before editing.
   Avoid spending an elaborate planning session on a trivial typo.

There is no need for “you are a genius full-stack engineer” or an exhaustive dump
of every source file. Give a concrete outcome, constraints and observable checks.

## A normal engineering task

**Specify:** symptom/desired result, reproduction, affected environment, exclusions,
and acceptance criteria. Example: disabling wake must stop feeding detections;
blocked inference must not freeze the UI; restart must not duplicate workers.

**Explore:** have Claude trace input → UI/API → dispatch → adapter → result. Read
existing tests and relevant safety reports. Correct misunderstandings before edits.

**Implement:** one bounded change, regression coverage, inspect adjacent callers.
For a reproducible bug use red/green tests: confirm a meaningful failure, fix the
cause, confirm success. Do not accept tests that merely restate the implementation.

**Verify:** invoke `/ultron-check`. Inspect command outputs, not only the summary.
For dashboard work verify API and visible failure states; for Qt/audio changes use
an approved native environment. Browser automation does not certify Qt behavior.

**Review:** inspect `git diff`; request a fresh review focused on bugs, unsafe
boundaries and missing tests. Human review still owns acceptance. Commit/push/PR
only when authorized, and verify real CI rather than assuming it exists.

## Context and multiple agents

Use a fresh session for an unrelated task. For long work, retain a short handoff
with decisions, touched files, commands/results and remaining blockers; reference
files instead of repeatedly pasting the entire history. Use context/compaction
controls available in your version when needed.

Subagents are useful for independent read-only reviews or bounded investigations.
Give each a precise question and evidence requirement. Do not claim a swarm if the
runner cannot create independent agents. Avoid concurrent writers in the same
files. Separate worktrees can help in environments that permit them, but Arena's
session branch restrictions take precedence; do not create/switch branches here
without the host workflow. Parallelism increases review and integration costs.

## Permissions and enforcement

Ultron can execute host-side effects. Review any requested shell, device, network,
credential or MCP permission. Use least privilege and isolated synthetic state.
Never use bypass-permissions flags as a productivity shortcut.

For non-negotiable restrictions, separately design and test permission settings,
sandboxing, reviewed hooks and CI/branch protection. A hook can enforce its defined
check, not prove all actions safe; a Markdown prohibition is not a security control.
Do not install arbitrary “agent packs” or MCP servers just to imitate someone's setup.

## Maintain the setup

When a correction is genuinely reusable, add a short specific rule or improve the
relevant procedure/test. Delete obsolete/duplicated rules; do not append every
conversation as permanent instructions. Prefer tested constraints to louder wording.

Success means reproducible behavior and a reviewable diff—not more agents, more
instruction files, a bigger prompt or an unsupported “production-ready” claim.
