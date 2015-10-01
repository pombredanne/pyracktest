from contextlib import contextmanager
import logging
import os
import json
import shutil
import base64
import lockfile
import cacheregistry
import argparse
import sys
import glob


class FileCache(object):

    def __init__(self, cacheDir):
        self._cacheDir = cacheDir
        self._ensure_dir(self._cacheDir)

    def _ensure_dir(self, d):
        if not os.path.exists(d):
            os.makedirs(d)

    def _generatePath(self, key, suffix):
        return "%s/%s.%s" % (self._cacheDir, key, suffix)

    def _lockFileName(self, key):
        return self._generatePath(key, 'lock')

    def _depsFileName(self, key):
        return self._generatePath(key, 'deps')

    def _seedFileName(self, key):
        return self._generatePath(key, 'code')

    def _sanitizeKeyForFileName(self, key):
        return base64.urlsafe_b64encode(key)

    @contextmanager
    def lock(self, key):
        sanitizedKey = self._sanitizeKeyForFileName(key)
        lock = lockfile.LockFile(self._lockFileName(sanitizedKey))
        lock.acquire(timeout=60)
        try:
            yield
        finally:
            lock.release()

    def _loadDependenciesFile(self, key):
        path = self._depsFileName(key)
        with open(path, 'r') as f:
            return json.loads(f.read())

    def _validateDependencies(self, key):
        dependencies = self._loadDependenciesFile(key)
        for depPath, mTime in dependencies.iteritems():
            fileMtime = int(os.path.getmtime(depPath))
            if fileMtime != int(mTime):
                logging.debug('Mismatched timestemp on artifact %(depPath)s'
                              'current %(current)d registered %(registered)d',
                              dict(depPath=depPath, current=fileMtime, registered=mTime))
                return False
        return True

    def _storeDependencies(self, key, deps):
        path = self._depsFileName(key)
        with open(path, 'w') as f:
            f.write(json.dumps(deps))

    def _storeCode(self, key, code):
        seedFile = self._seedFileName(key)
        with open(seedFile, 'wb') as f:
            return f.write(code)

    def get(self, key):
        sanitizedKey = self._sanitizeKeyForFileName(key)
        seedFile = self._seedFileName(sanitizedKey)
        if not os.path.exists(seedFile):
            return None
        try:
            if not self._validateDependencies(sanitizedKey):
                logging.debug('Seed for key %(key)s is outdated', dict(key=key))
                return None
            with open(seedFile, 'r') as f:
                return f.read()
        except:
            logging.warn("Failed to validate and fetch seed for key %(key)s",
                         dict(key=key), exc_info=1)
            return None

    def install(self, seedKey, seedEntry):
        sanitizedKey = self._sanitizeKeyForFileName(seedKey)
        logging.debug('Installing seed for key %(key)s - sanitized %(sanitized)s',
                      dict(key=seedKey, sanitized=sanitizedKey))
        self._storeCode(sanitizedKey, seedEntry['code'])
        self._storeDependencies(sanitizedKey, seedEntry['deps'])

    def clean(self):
        if self._cacheDir is None or self._cacheDir == '':
            raise Exception('Avoid erasing your laptop')
        shutil.rmtree(self._cacheDir, ignore_errors=True)

    def traverse(self):
        for codeFile in glob.iglob(self._cacheDir + '/*.code'):
            keyName = codeFile[len(self._cacheDir) + 1:-len('.code')]
            lockFile = self._lockFileName(keyName)
            args = base64.urlsafe_b64decode(keyName).split(':')
            try:
                deps = self._loadDependenciesFile(keyName)
            except:
                deps = {'error': sys.exc_info()[0]}
            yield keyName, args, deps, lockfile.LockFile(lockFile)

    def _unlinkIfExists(self, path):
        if os.path.exists(path):
            os.unlink(path)

    def removeKey(self, key):
        self.break_lock(key)
        self._unlinkIfExists(self._depsFileName(key))
        self._unlinkIfExists(self._seedFileName(key))

    def break_lock(self, key):
        lockfile.LockFile(self._lockFileName(key)).break_lock()


def fileCacheDir():
    rootDir = os.path.dirname(os.getcwd()) + "/" + ".seedcache"
    return os.getenv('SEED_CACHE_DIR', rootDir)


cacheregistry.register('file', lambda: FileCache(fileCacheDir()))
