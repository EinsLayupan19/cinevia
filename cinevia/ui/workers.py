"""Runs network and hashing work off the UI thread and hands results back to it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import shiboken6
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_pool = QThreadPool.globalInstance()
_pool.setMaxThreadCount(max(8, _pool.maxThreadCount()))
_live: set[_Relay] = set()


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any], relay: _Relay) -> None:
        super().__init__()
        self.fn = fn
        self.relay = relay

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as e:  # handed to the UI as an error state
            self.relay.failed.emit(e)
        else:
            self.relay.done.emit(result)


def run_async(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None],
    on_error: Callable[[Exception], None] | None = None,
    owner: QObject | None = None,
) -> None:
    """Calls ``fn`` on a worker thread, then ``on_done(result)`` on the UI thread.
    If ``owner`` was closed in the meantime the result is dropped."""
    relay = _Relay()
    _live.add(relay)

    def alive() -> bool:
        return owner is None or shiboken6.isValid(owner)

    def finish(callback: Callable | None, value: Any) -> None:
        _live.discard(relay)
        relay.deleteLater()
        if callback and alive():
            callback(value)

    relay.done.connect(lambda v: finish(on_done, v))
    relay.failed.connect(lambda e: finish(on_error, e))
    _pool.start(_Job(fn, relay))
