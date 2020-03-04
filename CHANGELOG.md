# Changelog

## Version 0.1.3

This version adds some bugfixes and new features.

* Add the object manager interface to the service. (#14, #37)
* Allow coroutines in service methods. (#24, #27)
* Client: don't send method replies with `NO_REPLY_EXPECTED` message flag. (#22)
* Fix duplicate nodes in introspection. (#13)

## Version 0.1.2

This version adds some bugfixes.

* Allow exporting interface multiple times (#4)
* Fix super call in exceptions (#5)
* Add timeout support on `introspect` (#7)
* Add unix fd type 'h' to valid tokens (#9)
* Dont use future annotations (#10)
* Fix variant validator (d724fc2)

## Version 0.1.1

This version adds some major features and breaking changes.

* Remove the MessageBus convenience constructors (breaking).
* Complete documentation.
* Type annotation for all public methods.

## Version 0.0.1

This is the first release of python-dbus-next.
