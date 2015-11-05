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
import re
import errno


class FileCache(object):

    def __init__(self, cacheDir):
        self._cacheDir = cacheDir
        self._ensure_dir(self._cacheDir)

    def _ensure_dir(self, d):
        try:
            if not os.path.exists(d):
                os.makedirs(d)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise

    def _generatePath(self, key, suffix):
        return "%s/%s.%s" % (self._cacheDir, key, suffix)

    def _lockFileName(self, key):
        return self._generatePath(key, 'lock')

    def _manifestFileName(self, key):
        return self._generatePath(key, 'manifest')

    def _seedFileName(self, key):
        return self._generatePath(key, 'code')

    def _sanitizeKeyForFileName(self, key):
        return base64.urlsafe_b64encode(key)

    @contextmanager
    def lock(self, key):
        sanitizedKey = key.hash
        lock = lockfile.LockFile(self._lockFileName(sanitizedKey))
        while True:
            try:
                lock.acquire(timeout=60)
                break
            except lockfile.LockTimeout:
                logging.warning('Lock timed out for key %(key)s try to heal cache', dict(key=key))
                if self._isLockingProcessAliveForLockFile(lock):
                    raise
                logging.warning('Cache is locked by dead process.'
                                'unlock and drop key %(key)s', dict(key=key))
                self.removeKey(sanitizedKey)
                continue
        try:
            yield
        finally:
            lock.release()

    def _validateDependencies(self, key):
        dependencies = self._loadManifest(key)['deps']
        for depPath, mTime in dependencies.iteritems():
            fileMtime = int(os.path.getmtime(depPath))
            if fileMtime != int(mTime):
                logging.debug('Mismatched timestemp on artifact %(depPath)s'
                              'current %(current)d registered %(registered)d',
                              dict(depPath=depPath, current=fileMtime, registered=mTime))
                return False
        return True

    def _isLockingProcessAliveForLockFile(self, lock):
        lockFileStat = os.stat(lock.lock_file)

        def _isSameUniqueLock(uniqueFile):
            fullPath = os.path.join(self._cacheDir, uniqueFile)
            return lockFileStat.st_ino == os.stat(fullPath).st_ino

        def _getPidFromUniqueFile(uniqueLockFile):
            return uniqueLockFile.split('.')[1]

        def _existsPid(pid):
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            else:
                return True

        uniqueLockFiles = [f for f in os.listdir(self._cacheDir)
                           if not (f.endswith('.code') or f.endswith('.deps') or f.endswith('.lock'))]
        for uniqueLockFile in uniqueLockFiles:
            if _isSameUniqueLock(uniqueLockFile):
                pid = _getPidFromUniqueFile(uniqueLockFile)
                return _existsPid(int(pid))

    def _loadManifest(self, key):
        path = self._manifestFileName(key)
        with open(path, 'r') as f:
            return json.loads(f.read())

    def _storeManifest(self, key, manifest):
        path = self._manifestFileName(key)
        with open(path, 'w') as f:
            f.write(json.dumps(manifest))

    def _storeCode(self, key, code):
        seedFile = self._seedFileName(key)
        with open(seedFile, 'wb') as f:
            return f.write(code)

    def get(self, key):
        sanitizedKey = key.hash
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
        sanitizedKey = seedKey.hash
        logging.debug('Installing seed for key %(key)s - sanitized %(sanitized)s',
                      dict(key=seedKey, sanitized=sanitizedKey))
        self._storeCode(sanitizedKey, seedEntry['code'])
        self._storeManifest(sanitizedKey, {'deps': seedEntry['deps'], 'key':  seedKey.__repr__()})

    def clean(self):
        if self._cacheDir is None or self._cacheDir == '':
            raise Exception('Avoid erasing your laptop')
        shutil.rmtree(self._cacheDir, ignore_errors=True)

    def traverse(self):
        for codeFile in glob.iglob(self._cacheDir + '/*.code'):
            keyName = codeFile[len(self._cacheDir) + 1:-len('.code')]
            lockFile = self._lockFileName(keyName)
            try:
                manifest = self._loadManifest(keyName)
                deps = manifest['deps']
                args = manifest['key'].split(':')
            except:
                deps = {'error': sys.exc_info()[0]}
                args = None
            yield keyName, args, deps, lockfile.LockFile(lockFile)

    def _unlinkIfExists(self, path):
        if os.path.exists(path):
            os.unlink(path)

    def removeKey(self, key):
        self.break_lock(key)
        self._unlinkIfExists(self._manifestFileName(key))
        self._unlinkIfExists(self._seedFileName(key))

    def break_lock(self, key):
        lockfile.LockFile(self._lockFileName(key)).break_lock()


def fileCacheDir():
    rootDir = os.path.dirname(os.getcwd()) + "/" + ".seedcache"
    return os.getenv('SEED_CACHE_DIR', rootDir)


cacheregistry.register('file', lambda: FileCache(fileCacheDir()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='File SeedCache controller')
    parser.add_argument('--root', required=False, default=fileCacheDir())
    parser.add_argument('--verbose', action='store_true', default=False)
    commandGroup = parser.add_mutually_exclusive_group()
    commandGroup.add_argument('--clear', action='store_true', default=False)
    commandGroup.add_argument('--display', action='store_true', default=True)
    commandGroup.add_argument('--fix-locked', dest='fix_locked', action='store_true', default=False)

    args = parser.parse_args()
    cache = FileCache(args.root)
    if args.clear:
        cache.clean()
        sys.exit(0)
    if args.fix_locked:
        for keyName, seedArgs, deps, lockFile in cache.traverse():
            if lockFile.is_locked() and not cache._isLockingProcessAliveForLockFile(lockFile):
                cache.removeKey(keyName)
        sys.exit(0)
    if args.display:
        for keyName, seedArgs, deps, lockFile in cache.traverse():
            output = sys.stdout if not lockFile.is_locked() else sys.stderr
            output.write('CachedSeed: %(module)s:%(method)s - locked: %(locked)s status: %(status)s\n' %
                         dict(module=seedArgs[0],
                              method=seedArgs[1],
                              locked=lockFile.is_locked(),
                              status='valid' if cache._validateDependencies(keyName) else 'outdated'))
            if args.verbose:
                print 'Dependencies: %s' % deps
