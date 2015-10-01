from strato.racktest.hostundertest import plugins
import random
import cPickle
import tempfile
import shutil
import subprocess
import os
import logging
import time
import sys
import inspect
from strato.racktest.infra.seed import cacheregistry
from strato.racktest.infra.seed import seedcache
from strato.racktest.infra.seed import seedcreator
from strato.racktest.infra.seed import invocation
import functools

_seedcache = seedcache.SeedCache(
    cacheregistry.create(os.getenv('SEED_CACHE', None)), seedcreator.SeedCreator)


class Seed:

    def __init__(self, host):
        self._host = host

    def runCode(self, code, takeSitePackages=False, outputTimeout=None,
                excludePackages=None, joinPythonNamespaces=True):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        seedGenerator = lambda: seedcreator.SeedCreator(invocation.snippetCode(code),
                                                        generateDependencies=False,
                                                        takeSitePackages=takeSitePackages,
                                                        excludePackages=excludePackages,
                                                        joinPythonNamespaces=joinPythonNamespaces)()['code']
        output = invocation.executeWithResult(self._host,
                                              seedGenerator,
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
        seedGenerator = self._prepareCallable(callable, unique, *args, **kwargs)
        output = invocation.executeWithResult(self._host,
                                              seedGenerator,
                                              unique,
                                              hasInput=True,
                                              outputTimeout=outputTimeout)
        result = invocation.downloadResult(self._host, unique)
        return result, output

    def forkCode(self, code, takeSitePackages=False, excludePackages=None, joinPythonNamespaces=True):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        seedGenerator = lambda: seedcreator.SeedCreator(invocation.snippetCode(code),
                                                        generateDependencies=False,
                                                        takeSitePackages=takeSitePackages,
                                                        excludePackages=excludePackages,
                                                        joinPythonNamespaces=joinPythonNamespaces)()['code']
        invocation.executeInBackground(self._host, seedGenerator, unique, hasInput=False)

        return _Forked(self._host, unique)

    def forkCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        kwargs = dict(kwargs)
        unique = self._unique()
        seedGenerator = self._prepareCallable(callable, unique, *args, **kwargs)
        invocation.executeInBackground(self._host, seedGenerator, unique, hasInput=True)
        return _Forked(self._host, unique)

    def _prepareCallable(self, callable, unique, *args, **kwargs):
        callableModule = callable.__module__
        callableBasePath = callableModule.replace('.', os.sep)
        if hasattr(sys.modules[callableModule], '__file__'):
            callableRootPath = sys.modules[callableModule].__file__.split(callableBasePath)[0]
        else:
            callableRootPath = None

        excludePackages = kwargs.pop('excludePackages', None)
        takeSitePackages = kwargs.pop('takeSitePackages', False)
        joinPythonNamespaces = kwargs.pop('joinPythonNamespaces', True)
        invocation.installArgs(self._host, unique, args, kwargs)
        code = invocation.callableCode(callable)
        cacheKey = self._cacheKey(callable,
                                  takeSitePackages=takeSitePackages,
                                  excludePackages=takeSitePackages,
                                  joinPythonNamespaces=joinPythonNamespaces,
                                  callableRootPath=callableRootPath)
        return functools.partial(_seedcache.makeSeed ,
                                 cacheKey,
                                 code,
                                 takeSitePackages=takeSitePackages,
                                 excludePackages=excludePackages,
                                 joinPythonNamespaces=joinPythonNamespaces,
                                 callableRootPath=callableRootPath)

    def _cacheKey(self, callable, **packArgs):
        args = ';'.join(["%s=%s" % (key, value) for key, value in packArgs.iteritems()])
        callableFilePath = inspect.getfile(callable)
        return callableFilePath + ":" + callable.__name__ + ":" + args

    def _unique(self):
        return "%09d" % random.randint(0, 1000 * 1000 * 1000)


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


plugins.register('seed', Seed)
