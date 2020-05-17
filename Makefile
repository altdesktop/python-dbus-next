.PHONY: lint check format test docker-test coverage clean publish docs livedocs all
.DEFAULT_GOAL := all

source_dirs = dbus_next test examples

lint:
	flake8 $(source_dirs)

check: lint
	yapf -rdp $(source_dirs)

format:
	yapf -rip $(source_dirs)

test:
	dbus-run-session python3 -m pytest -s

docker-test:
	docker build -t dbus-next38 .
	docker run -it dbus-next38

coverage:
	dbus-run-session pytest --cov=dbus_next

clean:
	rm -rf dist dbus_next.egg-info build docs/_build
	rm -rf `find -type d -name __pycache__`

publish:
	python3 setup.py sdist bdist_wheel
	python3 -m twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

docs:
	sphinx-build docs docs/_build/html

livedocs:
	sphinx-autobuild docs docs/_build/html --watch dbus_next -i '*swp' -i '*~'

all: format lint test
