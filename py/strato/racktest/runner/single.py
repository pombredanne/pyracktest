from strato.racktest.infra import config
from strato.racktest.infra import executioner
from strato.common.log import configurelogging
import logging
import os
import shutil
import argparse
from strato.common import log
import imp


def runSingleScenario(scenarioFilename, instance, preallocatedClusterConf=None):
    testName = os.path.splitext(scenarioFilename)[0].replace('/', '.')
    _configureTestLogging(testName + instance)
    logging.info("Running '%(scenarioFilename)s' as a test class (instance='%(instance)s')", dict(
        scenarioFilename=scenarioFilename, instance=instance))
    try:
        module = imp.load_source('test', scenarioFilename)
        execute = executioner.Executioner(module.Test, preallocatedClusterConf)
        execute.executeTestScenario()
    except:
        logging.exception(
            "Failed running '%(scenarioFilename)s' as a test class (instance='%(instance)s')",
            dict(scenarioFilename=scenarioFilename, instance=instance))
        logging.shutdown()
        raise
    finally:
        logging.info(
            "Done Running '%(scenarioFilename)s' as a test class (instance='%(instance)s')",
            dict(scenarioFilename=scenarioFilename, instance=instance))
        logging.shutdown()


def _configureTestLogging(testName):
    dirPath = os.path.join(config.TEST_LOGS_DIR, testName)
    shutil.rmtree(dirPath, ignore_errors=True)
    configurelogging.configureLogging('test', forceDirectory=dirPath)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run single test scenarion")
    parser.add_argument("configurationFile", help="configuration file")
    parser.add_argument("scenarioFilename", help="run given scenario file")
    parser.add_argument("instance", default="", help="test instance")
    parser.add_argument("--preallocatedClusterConf", default=None, help="cluster configuration file to run on preallocated")
    args = parser.parse_args()
    config.load(args.configurationFile)
    runSingleScenario(args.scenarioFilename, args.instance, args.preallocatedClusterConf)
