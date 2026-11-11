from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Literal

from app.models.domain import Order


@dataclass
class SentEmailRecord:
    to: str
    subject: str
    type: Literal["welcome", "password_reset", "order_confirmation", "order_shipped"]
    body: str
    sent_at: str


class EmailService(ABC):
    @abstractmethod
    def send_welcome(self, to: str, name: str) -> None: ...

    @abstractmethod
    def send_password_reset(
        self, to: str, name: str, reset_token: str, reset_url: str
    ) -> None: ...

    @abstractmethod
    def send_order_confirmation(
        self, to: str, customer_name: str, order: Order
    ) -> None: ...

    @abstractmethod
    def send_order_shipped(
        self, to: str, customer_name: str, order: Order
    ) -> None: ...

    @abstractmethod
    def get_sent_emails(self) -> list[SentEmailRecord]: ...


def _format_inr(paise: int) -> str:
    return f"₹{paise / 100:.2f}"


class ConsoleEmailService(EmailService):
    def __init__(self, quiet: bool = False) -> None:
        self._lock = RLock()
        self._sent: list[SentEmailRecord] = []
        self._quiet = quiet

    def _dispatch(
        self,
        to: str,
        email_type: Literal[
            "welcome", "password_reset", "order_confirmation", "order_shipped"
        ],
        subject: str,
        body: str,
    ) -> None:
        record = SentEmailRecord(
            to=to,
            type=email_type,
            subject=subject,
            body=body,
            sent_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        with self._lock:
            self._sent.append(record)

        if not self._quiet:
            print(
                f"\n[BeanBox Mock Email] -> To: {record.to} | Subject: {record.subject}\n{record.body}\n"
            )

    def send_welcome(self, to: str, name: str) -> None:
        self._dispatch(
            to=to,
            email_type="welcome",
            subject="Welcome to BeanBox — Freshly Roasted Indian Specialty Coffee",
            body=f"Namaste {name}, welcome to BeanBox! Use code WELCOME10 for 10% off your first roast.",
        )

    def send_password_reset(
        self, to: str, name: str, reset_token: str, reset_url: str
    ) -> None:
        self._dispatch(
            to=to,
            email_type="password_reset",
            subject="Reset your BeanBox password",
            body=f"Hi {name}, reset your password using this link (valid 15 mins): {reset_url}\nToken: {reset_token}",
        )

    def send_order_confirmation(
        self, to: str, customer_name: str, order: Order
    ) -> None:
        self._dispatch(
            to=to,
            email_type="order_confirmation",
            subject=f"Order Confirmed: {order.order_number} ({_format_inr(order.pricing.total_paise)})",
            body=(
                f"Hi {customer_name}, thank you for your BeanBox order {order.order_number}! "
                f"Total paid: {_format_inr(order.pricing.total_paise)} (includes 5% GST)."
            ),
        )

    def send_order_shipped(
        self, to: str, customer_name: str, order: Order
    ) -> None:
        self._dispatch(
            to=to,
            email_type="order_shipped",
            subject=f"Your BeanBox Order {order.order_number} Has Shipped!",
            body=(
                f"Hi {customer_name}, your freshly roasted coffee for order {order.order_number} "
                f"is on its way to {order.shipping_address.city}, {order.shipping_address.state}."
            ),
        )

    def get_sent_emails(self) -> list[SentEmailRecord]:
        with self._lock:
            return list(self._sent)
