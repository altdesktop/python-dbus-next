The Type System
===============

.. toctree::
   :maxdepth: 2

   variant
   signature-tree
   signature-type

Values that are sent or received over the message bus always have an
associated signature that specifies the types of those values. For the
high-level client and service, these signatures are specified in XML
data which is advertised in a `standard DBus
interface <https://dbus.freedesktop.org/doc/dbus-specification.html#introspection-format>`__.
The high-level client dynamically creates classes based on this
introspection data with methods and signals with arguments based on the
type signature. The high-level service does the inverse by introspecting
the class to create the introspection XML data which is advertised on
the bus for clients.

Each token in the signature is mapped to a Python type as shown in the table
below.

+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| Name        | Token | Python                               | Notes                                                                   |
|             |       | Type                                 |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| BYTE        | y     | int                                  | An integer 0-255. In an array, it has type ``bytes``.                   |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| BOOLEAN     | b     | bool                                 |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| INT16       | n     | int                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| UINT16      | q     | int                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| INT32       | i     | int                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| UINT32      | u     | int                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| INT64       | x     | int                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| UINT64      | t     | int                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| DOUBLE      | d     | float                                |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| STRING      | s     | str                                  |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| OBJECT_PATH | o     | str                                  | Must be a valid object path.                                            |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| SIGNATURE   | g     | str                                  | Must be a valid signature.                                              |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| UNIX_FD     | h     | int                                  | In the low-level interface, an index pointing to a file descriptor      |
|             |       |                                      | in the ``unix_fds`` member of the :class:`Message <dbus_next.Message>`. |
|             |       |                                      | In the high-level interface, it is the file descriptor itself.          |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| ARRAY       | a     | list                                 | Must be followed by a complete type which specifies the child type.     |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| STRUCT      | (     | list                                 | Types in the Python ``list`` must match the types between the parens.   |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| VARIANT     | v     | :class:`Variant <dbus_next.Variant>` | This class is provided by the library.                                  |
|             |       |                                      |                                                                         |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+
| DICT_ENTRY  | {     | dict                                 | Must be included in an array to be a ``dict``.                          |
+-------------+-------+--------------------------------------+-------------------------------------------------------------------------+

The types ``a``, ``(``, ``v``, and ``{`` are container types that hold
other values. Examples of container types and Python examples are in the
table below.

+-----------+--------------------------------------+-------------------------------------------------------+
| Signature | Example                              | Notes                                                 |
+===========+======================================+=======================================================+
| ``(su)``  | ``[ 'foo', 5 ]``                     | Each element in the array must match the              |
|           |                                      | corresponding type of the struct member.              |
+-----------+--------------------------------------+-------------------------------------------------------+
| ``as``    | ``[ 'foo', 'bar' ]``                 | The child type comes immediately after the ``a``.     |
|           |                                      | The array can have any number of elements, but        |
|           |                                      | they all must match the child type.                   |
+-----------+--------------------------------------+-------------------------------------------------------+
| ``a{su}`` | ``{ 'foo': 5 }``                     | An "array of dict entries" is represented by a        |
|           |                                      | ``dict``. The type after ``{`` is the key type and    |
|           |                                      | the type before the ``}`` is the value type.          |
+-----------+--------------------------------------+-------------------------------------------------------+
| ``ay``    | ``b'\0x62\0x75\0x66'``               | Special case: an array of bytes is represented by     |
|           |                                      | Python ``bytes``.                                     |
|           |                                      |                                                       |
|           |                                      |                                                       |
|           |                                      |                                                       |
|           |                                      |                                                       |
+-----------+--------------------------------------+-------------------------------------------------------+
| ``v``     | ``Variant('as', ['hello'])``         | Signature must be a single type. A variant may hold a |
|           |                                      | container type.                                       |
|           |                                      |                                                       |
|           |                                      |                                                       |
|           |                                      |                                                       |
+-----------+--------------------------------------+-------------------------------------------------------+
| ``(asv)`` | ``[ ['foo'], Variant('s', 'bar') ]`` | Containers may be nested.                             |
+-----------+--------------------------------------+-------------------------------------------------------+

For more information on the DBus type system, see `the
specification <https://dbus.freedesktop.org/doc/dbus-specification.html#type-system>`__.
