"""Keep Python's cyclic GC on the Tk thread while background workers run.

Destroyed Tk objects (interpreters, Variables, images, fonts) often sit in
reference cycles. If a worker thread's allocations trigger the collector, their
finalizers call Tcl from the wrong thread; a dead interpreter then aborts the
process ("Tcl_AsyncDelete"). So automatic collection is paused while any
worker runs:

- the Tk thread takes a hold *before* Thread.start(), because thread bootstrap
  allocates before the worker body runs;
- the worker releases the hold when finished, but never re-enables GC itself;
- the Tk thread resumes, and only after every releasing worker thread has
  fully exited: thread teardown after release still runs Python code;
- results are often consumed before the worker releases, so Tk-side consumers
  call resume_gc_soon() to retry until resuming succeeds.

Explicit gc.collect() calls still work while paused.
"""

import gc
import threading


_lock = threading.Lock()
_active = 0
_paused = False  # True only while this module, not the caller, disabled GC.
_finishing = set()  # Released worker threads that may still be tearing down.
_retry_widget = None


class GCHold:
    """One worker's pause. Usable once as a context manager; release is idempotent."""

    def __init__(self):
        global _active, _paused
        self._released = False
        with _lock:
            if not _paused and gc.isenabled():
                gc.disable()
                _paused = True
            _active += 1

    def release(self):
        global _active
        current = threading.current_thread()
        with _lock:
            if self._released:
                return
            self._released = True
            _active -= 1
            if current is not threading.main_thread():
                _finishing.add(current)
        if current is threading.main_thread():
            resume_gc()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()
        return False


def hold_gc():
    """Tk thread: pause automatic GC for a worker about to start."""
    return GCHold()


def paused():
    with _lock:
        return _paused


def resume_gc():
    """Tk thread only: re-enable GC once no worker holds it or is still exiting."""
    global _paused
    with _lock:
        _finishing.difference_update([thread for thread in _finishing
                                      if not thread.is_alive()])
        if _active or _finishing or not _paused:
            return False
        _paused = False
        gc.enable()
    return True


def _alive(widget):
    if widget is None:
        return False
    try:
        return bool(widget.winfo_exists())
    except Exception:  # Its interpreter is gone, so its pending retry never runs.
        return False


def resume_gc_soon(widget, interval=50):
    """Tk thread: retry resume_gc() via widget.after until it succeeds.

    One retry loop at a time. A destroyed widget simply ends the loop; the next
    Tk-thread resume or retry picks the pause up again.
    """
    global _retry_widget
    if resume_gc() or not paused() or _alive(_retry_widget):
        return

    def retry():
        global _retry_widget
        _retry_widget = None
        resume_gc_soon(widget, interval)

    try:
        widget.after(interval, retry)
    except Exception:  # Destroyed interpreter/widget: nothing left to schedule on.
        return
    _retry_widget = widget
