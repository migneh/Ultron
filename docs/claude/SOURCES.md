# Research and rationale

Reviewed 2026-11-23. These are paraphrases, not verbatim quotations. Live docs and
CLI defaults change; verify commands against the installed Claude Code version.
Repository-specific safety rules are our engineering decisions, not claims that
Anthropic requires this exact workflow.

| Source | What it supports | How applied here |
|---|---|---|
| [Current official best practices](https://code.claude.com/docs/en/best-practices) | Keep context specific, provide a verification signal, distinguish model guidance from harness enforcement. | Short root instructions, explicit checks and no claim that Markdown enforces safety. |
| [Official memory documentation](https://code.claude.com/docs/en/memory) | Shared CLAUDE.md context, local/user scopes, concise instructions and on-demand organization. | One shared root file; longer architecture/workflow references are not automatically imported. |
| [Official skills documentation](https://code.claude.com/docs/en/skills) | Repeated procedures belong in SKILL.md; skills support manual invocation and invocation controls. | User-invoked `/ultron-check`, with `disable-model-invocation: true`. |
| [Anthropic engineering team's original workflow article](https://www.anthropic.com/research/claude-code-best-practices) | Internal/external engineering patterns: explore/plan/implement, tests and separate review. | Bounded planning, regressions and a fresh reviewer where useful. This article explicitly says it is no longer maintained; current docs take precedence for commands/defaults. |
| [Simon Willison: First run the tests](https://simonwillison.net/guides/agentic-engineering-patterns/first-run-the-tests/) | Run existing tests for baseline evidence and to teach the agent the project's testing workflow; tests help establish whether generated code works. | Baseline then targeted regressions and full-suite checks where feasible. His uv command is not copied because Ultron does not establish that workflow. |

## What we deliberately did not copy

Search results included third-party summaries of Boris Cherny's workflow, but they
are not used as primary evidence for quotations, claimed speedups, fixed planning
percentages, exact agent counts or strict CLAUDE.md size limits. An engineer's
personal setup is not a universal requirement. No productivity multiplier is claimed.

The current official docs emphasize useful defaults and minimal project-specific
setup. The older engineering article describes more explicit manual orchestration.
We keep the durable parts—clear scope, concise context and observable verification—
without treating every historical command or permission default as current.

## Limits of this change

This adds documentation and one Markdown skill only. Claude Code was not installed
or executed in this environment. Loading/invocation should be smoke-tested in the
user's installed client. No runtime tests were rerun for this documentation-only
change, and historical test counts are clearly labeled as historical.
