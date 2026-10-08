"""Serialize access to the application's shared SQLite connection."""

from contextlib import nullcontext
from functools import wraps


def with_database_lock(action):
    @wraps(action)
    def wrapped(self, *args, **kwargs):
        with getattr(self.db, "write_lock", nullcontext()):
            return action(self, *args, **kwargs)
    return wrapped
