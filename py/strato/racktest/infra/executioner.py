import logging
from strato.racktest.infra import suite
from strato.racktest.infra import rackattackallocation
from strato.racktest import hostundertest
import strato.racktest.hostundertest.host
from strato.whiteboxtest.infra import timeoutthread
from strato.common.log import discardinglogger
from detachednode import DetachedNode
import os
import signal
import time
import yaml
import sys


class Executioner:
    ABORT_TEST_TIMEOUT_DEFAULT = 10 * 60
    ON_TIMEOUT_CALLBACK_TIMEOUT_DEFAULT = 5 * 60
    DISCARD_LOGGING_OF = (
        'paramiko',
        'pika',
        'selenium.webdriver.remote.remote_connection',
        'requests.packages.urllib3.connectionpool')

    CREATE_NEW_ALLOCATION = None
    EXISTING_ALLOCATION_FILENAME = 'allocation.ID'
    RUN_ON_DETACHED = os.getenv('RUN_ON_DETACHED', 'false').lower() == 'true'

    def __init__(self, klass):
        self._cleanUpMethods = []
        if not hasattr(klass, 'addCleanup'):
            klass.addCleanup = self._addCleanup
        self._test = klass()
        self._testTimeout = getattr(self._test, 'ABORT_TEST_TIMEOUT', self.ABORT_TEST_TIMEOUT_DEFAULT)
        self._onTimeoutCallbackTimeout = getattr(
            self._test, 'ON_TIMEOUT_CALLBACK_TIMEOUT', self.ON_TIMEOUT_CALLBACK_TIMEOUT_DEFAULT)
        self._doNotReleaseAllocation = os.getenv('KEEP_ALLOCATION', 'false').lower() in ['true']
        self._existingAllocationID = self._setupExistingAllocation()

    def host(self, name):
        return self._hosts[name]

    def hosts(self):
        return self._hosts

    def executeTestScenario(self):
        discardinglogger.discardLogsOf(self.DISCARD_LOGGING_OF)
        self._hosts = dict()
        suite.findHost = self.host
        suite.hosts = self.hosts
        if not hasattr(self._test, 'host'):
            self._test.host = self.host
        if not hasattr(self._test, 'hosts'):
            self._test.hosts = self.hosts
        if not hasattr(self._test, 'releaseHost'):
            self._test.releaseHost = self._releaseHost
        if not self.RUN_ON_DETACHED:
            logging.progress("Allocating Nodes...")
            self._allocation = rackattackallocation.RackAttackAllocation(
                self._test.HOSTS, self._existingAllocationID)
            timeoutthread.TimeoutThread(self._testTimeout, self._testTimedOut)
            logging.info("Test timer armed. Timeout in %(seconds)d seconds", dict(seconds=self._testTimeout))
            logging.progress("Done allocating nodes.")
        else:
            logging.progress("Attempting connection to detached nodes...")
        try:
            self._setUp()
            try:
                self._run()
            finally:
                self._tearDown()
        finally:
            self._cleanUp()
            wasAllocationFreedSinceAllHostsWereReleased = not bool(self._hosts)
            if not (wasAllocationFreedSinceAllHostsWereReleased or self._doNotReleaseAllocation):
                try:
                    self._allocation.free()
                except:
                    logging.exception("Unable to free allocation")
            else:
                logging.info('Not freeing allocation')

    def _cleanUp(self):
        if not self._cleanUpMethods:
            return
        logging.info("Performing cleanup...")
        while self._cleanUpMethods:
            callback, args, kwargs = self._cleanUpMethods.pop()
            logging.info("Invoking cleanup method '%(callback)s with (%(args)s, %(kwargs)s...",
                         dict(callback=callback, args=args, kwargs=kwargs))
            try:
                callback(*args, **kwargs)
            except:
                logging.exception("An error has occurred during the cleanup method '%(callback)s'. Skipping",
                                  dict(callback=callback))
        logging.info("Cleanup done.")

    def _addCleanup(self, callback, *args, **kwargs):
        self._cleanUpMethods.append((callback, args, kwargs))

    def _releaseHost(self, name):
        if name not in self._hosts:
            logging.error("Cannot release host %(name)s since it's not allocated", dict(name=name))
            raise ValueError(name)
        self._allocation.releaseHost(name)
        del self._hosts[name]

    def _testTimedOut(self):
        logging.error(
            "Timeout: test is running for more than %(seconds)ds, calling 'onTimeout' and arming "
            " additional timer. "
            "You might need to increase the scenario ABORT_TEST_TIMEOUT", dict(seconds=self._testTimeout))
        timeoutthread.TimeoutThread(self._onTimeoutCallbackTimeout, self._killSelf)
        timeoutthread.TimeoutThread(self._onTimeoutCallbackTimeout + 5, self._killSelfHard)
        try:
            getattr(self._test, 'onTimeout', lambda: None)()
        except:
            logging.exception("Failed 'onTimeout' callback for test in '%(filename)s', commiting suicide.",
                              dict(filename=self._filename()))
            suite.outputExceptionStackTrace()
        else:
            logging.info("'onTimeout' completed, will commit suicide now")
        self._cleanUp()
        self._killSelf()
        time.sleep(2)
        self._killSelfHard()

    def _sendMeASignal(self, signalNr):
        signalNrToName = dict([(number, name) for (name, number) in signal.__dict__.items()
                               if 'SIG' in name])
        signalName = signalNrToName[signalNr]
        myPID = os.getpid()
        logging.info("Sending %(signalName)s to self (PID: %(myPID)s)",
                     dict(signalName=signalName, myPID=myPID))
        os.kill(myPID, signalNr)

    def _killSelf(self):
        self._sendMeASignal(signal.SIGTERM)

    def _killSelfHard(self):
        self._sendMeASignal(signal.SIGKILL)

    def _filename(self):
        filename = sys.modules[self._test.__class__.__module__].__file__
        if filename.endswith(".pyc"):
            filename = filename[: -1]
        return filename

    def _setUpHost(self, name):
        node = self._allocation.nodes()[name]
        host = hostundertest.host.Host(node, name)
        credentials = host.node.rootSSHCredentials()
        address = "%(hostname)s:%(port)s" % credentials
        logging.info("Connecting to host '%(nodeName)s' (%(server)s, address: %(address)s)...",
                     dict(nodeName=name, server=node.id(), address=address))
        logging.debug("Full credentials of host: %(credentials)s", dict(credentials=credentials))
        try:
            host.ssh.waitForTCPServer(timeout=2*60)
            host.ssh.connect()
        except:
            logging.error(
                "Rootfs did not wake up after inauguration. Saving serial file in postmortem dir "
                "host %(id)s name %(name)s", dict(id=host.node.id(), name=name))
            host.logbeam.postMortemSerial()
            raise
        logging.info("Connected to %(node)s.", dict(node=name))
        self._hosts[name] = host
        getattr(self._test, 'setUpHost', lambda x: x)(name)

    def _setUpDetachedHosts(self):
        with open("nodes.conf", "r") as confFile:
            detachedNodes = yaml.load(confFile)
        nodeList = detachedNodes.keys()
        for name in nodeList:
            node = DetachedNode(username=detachedNodes[name]['credentials']['username'],
                                password=detachedNodes[name]['credentials']['password'],
                                hostname=detachedNodes[name]['credentials']['hostname'],
                                port=detachedNodes[name]['credentials']['port'],
                                ipAddress=detachedNodes[name]['ipAddress'],
                                nodeId=detachedNodes[name]['nodeId'])
            host = hostundertest.host.Host(node, name)
            self._hosts[name] = host
            try:
                host.ssh.waitForTCPServer()
                host.ssh.connect()
            except:
                logging.error("Could not connect to detached servers")
                raise

    def _setUp(self):
        logging.info("Setting up test in '%(filename)s'", dict(filename=self._filename()))
        if self.RUN_ON_DETACHED:
            self._setUpDetachedHosts()
        else:
            self._allocation.runOnEveryHost(self._setUpHost, "Setting up host")
        try:
            getattr(self._test, 'setUp', lambda: None)()
        except:
            logging.exception(
                "Failed setting up test in '%(filename)s'", dict(filename=self._filename()))
            suite.outputExceptionStackTrace()
            raise

    def _run(self):
        logging.progress("Running test in '%(filename)s'", dict(filename=self._filename()))
        try:
            self._test.run()
            suite.anamnesis['testSucceeded'] = True
            logging.success(
                "Test completed successfully, in '%(filename)s', with %(asserts)d successfull asserts",
                dict(filename=self._filename(), asserts=suite.successfulTSAssertCount()))
            print ".:1: Test passed"
        except:
            suite.anamnesis['testFailed'] = True
            logging.exception("Test failed, in '%(filename)s'", dict(filename=self._filename()))
            suite.outputExceptionStackTrace()
            raise

    def _tearDown(self):
        areThereHostsToTearDown = bool(self._hosts)
        if not areThereHostsToTearDown:
            return
        logging.info("Tearing down test in '%(filename)s'", dict(filename=self._filename()))
        try:
            getattr(self._test, 'tearDown', lambda: None)()
        except:
            logging.exception(
                "Failed tearing down test in '%(filename)s'", dict(filename=self._filename()))
            suite.outputExceptionStackTrace()
            raise
        tearDownHost = getattr(self._test, 'tearDownHost', lambda x: x)
        self._allocation.runOnEveryHost(tearDownHost, "Tearing down host")

    def _setupExistingAllocation(self):
        existingAllocationID = os.getenv('ALLOCATION_ID', None)
        if existingAllocationID == self.CREATE_NEW_ALLOCATION:
            return self.CREATE_NEW_ALLOCATION
        elif existingAllocationID == self.EXISTING_ALLOCATION_FILENAME:
            return self._readAllocationFromFile(self.EXISTING_ALLOCATION_FILENAME)
        else:
            return int(existingAllocationID)

    def _readAllocationFromFile(self, filename):
        allocationID = None
        f = open(filename, 'r')
        try:
            allocationID = int(f.readlines()[0])
        except Exception as e:
            logging.error('failed to fetch allocationID from %(_filename)s. Exception %(_err)s', dict(
                _filename=filename, _err=e.message))
            raise e
        finally:
            f.close()
        return allocationID
