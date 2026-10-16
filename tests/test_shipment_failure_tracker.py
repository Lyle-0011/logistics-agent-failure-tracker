from typing import Any

import pytest

from shipment_failure_tracker import ProofOfDelivery, ShipmentEvent, run_agent_step


class RecordingCapture:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None
        self.idempotency_key = ""

    def capture_error(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        self.payload = payload
        self.idempotency_key = idempotency_key
        return {"event_id": "recorded-event"}


def test_failed_pod_step_uses_stable_group_and_metadata_only() -> None:
    recorder = RecordingCapture()
    event = ShipmentEvent(
        shipment_id="SHIP-2048",
        event_id="EVT-17",
        event_type="delivery_attempted",
        agent_step="classify-pod",
        proof_of_delivery=(ProofOfDelivery("signed-receipt.jpg", "image/jpeg", 18432),),
    )

    with pytest.raises(ValueError, match="signature is unclear"):
        run_agent_step(
            event,
            lambda: (_ for _ in ()).throw(ValueError("signature is unclear")),
            recorder,
        )

    assert recorder.payload is not None
    assert recorder.payload["fingerprint"] == ["SHIP-2048", "classify-pod"]
    assert recorder.payload["context"]["proof_of_delivery"] == [
        {"name": "signed-receipt.jpg", "media_type": "image/jpeg", "size_bytes": 18432}
    ]
    assert recorder.idempotency_key == "shipment-error:EVT-17:classify-pod"
