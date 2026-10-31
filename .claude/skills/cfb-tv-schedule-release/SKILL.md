---
name: cfb-tv-schedule-release
description: Updates the dependencies and base image of cfb-tv-schedule (ota-sports-schedule), tests it, and redeploys it to the media VM through the homelab repo's task. Use when asked to update or redeploy cfb-tv-schedule, the OTA schedule site or the live site, fix CVEs in its image, or ship a code change to production.
---

# cfb-tv-schedule Release

The live site is `http://10.0.0.162:8100`. The image is built on the media VM from rsynced source and bundles the sibling `stealth-fetcher` repo. The deploy task is in the homelab repo at `~/src/homelab`.

## Check before you change

1. Run `git status -sb` in this repo and in `~/src/stealth-fetcher`.
2. If either repo has uncommitted work that you did not make, stop and ask Kyle. The deploy sends the working tree, including uncommitted files.
3. If a change also needs `stealth-fetcher`, use that repo's `stealth-fetcher-update` skill first.

## Update dependencies

Skip this section when you only ship a code change.

- **One package, for a CVE:** run `uv lock --upgrade-package <package>`.
- **Everything:** run `uv lock --upgrade`, then read the diff of `uv.lock` for major version changes.

## Test

1. Run `uv sync --frozen`.
2. Run `uv run pytest`. This runs the offline tests.
3. Stop if a test fails. Do not deploy.
4. If a scraper changed, run `uv run pytest -m live`. This test reaches the real sites, so a failure can mean that an upstream site changed.

## Deploy

**CAUTION:** The site restarts during the deploy. A full rebuild takes about 4.5 minutes. An app-only change takes about 20 seconds.

1. Run `task -d ~/src/homelab media:deploy-cfb-schedule`.
2. Make sure the output ends with `refresh HTTP 200`.

## Rebuild for CVE fixes

A cached build keeps the old base image and the old `apt-get upgrade` layer. The deploy task uses the cache, so it does not pick up newer OS fixes. Do these steps after the task when OS or base image findings remain:

1. Run `ssh kyle@10.0.0.162 "docker buildx build --pull --no-cache --build-context stealth-fetcher=build/stealth-fetcher -t cfb-tv-schedule:latest -t localhost/cfb-tv-schedule:latest --load build/cfb-tv-schedule"`.
2. Run `ssh kyle@10.0.0.162 "cd /opt/appdata && docker compose up -d --no-deps cfb-tv-schedule"`.
3. Run `ssh kyle@10.0.0.162 "curl -fsS -X POST -o /dev/null -w '%{http_code}\n' --retry 10 --retry-delay 3 --retry-connrefused --retry-all-errors --max-time 300 http://localhost:8100/api/refresh"`. Make sure it prints `200`.

## Verify

1. Run `curl -s -o /dev/null -w '%{http_code}\n' http://10.0.0.162:8100/`. Make sure it prints `200`.
2. Run `curl -s http://10.0.0.162:8100/api/games | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["games"]), "games, degraded:", d["degraded"])'`. The game count must not be `0`. Report the `degraded` value to Kyle if it shows a problem.
3. Run `ssh kyle@10.0.0.162 'docker logs --tail 20 cfb-tv-schedule'`. Look for scrape errors.
4. Run `task -d ~/src/homelab media:check-all`.
5. For a CVE update, use the `homelab-trivy` skill in the homelab repo to rescan the media VM.

## Rules

- Keep the Dockerfile's camoufox font list in step with `FINGERPRINT_OS` in `stealth_fetcher/engines.py`. Change both together.
- Update `CHANGELOG.md` for a change that users can see.
- Commit only when Kyle asks, and follow `~/.claude/rules/git-conventions.md`.
- Never push. Say what is committed and ready, and that Kyle must push it.

## Report

Give the commit deployed, whether the working tree was clean, the refresh result and the game count.
