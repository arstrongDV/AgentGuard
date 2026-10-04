# AgentGuard gateway (also runs the mock MCP servers with a different command).
# Build context: the repository root (docker-compose.yml sets it).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv/agentguard/backend

COPY backend/requirements.txt backend/requirements-dev.txt backend/requirements-ml.txt ./
ARG WITH_ML=1
RUN pip install -r requirements-dev.txt \
 && if [ "$WITH_ML" = "1" ]; then pip install -r requirements-ml.txt; fi

# The injection model is baked into the image (no downloads at runtime), and its SHA-256 is checked
# against policy.yaml (supply_chain.pinned) every time it is loaded.
COPY backend/scripts/download_models.py scripts/download_models.py
RUN if [ "$WITH_ML" = "1" ]; then python scripts/download_models.py; fi

COPY backend/ ./
# Baked defaults; docker-compose mounts the live repo at /workspace and points POLICY_PATH there.
COPY policy.yaml /srv/agentguard/policy.yaml
COPY feeds /srv/agentguard/feeds

RUN useradd --create-home --uid 1000 agentguard && mkdir -p data && chown -R agentguard /srv/agentguard
USER agentguard

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
