FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command is overridden in docker-compose
CMD ["uvicorn", "fastapi-app:app", "--host", "0.0.0.0", "--port", "9000"]
