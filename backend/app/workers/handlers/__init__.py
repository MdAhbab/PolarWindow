"""Job handlers, one module per kind. Importing this package registers them all."""

from app.workers.handlers import contact, launch, rover, trip  # noqa: F401
