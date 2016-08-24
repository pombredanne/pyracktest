import psutil
import logging
import os


def _safelyKillProcess(process):
    try:
        if process.is_running():
            process.kill()
    except:
        logging.debug("Couldn't kill process %s", process.pid)


def killSubprocesses(pid=None):
    pid = pid or os.getpid()
    process = psutil.Process(pid)
    children = process.children(recursive=True)
    if children:
        logging.debug("Killing children...")
        for son in children:
            _safelyKillProcess(son)
        logging.debug("Done killing children.")
