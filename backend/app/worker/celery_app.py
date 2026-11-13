"""
BeanBox Celery Application, Task Routing, Beat Scheduler, and Fork-Safe Process Lifecycle.

FORK SAFETY ARCHITECTURE:
Celery's default prefork pool imports the application code in a parent supervisor process,
then invokes os.fork() to spawn worker child processes.
In UNIX environments, fork() duplicates all open file descriptors and TCP sockets.
If database connection pools (Postgres ConnectionPool) or Redis connection pools are created
before forking, child worker processes will share the exact same underlying TCP socket.
When multiple worker processes attempt to read/write concurrently to the same socket,
packet interleaving, SSL protocol corruption, and connection dropouts occur.

To prevent this:
1. We listen to Celery's `worker_process_init` signal, which executes inside each child process
   immediately after forking and before accepting any tasks.
2. The signal handler resets all inherited connection pools and state.
3. Database and Redis connections are opened lazily inside the child worker.
4. The worker PostgreSQL connection pool is explicitly configured with `max_size=2`.
   Why max_size=2? Each worker process runs a single task at a time (prefetch=1). Setting
   max_size=2 provides 1 primary connection for the running task plus at most 1 spare
   connection for concurrent dead-letter or audit logging, preventing large Celery worker
   clusters from exhausting the PostgreSQL server's connection limits (e.g. Supabase limits).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

import celery
import redis
from celery.schedules import crontab
from celery.signals import worker_process_init
from kombu import Queue

from app.config import Settings, get_settings
from app.repositories.interfaces import Repositories
from app.worker.failures import TrackedTask

if TYPE_CHECKING:
    from app.services import Services

logger = logging.getLogger("beanbox.worker.boot")


def create_celery_app(settings: Optional[Settings] = None) -> celery.Celery:
    app_settings = settings or get_settings()

    app = celery.Celery("beanbox")

    app.conf.update(
        # Broker configuration (Redis DB 1, isolated from cache on DB 0)
        broker_url=app_settings.celery_broker_url,
        # Results backend disabled: tasks are fire-and-forget; results are stored in domain DB
        result_backend=app_settings.celery_result_backend or None,
        task_ignore_result=True,
        # Serialization: enforce JSON only (no pickle for security)
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Queues & Routing
        task_default_queue="default",
        task_queues=[
            Queue("default", routing_key="default"),
            Queue("emails", routing_key="emails"),
            Queue("maintenance", routing_key="maintenance"),
        ],
        task_routes={
            "app.worker.tasks_email.*": {"queue": "emails"},
            "app.worker.tasks_orders.*": {"queue": "maintenance"},
            "app.worker.tasks_maintenance.*": {"queue": "maintenance"},
        },
        # Reliability & Acks
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        # Time limits (seconds)
        task_soft_time_limit=30,
        task_time_limit=60,
        # Visibility timeout: 1 hour (prevent premature redelivery during long-running tasks)
        broker_transport_options={"visibility_timeout": 3600},
        # Timezone
        timezone="Asia/Kolkata",
        enable_utc=True,
        # Eager execution for testing
        task_always_eager=app_settings.is_celery_eager,
        task_eager_propagates=True,
        # Periodic Beat Schedule
        beat_schedule={
            "expire-unpaid-orders-every-60s": {
                "task": "app.worker.tasks_orders.expire_unpaid_orders",
                "schedule": 60.0,
                "options": {"queue": "maintenance"},
            },
            "cleanup-expired-auth-data-hourly": {
                "task": "app.worker.tasks_maintenance.cleanup_expired_auth_data",
                "schedule": 3600.0,
                "options": {"queue": "maintenance"},
            },
            "low-stock-digest-daily-0900-ist": {
                "task": "app.worker.tasks_maintenance.low_stock_digest",
                "schedule": crontab(hour=9, minute=0),
                "options": {"queue": "maintenance"},
            },
        },
    )

    app.Task = TrackedTask  # type: ignore[misc]
    return app


celery_app = create_celery_app()

# Auto-discover tasks in worker package
celery_app.autodiscover_tasks(["app.worker"])

# Per-process lazy state for fork safety
_worker_repos: Optional[Repositories] = None
_worker_services: Optional[Services] = None
_worker_pg_pool: Any = None
_worker_redis_client: Optional[redis.Redis] = None
_worker_broker_redis_client: Optional[redis.Redis] = None


def reset_worker_state() -> None:
    """Closes inherited connections and resets process-local singletons."""
    global _worker_repos, _worker_services, _worker_pg_pool
    global _worker_redis_client, _worker_broker_redis_client

    if _worker_pg_pool is not None:
        try:
            _worker_pg_pool.close(timeout=1.0)
        except Exception:
            pass
        _worker_pg_pool = None

    if _worker_redis_client is not None:
        try:
            _worker_redis_client.close()
        except Exception:
            pass
        _worker_redis_client = None

    if _worker_broker_redis_client is not None:
        try:
            _worker_broker_redis_client.close()
        except Exception:
            pass
        _worker_broker_redis_client = None

    _worker_repos = None
    _worker_services = None


@worker_process_init.connect
def on_worker_process_init(**kwargs: Any) -> None:
    """
    Executed inside each child worker process immediately after forking.
    Guarantees no sockets/connection pools are shared with the supervisor process.
    """
    logger.info("Initializing Celery worker child process (resetting connections for fork safety)")
    reset_worker_state()


def get_worker_repos() -> Repositories:
    global _worker_repos
    if _worker_repos is None:
        _init_worker_runtime()
    assert _worker_repos is not None
    return _worker_repos


def get_worker_services() -> Services:
    global _worker_services
    if _worker_services is None:
        _init_worker_runtime()
    assert _worker_services is not None
    return _worker_services


def get_worker_redis() -> Optional[redis.Redis]:
    global _worker_redis_client
    if _worker_redis_client is None:
        _init_worker_runtime()
    return _worker_redis_client


def get_broker_redis() -> Optional[redis.Redis]:
    """Provides a Redis client pointing to the Celery broker (DB 1) for LLEN telemetry."""
    global _worker_broker_redis_client
    if _worker_broker_redis_client is not None:
        return _worker_broker_redis_client

    settings = get_settings()
    try:
        pool = redis.ConnectionPool.from_url(
            settings.celery_broker_url,
            socket_timeout=2,
            decode_responses=True,
        )
        client: redis.Redis = redis.Redis(connection_pool=pool)
        client.ping()
        _worker_broker_redis_client = client
        return client
    except Exception as exc:
        logger.warning("Could not connect to Celery Redis broker (%s): %s", settings.celery_broker_url, exc)
        return None


def _init_worker_runtime() -> None:
    """
    Lazily initializes repositories, services, and database pools per child process.
    """
    global _worker_repos, _worker_services, _worker_pg_pool, _worker_redis_client
    if _worker_repos is not None and _worker_services is not None:
        return

    settings = get_settings()
    is_test = settings.app_env == "test"

    # Database repository initialization
    wants_supabase = settings.repository_backend == "supabase" or (
        settings.repository_backend == "auto"
        and bool(settings.database_url)
        and not is_test
    )

    if wants_supabase and settings.database_url:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        from app.repositories import create_supabase_repositories

        # WORKER DB POOL max_size=2:
        # Forked workers only need 1 connection for the task query plus at most 1 spare
        # connection for audit/dead-letter logs. A small pool prevents worker concurrency
        # from exhausting PostgreSQL database connection limits.
        _worker_pg_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=2,
            max_idle=300,
            timeout=10.0,
            open=True,
            kwargs={
                "row_factory": dict_row,
                "prepare_threshold": None,
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000",
            },
        )
        _worker_repos, _ = create_supabase_repositories(
            settings.database_url, pool=_worker_pg_pool
        )
    else:
        from app.repositories import create_in_memory_repositories

        _worker_repos = create_in_memory_repositories()

    # Redis Client on DB 0 (dedupe keys, distributed locks, last run stamps)
    if settings.redis_enabled != "false":
        target_url = (
            settings.redis_url_test.strip()
            if settings.app_env == "test" and settings.redis_url_test.strip()
            else settings.redis_url.strip()
        )
        if target_url:
            try:
                pool = redis.ConnectionPool.from_url(
                    target_url,
                    socket_timeout=2,
                    decode_responses=True,
                )
                client = redis.Redis(connection_pool=pool)
                client.ping()
                _worker_redis_client = client
            except Exception as exc:
                logger.warning(
                    "Redis cache unavailable for worker (%s): %s; using in-memory fallbacks",
                    target_url,
                    exc,
                )
                _worker_redis_client = None

    from app.services import create_services
    from app.services.email_service import ConsoleEmailService

    _worker_services = create_services(
        _worker_repos,
        settings,
        email_service=ConsoleEmailService(
            quiet=settings.app_env == "test",
        ),
    )
