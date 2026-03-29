FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY tools/ ./tools/
COPY mcp_server.py ./

EXPOSE 8000

CMD ["uv", "run", "python", "mcp_server.py"]
