from strato.racktest.infra import config
from strato.racktest.infra import executioner
from strato.common.log import configurelogging
import logging
import os
import shutil
import argparse
from strato.common import log
import imp
import sys
import atexit
import psutil


def _safelyKillProcess(process):
    try:
        if process.is_running():
            process.kill()
    except:
        logging.debug("Couldn't kill process %s", process.pid)


def killSubprocesses(pid=None, killGivenProcess=False):
    try:
        pid = pid or os.getpid()
        process = psutil.Process(pid)
        children = process.children(recursive=True)
        logging.debug("Children pids list %s", children)
        for son in children:
            _safelyKillProcess(son)
        if killGivenProcess and process.pid > 1:
            _safelyKillProcess(process)
    except Exception as e:
        logging.exception(e)


def runSingleScenario(scenarioFilename, instance, testRunAttributes=None):
    testName = os.path.splitext(scenarioFilename)[0].replace('/', '.')
    _configureTestLogging(testName + instance)
    logging.info("Running '%(scenarioFilename)s' as a test class (instance='%(instance)s')", dict(
        scenarioFilename=scenarioFilename, instance=instance))
    try:
        module = imp.load_source('test', scenarioFilename)
        execute = executioner.Executioner(module.Test, testRunAttributes)
        execute.executeTestScenario()
    except:
        logging.exception(
            "Failed running '%(scenarioFilename)s' as a test class (instance='%(instance)s')",
            dict(scenarioFilename=scenarioFilename, instance=instance))
        raise
    finally:
        logging.info(
            "Done Running '%(scenarioFilename)s' as a test class (instance='%(instance)s')",
            dict(scenarioFilename=scenarioFilename, instance=instance))


def _configureTestLogging(testName):
    dirPath = os.path.join(config.TEST_LOGS_DIR, testName)
    shutil.rmtree(dirPath, ignore_errors=True)
    configurelogging.configureLogging('test', forceDirectory=dirPath)


if __name__ == "__main__":
    atexit.register(killSubprocesses)
    parser = argparse.ArgumentParser(description="Run single test scenarion")
    parser.add_argument("configurationFile", help="configuration file")
    parser.add_argument("scenarioFilename", help="run given scenario file")
    parser.add_argument("instance", default="", help="test instance")
    parser.add_argument("--testRunAttributes", default=None, help="json string with test attributes that will be set "
                                                                  "before test initialization in executioner")
    args = parser.parse_args()
    returnCode = 0
    try:
        config.load(args.configurationFile)
        runSingleScenario(args.scenarioFilename, args.instance, args.testRunAttributes)
    except:
        returnCode = 1

    logging.info("Finished running %s with returnCode %s", args.scenarioFilename, returnCode)
    sys.exit(returnCode)
