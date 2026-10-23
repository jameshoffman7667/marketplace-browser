FROM python:3.12-slim

LABEL org.opencontainers.image.title="Marketplace Browser" \
      org.opencontainers.image.description="Self-hosted classifieds watcher with saved searches, a global location and alerts" \
      org.opencontainers.image.source="https://github.com/jameshoffman7667/marketplace-browser"

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=3501

# Fixed non-root user 1000:100 (the server's PUID/PGID). /data is created owned by it; a bind-mounted
# host folder must be owned by 1000:100 too. The version comes from the VERSION file, not from a build arg.
RUN mkdir /data && chown 1000:100 /data

WORKDIR /srv
COPY VERSION /srv/VERSION
COPY app/ /srv/app/

USER 1000:100
VOLUME /data
EXPOSE 3501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:${PORT}/healthz',timeout=4)"

CMD ["python", "/srv/app/server.py"]
