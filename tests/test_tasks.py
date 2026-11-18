"""
tests/test_tasks.py — `core.tasks.spawn()` must make fire-and-forget failures visible.

The behaviour being locked in: an exception inside an un-awaited coroutine is
reported *when it happens*, with the task's name, instead of being deferred to
garbage collection as "Task exception was never retrieved" (or never printed at
all in a long-running session).
"""
from __future__ import annotations

import asyncio
import contextlib
import gc
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import tasks


class SpawnTests(unittest.TestCase):
    def setUp(self):
        tasks.cancel_all()

    def tearDown(self):
        tasks.cancel_all()

    def test_failing_task_is_reported_with_its_name(self):
        async def scenario():
            async def boom():
                await asyncio.sleep(0)
                raise RuntimeError("kaboom")

            spawned = tasks.spawn(boom(), name="exploder")
            await asyncio.sleep(0.05)
            return spawned

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            spawned = asyncio.run(scenario())
        output = buffer.getvalue()

        self.assertIn("Task:exploder", output)
        self.assertIn("kaboom", output)
        self.assertTrue(spawned.done())
        # retrieving it here proves the exception was consumed, not left dangling
        self.assertIsInstance(spawned.exception(), RuntimeError)

    def test_successful_task_reports_nothing_and_is_released(self):
        async def scenario():
            async def fine():
                await asyncio.sleep(0)
                return 42

            spawned = tasks.spawn(fine(), name="quiet")
            await asyncio.sleep(0.05)
            return spawned, tasks.pending()

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            spawned, still_pending = asyncio.run(scenario())

        self.assertEqual(spawned.result(), 42)
        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(still_pending, 0, "completed tasks were not released")

    def test_task_survives_garbage_collection_while_awaiting(self):
        async def scenario():
            finished = []

            async def slow():
                await asyncio.sleep(0.05)
                finished.append(True)

            tasks.spawn(slow(), name="slow")
            gc.collect()                    # nothing else references the task
            await asyncio.sleep(0.1)
            return finished

        self.assertEqual(asyncio.run(scenario()), [True])

    def test_on_error_hook_receives_the_exception(self):
        seen = []

        async def scenario():
            async def boom():
                raise ValueError("bad input")

            tasks.spawn(boom(), name="hooked", on_error=seen.append)
            await asyncio.sleep(0.05)

        asyncio.run(scenario())
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], ValueError)

    def test_cancel_all_cancels_running_tasks(self):
        async def scenario():
            cancelled = []

            async def forever():
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    cancelled.append(True)
                    raise

            tasks.spawn(forever(), name="forever")
            await asyncio.sleep(0.01)
            count = tasks.cancel_all()
            await asyncio.sleep(0.05)
            return count, cancelled

        count, cancelled = asyncio.run(scenario())
        self.assertEqual(count, 1)
        self.assertEqual(cancelled, [True])


if __name__ == "__main__":
    unittest.main(verbosity=2)
