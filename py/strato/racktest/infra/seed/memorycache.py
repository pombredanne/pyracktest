from contextlib import contextmanager
import multiprocessing
import logging


class MemoryCache(object):

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
        return self._cache.get(key.hash, None)

    def install(self, seedKey, seedEntry):
        logging.debug('Adding seed for key %(key)s to cache', dict(key=seedKey))
        self._cache[seedKey.hash] = seedEntry['code']

from strato.racktest.infra.seed import cacheregistry
cacheregistry.register('memory', MemoryCache.__init__)
