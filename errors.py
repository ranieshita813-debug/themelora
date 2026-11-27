"""Exception types shared across Malora."""


class MaloraError(Exception):
    """A user-facing failure.

    The message is printed as a single line. It is never shown as a traceback.
    """
