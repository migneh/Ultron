# Scoped regular-file Trash submission; guessed restore disabled

## Boundary and compatibility

`ultron/actions/file_controller.py` delete_file and direct `_safe_trash` both route to `ultron/core/file_trash.py`. Request snapshots one absolute regular-file path, identity/size/mtime/mode/SHA256, hardlink count and immediate parent path/device/inode/mode. Existing roots, symlink/junction ancestor checks and the regular-file size ceiling (64 MiB) apply. The preview binds this immutable snapshot and explicitly describes native storage/recoverability uncertainty. Hashing reads local contents before approval; no content upload is performed by this adapter. Paths/identity/hash are disclosed in the approval UI, not raw file content.

The effect sink consumes exactly that single-use grant, acquires the shared file lock and revalidates target snapshot, root policy, parent and the lazily resolved native backend callable before invoking it exactly once. No caller-supplied approval flag/token. Headless/denied/cancelled/expired/replayed approvals perform no native request. Changed/replaced/missing target, new hardlink, changed parent, revoked root or unavailable/changed backend refuse. Direct construction/invocation of an unapproved effect plan fails.

This intentionally narrows deletion: **no directories (including empty directories), batches, symlinks/junctions, special files, or files above 64 MiB**. There is no recursive deletion or `unlink`/permanent-delete fallback. Send2Trash must already be installed; request code imports it lazily and does not install dependencies or enumerate Trash. The installed package/backend/native configuration remains trusted; this change does not prove what an arbitrary substituted native library does.

## Outcomes, errors and no automatic undo

- Native call returns and original path absent: reports those two observations only. It does **not** claim a verified Trash receipt, stored item identity, persistence or recoverability.
- Native call returns but source exists/reappears: outcome unverified; it could be unchanged or a replacement. No retry and no extra deletion to make the report look successful.
- Native error (including one raised after a partial effect): sanitized unknown/failed result. No exception details, blind retry, automatic restore or destination cleanup.
- No undo entry is registered for native Trash submissions. Existing earlier undo entries remain untouched; they are not proof that a delete is reversible.

The former Windows Shell name/parent scan and `UNDELETE` invocation were removed. `_restore_from_trash` now returns a disabled explanation without reading paths, loading COM, enumerating Trash or invoking restore. Send2Trash supplies no portable stable item receipt through this interface; multiple deletions with the same original name/path cannot safely be distinguished. The adapter cannot safely infer which item to restore or promise the native UI will find it. Inspect native Trash manually; existence/recoverability are not guaranteed. A future restore adapter needs stable platform-specific identity, exact item/destination approval, no-overwrite publication and readback before re-enablement.

## Residual risks / coverage limits

Application-level checks are not a filesystem sandbox or atomic compare-and-delete. External writers can replace target/parent/ancestor paths after the final check or while native code acts; a post-call absence check cannot distinguish all races. Identity checks cover immediate parent, not a persistent full ancestor chain. Hardlink count is snapshotted but deleting this name does not erase other links/copies. Native Trash may use a different volume or implementation-specific storage with its own policy and metadata behavior. The adapter does not inspect native Trash permissions, quotas, retention, eviction or encryption. Operators must trust/validate the installed Send2Trash/native implementation. This is not secure erase, backup or a recoverability guarantee.

Hashing and native submission are synchronous with no hard wall-clock timeout, cancellation during the call, process isolation or cross-process serialization. Shared RLock covers these migrated paths only; unrelated file writers/native actors remain concurrent. A hung native call can block a worker and other lock users. There is no durable lifecycle/audit receipt, crash reconciliation or shutdown admission barrier for this adapter. Root policy still defaults to home, not a dedicated sandbox. Arbitrary malicious Python/in-process dependency replacement remains outside the approval primitive's security model. The selected callable object identity is a compatibility/change guard, not code-signing or native provider attestation.

This batch covers only file_controller's delete/Trash route and its former direct Trash/restore helpers. It does not migrate download publication, legacy download inverse helpers, Recycle Bin purge, unrelated cleanup/purge/Git/plugin/macro file effects or global permission coverage. No claim that every deletion in the assistant is protected. Previous transfer/write reports describe their historical unmigrated-delete status; this report supersedes only that scoped status.

## Validation

30 new tests in `tests/test_file_trash.py`, using only fake native callable/temporary files: public helper/core headless refusal, exact approval/replay, denial and expiry, modified/replaced/missing/symlink/retyped file, hardlink-count change, revoked roots, replaced parent, changed/missing backend, native failure before/after effects, source remains/reappears, directory/FIFO/missing/parent-symlink refusal, cap, direct sink without grant, disabled restore and hardlink alias survival. Successful fake callable disposes of its isolated tmp test path; it never calls real Send2Trash or native Trash/COM.

Full suite **1087 passed**, one existing Starlette warning. Targeted Ruff and diff checks clean. No user files/native Trash/desktop/provider/network effects exercised. The excluded virtualenv was recreated for test dependencies. Native Windows/macOS/Linux Trash certification and actual platform-specific receipt/restore design remain open. Next P0 implementation: downloads receive/publication and legacy download inverse review. No commit/push; default configurable wake model remains hey_jarvis.
