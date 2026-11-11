"""Job handlers, one module per kind. Importing this package registers them all."""

from app.workers.handlers import (  # noqa: F401
    contact,
    launch,
    rover,
    scenario,
    site_build,
    trip,
)
