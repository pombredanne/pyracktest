from strato.racktest.hostundertest import plugins
import random
import cPickle
import tempfile
import shutil
import subprocess
import os
import logging
import time
import inspect
from strato.racktest.infra.seed import seedcache
from strato.racktest.infra.seed import seedcreator
from strato.racktest.infra.seed import invocation
from strato.racktest.infra.seed import filecache
from strato.racktest.infra.seed import backedfilecache
from strato.racktest.infra.seed import memorycache
import functools


class Seed:
    def __init__(self, host):
        self._host = host

    def runCode(self, code, takeSitePackages=False, outputTimeout=None, excludePackages=None):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        seed = seedcreator.seedFactory(invocation.snippetCode(code),
                                       generateDependencies=False,
                                       takeSitePackages=takeSitePackages,
                                       excludePackages=excludePackages)
        output = invocation.executeWithResult(self._host,
                                              seed,
                                              unique,
                                              hasInput=False,
                                              outputTimeout=outputTimeout)
        result = invocation.downloadResult(self._host, unique)
        return result, output

    def runCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        kwargs = dict(kwargs)
        outputTimeout = kwargs.pop('outputTimeout', None)
        unique = self._unique()
        seed = self._generateSeedWithCacheWithNoCacheFallback(callable, unique, *args, **kwargs)
        output = invocation.executeWithResult(self._host,
                                              seed,
                                              unique,
                                              hasInput=True,
                                              outputTimeout=outputTimeout)
        result = invocation.downloadResult(self._host, unique)
        return result, output

    def forkCode(self, code, takeSitePackages=False, excludePackages=None):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        seed = seedcreator.seedFactory(invocation.snippetCode(code),
                                       generateDependencies=False,
                                       takeSitePackages=takeSitePackages,
                                       excludePackages=excludePackages)
        invocation.executeInBackground(self._host, seed, unique, hasInput=False)
        return _Forked(self._host, unique)

    def forkCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        kwargs = dict(kwargs)
        unique = self._unique()
        seed = self._generateSeedWithCacheWithNoCacheFallback(callable, unique, *args, **kwargs)
        invocation.executeInBackground(self._host, seed, unique, hasInput=True)
        return _Forked(self._host, unique)

    def _generateSeedWithCacheWithNoCacheFallback(self, callable, unique, *args, **kwargs):
        excludePackages = kwargs.pop('excludePackages', None)
        takeSitePackages = kwargs.pop('takeSitePackages', False)
        noCache = kwargs.pop('noCache', False)
        invocation.installArgs(self._host, unique, args, kwargs)
        code = invocation.callableCode(callable)
        cacheKey = self._cacheKey(callable,
                                  takeSitePackages=takeSitePackages,
                                  excludePackages=takeSitePackages)
        global cache
        if cache is None or noCache:
            seed = seedcreator.seedFactory(code, False, takeSitePackages, excludePackages)
        else:
            try:
                seed = cache.make(cacheKey, code, takeSitePackages, excludePackages)
            except:
                logging.warn('Failed to operate cache for key %(key)s, failover to creation clear cache?',
                             dict(cacheKey=cacheKey), exc_info=1)
            seed = seedcreator.seedFactory(code, False, takeSitePackages, excludePackages)
        return seed

    def _cacheKey(self, callable, **packArgs):
        args = ';'.join(["%s=%s" % (key, value) for key, value in packArgs.iteritems()])
        callableFilePath = inspect.getfile(callable)
        return callableFilePath + ":" + callable.__name__ + ":" + args

    def _unique(self):
        return "%09d" % random.randint(0, 1000 * 1000 * 1000)

    @classmethod
    def _generateSeedCacheEngine(cls, engineType):
        engineTypeToClass = dict(filecached=backedfilecache.FileBackedByMemory,
                                 file=filecache.FileCache,
                                 memory=filecache.FileCache)
        if engineType not in engineTypeToClass:
            logging.error("Invalid seed cache engine type given: %(engineType)s",
                          dict(engineType=engineType))
            raise ValueError(engineType)
        engineClass = engineTypeToClass[engineType]
        engineInstance = engineClass()
        return engineInstance

    @classmethod
    def generateSeedCache(cls):
        seedCacheEngineType = os.getenv('SEED_CACHE', None)
        if seedCacheEngineType is None:
            return None
        seedCacheEngine = cls._generateSeedCacheEngine(seedCacheEngineType)
        return seedcache.SeedCache(seedCacheEngine)


class _Forked:
    def __init__(self, host, unique):
        self._host = host
        self._unique = unique
        self._pid = self._getPid()

    def _getPid(self):
        for i in xrange(10):
            try:
                return self._host.ssh.ftp.getContents("/tmp/pid%s.txt" % self._unique).strip()
            except:
                time.sleep(0.1)
        return self._host.ssh.ftp.getContents("/tmp/pid%s.txt" % self._unique).strip()

    def poll(self):
        if 'DEAD' not in self._host.ssh.run.script("test -d /proc/%s || echo DEAD" % self._pid):
            return None
        if 'FAILED' in self._host.ssh.run.script(
                "test -e /tmp/result%s.pickle || echo FAILED" % self._unique):
            return False
        return True

    def result(self):
        return cPickle.loads(self._host.ssh.ftp.getContents("/tmp/result%s.pickle" % self._unique))

    def output(self):
        return self._host.ssh.ftp.getContents("/tmp/output%s.txt" % self._unique)

    def kill(self, signalNameOrNumber=None):
        if signalNameOrNumber is None:
            signalNameOrNumber = 'TERM'
        self._host.ssh.run.script("kill -%s %s" % (str(signalNameOrNumber), self._pid))


cache = Seed.generateSeedCache()
plugins.register('seed', Seed)
