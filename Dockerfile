FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core core
COPY ingest ingest
COPY retrieval retrieval
COPY agent agent
COPY generation generation
COPY api api
COPY eval eval
COPY data data
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
