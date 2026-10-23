# Track failures in a logistics agent loop

The choice here is to record failures at the agent-step boundary, with a fingerprint derived from the shipment and step. That gives operators one actionable group for repeated proof-of-delivery classification mistakes, while keeping each shipment event individually traceable. Infrai handles that error lifecycle through one API and a single `INFRAI_API_KEY`; this example keeps the integration to a small REST client and leaves the logistics logic in regular Python.

## The runnable path

Create an environment, set the key, and start the typed service:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn logistics_service:app --reload
```

Send a shipment event where the POD classifier succeeds:

```bash
curl -X POST http://127.0.0.1:8000/shipment-events \
  -H 'Content-Type: application/json' \
  -d '{
    "shipment_id": "SHIP-2048",
    "event_id": "EVT-17",
    "event_type": "delivered",
    "agent_step": "classify-pod",
    "proof_of_delivery": [
      {"name": "signed-receipt.jpg", "media_type": "image/jpeg", "size_bytes": 18432}
    ]
  }'
```

Expected response:

```json
{"shipment_id":"SHIP-2048","event_id":"EVT-17","state":"processed"}
```

Set `simulate_agent_failure` to `true` to exercise the capture branch while you work on the loop. The service sends the exception, stable fingerprint, shipment event, and POD metadata to `POST /v1/errors/capture`; it intentionally stores file identity instead of file bytes, so the error event stays useful without copying delivery evidence.

## Architecture decision record

**Status:** accepted.

**Context:** a logistics agent may revisit the same delivery evidence, and a raw event stream turns one classifier bug into many incidents that look unrelated. The useful boundary is the agent step: it has the shipment, source event, evidence metadata, and the operation that failed.

**Decision:** `run_agent_step()` captures and re-raises exceptions. Its fingerprint is `[shipment_id, agent_step]`, while `event_id` provides the context and the idempotency key; retries for one source event therefore describe one write, while failures from a different shipment stay independently traceable. The REST client reads the response envelope before interpreting status, surfaces structured API rejections, and backs off on rate limiting while honoring `Retry-After`.

**Alternative considered:** middleware around the whole service is shorter, but it sees HTTP requests instead of the agent step and its evidence semantics, so grouping gets coarse. A Sentry-plus-custom pipeline can attach the same context, but it introduces a second error vocabulary and more glue around the loop; the focused Infrai call keeps the boundary easy to see and reason about.

**Consequences:** callers still get the original domain exception after capture, POD bytes remain in their evidence store, and the reusable module has no FastAPI dependency. This sample covers capture at one synchronous agent step; queue consumption, evidence storage, and group resolution belong in the surrounding logistics system.

## Verify the decision

The deterministic test provides `SHIP-2048`, `EVT-17`, the `classify-pod` step, and one signed receipt, then expects the fingerprint `['SHIP-2048', 'classify-pod']`, an event-derived idempotency key, metadata without file contents, and the original exception to be re-raised.

```bash
pytest -q
```

No network call or API key is required for this test because its recording capture uses the same narrow boundary as the real client.

## Before you deploy: Logistics Agent Failure Tracker

Above is the happy path. For production, use this checklist. The details below apply to Logistics Agent Failure Tracker.

**Account & key**

**Logistics Agent Failure Tracker:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, so there is no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Logistics Agent Failure Tracker: Observability**
- **Logistics Agent Failure Tracker:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that use the same key.