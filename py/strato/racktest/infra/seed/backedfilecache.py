from strato.racktest.infra.seed import memorycache
from strato.racktest.infra.seed import filecache


class FileBackedByMemory(filecache.FileCache):
    def __init__(self, cacheDir=None):
        filecache.FileCache.__init__(self, cacheDir)
        self._memoryCache = memorycache.MemoryCache()

    def get(self, key):
        with self._memoryCache.lock(key):
            entry = self._memoryCache.get(key)
            if entry:
                return entry
        entry = filecache.FileCache.get(self, key)
        if entry is None:
            return None
        with self._memoryCache.lock(key):
            self._memoryCache.install(key, {'code': entry})
        return entry

    def install(self, seedKey, seedEntry):
        filecache.FileCache.install(self, seedKey, seedEntry)
        with self._memoryCache.lock(seedKey):
            self._memoryCache.install(seedKey, seedEntry)
