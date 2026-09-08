FROM python:3.12-slim

WORKDIR /app

# Dependencies first so the layer caches unless requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what serves requests. The pipeline and its scraping dependencies stay out
# of the image entirely.
COPY rag/ ./rag/
COPY api/ ./api/

ENV PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
