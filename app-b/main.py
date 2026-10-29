import logging
import random
import time

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics

from telemetry import setup_telemetry

app = FastAPI(title="app-b")
setup_telemetry(app)

logger = logging.getLogger("app-b")
meter = metrics.get_meter("app-b")
work_counter = meter.create_counter("app_b.work", description="Chamadas ao endpoint /work")

APP_C_URL = "http://app-c:8000/work"

@app.get("/work")
def work():
    time.sleep(random.uniform(0.01, 0.1))
    work_counter.add(1)
    logger.info("app-b chamando app-c")
    try:
        resp = httpx.get(APP_C_URL, timeout=5)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("app-c falhou: %s", exc)
        raise HTTPException(status_code=502, detail="app-c falhou")
    return {"service": "app-b", "next": resp.json()}