import unittest
import shutil
from strato.racktest.infra.seed import filecache
import os
import tempfile
from strato.racktest.infra.seed import seedcache


class Test(unittest.TestCase):

    def test_fileCacheAccess(self):
        targetDir = tempfile.mkdtemp(suffix="_testdir")
        depFile = tempfile.NamedTemporaryFile()
        try:
            tested = filecache.FileCache(targetDir)
            key = seedcache.SeedID('key1')
            self.assertEqual(None, tested.get(key))
            seedEntry = {'code': 'codecode', 'deps': {depFile.name: os.path.getmtime(depFile.name)}}
            tested.install(key, seedEntry)
            self.assertEqual('codecode', tested.get(key))
            newTime = os.path.getmtime(depFile.name) + 1
            os.utime(depFile.name, (os.path.getmtime(depFile.name), newTime))
            self.assertEqual(None, tested.get(key))
            # Reinstall file
            seedEntry = {'code': 'codecode', 'deps': {depFile.name: os.path.getmtime(depFile.name)}}
            tested.install(key, seedEntry)
            self.assertEqual('codecode', tested.get(key))
        finally:
            shutil.rmtree(targetDir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
