from strato.racktest.hostundertest import plugins
import random
import cPickle
import tempfile
import shutil
import subprocess
import os
import logging
import time


class Seed:
    def __init__(self, host):
        self._host = host

    def runCode(self, code, takeSitePackages=False, outputTimeout=None):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        self._install(code, unique, takeSitePackages)
        output = self._run(unique, outputTimeout=outputTimeout)
        result = self._downloadResult(unique)
        return result, output

    def _initCallable(self, callable, *args, **kwargs):
        takeSitePackages = kwargs.pop('takeSitePackages', False)
        excludePackages = kwargs.pop('excludePackages', None)
        unique = self._unique()
        self._installCallable(unique, callable, args, kwargs, takeSitePackages, excludePackages)
        return unique

    def runCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        outputTimeout = kwargs.pop('outputTimeout', None)
        unique = self._initCallable(callable, *args, **kwargs)
        output = self._run(unique, outputTimeout=outputTimeout)
        result = self._downloadResult(unique)
        return result, output

    def forkCode(self, code, takeSitePackages=False):
        """
        make sure to assign to 'result' in order for the result to come back!
        for example: "runCode('import yourmodule\nresult = yourmodule.func()\n')"
        """
        unique = self._unique()
        self._install(code, unique, takeSitePackages)
        return _Forked(self._host, unique)

    def forkCallable(self, callable, *args, **kwargs):
        "Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg"
        unique = self._initCallable(callable, *args, **kwargs)
        return _Forked(self._host, unique)

    def offlineCallable(self, callable, *args, **kwargs):
        """
        Currently, only works on global functions. Also accepts 'takeSitePackages' kwarg
        This is like forkCallable, but keeps all ssh connections to host down after running the
        code, and in between actions. For every action, ssh is reconnected, and closed after
        """
        self._host.connect()
        unique = self._initCallable(callable, *args, **kwargs)
        self._host.close()
        return _OfflineForked(self._host, unique)

    def _installCallable(self, unique, callable, args, kwargs, takeSitePackages, excludePackages):
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
        self._install(code, unique, takeSitePackages)

    def _install(self, code, unique, takeSitePackages):
        outputPickle = "/tmp/result%s.pickle" % unique
        packingCode = "result = None\n" + code + "\n" + (
            "import cPickle\n"
            "with open('%(outputPickle)s', 'wb') as f:\n"
            " cPickle.dump(result, f, cPickle.HIGHEST_PROTOCOL)\n") % dict(outputPickle=outputPickle)
        packed = self._pack(packingCode, takeSitePackages)
        eggFilename = "/tmp/seed%s.egg" % unique
        self._host.ssh.ftp.putContents(eggFilename, packed)

    def _unique(self):
        return "%09d" % random.randint(0, 1000 * 1000 * 1000)

    def _pack(self, code, takeSitePackages):
        codeDir = tempfile.mkdtemp(suffix="_eggDir")
        try:
            codeFile = os.path.join(codeDir, "seedentrypoint.py")
            with open(codeFile, "w") as f:
                f.write(code)
            eggFile = tempfile.NamedTemporaryFile(suffix=".egg")
            try:
                subprocess.check_output([
                    "python", "-m", "upseto.packegg", "--entryPoint", codeFile,
                    "--output", eggFile.name, "--joinPythonNamespaces"] +
                    (['--takeSitePackages'] if takeSitePackages else []),
                    stderr=subprocess.STDOUT, close_fds=True, env=dict(
                        os.environ, PYTHONPATH=codeDir + ":" + os.environ['PYTHONPATH']))
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


class _Forked(object):
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


class _OfflineForked(_Forked):
    def __init__(self, host, unique):
        host.connect()
        super(_OfflineForked, self).__init__(host, unique)
        self._host.close()

    def poll(self):
        self._host.connect()
        res = super(_OfflineForked, self).poll()
        self._host.close()
        return res

    def result(self):
        self._host.connect()
        res = super(_OfflineForked, self).result()
        self._host.close()
        return res

    def output(self):
        self._host.connect()
        res = super(_OfflineForked, self).output()
        self._host.close()
        return res

    def kill(self):
        self._host.connect()
        super(_OfflineForked, self).kill()
        self._host.close()


plugins.register('seed', Seed)
