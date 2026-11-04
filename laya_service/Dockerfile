FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 USE_TF=0 HF_HOME=/models/huggingface
# Isolated worker: Torch / Transformers do not alter InsightFace backend dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --timeout 120 'torch==2.9.1+cpu' --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 120 'laya==0.4.17' 'fastapi==0.115.12' 'uvicorn==0.34.2'
COPY server.py .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
