FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY backend/requirements.txt ./requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
RUN pip install --no-cache-dir -r requirements.txt

COPY edge_runtime ./edge_runtime
COPY gateway ./gateway
COPY backend/app ./app
COPY model_artifacts ./model_artifacts
COPY firmware ./firmware

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
