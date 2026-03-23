FROM python:3.11-slim

WORKDIR /app

# Copy shared library first (better layer caching)
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

# Copy service code and install
COPY services/crawler/ /app/service/
RUN pip install --no-cache-dir /app/service

CMD ["python", "-m", "crawler.main"]
