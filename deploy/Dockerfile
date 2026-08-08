FROM node:20-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock LICENSE README.md ./
COPY drift ./drift
COPY demo_target ./demo_target
COPY scripts ./scripts
COPY licence ./licence
COPY --from=webbuild /web/dist ./web/dist

RUN uv sync --frozen --no-editable && \
    useradd --create-home --uid 1001 drift && chown -R drift:drift /app
USER drift

ENV SERVICE=api
CMD ["sh", "-c", "if [ \"$SERVICE\" = \"demo\" ]; then exec uvicorn demo_target.api:app --host 0.0.0.0 --port $PORT; else exec uvicorn drift.api:app --host 0.0.0.0 --port $PORT; fi"]
