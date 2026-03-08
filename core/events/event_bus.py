"""
Thread-safe event bus for decoupled communication between services.

Any component that holds a reference to the bus can **emit** typed
events, and any number of subscribers can react to them — optionally
filtering by ``EventKind``.

Two delivery modes are available:

* :meth:`emit` – **synchronous**.  Subscribers run on the calling thread
  and the call blocks until all have returned.
* :meth:`emit_async` – **asynchronous**.  The event is placed on an
  internal queue and delivered by a dedicated daemon worker thread.  The
  call returns immediately.
"""
from __future__ import annotations

import logging
import threading
from queue import Empty, SimpleQueue
from typing import Callable

from .event_types import Event, EventKind

_log = logging.getLogger(__name__)

_SENTINEL = object()  # poison pill for clean shutdown


class EventBus:
    """A thread-safe publish/subscribe event bus.

    Supports both synchronous (:meth:`emit`) and asynchronous
    (:meth:`emit_async`) delivery.  The async worker is started
    automatically on construction and torn down via :meth:`shutdown`.

    For Qt UI consumption, use the ``QtEventBridge`` adapter in the
    client layer which re-emits events as Qt signals (auto-queued to
    the main thread).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[
            tuple[Callable[[Event], None], frozenset[EventKind] | None]
        ] = []

        # -- async worker --
        self._queue: SimpleQueue[Event | object] = SimpleQueue()
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="event-bus-worker",
        )
        self._worker.start()

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        callback: Callable[[Event], None],
        kinds: set[EventKind] | None = None,
    ) -> Callable[[], None]:
        """Register *callback* for events matching *kinds*.

        If *kinds* is ``None`` the callback receives **all** events.

        Returns an *unsubscribe* callable — call it to remove the
        subscription.
        """
        frozen = frozenset(kinds) if kinds is not None else None
        entry = (callback, frozen)
        with self._lock:
            self._subscribers.append(entry)

        def _unsub() -> None:
            with self._lock:
                self._subscribers[:] = [
                    s for s in self._subscribers if s is not entry
                ]

        return _unsub

    # ------------------------------------------------------------------
    # Emit
    # ------------------------------------------------------------------

    def emit(self, event: Event) -> None:
        """Broadcast *event* **synchronously** to all matching subscribers.

        Subscribers run on the calling thread.  Exceptions in individual
        callbacks are logged but do **not** prevent delivery to remaining
        subscribers.
        """
        with self._lock:
            snapshot = list(self._subscribers)

        for callback, kinds in snapshot:
            if kinds is not None and event.kind not in kinds:
                continue
            try:
                callback(event)
            except Exception:
                _log.exception(
                    "Subscriber %r failed handling %s", callback, event.kind
                )

    def emit_async(self, event: Event) -> None:
        """Enqueue *event* for **asynchronous** delivery.

        Returns immediately.  The event is delivered to subscribers on
        the dedicated worker thread.
        """
        self._queue.put(event)

    # ------------------------------------------------------------------
    # Async worker
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Drain the async queue and deliver events until shutdown."""
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            self.emit(item)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop the async worker.  Safe to call multiple times."""
        self._queue.put(_SENTINEL)
        self._worker.join(timeout=5)
