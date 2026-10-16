"""Typed HTTP boundary for the logistics agent example."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrai_client import InfraiClient, InfraiError
from shipment_failure_tracker import ProofOfDelivery, ShipmentEvent, run_agent_step


class ProofOfDeliveryRequest(BaseModel):
    name: str
    media_type: str
    size_bytes: int = Field(ge=0)


class ShipmentEventRequest(BaseModel):
    shipment_id: str
    event_id: str
    event_type: str
    agent_step: str
    proof_of_delivery: list[ProofOfDeliveryRequest] = Field(default_factory=list)
    simulate_agent_failure: bool = False


class ProcessingResult(BaseModel):
    shipment_id: str
    event_id: str
    state: str


app = FastAPI(title="Logistics agent failure tracking")


@app.post("/shipment-events", response_model=ProcessingResult)
def process_shipment_event(request: ShipmentEventRequest) -> ProcessingResult:
    event = ShipmentEvent(
        shipment_id=request.shipment_id,
        event_id=request.event_id,
        event_type=request.event_type,
        agent_step=request.agent_step,
        proof_of_delivery=tuple(
            ProofOfDelivery(name=item.name, media_type=item.media_type, size_bytes=item.size_bytes)
            for item in request.proof_of_delivery
        ),
    )

    def agent_operation() -> str:
        if request.simulate_agent_failure:
            raise ValueError("proof-of-delivery classification needs review")
        return "processed"

    try:
        state = run_agent_step(event, agent_operation, InfraiClient())
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=client_status, detail={"code": exc.code, **exc.detail}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ProcessingResult(shipment_id=event.shipment_id, event_id=event.event_id, state=state)
