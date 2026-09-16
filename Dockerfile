FROM node:24-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
RUN useradd --uid 10001 --create-home quant && mkdir /state && chown quant:quant /state
COPY app/ app/
COPY data_engine/ data_engine/
COPY quant_engine/ quant_engine/
COPY scripts/ scripts/
COPY --from=frontend /src/frontend/dist/ frontend/dist/
USER quant
ENV QS_STORAGE_DIR=/state
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
