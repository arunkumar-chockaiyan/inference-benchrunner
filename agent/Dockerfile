FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -r -u 1001 -g root appuser

COPY agent.py .

RUN chown -R appuser:root /app && chmod -R g=u /app

USER appuser

EXPOSE 8787

CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8787"]
