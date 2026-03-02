import json
import logging
from typing import Any


class StructuredLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, event: str, **context: Any) -> None:
        self._logger.info(json.dumps({"event": event, **context}, ensure_ascii=False))

    def error(self, event: str, **context: Any) -> None:
        self._logger.error(json.dumps({"event": event, **context}, ensure_ascii=False))
