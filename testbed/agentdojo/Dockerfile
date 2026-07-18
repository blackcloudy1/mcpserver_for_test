FROM python:3.12-slim

ARG AGENTDOJO_VERSION=0.1.35

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN groupadd --system dojo \
    && useradd --system --gid dojo --home-dir /workspace dojo \
    && pip install --upgrade pip \
    && pip install "agentdojo==${AGENTDOJO_VERSION}"

COPY verify_install.py /usr/local/bin/verify_agentdojo.py

RUN mkdir -p /workspace/runs /workspace/custom_attacks \
    && chown -R dojo:dojo /workspace

USER dojo

CMD ["sleep", "infinity"]
