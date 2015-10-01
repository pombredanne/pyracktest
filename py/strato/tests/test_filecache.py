import unittest
import shutil
from strato.racktest.infra.seed import filecache
import os
import tempfile


class Test(unittest.TestCase):

    def test_fileCacheAccess(self):
        targetDir = tempfile.mkdtemp(suffix="_testdir")
        depFile = tempfile.NamedTemporaryFile()
        try:
            tested = filecache.FileCache(targetDir)
            self.assertEqual(None, tested.get('key1'))
            seedEntry = {'code': 'codecode', 'deps': {depFile.name: os.path.getmtime(depFile.name)}}
            tested.install('key1', seedEntry)
            self.assertEqual('codecode', tested.get('key1'))
            newTime = os.path.getmtime(depFile.name) + 1
            os.utime(depFile.name, (os.path.getmtime(depFile.name), newTime))
            self.assertEqual(None, tested.get('key1'))
            # Reinstall file
            seedEntry = {'code': 'codecode', 'deps': {depFile.name: os.path.getmtime(depFile.name)}}
            tested.install('key1', seedEntry)
            self.assertEqual('codecode', tested.get('key1'))
        finally:
            shutil.rmtree(targetDir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
