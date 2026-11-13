from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal

from app.models.domain import Order

EmailType = Literal[
    "welcome",
    "email_verification",
    "password_reset",
    "order_confirmation",
    "order_shipped",
    "order_expired",
    "order_refunded",
    "low_stock_digest",
    "security_notification",
]


@dataclass
class SentEmailRecord:
    to: str
    subject: str
    type: EmailType
    body: str
    sent_at: str


class EmailService(ABC):
    @abstractmethod
    def send_welcome(self, to: str, name: str) -> None: ...

    @abstractmethod
    def send_email_verification(
        self, to: str, name: str, verify_token: str, verify_url: str
    ) -> None: ...

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
    def send_order_expired(
        self, to: str, customer_name: str, order: Order
    ) -> None: ...

    @abstractmethod
    def send_order_refunded(
        self, to: str, customer_name: str, order: Order, amount_paise: int, reason: str = ""
    ) -> None: ...

    @abstractmethod
    def send_low_stock_digest(
        self, to: str, admin_name: str, low_stock_items: list[dict[str, Any]]
    ) -> None: ...

    @abstractmethod
    def send_password_changed_notification(
        self, to: str, name: str, ip: str, user_agent: str
    ) -> None: ...

    @abstractmethod
    def send_2fa_status_notification(
        self, to: str, name: str, enabled: bool, ip: str, user_agent: str
    ) -> None: ...

    @abstractmethod
    def send_new_device_login_notification(
        self, to: str, name: str, ip: str, user_agent: str
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
        email_type: EmailType,
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

    def send_email_verification(
        self, to: str, name: str, verify_token: str, verify_url: str
    ) -> None:
        self._dispatch(
            to=to,
            email_type="email_verification",
            subject="Verify your BeanBox email address",
            body=(
                f"Namaste {name}, verify your BeanBox email (valid for 24 hours): "
                f"{verify_url}\nToken: {verify_token}"
            ),
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

    def send_order_expired(
        self, to: str, customer_name: str, order: Order
    ) -> None:
        self._dispatch(
            to=to,
            email_type="order_expired",
            subject=f"BeanBox Order {order.order_number} Expired (Payment Timeout)",
            body=(
                f"Hi {customer_name}, order {order.order_number} has expired because payment "
                "was not received within the 30-minute reservation window. Reserved stock has been released."
            ),
        )

    def send_order_refunded(
        self, to: str, customer_name: str, order: Order, amount_paise: int, reason: str = ""
    ) -> None:
        reason_text = f" (Reason: {reason})" if reason else ""
        self._dispatch(
            to=to,
            email_type="order_refunded",
            subject=f"Refund Issued for BeanBox Order {order.order_number}",
            body=(
                f"Hi {customer_name}, a refund of {_format_inr(amount_paise)} has been processed "
                f"for order {order.order_number}{reason_text}. Funds typically reflect in 5-7 business days."
            ),
        )

    def send_low_stock_digest(
        self, to: str, admin_name: str, low_stock_items: list[dict[str, Any]]
    ) -> None:
        lines = [f"Hi {admin_name}, here is the daily BeanBox roastery low-stock alert:"]
        for it in low_stock_items:
            lines.append(f" - {it.get('product_name')} ({it.get('variant_label')}): Stock = {it.get('stock')}")
        self._dispatch(
            to=to,
            email_type="low_stock_digest",
            subject=f"BeanBox Roastery Alert: {len(low_stock_items)} Variants Low on Stock",
            body="\n".join(lines),
        )

    def send_password_changed_notification(
        self, to: str, name: str, ip: str, user_agent: str
    ) -> None:
        self._dispatch(
            to=to,
            email_type="security_notification",
            subject="Security Alert: Your BeanBox password was changed",
            body=(
                f"Hi {name}, the password for your BeanBox account was just changed "
                f"(IP: {ip}, Device: {user_agent}). Other active sessions have been signed out. "
                "If you did not make this change, reset your password immediately and review your Security settings."
            ),
        )

    def send_2fa_status_notification(
        self, to: str, name: str, enabled: bool, ip: str, user_agent: str
    ) -> None:
        state_word = "enabled" if enabled else "disabled"
        self._dispatch(
            to=to,
            email_type="security_notification",
            subject=f"Security Alert: Two-factor authentication {state_word} on BeanBox",
            body=(
                f"Hi {name}, two-factor authentication (2FA) was {state_word} on your BeanBox account "
                f"(IP: {ip}, Device: {user_agent}). If you did not authorize this change, "
                "secure your account immediately by changing your password and revoking unfamiliar sessions."
            ),
        )

    def send_new_device_login_notification(
        self, to: str, name: str, ip: str, user_agent: str
    ) -> None:
        self._dispatch(
            to=to,
            email_type="security_notification",
            subject="Security Alert: New sign-in to your BeanBox account from a new device",
            body=(
                f"Hi {name}, we noticed a new sign-in to your BeanBox account from an unrecognized device "
                f"(Device: {user_agent}, IP: {ip}). If this was you, you can ignore this message. "
                "If you do not recognize this sign-in, revoke the session and change your password immediately."
            ),
        )

    def get_sent_emails(self) -> list[SentEmailRecord]:
        with self._lock:
            return list(self._sent)
