"""
Thread-safe event bus for decoupled communication between services.

Any component that holds a reference to the bus can **emit** typed
events, and any number of subscribers can react to them — optionally
filtering by ``EventKind``.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from .event_types import Event, EventKind

_log = logging.getLogger(__name__)


class EventBus:
    """A synchronous, thread-safe publish/subscribe event bus.

    Subscribers are invoked **on the emitting thread**.  For Qt UI
    consumption, use the ``QtEventBridge`` adapter in the client layer
    which re-emits events as Qt signals (auto-queued to the main thread).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[
            tuple[Callable[[Event], None], frozenset[EventKind] | None]
        ] = []

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
        """Broadcast *event* to all matching subscribers.

        Exceptions in individual callbacks are logged but do **not**
        prevent delivery to remaining subscribers.
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
