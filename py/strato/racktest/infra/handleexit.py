import psutil
import logging
import os


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
