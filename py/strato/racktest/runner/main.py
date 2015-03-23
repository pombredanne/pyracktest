#!/usr/bin/python

from strato.racktest.infra import config
from strato.common.log import configurelogging
configurelogging.configureLogging('racktest.runner', forceDirectory=config.TEST_LOGS_DIR)
import logging
import argparse
import sys
import glob
import time
import json
import re
import os
import subprocess
from strato.racktest.infra import suite
from strato.racktest.infra import concurrently
from strato.racktest.infra import handlekill
from strato.racktest import runner
import atexit
import signal
import threading
import datetime

_defaultReport = os.path.join(config.TEST_LOGS_DIR, "racktestrunnerreport.json")
_defaultLiveReport = os.path.join(config.TEST_LOGS_DIR, "racktestrunnerlivereport.json")
_single = os.path.join(os.path.dirname(runner.__file__), "single.py")

parser = argparse.ArgumentParser(
    description="run Integration test scenarios. If no arguments given, run all rack scenarios")
parser.add_argument(
    "--interactOnAssert", help="go into interact mode on assert", action='store_true')
parser.add_argument("--regex", default="", help="run all scenarios matching the regular expression")
parser.add_argument('--listOnly', action='store_true', help='list scenarios and exit')
parser.add_argument('--liveReportFilename', default=_defaultLiveReport)
parser.add_argument("--reportFilename", default=_defaultReport)
parser.add_argument("--scenariosRoot", default="racktests")
parser.add_argument("--configurationFile", default="/etc/racktest.conf")
parser.add_argument("--parallel", type=int, default=0)
parser.add_argument("--repeat", type=int, default=0)
args = parser.parse_args()
if args.interactOnAssert:
    suite.enableInteractOnAssert()
config.load(args.configurationFile)


class Runner:
    def __init__(self, args):
        self._args = args
        self._liveReportLock = threading.Lock()
        self._pids = []
        atexit.register(self._killSubprocesses)
        if args.repeat == 0:
            self._instances = ['']
        else:
            self._instances = ['_try%d' % i for i in xrange(args.repeat)]
        self._scenarios = self._matchingScenarios()
        if len(self._scenarios) == 0:
            raise Exception("No scenarios files found")
        self._results = []
        os.environ['RUN_TIMESTAMP'] = datetime.datetime.now().strftime("%Y_%m_%d__%H_%M_%S_%f")

    def _killSubprocesses(self):
        for pid in self._pids:
            os.kill(signal.SIGTERM, pid)

    def runSequential(self):
        for scenario in self._scenarios:
            for instance in self._instances:
                self._runScenario(scenario, instance)

    def runParallel(self):
        os.environ['RACKTEST_MINIMUM_NICE_FOR_RACKATTACK'] = "1.0"
        jobs = []
        for scenario in self._scenarios:
            for instance in self._instances:
                jobs.append(dict(callback=self._runScenario, scenario=scenario, instance=instance))
        concurrently.run(jobs, threads=self._args.parallel)

    def printScenarios(self):
        for scenario in self._scenarios:
            print scenario

    def total(self):
        return len(self._scenarios) * len(self._instances)

    def passedCount(self):
        return len([res for res in self._results if res['passed']])

    def failedCount(self):
        return self.total() - self.passedCount()

    def failed(self):
        return [res['scenario'] for res in self._results if not res['passed']]

    def writeReport(self):
        with open(self._args.reportFilename, "w") as f:
            json.dump(self._results, f)

    def _matchingScenarios(self):
        root = self._args.scenariosRoot
        scenarios = \
            glob.glob(root + "/*.py") + \
            glob.glob(root + "/*/*.py") + \
            glob.glob(root + "/*/*/*.py") + \
            glob.glob(root + "/*/*/*/*.py")
        for scenario in scenarios:
            if scenario.endswith("/__init__.py"):
                raise Exception("'__init__.py' must not be found under the scenarios directory")
        scenarios.sort()
        return [s for s in scenarios if re.search(self._args.regex, s) is not None]

    def _dumpLiveReport(self):
        with self._liveReportLock:
            everything = dict(
                results=self._results, scenarios=self._scenarios, instances=self._instances)
            with open(self._args.liveReportFilename, "w") as f:
                json.dump(everything, f)

    def _runScenario(self, scenario, instance):
        before = time.time()
        popen = subprocess.Popen(
            ['python', _single, args.configurationFile, scenario, instance], close_fds=True)
        self._pids.append(popen.pid)
        result = popen.wait()
        self._pids.remove(popen.pid)
        took = time.time() - before
        self._results.append(dict(
            scenario=scenario, instance=instance, passed=result == 0, timeTook=took, host='localhost'))
        self._dumpLiveReport()


runner = Runner(args)
if args.listOnly:
    runner.printScenarios()
    sys.exit(0)
if args.parallel:
    runner.runParallel()
else:
    runner.runSequential()
runner.writeReport()
if runner.passedCount() < runner.total():
    logging.error(
        "%(failed)d tests Failed. %(passed)d/%(total)d Passed",
        dict(failed=runner.failedCount(), passed=runner.passedCount(), total=runner.total()))
    for scenario in runner.failed():
        logging.error("Failed scenario: %(scenario)s", dict(scenario=scenario))
    sys.exit(1)
else:
    logging.success(
        "Tests Passed: %(passed)d/%(total)d", dict(passed=runner.passedCount(), total=runner.total()))
