FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY scraper.py app.py networks.py ncaa_scraper.py fetch_fbschedules.py fetch_logos.py ./
COPY static/ ./static/

# ── stealth-fetcher: sibling project (github.com/kylegalloway/stealth-fetcher),
# bundled in so scraper.py's Cloudflare-bypass fallback (_scrape_via_stealth_fetcher)
# works from inside the container instead of just failing closed. Pulled in
# via an extra build context pointing at ../stealth-fetcher on the host —
# see .taskfiles/media.yaml's --build-context flag in the homelab repo.
WORKDIR /stealth-fetcher
COPY --from=stealth-fetcher pyproject.toml uv.lock ./
COPY --from=stealth-fetcher stealth_fetcher/ ./stealth_fetcher/
RUN uv sync --frozen --no-dev \
    && uv run playwright install-deps firefox \
    && uv run camoufox fetch \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PORT=8100
EXPOSE 8100

VOLUME ["/app/data"]

CMD ["uv", "run", "app.py"]
