"""Automatic GC stays off the Tk thread's objects while background workers run."""

import gc
import threading
import unittest

from python_to_exe import background


class GCHoldTests(unittest.TestCase):
    def setUp(self):
        background.resume_gc()  # Start from a clean module state.
        self.addCleanup(gc.enable if gc.isenabled() else gc.disable)
        self.addCleanup(background.resume_gc)
        gc.enable()

    @staticmethod
    def run_in_worker(function):
        thread = threading.Thread(target=function)
        thread.start()
        thread.join()
        return thread

    def test_overlapping_workers_resume_only_after_the_last_one_in_any_order(self):
        first, second = background.hold_gc(), background.hold_gc()
        self.assertFalse(gc.isenabled())
        observed = []

        def finish(hold):
            with hold:
                pass
            observed.append(gc.isenabled())  # Workers never re-enable.

        self.run_in_worker(lambda: finish(second))  # Finishes first.
        self.assertFalse(background.resume_gc())     # The other worker still holds.
        self.assertFalse(gc.isenabled())
        self.run_in_worker(lambda: finish(first))
        self.assertEqual(observed, [False, False])
        self.assertTrue(background.resume_gc())
        self.assertTrue(gc.isenabled())
        self.assertFalse(background.resume_gc())

    def test_resume_waits_until_a_released_worker_thread_has_exited(self):
        hold = background.hold_gc()
        released, finish = threading.Event(), threading.Event()

        def worker():
            with hold:
                pass
            released.set()
            finish.wait(5)  # Still running Python after its release.

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(released.wait(5))
        self.assertFalse(background.resume_gc())
        self.assertFalse(gc.isenabled())
        finish.set()
        thread.join()
        self.assertTrue(background.resume_gc())

    def test_exception_in_worker_releases_and_release_is_idempotent(self):
        hold = background.hold_gc()

        def worker():
            try:
                with hold:
                    raise ValueError("worker failure")
            except ValueError:
                pass
            hold.release()

        self.run_in_worker(worker)
        self.assertTrue(background.resume_gc())

    def test_main_thread_release_resumes_inline(self):
        with background.hold_gc():  # e.g. a direct convert() call in tests.
            self.assertFalse(gc.isenabled())
        self.assertTrue(gc.isenabled())

    def test_caller_disabled_gc_is_never_enabled_by_the_hold(self):
        gc.disable()
        with background.hold_gc():
            pass
        self.assertFalse(background.resume_gc())
        self.assertFalse(gc.isenabled())

    def test_retry_loop_is_single_and_survives_a_destroyed_widget(self):
        class Widget:
            def __init__(self):
                self.jobs, self.exists = [], True

            def after(self, _ms, callback):
                if not self.exists:
                    raise RuntimeError("destroyed")
                self.jobs.append(callback)

            def winfo_exists(self):
                if not self.exists:
                    raise RuntimeError("application has been destroyed")
                return True

        hold = background.hold_gc()
        root = Widget()
        background.resume_gc_soon(root)
        background.resume_gc_soon(root)
        self.assertEqual(len(root.jobs), 1)  # One loop at a time.
        root.jobs.pop()()                    # Still held: it reschedules.
        self.assertEqual(len(root.jobs), 1)
        root.exists = False                  # Its pending retry will never run.
        replacement = Widget()
        background.resume_gc_soon(replacement)
        self.assertEqual(len(replacement.jobs), 1)
        self.run_in_worker(hold.release)
        replacement.jobs.pop()()
        self.assertTrue(gc.isenabled())
        self.assertEqual(replacement.jobs, [])


