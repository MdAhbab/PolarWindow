"""Job handlers, one module per kind. Importing this package registers them all."""

from app.workers.handlers import contact, trip  # noqa: F401
