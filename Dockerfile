FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY scraper.py app.py networks.py ncaa_scraper.py ./
COPY static/ ./static/

ENV PORT=8100
EXPOSE 8100

VOLUME ["/app/data"]

CMD ["uv", "run", "app.py"]
