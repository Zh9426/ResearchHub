FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 researchhub
COPY apps/api /app/apps/api
COPY packages /app/packages
COPY infrastructure/migrations /app/infrastructure/migrations
COPY scripts/backup_data.py /app/scripts/backup_data.py
USER researchhub
EXPOSE 8000
CMD ["sh", "-c", "alembic -c infrastructure/migrations/alembic.ini upgrade head && uvicorn apps.api.researchhub.main:app --host 0.0.0.0 --port 8000"]
