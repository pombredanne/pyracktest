all: check_convention

clean:
	rm -fr logs.racktest

racktest:
	UPSETO_JOIN_PYTHON_NAMESPACES=yes PYTHONPATH=$(PWD):$(PWD)/py python tests/test.py
virttest:
	RACKATTACK_PROVIDER=tcp://localhost:1014@@amqp://guest:guest@localhost:1013/%2F@@http://localhost:1016 $(MAKE) racktest
phystest:
	RACKATTACK_PROVIDER=tcp://rackattack-provider:1014@@amqp://guest:guest@rackattack-provider:1013/%2F@@http://rackattack-provider:1016 $(MAKE) racktest
devphystest:
	RACKATTACK_PROVIDER=tcp://rack01-server58:1014@@amqp://guest:guest@rack01-server58:1013/%2F@@http://rack01-server58:1016 $(MAKE) racktest

check_convention:
	pep8 py test* example* --max-line-length=109

unittest:
	UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=py:. python py/strato/tests/runner.py