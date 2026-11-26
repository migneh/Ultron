# Git Sentinel: approved fixed local inspection; mutations disabled

## Traced surface and narrowing

`ultron/actions/git_sentinel.py` was the only discovered caller of its general
`_run_git` helper. Former auto-commit staged every change (`add -A`), generated a
message and could commit/push; branch/create/checkout, stash and remote operations
were direct effects without exact sink approval. All those helpers/aliases now
fail closed before process launch or even repository resolution. Former raw argv
helper returns a disabled error tuple; it cannot bypass the fixed adapter. No
commit/index/ref/branch/remote mutation adapter is claimed. This is a deliberate
compatibility restriction, not completed permission-safe auto-commit.

Only explicit-root local `status`, diff-stat, log (integer 1–20) and branch listing
remain, all through `ultron/core/git_inspection.py` host-approved plans. Missing or
invalid repo input no longer silently inspects the assistant repository. The
adapter accepts ordinary repository roots with .git directories; linked worktrees,
submodule .git files, symlink/junction paths, commondir and alternate object stores
are refused. It is not a general repository discovery or worktree adapter.

## Approval/effect boundary

Preview binds fixed argument vectors, root device/inode/mode, .git identity,
local config fingerprint and resolved Git executable fingerprint. Local paths and
history/filenames/stat output will be exposed to existing model/UI/log surfaces;
preview warns about that even though the operation is nominally read-only. Sink
consumes one exact grant, revalidates before each command and after queries, and
refuses changed repository/config/binary/commands. It does not bind every worktree
file/ref/HEAD to an immutable whole-repository snapshot; concurrent edits can yield
mixed-time data. Returned output is untrusted repository text, not instructions or
verified remote freshness. No legacy claim that absent error output proves clean
working tree or up-to-date remote state remains.

Vectors disable external diff and textconv for diff-stat; submodule inspection is
ignored for status/diff. CLI disables pagers and optional locks; fsmonitor and
untracked cache are overridden off. Inherited GIT_* variables are stripped;
system/global Git config ignored, interactive prompts disabled, lazy fetch off,
protocol allowlist empty and pager set to noninteractive. Local config/includes,
attributes, filesystem, runtime/native Git and non-Git host environment remain
trusted. Unsupported native flags fail without weaker fallback. These controls
reduce known side effects, not all possible helper/code/network execution.

Each command gets a 5-second checkpoint budget and 64KiB combined stdout/stderr
spooled-size checks. Polling is 20ms; spool can overshoot before a check, so this is
NOT a hard disk/output/resource cap. Output shown is bounded, stderr omitted; known
process errors/timeout/output-cap cases do not leak captured error contents and
never retry. Only owned native process is killed/waited on timeout/limit; descendants
or native blocking aren't process-tree isolated/certified stopped. Diff issues two
fixed queries, each with its own budget; path/binary hashing and cleanup add time.

## Limits / remaining work

This is not a Git or OS sandbox. Repository/native configuration can have executable
or indirect effects beyond the disabled paths; permission to inspect is explicit
because even read commands are not assumed safe in an untrusted environment.
Executable/parent/config checks can race; binaries, includes, attributes or filesystem
state can change after checks. No cryptographic repo identity, full config/include
fingerprint, dedicated account, egress enforcement, durable audit/receipt, global
process serialization or shutdown barrier is implemented. Worktrees/alternates
unsupported does not certify every accepted directory benign. Per-command timeout
cannot forcibly stop every child or native filesystem operation.

No real Git operation was invoked by tests or the app adapter during this batch.
Agent tooling used only allowed local status/inspection/build operations; no
commit, tag, push or branch switch occurred. Application release preparation uses
its separate source-version tool and does not re-enable Git mutation paths.

Macros/plugins/inline tools and other subprocess/Git producers are **not migrated**
by disabling Git Sentinel helpers. Those remain P0 NEXT, along with manual global
permission graph classification, native validation and durable audit/isolation.
Future safe Git writes need exact paths/index/content/HEAD/ref/remote/hook/helper
preconditions and separate irreversible disclosure approval; a branch name or
command confirmation alone is insufficient.

## Validation

33 fake-process/temp-metadata tests cover absent/denied/expired/replayed approvals,
fixed vectors/environment, changed config before/after queries, diff flags/two
queries, time/output checks and kill/no-retry, stderr omission, raw sink/argv helper and approved noninspection-vector
refusal, mutation aliases/direct helpers, invalid log count and explicit-root/no
fallback/worktree refusal. No real repo mutation, Git process, network or hook ran.
Together with 20 version-system tests: full suite **1162 passed**, one existing
Starlette warning; targeted Ruff/diff/version checks clean. Native Git/platform
certification remains open; this does not establish whole-app safety.
