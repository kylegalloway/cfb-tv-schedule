FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# ── stealth-fetcher: sibling project (github.com/kylegalloway/stealth-fetcher),
# bundled in so scraper.py's Cloudflare-bypass fallback (_scrape_via_stealth_fetcher)
# works from inside the container instead of just failing closed. Pulled in
# via an extra build context pointing at ../stealth-fetcher on the host —
# see .taskfiles/media.yaml's --build-context flag in the homelab repo.
#
# This goes first on purpose: it downloads a real Firefox (camoufox) and
# runs apt-get, which takes 10+ minutes under emulation. Anything COPY'd
# above it would rebuild it on every change, so the app's own files come
# after it, least often changed first.
WORKDIR /stealth-fetcher
COPY --from=stealth-fetcher pyproject.toml uv.lock ./
COPY --from=stealth-fetcher stealth_fetcher/ ./stealth_fetcher/
RUN uv sync --frozen --no-dev \
    && uv run playwright install-deps firefox \
    && uv run camoufox fetch \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY scraper.py app.py networks.py ncaa_scraper.py kstp_scraper.py schedule.py stations.py logos.py fetch_fbschedules.py fetch_logos.py ./
COPY static/ ./static/

ENV PORT=8100
EXPOSE 8100

VOLUME ["/app/data"]

CMD ["uv", "run", "app.py"]
