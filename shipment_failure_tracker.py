"""Domain decision for observing failures in a logistics agent loop."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class ProofOfDelivery:
    name: str
    media_type: str
    size_bytes: int


@dataclass(frozen=True)
class ShipmentEvent:
    shipment_id: str
    event_id: str
    event_type: str
    agent_step: str
    proof_of_delivery: tuple[ProofOfDelivery, ...] = ()


class ErrorCapture(Protocol):
    def capture_error(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...


def run_agent_step(
    event: ShipmentEvent,
    operation: Callable[[], T],
    capture: ErrorCapture,
) -> T:
    """Run one step, record a domain-shaped failure, then preserve the exception."""
    try:
        return operation()
    except Exception as exc:
        capture.capture_error(
            {
                "title": f"Shipment agent failed during {event.agent_step}",
                "message": f"{type(exc).__name__}: {exc}",
                "level": "error",
                "fingerprint": [event.shipment_id, event.agent_step],
                "exception": traceback.format_exc(),
                "context": {
                    "shipment_id": event.shipment_id,
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "agent_step": event.agent_step,
                    "proof_of_delivery": [
                        {
                            "name": item.name,
                            "media_type": item.media_type,
                            "size_bytes": item.size_bytes,
                        }
                        for item in event.proof_of_delivery
                    ],
                },
            },
            idempotency_key=f"shipment-error:{event.event_id}:{event.agent_step}",
        )
        raise
