#!/usr/bin/env bash

export PYTHONPATH=$PWD
#dbus-run-session pytest -sq test/test_big_message.py
dbus-run-session pytest -sq
