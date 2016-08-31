import psutil
import logging
import os
import threading
import inspect


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
    stopingAllParamikoThreads()
    logging.debug("Done killing children.")


# WORKAROUND to close all open paramiko threads
def stopingAllParamikoThreads():
    for thread in threading.enumerate():
        if hasattr(thread, 'stop_thread') and inspect.ismethod(thread.stop_thread):
            thread.stop_thread()
