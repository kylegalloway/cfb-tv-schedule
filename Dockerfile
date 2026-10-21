FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

# trixie, not bookworm: by 2026-10-20 the image's CRITICALs (zlib, sqlite,
# glib, libxml2) were all will_not_fix/fix_deferred on bookworm, so no
# rebuild there could clear them.
#
# python3.14 matches .python-version. On a 3.12 base, uv quietly downloaded
# a second interpreter (3.15, since .python-version wasn't copied in) for
# the app — 112 MB plus a bundled pip with its own CVEs. Never download one
# again: a mismatch should fail the build, not grow the image. No uv cache
# either; it was another ~400 MB nothing reads at runtime.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1
#
# The uv base tag isn't rebuilt often, so its Debian packages lag behind
# bookworm-security (Trivy, 2026-10-19: openssl, gnutls, krb5, perl, pcre2,
# libcap with fixes available). Patch them here, before the slow
# stealth-fetcher layer, so playwright's apt-get installs on top of current
# packages too. The layer cache keeps the old upgrade, so rebuild with
# --no-cache to pick up newer fixes (editing this comment doesn't bust it).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# ── stealth-fetcher: sibling project (github.com/kylegalloway/stealth-fetcher),
# bundled in so scraper.py's Cloudflare-bypass fallback (_scrape_via_stealth_fetcher)
# works from inside the container instead of just failing closed. Pulled in
# via an extra build context pointing at ../stealth-fetcher on the host —
# see .taskfiles/media.yaml's --build-context flag in the homelab repo.
#
# This goes first on purpose: it downloads a real Firefox (camoufox) and
# runs apt-get, the slowest step by far. Anything COPY'd
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

COPY .python-version pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY scraper.py app.py networks.py ncaa_scraper.py kstp_scraper.py schedule.py stations.py logos.py scores.py fetch_fbschedules.py fetch_logos.py ./
COPY static/ ./static/

# The python base installs pip system-wide and bundles another copy for
# `python -m ensurepip`, and pip vendors its own urllib3/msgpack/setuptools,
# which Trivy flags. uv manages both venvs here and nothing uses pip, so
# remove both. Last, so it never invalidates the camoufox layer.
RUN python3 -m pip uninstall -y --root-user-action=ignore pip \
    && rm -rf /usr/local/lib/python3*/ensurepip/_bundled

ENV PORT=8100
EXPOSE 8100

VOLUME ["/app/data"]

CMD ["uv", "run", "app.py"]
