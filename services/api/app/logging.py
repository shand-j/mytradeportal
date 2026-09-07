"""API service logging configuration.

Builds on the shared structlog setup in ``mtp_shared.logging`` but routes the
final rendering through the stdlib so that BOTH ``structlog.get_logger(...)``
and plain ``logging.getLogger(...)`` calls emit identical JSON lines on
stdout. ``mtp_shared`` keeps its minimal chain (it is shared with services
that configure logging differently), so this module is the API-specific
extension point.

Key properties of the resulting log stream (one JSON object per line):

- ``timestamp`` — ISO-8601 (added by ``TimeStamper``)
- ``level`` — lowercase level name
- ``event`` — the message / event name
- ``request_id`` / ``tenant_id`` — merged from structlog contextvars, so
  every event emitted during a request carries them automatically
- ``logger`` — logger name (e.g. ``api.http``, ``api.rag``)
"""

import logging
import sys

import structlog
from structlog.typing import Processor

# Processors shared by structlog loggers (run inline) and stdlib records
# (run as the ProcessorFormatter's ``foreign_pre_chain``).
_SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.stdlib.ExtraAdder(),
]


def configure_logging(log_level: str = "INFO") -> None:
    """Configure JSON stdout logging for structlog and stdlib loggers alike."""
    level = getattr(logging, log_level.upper())

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            # Hand the event dict to the stdlib handler's ProcessorFormatter
            # instead of rendering here, so structlog and stdlib records are
            # rendered by the same JSONRenderer below.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
