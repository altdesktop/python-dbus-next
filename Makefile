.PHONY: lint check format test docker-test clean publish docs livedocs all
.DEFAULT_GOAL := all

source_dirs = dbus_next test examples

lint:
	python3 -m flake8 $(source_dirs)

check: lint
	python3 -m yapf -rdp $(source_dirs)

format:
	python3 -m yapf -rip $(source_dirs)

test:
	for py in python3.10 python3.6 python3.7 python3.8 python3.9 ; do \
		if hash $$py; then \
			dbus-run-session $$py -m pytest -sv --cov=dbus_next || exit 1 ; \
		fi \
	done \

docker-test:
	docker build -t dbus-next-test .
	docker run -it dbus-next-test

clean:
	rm -rf dist dbus_next.egg-info build docs/_build
	rm -rf `find -type d -name __pycache__`

publish:
	python3 setup.py sdist bdist_wheel
	python3 -m twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

docs:
	sphinx-build docs docs/_build/html

livedocs:
	sphinx-autobuild docs docs/_build/html --watch dbus_next

all: format lint test
