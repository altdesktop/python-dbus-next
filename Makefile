.PHONY: test format lint all clean publish docs coverage
.DEFAULT_GOAL := all

source_dirs = dbus_next test examples

lint:
	flake8 $(source_dirs)

format:
	yapf -rip $(source_dirs)

test:
	dbus-run-session pytest -s

docker-test:
	docker build -t dbus-next .
	docker run -it dbus-next

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
