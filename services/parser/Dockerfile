FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first (better layer caching)
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

# Copy service code and install
COPY services/parser/ /app/service/
RUN pip install --no-cache-dir /app/service

CMD ["python", "-m", "parser.main"]
