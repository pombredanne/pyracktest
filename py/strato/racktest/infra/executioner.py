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
import json


class Executioner:
    ABORT_TEST_TIMEOUT_DEFAULT = 10 * 60
    ON_TIMEOUT_CALLBACK_TIMEOUT_DEFAULT = 5 * 60
    DISCARD_LOGGING_OF = (
        'paramiko',
        'pika',
        'selenium.webdriver.remote.remote_connection',
        'requests.packages.urllib3.connectionpool')

    DEFAULT_RACKATTACK = 'defaultRackattack'
    MULTICLUSTER_ALLOCATION = 'multicluster'
    DEFAULT_CLUSTER_NAME = 'cluster1'

    def __init__(self, klass, testRunAttributes=None):
        self._cleanUpMethods = []
        if not hasattr(klass, 'addCleanup'):
            klass.addCleanup = self._addCleanup
        self._setTestAttributes(klass, testRunAttributes)
        self._test = klass()
        self._testTimeout = getattr(self._test, 'ABORT_TEST_TIMEOUT', self.ABORT_TEST_TIMEOUT_DEFAULT)
        self._onTimeoutCallbackTimeout = getattr(
            self._test, 'ON_TIMEOUT_CALLBACK_TIMEOUT', self.ON_TIMEOUT_CALLBACK_TIMEOUT_DEFAULT)
        self._hostToRackattackMap = self._createHostToRackattackMap(self._test.HOSTS)
        self._allocations = None
        self._runTestOnPreAllocated = hasattr(self._test, 'RUN_ON_PREALLOCATED') and self._test.RUN_ON_PREALLOCATED

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
        timeoutthread.TimeoutThread(self._testTimeout, self._testTimedOut)
        logging.info("Test timer armed. Timeout in %(seconds)d seconds", dict(seconds=self._testTimeout))
        if not self._runTestOnPreAllocated:
            logging.progress("Allocating hosts...")
            self._allocations = self._createAllocations()
            logging.progress("Done allocating hosts.")

            for allocation in self._allocations.values():
                allocation.runOnEveryHost(self._setUpHost, "Setting up host")
            if not hasattr(self._test, '_clusters'):
                self._test._clusters = self._getClusters()
        else:
            logging.progress("Attempting connection to pre-allocated nodes...")
            self._test._clusters = self._setUpDetachedClusters()

        try:
            self._setUp()
            self._run()
        finally:
            self._tearDown()
            if not self._runTestOnPreAllocated:
                self._cleanUp()
                for allocation in self._allocations.values():
                    wasAllocationFreedSinceAllHostsWereReleased = not bool(allocation.nodes())
                    if not wasAllocationFreedSinceAllHostsWereReleased:
                        try:
                            self._tryFreeAllocation(allocation)
                        except:
                            logging.exception("Unable to free allocation, hosts: "
                                              "%(_nodes)s may still be allocated",
                                              dict(_nodes=','.join(
                                                  [node.id() for node in allocation.nodes().values()])))
                            raise Exception('Unable to free allocation')
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
        hostRackattack = self._hostToRackattackMap[name]
        if name not in self._hosts:
            logging.error("Cannot release host %(name)s since it's not allocated", dict(name=name))
            raise ValueError(name)
        self._allocations[hostRackattack].releaseHost(name)
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
        hostRackattack = self._hostToRackattackMap[name]
        node = self._allocations[hostRackattack].nodes()[name]
        host = hostundertest.host.Host(node, name)
        credentials = host.node.rootSSHCredentials()
        address = "%(hostname)s:%(port)s" % credentials
        logging.info("Connecting to host '%(name)s' (%(server)s, address: %(address)s)...",
                     dict(name=name, server=node.id(), address=address))
        logging.debug("Full credentials of host: %(credentials)s", dict(credentials=credentials))
        try:
            host.ssh.waitForTCPServer(timeout=2 * 60)
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

    def _setUpDetachedClusters(self):
        with open(self._test.CLUSTERS_CONF_FILE, "r") as confFile:
            detachedClusters = yaml.load(confFile)
        clusters = {}
        for clusterName in detachedClusters.keys():
            clusters[clusterName] = {}
            for nodeName, nodeInfo in detachedClusters[clusterName]['nodes'].iteritems():
                node = DetachedNode(username=nodeInfo['credentials']['username'],
                                    password=nodeInfo['credentials']['password'],
                                    hostname=nodeInfo['credentials']['hostname'],
                                    port=nodeInfo['credentials']['port'],
                                    ipAddress=nodeInfo['ipAddress'],
                                    nodeId=nodeInfo['nodeId'],
                                    info=nodeInfo["networkInfo"]
                                    )
                host = hostundertest.host.Host(node, nodeName)
                self._hosts[nodeName] = host
                try:
                    host.ssh.waitForTCPServer()
                    host.ssh.connect()
                except:
                    logging.error("Could not connect to detached servers")
                    raise
                clusters[clusterName][nodeName] = host
        return clusters

    def _setUp(self):
        logging.info("Setting up test in '%(filename)s'", dict(filename=self._filename()))
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
        if self._runTestOnPreAllocated:
            return
        tearDownHost = getattr(self._test, 'tearDownHost', lambda x: x)
        for allocation in self._allocations.values():
            allocation.runOnEveryHost(tearDownHost, "Tearing down host")

    def _createAllocations(self):
        rackattackToHostMap = self._createRackattackToHostMap(self._test.HOSTS)
        allocations = dict()
        for rackattack, hostsFromRackattack in rackattackToHostMap.iteritems():
            logging.progress('Allocating %(_hosts)s from Rackattack %(_rackattack)s', dict(
                _hosts=hostsFromRackattack.keys(), _rackattack=rackattack))
            try:
                allocations[rackattack] = rackattackallocation.RackAttackAllocation(
                    hosts=hostsFromRackattack)
            except Exception:
                logging.error('failed to allocate from %(_rackattack)s, '
                              'freeing all allocations',
                              dict(_rackattack=rackattack))
                for allocation in allocations:
                    self._tryFreeAllocation(allocation)
                raise
            logging.progress(
                'Finished allocating hosts from Rackattack %(_rackattack)s', dict(_rackattack=rackattack))
        return allocations

    def _getClusters(self):
        clusters = dict()
        hostToClusterMap = self._createHostToClusterMap(self._test.HOSTS)
        for nodeName in self._hosts:
            host = self._hosts[nodeName]
            clusterName = hostToClusterMap[nodeName]
            clusterHosts = clusters.setdefault(clusterName, {})
            clusterHosts[nodeName] = host
        return clusters

    def _createHostToClusterMap(self, clustersDefinition):
        hostToClusterMap = dict()
        if clustersDefinition.get(self.MULTICLUSTER_ALLOCATION, False):
            for clusterName, clusterHosts in clustersDefinition.iteritems():
                if clusterName == self.MULTICLUSTER_ALLOCATION:
                    continue
                for name in clusterHosts:
                    hostToClusterMap[name] = clusterName
        else:
            [hostToClusterMap.setdefault(name, self.DEFAULT_CLUSTER_NAME)
             for name in clustersDefinition]
        return hostToClusterMap

    def _createRackattackToHostMap(self, clustersDefinition):
        rackattackToHostMap = dict()
        if clustersDefinition.get(self.MULTICLUSTER_ALLOCATION, False):
            for clusterName, clusterHosts in clustersDefinition.iteritems():
                if clusterName == self.MULTICLUSTER_ALLOCATION:
                    continue
                for name, parameters in clusterHosts.iteritems():
                    requiredRackattack = parameters.get('rackattack', self.DEFAULT_RACKATTACK)
                    rackattackHosts = rackattackToHostMap.setdefault(requiredRackattack, {})
                    rackattackHosts[name] = parameters
        else:
            for name, parameters in clustersDefinition.iteritems():
                requiredRackattack = parameters.get('rackattack', self.DEFAULT_RACKATTACK)
                rackattackHosts = rackattackToHostMap.setdefault(requiredRackattack, {})

                rackattackHosts[name] = parameters
        return rackattackToHostMap

    def _createHostToRackattackMap(self, clustersDefinition):
        hostToRackAttackMap = dict()
        if clustersDefinition.get(self.MULTICLUSTER_ALLOCATION, False):
            for clusterName, clusterHosts in clustersDefinition.iteritems():
                if clusterName == self.MULTICLUSTER_ALLOCATION:
                    continue
                for name, parameters in clusterHosts.iteritems():
                    requiredRackattack = parameters.get('rackattack', self.DEFAULT_RACKATTACK)
                    if name in hostToRackAttackMap:
                        logging.error('node %(_nodeName)s appears more than once', dict(_nodeName=name))
                        raise Exception('node names must be unique')
                    hostToRackAttackMap[name] = requiredRackattack
        else:
            for name, parameters in clustersDefinition.iteritems():
                requiredRackattack = parameters.get('rackattack', self.DEFAULT_RACKATTACK)
                hostToRackAttackMap[name] = requiredRackattack
        return hostToRackAttackMap

    def _tryFreeAllocation(self, allocation):
        try:
            allocation.free()
        except:
            logging.exception("Unable to free allocation, hosts: "
                              "%(_nodes)s may still be allocated",
                              dict(_nodes=','.join(
                                  [node.id() for node in allocation.nodes().values()])))

    def _setTestAttributes(self, klass, jsonWithAttrs):
        logging.info("Setting test attributes")
        try:
            if jsonWithAttrs and len(jsonWithAttrs) > 0:
                for key, value in json.loads(jsonWithAttrs).iteritems():
                    setattr(klass, key, value)
        except Exception as e:
            logging.exception(e)
