FROM python:3.11-slim

WORKDIR /app

# Copy shared library first (better layer caching)
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

# Copy service code and install
COPY services/api/ /app/service/
RUN pip install --no-cache-dir /app/service

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
