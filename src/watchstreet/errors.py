"""Root of the application's exception hierarchy.

Every error the application raises on purpose derives from :class:`WatchStreetError`, so
boundaries (HTTP routes, the worker harness) can tell expected failures from programming bugs.
Concrete errors live next to the code that raises them and keep their builtin base
(``ValueError`` for invalid input, ``RuntimeError`` for failing collaborators).
"""


class WatchStreetError(Exception):
    """Base class of all deliberate application errors."""
