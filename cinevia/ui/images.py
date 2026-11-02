"""Poster and backdrop loading with Qt's network stack, cached in memory and on disk."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkDiskCache,
    QNetworkReply,
    QNetworkRequest,
)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "image-cache"
MEMORY_ITEMS = 220


class ImageLoader(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.net = QNetworkAccessManager(self)
        disk = QNetworkDiskCache(self)
        disk.setCacheDirectory(str(CACHE_DIR))
        disk.setMaximumCacheSize(300 * 1024 * 1024)
        self.net.setCache(disk)
        # Decoded posters are ~1 MB each, so keep only the most recently used.
        self.memory: OrderedDict[str, QPixmap] = OrderedDict()
        self.waiting: dict[str, list[tuple[QObject | None, Callable[[QPixmap], None]]]] = {}

    def load(self, url: str, callback: Callable[[QPixmap], None], owner: QObject | None = None) -> None:
        """Calls back with the image (or a null pixmap on failure). Skipped if ``owner`` is gone."""
        if not url:
            callback(QPixmap())
            return
        if url in self.memory:
            self.memory.move_to_end(url)
            callback(self.memory[url])
            return
        if url in self.waiting:
            self.waiting[url].append((owner, callback))
            return
        self.waiting[url] = [(owner, callback)]
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.PreferCache)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self.net.get(req)
        reply.finished.connect(lambda: self._done(url, reply))

    def _done(self, url: str, reply: QNetworkReply) -> None:
        pix = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix.loadFromData(reply.readAll())
        reply.deleteLater()
        if not pix.isNull():
            self.memory[url] = pix
            while len(self.memory) > MEMORY_ITEMS:
                self.memory.popitem(last=False)
        for owner, callback in self.waiting.pop(url, []):
            if owner is None or shiboken6.isValid(owner):
                callback(pix)


_loader: ImageLoader | None = None


def images() -> ImageLoader:
    global _loader
    if _loader is None:
        _loader = ImageLoader()
    return _loader
