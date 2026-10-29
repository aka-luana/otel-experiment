import logging
import random
import time

from fastapi import FastAPI
from opentelemetry import metrics

from telemetry import setup_telemetry

app = FastAPI(title="app-a")
setup_telemetry(app)

logger = logging.getLogger("app-a")
meter = metrics.get_meter("app-a")
work_counter = meter.create_counter("app_a.work", description="Chamadas ao endpoint /work")


@app.get("/work")
def work():
    delay = random.uniform(0.05, 0.5)
    time.sleep(delay)
    work_counter.add(1)
    logger.info("trabalho concluído em %.0f ms", delay * 1000)
    return {"service": "app-a", "latency_ms": round(delay * 1000)}