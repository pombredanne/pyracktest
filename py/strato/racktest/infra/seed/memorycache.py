from contextlib import contextmanager
import multiprocessing
import logging


class MemoryCache:
    def __init__(self):
        self._lock = multiprocessing.Lock()
        self._manager = multiprocessing.Manager()
        self._cache = self._manager.dict()

    @contextmanager
    def lock(self, key):
        self._lock.acquire(timeout=60)
        try:
            yield
        finally:
            self._lock.release()

    def get(self, key):
        return self._cache.get(key, None)

    def install(self, seedKey, seedEntry):
        logging.debug('Adding seed for key %(key)s to cache', dict(key=seedKey))
        self._cache[seedKey] = seedEntry['code']
