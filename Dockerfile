FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first, separately from app code, so this layer is
# cached across rebuilds that only touch sagynysh/.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY sagynysh/ sagynysh/
COPY assets/ assets/
RUN uv sync --frozen --no-dev

ENV DB_PATH=/app/data/sagynysh.db
VOLUME ["/app/data"]

CMD ["uv", "run", "python", "-m", "sagynysh"]
