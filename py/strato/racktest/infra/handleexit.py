import psutil
import os
import threading
import inspect


def _safelyKillProcess(process):
    try:
        if process.is_running():
            process.kill()
    except:
        pass


def killSubprocesses(pid=None):
    pid = pid or os.getpid()
    process = psutil.Process(pid)
    if hasattr(process, 'children'):
        children = process.children(recursive=True)
    else:
        children = process.get_children(recursive=True)
    if children:
        for son in children:
            _safelyKillProcess(son)
    stopingAllParamikoThreads()


# WORKAROUND to close all open paramiko threads
def stopingAllParamikoThreads():
    for thread in threading.enumerate():
        if hasattr(thread, 'stop_thread') and inspect.ismethod(thread.stop_thread):
            thread.stop_thread()
