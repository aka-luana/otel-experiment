import logging
import os
import random
import time

from fastapi import FastAPI, HTTPException
from opentelemetry import metrics

from telemetry import setup_telemetry

app = FastAPI(title="app-c")
setup_telemetry(app)

logger = logging.getLogger("app-c")
meter = metrics.get_meter("app-c")
work_counter = meter.create_counter("app_c.work", description="Chamadas ao endpoint /work")

# Probabilidade de falha (0.0 a 1.0). Fica em 0 por enquanto; usaremos na Etapa 5.                                                                                                                                                     
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))

@app.get("/work")
def work():
    delay = random.uniform(0.02, 0.3)
    time.sleep(delay)
    work_counter.add(1)
    if random.random() < ERROR_RATE:
        logger.error("falha simulada no app-c")
        raise HTTPException(status_code=500, detail="falha simulada no app-c")
    logger.info("app-c concluiu em %.0f ms", delay * 1000)
    return {"service": "app-c", "latency_ms": round(delay * 1000)}