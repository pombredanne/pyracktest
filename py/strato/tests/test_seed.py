import unittest
import subprocess
import shutil
import json
from strato.racktest.infra.seed import seedcreator
from strato.racktest.infra.seed import seedcache
from strato.racktest.infra.seed import memorycache
from strato.racktest.infra.seed import filecache
from example_seeds import addition
import os
import tempfile
import cPickle
import mock


class Test(unittest.TestCase):

    def _generateSeed1(self):
        seedCallable = addition.addition
        code = ("import %(module)s\n"
                "import cPickle\n"
                "import sys\n"
                "result = %(module)s.%(callable)s(1,2)\n"
                "print result") % dict(module=seedCallable.__module__,
                                       callable=seedCallable.__name__)
        return code

    def test_seedCreator(self):
        code = self._generateSeed1()
        creator = seedcreator.SeedCreator(code, generateDependencies=True)
        seed = creator.create()
        deps = seed['deps']
        self.assertEquals(len(deps), 3)
        depsFileNames = [os.path.basename(dep) for dep in deps.keys()]
        self.assertListEqual(depsFileNames, ['additiondependency.py', 'addition.py', '__init__.py'])
        codeDir = tempfile.mkdtemp(suffix="_runDir")
        try:
            codeFile = os.path.join(codeDir, "run.egg")
            with open(codeFile, 'w') as f:
                f.write(seed['code'])
            output = subprocess.check_output(
                ['/bin/sh', '-c', 'PYTHONPATH=%s python -m seedentrypoint; exit 0' % codeFile],
                close_fds=True)
            self.assertEquals('3', output.strip())
        finally:
            shutil.rmtree(codeDir, ignore_errors=True)

    def test_seedCacheAddToCacheSingleProccess(self):
        engine = mock.MagicMock()
        engine.lock = mock.MagicMock()
        cache = seedcache.SeedCache(engine)
        code = self._generateSeed1()
        engine.get.side_effect = [None, code]
        code = cache.make('key1', code, takeSitePackages=True)
        self.assertNotEqual(None, code)
        self.assertEquals(1, engine.install.call_count)
        code = cache.make('key1', code, takeSitePackages=True)
        self.assertEquals(1, engine.install.call_count)


if __name__ == '__main__':
    unittest.main()
