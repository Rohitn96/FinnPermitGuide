FROM python:3.12-slim

WORKDIR /app

# Install deps first (cached layer unless requirements change)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy only the application code needed at runtime
COPY rag/ ./rag/
COPY api/ ./api/

# Ensure logs directory exists
RUN mkdir -p logs

ENV PORT=8000
ENV USE_PINECONE=true

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
