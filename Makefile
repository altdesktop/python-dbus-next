.PHONY: test format lint all clean
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

clean:
	rm -rf dist dbus_next.egg-info build
	rm -rf `find -type d -name __pycache__`

publish:
	python3 setup.py sdist bdist_wheel
	twine upload dist/*

all: format lint test
