import cPickle


def callableCode(callableSeed):
    return ("import %(module)s\n"
            "import cPickle\n"
            "import sys\n"
            "inputFile=sys.argv[1]\n"
            "outputFile=sys.argv[2]\n"
            "with open(inputFile, 'rb') as f:\n"
            " args, kwargs = cPickle.load(f)\n"
            "result = %(module)s.%(callable)s(*args, **kwargs)\n"
            "with open(outputFile, 'wb') as f:\n"
            " cPickle.dump(result, f, cPickle.HIGHEST_PROTOCOL)\n" % dict(
                module=callableSeed.__module__,
                callable=callableSeed.__name__))


def snippetCode(code):
    return ("import sys\n"
            "outputFile=sys.argv[1]\n"
            "result = None\n" + code + "\n"
            "import cPickle\n"
            "with open(outputFile, 'wb') as f:\n"
            " cPickle.dump(result, f, cPickle.HIGHEST_PROTOCOL)\n")


def executeWithResult(host, seed, unique, hasInput, outputTimeout=None):
    eggFilename = "/tmp/seed%s.egg" % unique
    host.ssh.ftp.putContents(eggFilename, seed["code"])
    kwargs = {}
    if outputTimeout is not None:
        kwargs['outputTimeout'] = outputTimeout
    if hasInput:
        moduleArgs = "/tmp/args%(unique)s.pickle /tmp/result%(unique)s.pickle" % dict(unique=unique)
    else:
        moduleArgs = "/tmp/result%(unique)s.pickle" % dict(unique=unique)
    return host.ssh.run.script(
        "PYTHONPATH=/tmp/seed%s.egg python -m seedentrypoint %s" % (unique, moduleArgs), **kwargs)


def executeInBackground(host, seed, unique, hasInput):
    eggFilename = '/tmp/seed%s.egg' % unique
    host.ssh.ftp.putContents(eggFilename, seed["code"])
    if hasInput:
        moduleArgs = "/tmp/args%(unique)s.pickle /tmp/result%(unique)s.pickle" % dict(unique=unique)
    else:
        moduleArgs = "/tmp/result%(unique)s.pickle" % dict(unique=unique)
    host.ssh.run.backgroundScript(
        "echo $$ > /tmp/pid%(unique)s.txt\n"
        "export PYTHONPATH=%(eggFilename)s\n"
        "exec python -m seedentrypoint %(moduleArgs)s >& /tmp/output%(unique)s.txt" %
        dict(unique=unique, eggFilename=eggFilename, moduleArgs=moduleArgs))


def downloadResult(host, unique):
    return cPickle.loads(host.ssh.ftp.getContents("/tmp/result%s.pickle" % unique))


def installArgs(host, unique, args, kwargs):
    argsPickle = "/tmp/args%s.pickle" % unique
    argsContents = cPickle.dumps((args, kwargs), cPickle.HIGHEST_PROTOCOL)
    host.ssh.ftp.putContents(argsPickle, argsContents)
