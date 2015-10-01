all: check_convention

clean:
	rm -fr logs.racktest

racktest:
	UPSETO_JOIN_PYTHON_NAMESPACES=yes PYTHONPATH=$(PWD):$(PWD)/py python tests/test.py

RACK_DOMAIN := rackattack-provider.dc1.strato
RACKATTACK_PROVIDER_PHYS = tcp://$(RACK_DOMAIN):1014@@amqp://guest:guest@$(RACK_DOMAIN):1013/%2F@@http://$(RACK_DOMAIN):1016
RACKATTACK_PROVIDER_VIRT = tcp://localhost:1014@@amqp://guest:guest@localhost:1013/%2F@@http://localhost:1016

virttest:
	RACKATTACK_PROVIDER=$(RACKATTACK_PROVIDER_VIRT) $(MAKE) racktest
phystest:
	RACKATTACK_PROVIDER=$(RACKATTACK_PROVIDER_PHYS) $(MAKE) racktest
devphystest:
	RACKATTACK_PROVIDER=tcp://rack01-server58:1014@@amqp://guest:guest@rack01-server58:1013/%2F@@http://rack01-server58:1016 $(MAKE) racktest

check_convention:
	pep8 py test* example* --max-line-length=109

unittest:
	UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=py:. python py/strato/tests/runner.py