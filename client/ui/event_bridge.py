"""
Qt bridge for the application event bus.

``QtEventBridge`` subscribes to the core ``EventBus`` and re-emits
incoming events as Qt signals so that widgets can connect to them with
the standard ``signal.connect(slot)`` pattern.

Because Qt signals cross thread boundaries via queued connections
automatically, this bridge is **thread-safe**: services may ``emit()``
from any worker thread and the connected slots will execute on the
Qt main thread.

Usage::

    bridge = QtEventBridge(ctx.event_bus)

    # receive ALL events
    bridge.event_received.connect(my_handler)

    # receive only specific kinds
    bridge.on(EventKind.ENGINEER_MESSAGE, my_msg_handler)
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal

from core.events import Event, EventBus, EventKind


class QtEventBridge(QObject):
    """Adapter that converts ``EventBus`` callbacks into Qt signals.

    The ``event_received`` signal carries the full ``Event`` object
    so that a single connection can dispatch on ``event.kind``.

    For convenience, :meth:`on` registers a slot that is only invoked
    for the requested ``EventKind``\\(s).
    """

    event_received = Signal(object)  # payload: Event

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus
        self._unsub = bus.subscribe(self._on_event)
        self.destroyed.connect(self._destroyed)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_event(self, event: Event) -> None:
        # Signal emission from a non-Qt thread is safe — PySide6
        # automatically queues it to the receiver's thread.
        self.event_received.emit(event)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def on(
        self,
        kinds: EventKind | set[EventKind],
        slot: Callable[[Event], None],
    ) -> None:
        """Connect *slot* so it fires only for the given *kinds*.

        *kinds* can be a single ``EventKind`` or a set of them.
        """
        if isinstance(kinds, EventKind):
            kinds = {kinds}
        accepted = frozenset(kinds)

        def _filter(event: Event) -> None:
            if event.kind in accepted:
                slot(event)

        self.event_received.connect(_filter)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Unsubscribe from the bus.  Safe to call multiple times."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def _destroyed(self) -> None:
        """Slot connected to the Qt ``destroyed`` signal."""
        self.close()
