"""
Lightweight async-task runner for PySide6.

Provides :func:`run_async` to offload any callable to a ``QThreadPool``
worker, with results / errors delivered back to the Qt main thread via
signals.  This keeps the UI responsive while heavy I/O (git commands,
file copies, LLM requests …) runs in the background.

Usage::

    from client.ui.async_runner import run_async

    run_async(
        lambda: git_utils.get_branches(path),
        on_result=lambda branches: self._populate_tree(branches),
        on_error=lambda exc: logger.warning("git failed: %s", exc),
    )
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_log = logging.getLogger(__name__)

# Set of workers that are currently in-flight.  Prevents Python from
# garbage-collecting the worker (and its _WorkerSignals QObject) before
# the queued Qt signals have been delivered to the main thread.
_active_workers: set["_Worker"] = set()


# ------------------------------------------------------------------
# Internal signal carrier
# ------------------------------------------------------------------

class _WorkerSignals(QObject):
    """Signals emitted by a :class:`_Worker` runnable."""
    finished = Signal()            # always emitted at the end
    error = Signal(object)         # payload: Exception
    result = Signal(object)        # payload: return value of fn


# ------------------------------------------------------------------
# QRunnable wrapper
# ------------------------------------------------------------------

class _Worker(QRunnable):
    """Wraps a plain callable so it can run on ``QThreadPool``."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:  # noqa: A003 – shadows builtin
        try:
            value = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            _log.debug("Worker error: %s\n%s", exc, traceback.format_exc())
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(value)
        finally:
            self.signals.finished.emit()


# ------------------------------------------------------------------
# Public helper
# ------------------------------------------------------------------

def run_async(
    fn: Callable[..., Any],
    *args: Any,
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    on_finished: Callable[[], None] | None = None,
    pool: QThreadPool | None = None,
) -> _Worker:
    """Run *fn(\*args)* on a ``QThreadPool`` and deliver callbacks on the
    main thread.

    Parameters
    ----------
    fn:
        The blocking callable to execute in a worker thread.
    *args:
        Positional arguments forwarded to *fn*.
    on_result:
        Called with the return value of *fn* on the **main thread**.
    on_error:
        Called with the exception if *fn* raises, on the **main thread**.
    on_finished:
        Called (no args) after *fn* completes (success or failure),
        on the **main thread**.
    pool:
        Optional explicit ``QThreadPool``.  Falls back to the global
        instance.

    Returns
    -------
    _Worker
        The enqueued worker (for testing / introspection only).
    """
    worker = _Worker(fn, *args)

    if on_result is not None:
        worker.signals.result.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)

    # prevent GC until the worker finishes and signals are delivered
    _active_workers.add(worker)
    worker.signals.finished.connect(lambda: _active_workers.discard(worker))

    (pool or QThreadPool.globalInstance()).start(worker)
    return worker
