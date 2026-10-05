"""Keep Python's cyclic GC on the Tk thread while background workers run.

Destroyed Tk objects (interpreters, Variables, images, fonts) often sit in
reference cycles. If a worker thread's allocations trigger the collector, their
finalizers call Tcl from the wrong thread; a dead interpreter then aborts the
process ("Tcl_AsyncDelete"). So automatic collection is paused while any
worker runs:

- the Tk thread takes a hold *before* Thread.start(), because thread bootstrap
  allocates before the worker body runs;
- the worker releases the hold when finished, but never re-enables GC itself:
  its very next allocation could run the overdue collection on the wrong thread;
- the Tk thread calls resume_gc() from its polling paths.

Explicit gc.collect() calls still work while paused.
"""

import gc
import threading


_lock = threading.Lock()
_active = 0
_paused = False  # True only while this module, not the caller, disabled GC.


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
        with _lock:
            if not self._released:
                self._released = True
                _active -= 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()
        return False


def hold_gc():
    """Tk thread: pause automatic GC for a worker about to start."""
    return GCHold()


def resume_gc():
    """Tk thread only: re-enable GC once no worker holds it. Cheap to call often."""
    global _paused
    with _lock:
        if _active or not _paused:
            return False
        _paused = False
        gc.enable()
    return True
