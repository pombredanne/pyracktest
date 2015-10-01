import django  # this verifies local libraries can be packed into the egg
import additiondependency


def addition(first, second):
    additiondependency.dependantMethod()
    return first + second


def addition2(first, second, third):
    additiondependency.dependantMethod()
    return first + second + third
