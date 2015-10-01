from strato.racktest.infra.suite import *
from example_seeds import addition
import time

SIGNALLED_CALLABLE_CODE = """
import signal
import time
signalReceived = None

def signalHandler(sigNum, _):
    global signalReceived
    signalReceived = sigNum

signal.signal(signal.SIGUSR2, signalHandler)

while not signalReceived:
    time.sleep(1)
"""


class Test:
    HOSTS = dict(it=dict(rootfs="rootfs-basic"))

    def run(self):
        TS_ASSERT_EQUALS(host.it.seed.runCallable(
            addition.addition, 1, second=2, takeSitePackages=True)[0], 3)

        TS_ASSERT_EQUALS(host.it.seed.runCode(
            "from example_seeds import addition\nresult = addition.addition(2, second=3)",
            takeSitePackages=True)[0], 5)

        forked = host.it.seed.forkCode(
            "import time\ntime.sleep(3)\n"
            "print 'OUTPUT LINE'\n"
            "from example_seeds import addition\nresult = addition.addition(2, second=3)",
            takeSitePackages=True)
        TS_ASSERT(forked.poll() is None)
        TS_ASSERT(forked.poll() is None)
        TS_ASSERT_PREDICATE_TIMEOUT(forked.poll, TS_timeout=4)
        TS_ASSERT(forked.poll())
        TS_ASSERT_EQUALS(forked.result(), 5)
        TS_ASSERT('OUTPUT LINE' in forked.output())

        forked = host.it.seed.forkCode(
            "import time\nwhile True: time.sleep(2)", takeSitePackages=True)
        TS_ASSERT(forked.poll() is None)
        TS_ASSERT(forked.poll() is None)
        forked.kill()
        for i in xrange(10):
            if forked.poll() is None:
                time.sleep(1)
            else:
                break
        TS_ASSERT_EQUALS(forked.poll(), False)

        forked = host.it.seed.forkCode(
            "import time\nwhile True: time.sleep(2)", takeSitePackages=True)
        TS_ASSERT(forked.poll() is None)
        TS_ASSERT(forked.poll() is None)
        forked.kill('TERM')
        for i in xrange(10):
            if forked.poll() is None:
                time.sleep(1)
            else:
                break
        TS_ASSERT_EQUALS(forked.poll(), False)

        forked = host.it.seed.forkCode(SIGNALLED_CALLABLE_CODE, takeSitePackages=True)
        TS_ASSERT(forked.poll() is None)
        TS_ASSERT(forked.poll() is None)
        forked.kill('USR2')
        for i in xrange(10):
            if forked.poll() is None:
                time.sleep(1)
            else:
                break
        TS_ASSERT_EQUALS(forked.poll(), True)
        forked = host.it.seed.forkCallable(addition.addition, 1, second=2, takeSitePackages=True)
        TS_ASSERT_PREDICATE_TIMEOUT(forked.poll, TS_timeout=4)
        TS_ASSERT_EQUALS(forked.result(), 3)
