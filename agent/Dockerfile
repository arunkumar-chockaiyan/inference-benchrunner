FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

EXPOSE 8787

CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8787"]
