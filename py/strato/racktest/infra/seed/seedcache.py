import logging
import time
import hashlib


class SeedID(object):

    def __init__(self, key, **packArgs):
        self.key = key
        self.args = packArgs
        self.hash = hashlib.md5(self.__repr__()).hexdigest()

    def __repr__(self):
        args = ';'.join(["%s=%s" % (key, value) for key, value in self.args.iteritems()])
        return self.key + ":" + args


class SeedCache(object):

    def __init__(self, engine, seedCreatorClass):
        self._engine = engine
        self._creator = seedCreatorClass

    def _createSeedFromCache(self, key, code, **packArgs):
        with self._engine.lock(key):
            seed = self._engine.get(key)
            if seed is not None:
                logging.debug('Cache hit for key %(key)s', dict(key=key))
                return seed
            logging.debug('Cache miss for %(key)s', dict(key=key))
            before = time.time()
            descriptor = self._creator(code, generateDependencies=True, **packArgs)()
            after = time.time()
            self._engine.install(key, descriptor)
            logging.debug('Seed generation took %(delta).3f sec', dict(delta=after - before))
            return descriptor['code']

    def makeSeed(self, key, code, **packArgs):
        #import ipdb;ipdb.set_trace()
        seedId = SeedID(key, **packArgs)
        noCache = packArgs.get('noCache', False)
        if self._engine is None or noCache:
            return self._creator(code, generateDependencies=False, **packArgs)()['code']
        try:
            return self._createSeedFromCache(seedId, code, **packArgs)
        except:
            logging.warn('Failed to operate cache for key %(key)s, failover to creation clear cache?',
                         dict(key=key), exc_info=1)
            return self._creator(code, generateDependencies=False, **packArgs)()['code']
