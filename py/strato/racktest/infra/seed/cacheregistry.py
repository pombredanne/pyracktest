_registry = {}


def register(name, creator):
    _registry[name] = creator


def create(name):
    return _registry[name]() if name is not None else None
