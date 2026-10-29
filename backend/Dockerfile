FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 DATABASE_PATH=/data/maintenance.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir "torch>=2.2,<3" --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser && mkdir /data && chown appuser:appuser /data
COPY --chown=appuser:appuser app ./app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
