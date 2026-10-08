FROM python:3.12.4-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY apps/relay/ingress/forward.py /srv/forward.py
USER 10001:10001
CMD ["python", "/srv/forward.py"]
