from upseto import gitwrapper
from upseto import run
import subprocess


class RootfsLabel:
    def __init__(self, rootfs, product="rootfs"):
        self._rootfs = rootfs
        self._product = product
        if rootfs == "THIS":
            self._label = run.run([
                "solvent", "printlabel", "--thisProject", "--product=%s" % (self._product,)]).strip()
            wrapper = gitwrapper.GitWrapper(".")
            self._hint = wrapper.originURLBasename()
        elif self._labelExists(self._rootfs):
            self._label = self._rootfs
            self._hint = self._rootfs
        elif "__" in self._rootfs:
            repository, product = self._rootfs.split("__")
            self._label = run.run([
                "solvent", "printlabel", "--repositoryBasename", repository, "--product", product]).strip()
            self._hint = repository
        else:
            self._label = run.run([
                "solvent", "printlabel", "--repositoryBasename", rootfs,
                "--product=%s" % (self._product,)]).strip()
            self._hint = rootfs

    def label(self):
        return self._label

    def imageHint(self):
        return self._hint

    def _labelExists(self, label):
        with open("/dev/null", "w") as out:
            return subprocess.call(["solvent", "labelexists", "--label", label], stdout=out, stderr=out) == 0
