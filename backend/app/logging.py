"""Logs estruturados em JSON com request id propagado por contextvar."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
tenant_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)

_SENSITIVE_KEYS = {
    "password",
    "passwordhash",
    "token",
    "secret",
    "authorization",
    "apikey",
    "api_key",
    "email",
    "phone",
    "to",
    "text",
    "refreshtoken",
    "accesstoken",
}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in _SENSITIVE_KEYS else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        tid = tenant_id_var.get()
        if tid:
            payload["tenant_id"] = tid
        uid = user_id_var.get()
        if uid:
            payload["user_id"] = uid
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(_scrub(extra))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class AppLogger(logging.LoggerAdapter):
    """Permite `log.info("msg", campo=valor)` sem colidir com a API do logging."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        reserved = {"exc_info", "stack_info", "stacklevel"}
        extra_fields = {k: v for k, v in kwargs.items() if k not in reserved}
        clean = {k: v for k, v in kwargs.items() if k in reserved}
        clean["extra"] = {"extra_fields": extra_fields}
        return msg, clean


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> AppLogger:
    return AppLogger(logging.getLogger(name), {})
