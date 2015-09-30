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
        self._install(code, unique, takeSitePackages, excludePackages, joinPythonNamespaces)
        output = self._run(unique, outputTimeout=outputTimeout)
        result = self._downloadResult(unique)
        return result, output

    def runCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        takeSitePackages = False
        if 'takeSitePackages' in kwargs:
            takeSitePackages = True
            kwargs = dict(kwargs)
            del kwargs['takeSitePackages']
        excludePackages = kwargs.pop('excludePackages', None)
        joinPythonNamespaces = kwargs.pop('joinPythonNamespaces', True)
        outputTimeout = None
        if 'outputTimeout' in kwargs:
            outputTimeout = kwargs['outputTimeout']
            del kwargs['outputTimeout']
        unique = self._unique()
        self._installCallable(unique,
                              callable,
                              args,
                              kwargs,
                              takeSitePackages,
                              excludePackages,
                              joinPythonNamespaces)
        output = self._run(unique, outputTimeout=outputTimeout)
        result = self._downloadResult(unique)
        return result, output

    def forkCode(self, code, takeSitePackages=False, excludePackages=None, joinPythonNamespaces=True):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        self._install(code, unique, takeSitePackages, excludePackages, joinPythonNamespaces)
        return _Forked(self._host, unique)

    def forkCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        takeSitePackages = False
        if 'takeSitePackages' in kwargs:
            takeSitePackages = True
            kwargs = dict(kwargs)
            del kwargs['takeSitePackages']
        excludePackages = kwargs.pop('excludePackages', None)
        joinPythonNamespaces = kwargs.pop('joinPythonNamespaces', True)
        unique = self._unique()
        self._installCallable(unique,
                              callable,
                              args,
                              kwargs,
                              takeSitePackages,
                              excludePackages,
                              joinPythonNamespaces)
        return _Forked(self._host, unique)

    def _installCallable(self, unique, callable, args, kwargs, takeSitePackages,
                         excludePackages, joinPythonNamespaces):
        callableModule = callable.__module__
        callableBasePath = callableModule.replace('.', '/')
        callableRootPath = sys.modules[callable.__module__].__file__.split(callableBasePath)[0]
        argsPickle = "/tmp/args%s.pickle" % unique
        code = (
            "import %(module)s\n"
            "import cPickle\n"
            "with open('%(argsPickle)s', 'rb') as f:\n"
            " args, kwargs = cPickle.load(f)\n"
            "result = %(module)s.%(callable)s(*args, **kwargs)\n") % dict(
                module=callable.__module__,
                argsPickle=argsPickle,
                callable=callable.__name__)
        argsContents = cPickle.dumps((args, kwargs), cPickle.HIGHEST_PROTOCOL)
        self._host.ssh.ftp.putContents(argsPickle, argsContents)
        self._install(code,
                      unique,
                      takeSitePackages,
                      excludePackages,
                      joinPythonNamespaces,
                      callableRootPath)

    def _install(self, code, unique, takeSitePackages, excludePackages,
                 joinPythonNamespaces, callableRootPath=None):
        outputPickle = "/tmp/result%s.pickle" % unique
        packingCode = "result = None\n" + code + "\n" + (
            "import cPickle\n"
            "with open('%(outputPickle)s', 'wb') as f:\n"
            " cPickle.dump(result, f, cPickle.HIGHEST_PROTOCOL)\n") % dict(outputPickle=outputPickle)
        packed = self._pack(packingCode,
                            takeSitePackages,
                            excludePackages,
                            joinPythonNamespaces,
                            callableRootPath)
        eggFilename = "/tmp/seed%s.egg" % unique
        self._host.ssh.ftp.putContents(eggFilename, packed)

    def _unique(self):
        return "%09d" % random.randint(0, 1000 * 1000 * 1000)

    def _pack(self, code, takeSitePackages, excludePackages, joinPythonNamespaces, callableRootPath):
        codeDir = tempfile.mkdtemp(suffix="_eggDir")
        try:
            codeFile = os.path.join(codeDir, "seedentrypoint.py")
            with open(codeFile, "w") as f:
                f.write(code)
            eggFile = tempfile.NamedTemporaryFile(suffix=".egg")
            excludePackages = (['--excludeModule'] + [package for package in excludePackages]) \
                if excludePackages is not None else []
            try:
                subprocess.check_output(["python", "-m", "upseto.packegg", "--entryPoint", codeFile,
                                         "--output", eggFile.name] +
                                        (["--joinPythonNamespaces"] if joinPythonNamespaces else []) +
                                        (['--takeSitePackages'] if takeSitePackages else []) +
                                        (excludePackages),
                                        stderr=subprocess.STDOUT,
                                        close_fds=True,
                                        env=dict(
                                            os.environ, PYTHONPATH=codeDir +
                                            (":%s" % callableRootPath if callableRootPath else "") +
                                            (":" + os.environ['PYTHONPATH'])))
                return eggFile.read()
            except subprocess.CalledProcessError as e:
                logging.exception("Unable to pack egg, output: %(output)s" % dict(output=e.output))
                raise Exception("Unable to pack egg, output: %(output)s" % dict(output=e.output))
            finally:
                eggFile.close()
        finally:
            shutil.rmtree(codeDir, ignore_errors=True)

    def _run(self, unique, outputTimeout):
        kwargs = {}
        if outputTimeout is not None:
            kwargs['outputTimeout'] = outputTimeout
        return self._host.ssh.run.script(
            "PYTHONPATH=/tmp/seed%s.egg python -m seedentrypoint" % unique, **kwargs)

    def _downloadResult(self, unique):
        return cPickle.loads(self._host.ssh.ftp.getContents("/tmp/result%s.pickle" % unique))


class _Forked:
    def __init__(self, host, unique):
        self._host = host
        self._unique = unique
        host.ssh.run.backgroundScript(
            "echo $$ > /tmp/pid%(unique)s.txt\n"
            "PYTHONPATH=/tmp/seed%(unique)s.egg "
            "exec python -m seedentrypoint >& /tmp/output%(unique)s.txt" % dict(unique=unique)
        )
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
