FROM python:3.12-slim

ARG VERSION=0.1.0
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Classifieds Tracker" \
      org.opencontainers.image.description="Self-hosted classifieds watcher with saved searches, a global location and alerts" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$VCS_REF

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8080 \
    APP_VERSION=$VERSION

# /data is created owned by the app user so a fresh named volume inherits that ownership.
RUN useradd --system --create-home --uid 10001 tracker \
 && mkdir /data && chown tracker /data

WORKDIR /srv
COPY app/ /srv/app/

USER tracker
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','8080'),timeout=4)"

CMD ["python", "/srv/app/server.py"]
