.PHONY: test format lint precommit

lint:
	flake8

format:
	yapf -ipr .

test:
	dbus-run-session pytest -sq

coverage:
	dbus-run-session pytest --cov=dbus_next

precommit: format lint test
