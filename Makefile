.PHONY: test format lint all
.DEFAULT_GOAL := all

source_dirs = dbus_next test examples

lint:
	flake8 $(source_dirs)

format:
	yapf -ipr $(source_dirs)

test:
	dbus-run-session pytest -s

docker-test:
	docker build -t dbus-next .
	docker run -it dbus-next

coverage:
	dbus-run-session pytest --cov=dbus_next

all: format lint test
