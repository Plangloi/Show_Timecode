# Multi-stage: python-rtmidi compiles a C extension against ALSA, needs a
# compiler + dev headers at build time only. websockets is pure Python.
# Final image keeps just the ALSA runtime lib — matters on a Pi (pull size,
# storage, attack surface).
FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libasound2-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --user websockets python-rtmidi

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libasound2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/root/.local/lib/python3.12/site-packages \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY qsys_tc_relay.py .

EXPOSE 8765
ENTRYPOINT ["python3", "qsys_tc_relay.py"]
# Default: free-run generator — works with zero hardware/config, good for
# testing the cue sheet. Override via `command:` in docker-compose.yml or
# `docker compose run --rm relay --core ... / --mtc ...`.
CMD ["--fake", "01:00:00:00"]
