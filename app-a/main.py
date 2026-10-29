import logging
import random
import time

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics

from telemetry import setup_telemetry

app = FastAPI(title="app-a")
setup_telemetry(app)

logger = logging.getLogger("app-a")
meter = metrics.get_meter("app-a")
work_counter = meter.create_counter("app_a.work", description="Chamadas ao endpoint /work")

APP_B_URL = "http://app-b:8000/work"

@app.get("/work")
def work():
    time.sleep(random.uniform(0.01, 0.1))
    work_counter.add(1)
    logger.info("app-a chamando app-b")
    try:
        resp = httpx.get(APP_B_URL, timeout=5)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("app-b falhou: %s", exc)
        raise HTTPException(status_code=502, detail="app-b falhou")
    return {"service": "app-a", "next": resp.json()}