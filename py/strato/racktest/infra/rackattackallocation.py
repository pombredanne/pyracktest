from rackattack import clientfactory
from rackattack import api
from strato.racktest.infra import config
import logging
from strato.racktest.infra import concurrently
from strato.racktest.infra import suite
from strato.racktest.infra import rootfslabel
import tempfile
import os
import shutil
import time
from strato.racktest.infra import logbeamfromlocalhost


class RackAttackAllocation:
    _NO_PROGRESS_TIMEOUT = 2 * 60

    def __init__(self, hosts):
        self._hosts = hosts
        self._overallPercent = 0
        self._client = clientfactory.factory()
        self._allocation = self._client.allocate(
            requirements=self._rackattackRequirements(), allocationInfo=self._rackattackAllocationInfo())
        self._allocation.registerProgressCallback(self._progress)
#       self._allocation.setForceReleaseCallback()
        try:
            self._waitForAllocation()
        except:
            logging.exception("Allocation failed, attempting post mortem")
            self._postMortemAllocation()
            raise
        self._nodes = self._allocation.nodes()
        assert suite.runOnEveryHost is None
        suite.runOnEveryHost = self.runOnEveryHost

    def nodes(self):
        return self._nodes

    def free(self):
        assert suite.runOnEveryHost == self.runOnEveryHost
        suite.runOnEveryHost = None
        self._allocation.free()

    def _rackattackRequirements(self):
        result = {}
        for name, requirements in self._hosts.iteritems():
            pool = None
            if "pool" in requirements:
                pool = requirements["pool"]
            rootfs = rootfslabel.RootfsLabel(requirements['rootfs'])
            hardwareConstraints = dict(requirements)
            del hardwareConstraints['rootfs']
            result[name] = api.Requirement(
                imageLabel=rootfs.label(), imageHint=rootfs.imageHint(),
                hardwareConstraints=hardwareConstraints, pool=pool)
        return result

    def _rackattackAllocationInfo(self):
        nice = 0
        nice = max(nice, float(os.environ.get('RACKTEST_MINIMUM_NICE_FOR_RACKATTACK', 0)))
        return api.AllocationInfo(user=config.USER, purpose="racktest", nice=nice)

    def runOnEveryHost(self, callback, description):
        concurrently.run([
            dict(callback=callback, args=(name,))
            for name in self._nodes])

    def releaseHost(self, name):
        if name not in self._nodes:
            logging.error("Cannot release node '%(name)s' since it's not allocated", dict(name=name))
            raise ValueError(name)
        self._allocation.releaseHost(name)
        del self._nodes[name]

    def _postMortemAllocation(self):
        try:
            filename, contents = self._allocation.fetchPostMortemPack()
        except:
            logging.exception("Unable to get post mortem pack from rackattack provider")
            return
        tempDir = tempfile.mkdtemp()
        try:
            fullPath = os.path.join(tempDir, filename)
            with open(fullPath, 'wb') as f:
                f.write(contents)
            logbeamfromlocalhost.beam([fullPath])
        finally:
            shutil.rmtree(tempDir, ignore_errors=True)
        logging.info("Beamed post mortem pack into %(filename)s", dict(filename=filename))

    def _progress(self, overallPercent, event):
        self._overallPercent = overallPercent

    def _waitForAllocation(self):
        INTERVAL = 5
        lastOverallPercent = 0
        lastOverallPercentChange = time.time()
        while self._allocation.dead() is None:
            try:
                self._allocation.wait(timeout=INTERVAL)
                return
            except:
                if self._overallPercent != lastOverallPercent:
                    lastOverallPercent = self._overallPercent
                    lastOverallPercentChange = time.time()
                    logging.progress("Allocation %(percent)s%% complete", dict(percent=lastOverallPercent))
                if time.time() > lastOverallPercentChange + self._NO_PROGRESS_TIMEOUT:
                    raise Exception("Allocation progress hanged at %(percent)s%% for %(seconds)s seconds",
                                    dict(percent=lastOverallPercent, seconds=self._NO_PROGRESS_TIMEOUT))
        raise Exception(self._allocation.dead())
