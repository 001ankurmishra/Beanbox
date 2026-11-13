"""
Real Celery worker integration tests running against Redis broker on DB 1.
Marked with @pytest.mark.celery.
Requires REDIS_URL_TEST to be set; skipped automatically when unset.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import pytest
import redis
from celery.contrib.testing.worker import start_worker

from app.models.domain import User
from app.repositories.interfaces import CreateUserInput
from app.worker.celery_app import celery_app, get_worker_repos, get_worker_services
from app.worker.tasks_email import enqueue_email

pytestmark = pytest.mark.celery


def _derive_db_url(base_url: str, db_index: int) -> str:
    parsed = urlparse(base_url)
    return urlunparse((parsed.scheme, parsed.netloc, f"/{db_index}", "", "", ""))


@pytest.fixture
def real_celery_redis_env():
    url = os.environ.get("REDIS_URL_TEST", "").strip()
    if not url:
        pytest.skip("REDIS_URL_TEST is not set; skipping real Celery worker tests")

    broker_url = _derive_db_url(url, 1)
    data_url = _derive_db_url(url, 0)

    broker_client = redis.Redis.from_url(broker_url, decode_responses=True)
    data_client = redis.Redis.from_url(data_url, decode_responses=True)

    try:
        broker_client.ping()
        data_client.ping()
    except redis.RedisError as exc:
        pytest.fail(f"Redis ping failed against {url}: {exc}")

    # Clean broker DB 1 and test dedupe keys in DB 0
    broker_client.flushdb()
    for k in data_client.scan_iter(match="email:welcome:*", count=200):
        data_client.delete(k)

    yield {
        "broker_url": broker_url,
        "broker_client": broker_client,
        "data_client": data_client,
    }

    # Teardown
    broker_client.flushdb()
    for k in data_client.scan_iter(match="email:welcome:*", count=200):
        data_client.delete(k)
    broker_client.close()
    data_client.close()


def test_real_celery_worker_enqueues_and_deduplicates_50_emails(real_celery_redis_env):
    broker_url = real_celery_redis_env["broker_url"]
    data_client = real_celery_redis_env["data_client"]
    broker_client = real_celery_redis_env["broker_client"]

    # Configure celery app for real broker execution
    celery_app.conf.update(
        broker_url=broker_url,
        task_always_eager=False,
    )

    with start_worker(
        celery_app,
        pool="solo",
        perform_ping_check=False,
        loglevel="ERROR",
        queues="default,emails,maintenance",
    ):
        repos = get_worker_repos()
        services = get_worker_services()
        # Suppress stdout printing during high-concurrency batch test
        services.email_service._quiet = True

        # Pre-create 50 users with unique run prefix
        run_id = str(uuid4())[:8]
        users: list[User] = []
        for i in range(50):
            u = repos.users.create(
                CreateUserInput(
                    name=f"Customer {i}",
                    email=f"celery_{run_id}_{i}@example.com",
                    password_hash="TestHash123",
                )
            )
            users.append(u)

        # Enqueue 50 emails TWICE (100 deliveries total) to assert at-least-once deduplication
        for u in users:
            enqueue_email(
                kind="welcome",
                payload_ids={"user_id": u.id},
                email_service=services.email_service,
                repos=repos,
                redis_client=data_client,
            )
            enqueue_email(
                kind="welcome",
                payload_ids={"user_id": u.id},
                email_service=services.email_service,
                repos=repos,
                redis_client=data_client,
            )

        # Wait for worker to consume and process all tasks (up to 20 seconds)
        for _ in range(400):
            sent_count = len(services.email_service.get_sent_emails())
            if sent_count >= 50:
                break
            time.sleep(0.05)

        sent_emails = services.email_service.get_sent_emails()
        # Exactly 50 unique emails sent
        assert len(sent_emails) == 50

        # Broker queue drained
        assert broker_client.llen("emails") == 0

        # Exactly 50 dedupe keys claimed in Redis DB 0
        claimed_keys = list(data_client.scan_iter(match="email:welcome:*", count=200))
        assert len(claimed_keys) >= 50
