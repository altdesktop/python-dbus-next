Python DBus-Next Documentation
==============================

.. module:: dbus_next

.. toctree::
   :maxdepth: 3
   :caption: Reference:

   type-system/index.rst
   high-level-client/index.rst
   high-level-service/index.rst
   low-level-interface/index.rst
   message-bus/index.rst
   introspection
   validators
   constants
   errors
   authentication

Overview
++++++++

Python DBus-Next is a library for the `DBus message bus system <https://www.freedesktop.org/wiki/Software/dbus/>`_ for interprocess communcation in a Linux desktop or mobile environment.

Desktop application developers can use this library for integrating their applications into desktop environments by implementing common DBus standard interfaces or creating custom plugin interfaces.

Desktop users can use this library to create their own scripts and utilities to interact with those interfaces for customization of their desktop environment.

While other libraries for DBus exist for Python, this library offers the following improvements:

- Zero dependencies and pure Python 3.
- Support for multiple main loop backends including asyncio and the GLib main loop.
- Nonblocking IO suitable for GUI development.
- Target the latest language features of Python for beautiful services and clients.
- Complete implementation of the DBus type system without ever guessing types.
- Integration tests for all features of the library.
- Completely documented public API.

The library offers three core interfaces:

- `The High Level Client <high-level-client/index.html>`_ - Communicate with an existing interface exported on the bus by another client through a proxy object.
- `The High Level Service <high-level-service/index.html>`_ - Export a service interface for your application other clients can connect to for interaction with your application at runtime.
- `The Low Level Interface <low-level-interface/index.html>`_ - Work with DBus messages directly for applications that work with the DBus daemon directly or to build your own high level abstractions.

Installation
++++++++++++

This library is available on PyPi as `dbus-next <https://pypi.org/project/dbus-next/>`_.

.. code-block:: bash

    pip3 install dbus-next

Contributing
++++++++++++

Development for this library happens on `Github <https://github.com/altdesktop/python-dbus-next>`_. Report bugs or request features there. Contributions are welcome.

License
++++++++

This library is available under an `MIT License <https://github.com/altdesktop/python-dbus-next/blob/master/LICENSE>`_.

© 2019, Tony Crisci

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
