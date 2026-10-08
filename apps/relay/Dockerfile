FROM python:3.12.4-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv:/srv/apps/relay
WORKDIR /srv
COPY apps/relay/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --no-create-home relay
COPY packages/secure_wire /srv/packages/secure_wire
COPY apps/relay/researchhub_relay /srv/apps/relay/researchhub_relay
USER 10001:10001
CMD ["python", "-m", "uvicorn", "researchhub_relay.main:app", "--host", "0.0.0.0", "--port", "8443", "--ssl-certfile", "/tls/server.crt", "--ssl-keyfile", "/tls/server.key", "--no-access-log", "--log-level", "critical", "--timeout-keep-alive", "3", "--limit-concurrency", "64", "--backlog", "64", "--h11-max-incomplete-event-size", "16384"]
