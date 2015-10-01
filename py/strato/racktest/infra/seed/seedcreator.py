import tempfile
import os
import subprocess
import logging
import shutil


class SeedCreator(object):
    ENTRYPOINT_NAME = 'seedentrypoint.py'

    def __init__(self, code, generateDependencies=False, takeSitePackages=False, excludePackages=None, joinPythonNamespaces=True):
        self._takeSitePackages = takeSitePackages
        self._excludePackages = excludePackages
        self._generateDependencies = generateDependencies
        self._code = code
        self._joinPythonNamespaces = joinPythonNamespaces

    def _shouldManifestDependency(self, depedency):
        return os.path.basename(depedency) != self.ENTRYPOINT_NAME

    def _parseDepsFile(self, depsFile):
        # First line is the egg name
        depsList = depsFile.readlines()[1:]
        depsManifest = {}
        for dep in depsList:
            depPath = dep.strip(' \t\n\r\\')
            if depPath == '':
                continue
            if not self._shouldManifestDependency(depPath):
                continue
            depAbsPath = os.path.abspath(depPath)
            mTime = os.path.getmtime(depAbsPath)
            depsManifest[depAbsPath] = mTime
        return depsManifest

    def _generateManifest(self, eggFile, depsFile):
        eggContents = eggFile.read()
        depsContents = self._parseDepsFile(depsFile) if depsFile is not None else None
        return {'code': eggContents, 'deps': depsContents}

    def __call__(self, *args):
        codeDir = tempfile.mkdtemp(suffix="_eggDir")
        try:
            codeFile = os.path.join(codeDir, self.ENTRYPOINT_NAME)
            with open(codeFile, "w") as f:
                f.write(self._code)
            eggFile = tempfile.NamedTemporaryFile(suffix=".egg")
            depsFile = tempfile.NamedTemporaryFile(suffix=".deps") if self._generateDependencies else None
            excludePackages = (['--excludeModule'] + [package for package in self._excludePackages]) \
                if self._excludePackages is not None else []
            depedenciesGeneratorPart = (["--createDeps", depsFile.name])\
                if self._generateDependencies else []
            try:
                cmd = ["python", "-m", "upseto.packegg", "--entryPoint", codeFile,
                       "--output", eggFile.name] + \
                      (["--joinPythonNamespaces"] if joinPythonNamespaces else []) + \
                      (['--takeSitePackages'] if takeSitePackages else []) + \
                      (excludePackages) + (depedenciesGeneratorPart)
                env = dict(os.environ, PYTHONPATH=codeDir +
                           (":%s" % callableRootPath if callableRootPath is not None else "") +
                           (":" + os.environ['PYTHONPATH']))
                subprocess.check_output(cmd, stderr=subprocess.STDOUT, close_fds=True, env=env)
                manifest = self._generateManifest(eggFile, depsFile)
                return manifest
            except subprocess.CalledProcessError as e:
                logging.exception("Unable to pack egg, output: %(output)s" % dict(output=e.output))
                raise Exception("Unable to pack egg, output: %(output)s" % dict(output=e.output))
            finally:
                eggFile.close()
                if depsFile is not None:
                    depsFile.close()
        finally:
            shutil.rmtree(codeDir, ignore_errors=True)
