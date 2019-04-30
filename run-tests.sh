#!/usr/bin/env bash

export PYTHONPATH=$PWD
dbus-run-session pytest -sq
