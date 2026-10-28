# Base image is overridable so users behind a registry mirror can still build:
#   docker build --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim .
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ANINEST_MCP_TRANSPORT=streamable-http \
    ANINEST_MCP_HOST=0.0.0.0 \
    ANINEST_MCP_PORT=8765

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY eval ./eval

RUN pip install --upgrade pip && pip install .

# Run as a non-root user; the server only needs outbound HTTP.
RUN useradd --create-home --uid 10001 aninest
USER aninest

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket;s=socket.create_connection(('127.0.0.1',8765),3);s.close()"

CMD ["aninest-mcp"]
