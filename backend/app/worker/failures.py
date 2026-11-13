"""
Dead-letter failure tracking and base Celery task for BeanBox.

When a background job exhausts its retries, an entry is recorded in the failed_jobs
table with task metadata, IDs-only arguments, error description, and a 4KB-truncated
traceback. Sensitive fields (tokens, passwords, PII) are strictly omitted.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import celery
from celery.exceptions import Retry

from app.models.domain import FailedJob
from app.repositories.interfaces.failed_job_repository import (
    CreateFailedJobInput,
    FailedJobRepository,
)

logger = logging.getLogger("beanbox.worker")

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "verify_token",
        "reset_token",
        "email",
        "phone",
        "name",
        "code",
        "key",
    }
)


def sanitize_task_args(args: Any) -> Any:
    """
    Ensures task arguments and logged payloads contain IDs and primitives only.
    Redacts any unexpected sensitive keys.
    """
    if isinstance(args, dict):
        clean = {}
        for k, v in args.items():
            if k.lower() in SENSITIVE_KEYS:
                clean[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                clean[k] = sanitize_task_args(v)
            else:
                clean[k] = v
        return clean
    if isinstance(args, (list, tuple)):
        return [sanitize_task_args(item) for item in args]
    return args


def record_dead_letter(
    task_name: str,
    args: Any,
    kwargs: Any,
    exc: BaseException,
    traceback_str: str,
    attempts: int,
    queue: str,
    repo: Optional[FailedJobRepository] = None,
) -> Optional[FailedJob]:
    """
    Inserts a failed task entry into the failed_jobs repository.
    Traceback is strictly capped at 4096 characters (4KB limit).
    """
    sanitized_payload = {
        "args": sanitize_task_args(args),
        "kwargs": sanitize_task_args(kwargs),
    }
    truncated_traceback = (traceback_str or "")[:4096]
    error_message = f"{exc.__class__.__name__}: {str(exc)}"

    if repo is None:
        from app.worker.celery_app import get_worker_repos

        repo = get_worker_repos().failed_jobs

    try:
        failed_job = repo.create(
            CreateFailedJobInput(
                task_name=task_name,
                args_json=sanitized_payload,
                error_message=error_message,
                traceback=truncated_traceback,
                attempts=attempts,
                queue=queue or "default",
            )
        )
        logger.error(
            "DEAD_LETTER: task=%s id=%s attempts=%d queue=%s error=%s",
            task_name,
            failed_job.id,
            attempts,
            queue,
            error_message,
        )
        return failed_job
    except Exception as db_exc:
        logger.critical(
            "Failed to record dead letter for task=%s: %s", task_name, db_exc
        )
        return None


class TrackedTask(celery.Task):
    """
    Base Celery task providing:
    1. Cross-service correlation logging (task_id, task name, attempt, duration, request_id).
    2. Automatic dead-letter recording into failed_jobs upon retry exhaustion.
    """

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        task_id = self.request.id or "internal"
        task_name = self.name
        attempt = self.request.retries + 1
        req_id = kwargs.get("request_id") or getattr(self.request, "request_id", None) or "-"
        t0 = time.perf_counter()

        logger.info(
            "task_start task_id=%s task=%s attempt=%d req_id=%s",
            task_id,
            task_name,
            attempt,
            req_id,
        )
        try:
            result = super().__call__(*args, **kwargs)
            duration = time.perf_counter() - t0
            logger.info(
                "task_success task_id=%s task=%s attempt=%d duration=%.3fs req_id=%s",
                task_id,
                task_name,
                attempt,
                duration,
                req_id,
            )
            return result
        except Retry:
            duration = time.perf_counter() - t0
            logger.warning(
                "task_retry task_id=%s task=%s attempt=%d duration=%.3fs req_id=%s",
                task_id,
                task_name,
                attempt,
                duration,
                req_id,
            )
            raise
        except Exception as exc:
            duration = time.perf_counter() - t0
            logger.error(
                "task_failure task_id=%s task=%s attempt=%d duration=%.3fs req_id=%s error=%s",
                task_id,
                task_name,
                attempt,
                duration,
                req_id,
                exc,
            )
            raise

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        super().on_failure(exc, task_id, args, kwargs, einfo)
        if isinstance(exc, Retry):
            return

        attempts = self.request.retries + 1
        queue = getattr(self.request, "delivery_info", {}).get("routing_key", "default")
        record_dead_letter(
            task_name=self.name,
            args=args,
            kwargs=kwargs,
            exc=exc,
            traceback_str=str(einfo or ""),
            attempts=attempts,
            queue=queue,
        )
