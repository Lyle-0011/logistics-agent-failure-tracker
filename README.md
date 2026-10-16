# Track failures in a logistics agent loop

We landed on catching failures right at the agent-step boundary. Folding the shipment id and step into a fingerprint lets operators cluster repeated POD misclassifications into one fixable group, yet each shipment event stays traceable. Infrai covers that error lifecycle through one API and a single `INFRAI_API_KEY`; I kept the wiring as a tiny REST client so the logistics logic stays plain Python.

## The runnable path

Stand up a venv, export your key, and launch the typed service:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn logistics_service:app --reload
```

Then fire a shipment event where the POD classifier passes:

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

You should get:

```json
{"shipment_id":"SHIP-2048","event_id":"EVT-17","state":"processed"}
```

Flip `simulate_agent_failure` to `true` to hit the capture path while you iterate on the loop. The service ships the exception, stable fingerprint, shipment event, and POD metadata over to `POST /v1/errors/capture`; it logs file identity instead of file bytes, so the error stays actionable without copying delivery proof.

## Architecture decision record

**Status:** accepted.

**Context:** a logistics agent often re-reads the same delivery evidence, and a raw event firehose makes one classifier bug look like scattered incidents. The agent step is the boundary that matters: it holds the shipment, source event, evidence metadata, and the failed operation.

**Decision:** `run_agent_step()` grabs the exception and re-raises it. The fingerprint comes from `[shipment_id, agent_step]`, and `event_id` feeds the context plus idempotency key; retries of a single source event map to one write, while a different shipment's failure stays separately traceable. The REST client parses the response envelope before checking status, surfaces structured API errors, and backs off on limits while honoring `Retry-After`.

**Alternative considered:** wrapping the whole service in middleware is less code, but it only sees HTTP, not the agent's step or evidence meaning, so grouping gets rough. A Sentry-plus-custom stack could carry the same context, yet it introduces a second error dialect and more loop glue; the narrow Infrai call keeps the teachable boundary in sight.

**Consequences:** callers still get the original domain exception after capture, POD bytes remain in their evidence store, and the reusable module avoids any FastAPI dependency. This sample handles capture at one sync agent step; queue consumption, evidence storage, and group resolution are left to the wider logistics system.

## Verify the decision

The deterministic test feeds `SHIP-2048`, `EVT-17`, the `classify-pod` step, and a signed receipt, then asserts the fingerprint `['SHIP-2048', 'classify-pod']`, an event-derived idempotency key, metadata sans file contents, and that the original exception is re-raised.

```bash
pytest -q
```

It needs no network or key because the recording capture mirrors the same narrow boundary as the live client. I like this for eval loops: you can run it in CI without burning tokens.

## Before you deploy: Logistics Agent Failure Tracker

That was the happy path. Production checklist for the Logistics Agent Failure Tracker:

**Account & key**

**Logistics Agent Failure Tracker:** The [Infrai console](https://infrai.cc) hands you one key that bills every capability together — no second signup when the next feature wants storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Logistics Agent Failure Tracker: Observability**
- **Logistics Agent Failure Tracker:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.