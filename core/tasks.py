"""
core/tasks.py — fire-and-forget tasks that report their own failures.

`asyncio.create_task()` is the right tool for work nobody awaits, but it has one
trap: if the coroutine raises, nothing surfaces at the moment it fails. Python
only prints "Task exception was never retrieved" when the Task object is finally
garbage collected — which, in a long-running app, can be minutes later, at
interpreter shutdown, or never. Worse, that message says nothing about what the
task was for.

`spawn()` fixes the reporting and the lifetime:

  * it keeps a strong reference until completion (asyncio holds only a weak one,
    and the docs advise storing it — being explicit beats relying on the loop's
    internal handles);
  * it reports exceptions immediately, with the name you gave the task, instead
    of deferring them to GC;
  * it drops the reference when done, so a long session cannot accumulate them.

Note on what this does NOT do: in practice an unreferenced task that is awaiting
something is kept alive by the loop's own callbacks, so "the task disappears
mid-flight" is mostly folklore. The concrete problem being solved here is
*invisible failure*, not vanishing work.

    from core.tasks import spawn
    spawn(self._save_session_summary(), name="session-summary")
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, Set

# Strong references to in-flight tasks, so they cannot be collected and so their
# exceptions reach _report() rather than the GC.
_pending: Set[asyncio.Task] = set()


def _report(task_name: str, exc: BaseException) -> None:
    print(f"[Task:{task_name}] failed — {type(exc).__name__}: {exc}")
    try:
        import traceback
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    except Exception:
        pass


def spawn(
    coro: Awaitable[Any],
    *,
    name: str = "",
    on_error: Optional[Callable[[BaseException], None]] = None,
) -> asyncio.Task:
    """Schedule `coro` in the running loop, keeping it alive and logging failures."""
    task = asyncio.ensure_future(coro)
    label = name or getattr(coro, "__qualname__", None) or repr(coro)
    _pending.add(task)

    def _done(t: asyncio.Task) -> None:
        _pending.discard(t)
        if t.cancelled():
            return
        exc = t.exception()          # also marks the exception as retrieved
        if exc is None:
            return
        _report(label, exc)
        if on_error is not None:
            try:
                on_error(exc)
            except Exception as hook_exc:
                print(f"[Task:{label}] on_error hook raised — {hook_exc}")

    task.add_done_callback(_done)
    return task


def pending() -> int:
    """Number of spawned tasks still running (diagnostics/tests)."""
    return len(_pending)


def cancel_all() -> int:
    """Cancel every spawned task. Returns how many were cancelled."""
    count = 0
    for task in list(_pending):
        if not task.done():
            task.cancel()
            count += 1
    _pending.clear()
    return count
