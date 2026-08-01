#!/usr/bin/env bash
# msi-deploy.sh — incremental-capable deploy.
#
# Modes:
#   FULL        — full astro build to dist/, published to WWW with --delete.
#   INCREMENTAL — astro build to dist-inc/ with MSI_INCREMENTAL_SLUGS_FILE
#                 pointing at a slug list; only those articles render. Published
#                 with rsync --update so untouched article HTML in WWW survives.
#
# Mode selection (first match wins):
#   --full flag → FULL
#   dist/ missing or WWW empty → FULL
#   last full build > FULL_BUILD_REFRESH_HOURS → FULL
#   structural file changed in git range → FULL
#   slug count > MAX_INCREMENTAL_SLUGS → FULL (with-everything rebuild)
#   incremental build fails → fall back to FULL automatically
#   otherwise → INCREMENTAL

set -euo pipefail

# ---------- Config ----------
REPO_DIR="$HOME/work/main-street-independent"
LIVE_DIR="$HOME/sites/mainstreetindependent"
WWW_DIR="/var/www/mainstreetindependent"
LOCK_FILE="/tmp/msi-deploy.lock"
# Shared by ALL astro builds on the box (this deploy AND the author pool's
# publish_cycle.py). Serializes dist/ writes and bounds memory (no two ~7GB
# builds at once -> no OOM). 2026-06-03.
BUILD_LOCK_FILE="/tmp/msi-astro-build.lock"
BUILD_LOCK_WAIT="${MSI_BUILD_LOCK_WAIT:-600}"
LOG_FILE="$HOME/msi-deploy.log"
STATE_FILE="$HOME/.msi-deploy-state.json"
SLUGS_FILE="/tmp/msi-incremental-slugs.txt"
NODE_HEAP_MB=10240  # 2026-06-03: restored after RAM upgrade CPX32->CPX42 (8GB->16GB, 15GB total, 8 vCPU); ~6GB build working set fits with headroom
FULL_BUILD_REFRESH_HOURS=26
MAX_INCREMENTAL_SLUGS=2000          # past this, FULL is cheaper than incremental
SMOKE_HOST="https://mainstreetindependent.com"
SMOKE_RESOLVE="mainstreetindependent.com:443:127.0.0.1"   # bypass CDN

STRUCTURAL_REGEX='^(src/(styles|components|layouts|pages|lib|plugins)/|public/fonts/|astro\.config\.mjs|src/content(/config\.ts|\.config\.ts)|package(-lock)?\.json|tsconfig\.json)'

# ---------- Args ----------
FORCE_FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) FORCE_FULL=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG_FILE"; }

# ---------- Lock ----------
exec 200>"$LOCK_FILE"
flock -n 200 || { log "already running"; exit 0; }

# In-flight detection — checked at TWO points:
#   1. After pull + ora-project/ rsync (Python files are safe to update
#      mid-run; modules are loaded into memory at import time, so on-disk
#      changes don't affect already-running processes — they just get
#      picked up by the NEXT process start).
#   2. Before src/ rsync, build, publish (these write into the deploy
#      target and must NOT race with article authoring or image sweeps).
# Splitting the guard this way fixes the chip's observation that
# multi-hour runs blocked all code deploys to LIVE: the Python sync is
# decoupled from the build guard. 2026-05-28.
msi_in_flight() {
  pgrep -af "unified_production\.py|backfill_orchestrator\.py|article_image_sweeper\.py|news_index\.py|article_generator\.py" > /dev/null
}

# ---------- State helpers ----------
read_state() {
  if [ -f "$STATE_FILE" ]; then
    python3 -c "import json; print(json.load(open('$STATE_FILE')).get('$1',''))"
  else
    echo ""
  fi
}
write_state() {
  python3 - "$@" << 'PYEOF'
import json, sys, os
path = os.path.expanduser("~/.msi-deploy-state.json")
try:
    with open(path) as f: d = json.load(f)
except Exception:
    d = {}
for kv in sys.argv[1:]:
    k, _, v = kv.partition("=")
    d[k] = v
with open(path, "w") as f: json.dump(d, f, indent=2)
PYEOF
}

# ---------- Pull ----------
cd "$REPO_DIR"
BEFORE=$(git rev-parse HEAD)
git fetch origin main 2>&1 | tail -3 >> "$LOG_FILE"
if ! git merge --ff-only origin/main 2>&1 | tail -3 >> "$LOG_FILE"; then
  log "ff-only failed: diverged; resetting to origin/main"
  git reset --hard origin/main 2>&1 | tail -3 >> "$LOG_FILE"
fi
AFTER=$(git rev-parse HEAD)

# ---------- Harvest live content → git (publish commits, revived) ----------
# Articles and columns are authored/enriched in LIVE (author pool + hourly
# sweeps); the repo is their version-control archive. Mirror LIVE → REPO and
# batch-commit BEFORE the repo→live rsyncs below, so repo bytes are always
# live-identical when the `rsync --update` runs. The harvest mirrors
# deletions too (all content collections since 2026-07-11), so those rsyncs
# cannot resurrect content deleted from LIVE — before that, a deleted column
# survived in the repo and was copied back into LIVE on every tick.
# Non-fatal: a failed harvest must never block a code deploy.
HARVEST="$REPO_DIR/ora-project/scripts/harvest-articles-to-git.sh"
if [ -x "$HARVEST" ]; then
  if MSI_DEPLOY_LOCK_HELD=1 MSI_REPO_DIR="$REPO_DIR" MSI_LIVE_DIR="$LIVE_DIR" \
      "$HARVEST" >> "$LOG_FILE" 2>&1; then
    AFTER=$(git rev-parse HEAD)   # harvest may have committed
  else
    log "content harvest failed (non-fatal; see msi-harvest.log)"
  fi
fi

# ---------- Sync ora-project/ to LIVE (always — safe mid-run) ----------
# Per-runtime Python modules are loaded into memory at import time, so
# updating files on disk during a long-running orchestrator/article-gen
# is safe: the running process keeps its in-memory copy; the NEXT process
# start picks up the new code. This sync therefore runs even when MSI is
# in flight, so code commits flow REPO -> /sites/ without waiting hours
# for the orchestrator to finish.
mkdir -p "$LIVE_DIR/ora-project" "$LIVE_DIR/src"
rsync -a --delete-after \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "state/" \
  --exclude "clusters/" \
  --exclude "data/hector-training-corpus/" \
  "$REPO_DIR/ora-project/" "$LIVE_DIR/ora-project/"

# ---------- In-flight guard for src/ rsync + build + publish ----------
# These write into the deploy target and must not race with article
# authoring or image sweeps. The ora-project/ sync above has already
# run, so even when we exit here the code half of the deploy has
# completed.
if msi_in_flight; then
  # Staleness override (2026-06-02): continuous production (the cycle's
  # news/article work) must not starve PUBLISHING indefinitely. If the last
  # successful publish is older than MSI_BUILD_MAX_STALENESS_MIN (default 20),
  # build anyway. Safe because the build renders into dist/ (FULL) or dist-inc/
  # (INCREMENTAL) and only publishes to WWW after a SUCCESSFUL build + smoke
  # test (set -e + pipefail abort before publish on any build error). So the
  # rare case of reading an authored .md mid-write fails safe — build errors,
  # nothing publishes, retried on the next tick. This bounds content lag to
  # ~the threshold instead of "until the orchestrator finally idles" (hours).
  # Set MSI_BUILD_MAX_STALENESS_MIN to a huge number to restore always-skip.
  MAX_STALE_MIN="${MSI_BUILD_MAX_STALENESS_MIN:-20}"
  PUBLISH_AGE_MIN=$(python3 -c "
from datetime import datetime, timezone
try:
    t = datetime.fromisoformat('$(read_state last_deploy_timestamp)'.replace('Z','+00:00'))
    print(int((datetime.now(timezone.utc) - t).total_seconds() // 60))
except Exception:
    print(999999)
" 2>/dev/null) || PUBLISH_AGE_MIN=999999
  if [ "${PUBLISH_AGE_MIN:-999999}" -lt "$MAX_STALE_MIN" ]; then
    log "MSI in flight (last publish ${PUBLISH_AGE_MIN}m ago < ${MAX_STALE_MIN}m): ora-project/ synced, skipping src/ rsync + build + publish"
    exit 0
  fi
  log "MSI in flight but last publish ${PUBLISH_AGE_MIN}m stale (>= ${MAX_STALE_MIN}m): building anyway (fails safe on mid-write)"
fi

rsync -a --delete-after \
  --exclude "node_modules/" \
  --exclude "dist/" \
  --exclude "dist-inc/" \
  --exclude ".astro/" \
  --exclude "content/articles/" \
  --exclude "content/columns/" \
  --exclude "content/columns-held/" \
  --exclude "content/propaganda/" \
  --exclude "content/propaganda-held/" \
  --exclude "content/propaganda-response/" \
  --exclude "content/propaganda-response-held/" \
  --exclude "content/analyses/" \
  "$REPO_DIR/src/" "$LIVE_DIR/src/"
# The *-held/ pens MUST stay excluded from --delete-after: they are
# server-side holding pens written by the quality gates. columns-held/'s
# absence from this list silently destroyed 83 finished held columns between
# 2026-06-24 and 07-01 (the repo had no copy yet, so --delete-after removed
# them within 15 min of every hold). held_resolution.py owns columns-held/'s
# lifecycle; propaganda-held/ and propaganda-response-held/ (written by
# msi_engine.produce_analysis holds) have NO auto-drain yet — a correcting
# pass will own draining them (deliberate; flagged to the publisher).

rsync -a --update \
  "$REPO_DIR/src/content/articles/" "$LIVE_DIR/src/content/articles/"

# Columns are also authored/enriched in LIVE, so do not delete the live
# directory. But tracked column artifacts (including standalone cartoons and
# house cartoons generated locally and committed to the repo) must still arrive
# on the runtime tree before a build. Mirror the articles strategy: add/update
# repo-side files only when they are newer, preserving server-authored columns.
rsync -a --update \
  "$REPO_DIR/src/content/columns/" "$LIVE_DIR/src/content/columns/"

rsync -a --update \
  --exclude=articles-pre-alpha-recolor-* \
  "$REPO_DIR/public/" "$LIVE_DIR/public/"

# Sync repo-root build scripts (the Pagefind search indexer) to LIVE. Not
# covered by the src/ sync above, and the build half runs from LIVE_DIR.
rsync -a --delete "$REPO_DIR/scripts/" "$LIVE_DIR/scripts/"

# Sync repo-ROOT config that affects the build. The build runs from LIVE_DIR
# (`cd "$LIVE_DIR"` below), but the rsyncs above only cover src/, ora-project/,
# public/, scripts/ — root files were never synced, so an astro.config.mjs /
# tsconfig.json change on origin/main never reached the live build: a structural
# change busts the .astro cache and FULL-rebuilds, but with the STALE live
# config. Sync them so root-config changes deploy on their own. package*.json
# now syncs too because the donation checkout endpoint needs runtime packages
# (Stripe + Astro's Node adapter) to land on the server.
PACKAGE_CHANGED=0
for f in astro.config.mjs tsconfig.json package.json package-lock.json; do
  if [ -f "$REPO_DIR/$f" ]; then
    if [[ "$f" == package* ]] && ! cmp -s "$REPO_DIR/$f" "$LIVE_DIR/$f"; then
      PACKAGE_CHANGED=1
    fi
    rsync -a "$REPO_DIR/$f" "$LIVE_DIR/$f"
  fi
done
if [ "$PACKAGE_CHANGED" -eq 1 ]; then
  log "package files changed -> installing npm dependencies in LIVE"
  (cd "$LIVE_DIR" && npm install --no-audit --no-fund 2>&1 | tail -5 >> "$LOG_FILE")
fi

# ---------- Mode decision ----------
LAST_FULL_TS=$(read_state last_full_build_timestamp)
LAST_DEPLOY_TS=$(read_state last_deploy_timestamp)
LAST_DEPLOY_COMMIT=$(read_state last_deploy_commit)

decide_mode_pre_count() {
  if [ "$FORCE_FULL" -eq 1 ]; then echo "FULL: --full flag"; return; fi
  if [ ! -d "$WWW_DIR" ] || [ -z "$(ls -A "$WWW_DIR" 2>/dev/null)" ]; then echo "FULL: WWW empty"; return; fi
  if [ -z "$LAST_FULL_TS" ]; then echo "FULL: no prior full build recorded"; return; fi

  AGE_HOURS=$(python3 -c "
from datetime import datetime, timezone
try:
    last = datetime.fromisoformat('$LAST_FULL_TS'.replace('Z','+00:00'))
    h = (datetime.now(timezone.utc) - last).total_seconds()/3600
    print(int(h))
except Exception:
    print(999)
")
  if [ "$AGE_HOURS" -ge "$FULL_BUILD_REFRESH_HOURS" ]; then
    echo "FULL: last full build ${AGE_HOURS}h ago"
    return
  fi

  if [ -n "$LAST_DEPLOY_COMMIT" ] && [ "$LAST_DEPLOY_COMMIT" != "$AFTER" ]; then
    if git diff --name-only "$LAST_DEPLOY_COMMIT" "$AFTER" -- 2>/dev/null \
        | grep -qE "$STRUCTURAL_REGEX"; then
      echo "FULL: structural change in commit range"
      return
    fi
  fi
  echo "INCREMENTAL"
}

DECISION=$(decide_mode_pre_count)
MODE=${DECISION%%:*}
REASON=${DECISION#*:}

# ---------- Slug discovery (incremental only) ----------
collect_changed_slugs() {
  python3 - << PYEOF
import os, re, subprocess
from datetime import datetime, timezone

live = "$LIVE_DIR"
repo = "$REPO_DIR"
last_ts = "$LAST_DEPLOY_TS"
last_commit = "$LAST_DEPLOY_COMMIT"
after = "$AFTER"
www_articles = "$WWW_DIR/articles"

articles_dir = os.path.join(live, "src/content/articles")

try:
    last_epoch = datetime.fromisoformat(last_ts.replace("Z","+00:00")).timestamp()
except Exception:
    last_epoch = 0

# slug-from-frontmatter cache: filename → resolved slug (frontmatter slug: if
# present, else filename minus .md). The route filter uses Astro's article.slug
# which is the frontmatter override when set, so the deploy filter must match.
_slug_cache = {}
def resolve_slug(filename):
    if filename in _slug_cache:
        return _slug_cache[filename]
    path = os.path.join(articles_dir, filename)
    canonical = filename[:-3]   # default = filename minus .md
    try:
        with open(path, encoding="utf-8") as fh:
            in_fm = False
            for line in fh:
                if line.startswith("---"):
                    if in_fm: break
                    in_fm = True
                    continue
                if not in_fm: continue
                m = re.match(r"^slug:\s*['\"]?([^'\"\s][^'\"\n]*?)['\"]?\s*$", line)
                if m:
                    canonical = m.group(1).strip()
                    break
    except Exception:
        pass
    _slug_cache[filename] = canonical
    return canonical

slugs = set()

# 1) Files newer than last deploy in LIVE
for f in os.scandir(articles_dir):
    if not f.name.endswith(".md"): continue
    if f.stat().st_mtime > last_epoch:
        slugs.add(resolve_slug(f.name))

# 2) Files added/modified in git commit range
if last_commit and last_commit != after:
    try:
        out = subprocess.check_output(
            ["git", "-C", repo, "diff", "--name-only", "--diff-filter=AM",
             last_commit, after, "--", "src/content/articles/"],
            text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if line.strip().endswith(".md"):
                slugs.add(resolve_slug(os.path.basename(line.strip())))
    except Exception:
        pass

# 3) Articles whose rendered HTML is missing from /var/www (canonical source)
for f in os.scandir(articles_dir):
    if not f.name.endswith(".md"): continue
    canonical = resolve_slug(f.name)
    if not os.path.exists(os.path.join(www_articles, canonical, "index.html")):
        slugs.add(canonical)

for s in sorted(slugs):
    print(s)
PYEOF
}

ARTICLES_RENDERED=0
if [ "$MODE" = "INCREMENTAL" ]; then
  collect_changed_slugs > "$SLUGS_FILE"
  ARTICLES_RENDERED=$(wc -l < "$SLUGS_FILE" | tr -d ' ')
  log "incremental: $ARTICLES_RENDERED articles candidate for render"

  if [ "$ARTICLES_RENDERED" -gt "$MAX_INCREMENTAL_SLUGS" ]; then
    MODE="FULL"
    REASON="incremental candidate count $ARTICLES_RENDERED > $MAX_INCREMENTAL_SLUGS"
    ARTICLES_RENDERED=0
  fi
fi

log "mode=$MODE reason=$REASON before=$BEFORE after=$AFTER"

VOICE_CONTENT_CHANGED=0
FIRST_COLUMN_SLUG=""
FIRST_COLUMN_URL=""
if [ -n "$LAST_DEPLOY_COMMIT" ] && [ "$LAST_DEPLOY_COMMIT" != "$AFTER" ]; then
  FIRST_COLUMN_PATH=$(git -C "$REPO_DIR" diff --name-only --diff-filter=AM \
    "$LAST_DEPLOY_COMMIT" "$AFTER" -- src/content/columns/ | head -1 || true)
  if git -C "$REPO_DIR" diff --name-only --diff-filter=AM \
    "$LAST_DEPLOY_COMMIT" "$AFTER" -- \
    src/content/columns/ src/content/propaganda/ \
    src/content/propaganda-response/ src/content/analyses/ \
    | grep -q '\.md$'; then
    VOICE_CONTENT_CHANGED=1
  fi
  if [ -n "$FIRST_COLUMN_PATH" ]; then
    VOICE_CONTENT_CHANGED=1
    FIRST_COLUMN_SLUG=$(basename "$FIRST_COLUMN_PATH" .md)
    FIRST_COLUMN_PEN=$(python3 - "$REPO_DIR/$FIRST_COLUMN_PATH" << 'PYEOF'
import re, sys
try:
    raw = open(sys.argv[1], encoding="utf-8").read()
except Exception:
    raw = ""
m = re.search(r"(?m)^pen_name:\s*['\"]?([^'\"\n]+)", raw)
print(m.group(1).strip() if m else "")
PYEOF
)
    if [ "$FIRST_COLUMN_PEN" = "phukher-tarlson" ]; then
      FIRST_COLUMN_URL="/advocacy/phukher-tarlson/${FIRST_COLUMN_SLUG}/"
    else
      FIRST_COLUMN_URL="/columns/${FIRST_COLUMN_SLUG}/"
    fi
    log "column changes detected; first column slug=$FIRST_COLUMN_SLUG"
  fi
fi

# ---------- Sanitize article frontmatter ----------
if [ -x "$HOME/sanitize-articles.py" ]; then
  $HOME/sanitize-articles.py 2>>"$LOG_FILE" || log "sanitize-articles.py failed (non-fatal, build will still try)"
fi

# ---------- Frontmatter parse-gate (repair / quarantine unbuildable files) ----------
# Astro aborts the WHOLE build on the first file whose frontmatter fails js-yaml
# parse — and since we only swap dist/ into WWW on a SUCCESSFUL build, one bad
# .md silently freezes the live site at the last good build (2026-06-09: a
# single article froze the site ~26h). This gate parses every content file with
# the SAME js-yaml the build uses, repairs the two known recurring corruptions
# (quote-wrapped mapping openers; list-of-object string fields), and quarantines
# anything that still won't parse so the build proceeds on the rest. Runs from
# LIVE (the ora-project/ rsync above keeps it current); never fatal.
GATE_SCRIPT="$LIVE_DIR/ora-project/scripts/frontmatter-gate.mjs"
if [ -f "$GATE_SCRIPT" ]; then
  node "$GATE_SCRIPT" "$LIVE_DIR" >>"$LOG_FILE" 2>&1 || log "frontmatter-gate.mjs failed (non-fatal, build will still try)"
fi

# ---------- Build ----------
cd "$LIVE_DIR"

run_full_build() {
  # Bust Astro's content-layer cache (.astro, node_modules/.astro) when a
  # render-affecting file changed since the last publish (templates, layouts,
  # pages, components, lib, styles, remark/rehype plugins, astro.config). Those
  # change how EXISTING content renders without changing its content digest, so
  # Astro would otherwise serve stale cached HTML. Keyed on the commit range so
  # unrelated FULL builds (age / --full / empty WWW) keep their warm cache and
  # skip the slow cold re-render. cwd is LIVE_DIR here; the git repo is REPO_DIR.
  if [ -n "$LAST_DEPLOY_COMMIT" ] && [ "$LAST_DEPLOY_COMMIT" != "$AFTER" ] \
     && git -C "$REPO_DIR" diff --name-only "$LAST_DEPLOY_COMMIT" "$AFTER" -- 2>/dev/null \
        | grep -qE "$STRUCTURAL_REGEX"; then
    log "render-affecting change since last publish -> clearing Astro content cache"
    rm -rf "$LIVE_DIR/.astro" "$LIVE_DIR/node_modules/.astro"
  fi
  log "running FULL astro build → dist/"
  NODE_OPTIONS="--max-old-space-size=${NODE_HEAP_MB}" \
    npm run build 2>&1 | tail -5 >> "$LOG_FILE"
}

INCREMENTAL_SCRATCH_ACTIVE=0

cleanup_incremental_scratch() {
  [ "$INCREMENTAL_SCRATCH_ACTIVE" -eq 1 ] || return 0
  if rm -rf -- "$LIVE_DIR/dist-inc"; then
    INCREMENTAL_SCRATCH_ACTIVE=0
    log "removed incremental build scratch dist-inc/" || true
  else
    # Cleanup must never turn a successful publish into a failed publish. Keep
    # the flag set so the EXIT trap gets one more attempt before releasing the
    # shared build lock.
    log "WARNING: could not remove incremental build scratch dist-inc/" || true
  fi
  return 0
}

cleanup_build_scratch_on_exit() {
  local rc=$?
  trap - EXIT HUP INT TERM
  set +e
  cleanup_incremental_scratch
  exit "$rc"
}

prepare_incremental_scratch() {
  INCREMENTAL_SCRATCH_ACTIVE=1
  if ! rm -rf -- "$LIVE_DIR/dist-inc"; then
    log "could not clear incremental build scratch dist-inc/ before build" || true
    return 1
  fi
  return 0
}

run_incremental_build() {
  log "running INCREMENTAL astro build → dist-inc/ ($ARTICLES_RENDERED slugs)"
  # This function is evaluated by an `if`, so Bash's errexit is disabled for
  # its body. Check pre-clean explicitly; never build on a dirty partial tree.
  prepare_incremental_scratch || return 1
  MSI_INCREMENTAL_SLUGS_FILE="$SLUGS_FILE" \
    NODE_OPTIONS="--max-old-space-size=${NODE_HEAP_MB}" \
    npx astro build --outDir dist-inc 2>&1 | tail -5 >> "$LOG_FILE"
}

static_output_dir() {
  local build_dir="$1"
  if [ -d "$LIVE_DIR/$build_dir/client" ]; then
    echo "$LIVE_DIR/$build_dir/client"
  else
    echo "$LIVE_DIR/$build_dir"
  fi
}

publish_full() {
  # Completeness gate (2026-06-03): never publish a truncated build. An
  # OOM-killed or interrupted astro build can leave dist/ missing whole
  # section trees; publishing that with --delete empties the live section
  # dir and nginx then 403s the dir (exists, no index.html). Assert the
  # core aggregate pages exist and are non-empty before publishing.
  local static_dir
  static_dir=$(static_output_dir "dist")
  local p
  for p in index.html propaganda/index.html analyses/index.html; do
    if [ ! -s "$static_dir/$p" ]; then
      log "PUBLISH ABORTED: ${static_dir#$LIVE_DIR/}/$p missing/empty - build truncated (OOM?); not publishing, retry next tick"
      exit 1
    fi
  done
  # --delete-after (not delete-during): deletions happen only after all
  # transfers succeed, so an interrupted publish never removes a file
  # before its replacement has landed.
  #
  # --checksum: Astro rewrites every file in dist/ with a fresh mtime on each
  # build, so a plain rsync -a would restamp all ~18k live files every publish
  # and reset their Last-Modified — breaking conditional GETs (304s only worked
  # within one build cycle) and making sitemap lastmod untrustworthy. With
  # --checksum rsync skips byte-identical files (builds are byte-deterministic),
  # preserving their Last-Modified; only genuinely changed pages get a new
  # timestamp. Adds one hash pass over the build dir + webroot; fine for FULL.
  sudo rsync -a --delete-after --checksum "$static_dir/" "$WWW_DIR/"
}
publish_incremental() {
  # Non-destructive: filtered article HTML + all aggregate pages get
  # copied into WWW_DIR; unchanged article HTML survives. The Pagefind
  # index under WWW_DIR/pagefind/ is preserved (no --delete) — it is only
  # rebuilt on FULL builds (see build_search_index).
  #
  # Exclude the full sitemap (sitemap-index.xml + sitemap-0.xml, …). An
  # INCREMENTAL build renders only the MSI_INCREMENTAL_SLUGS_FILE subset, so
  # @astrojs/sitemap emits a TRUNCATED sitemap (~3k of ~18k URLs). Copying it
  # with --update (newer mtime always wins) overwrote the complete sitemap
  # from the last FULL build, leaving crawlers a sitemap missing ~15k article
  # URLs for all but the ~30 min after each FULL build. Keeping the full
  # sitemap here means it refreshes on FULL builds (≥ every 26h) and is never
  # clobbered in between. The Google News sitemap (news-sitemap.xml) is driven
  # by the full articles collection, is complete on every build, and is
  # deliberately NOT excluded so its 48h window stays fresh incrementally.
  local static_dir
  static_dir=$(static_output_dir "dist-inc")
  # --checksum here too: an incremental publish re-copies every aggregate page
  # (home, section indexes) each tick even when unchanged; without it those
  # pages' Last-Modified churns every ~15 min. Skipping byte-identical files
  # keeps their timestamp stable; genuinely rebuilt slugs still update.
  sudo rsync -a --update --checksum --exclude 'sitemap-*.xml' "$static_dir/" "$WWW_DIR/"
}

# Purge the Cloudflare edge cache after a content publish so the CDN serves the
# new build/images immediately. Images + pages are served with s-maxage (cached
# at the edge until purged), so without this the edge holds stale copies until
# the s-maxage window. Token/zone files are server-only (chmod 600). 2026-05-30.
purge_cloudflare() {
  local zone token resp
  zone=$(cat "$HOME/.config/ora/cloudflare-zone-id" 2>/dev/null)
  token=$(cat "$HOME/.config/ora/cloudflare-token" 2>/dev/null)
  if [ -z "$zone" ] || [ -z "$token" ]; then
    log "cloudflare purge skipped: token/zone file missing"
    return 0
  fi
  resp=$(curl -s --max-time 20 -X POST \
    "https://api.cloudflare.com/client/v4/zones/$zone/purge_cache" \
    -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    --data '{"purge_everything":true}')
  if printf '%s' "$resp" | grep -q '"success":true'; then
    log "cloudflare cache purged (everything)"
  else
    log "cloudflare purge FAILED: $resp"
  fi
}

# Build the Pagefind full-text search index from SOURCE content into
# dist/client/pagefind, so the following publish_full (rsync --delete
# dist/client/ → WWW) carries it. FULL builds only — incremental publishes
# leave the existing index untouched. Non-fatal by design: if the indexer is
# absent, deps are missing, or the build errors, it logs and returns so the site still
# publishes; worst case is a stale/absent index with the page's
# headline-search fallback still working.
build_search_index() {
  if [ ! -f "$LIVE_DIR/scripts/build-search-index.mjs" ]; then
    log "search indexer not present in LIVE; skipping (headline-search fallback unaffected)"
    return 0
  fi
  if [ ! -d "$LIVE_DIR/node_modules/pagefind" ] || [ ! -d "$LIVE_DIR/node_modules/gray-matter" ]; then
    log "installing search-index deps (pagefind, gray-matter)"
    npm install --no-save --no-audit --no-fund pagefind gray-matter 2>&1 | tail -3 >> "$LOG_FILE" || true
  fi
  log "building Pagefind search index → dist/client/pagefind"
  node scripts/build-search-index.mjs 2>&1 | tail -3 >> "$LOG_FILE" \
    || log "search index build failed (non-fatal; site still publishes)"
}

restart_site_service() {
  if command -v systemctl >/dev/null 2>&1; then
    if sudo systemctl try-restart msi-site.service >> "$LOG_FILE" 2>&1; then
      log "msi-site.service restarted if active"
    else
      log "msi-site.service restart skipped or failed (service may not be installed yet)"
    fi
  fi
}

# ---------- Shared astro-build lock (serialize ALL builds) ----------
# The author pool (publish_cycle.py) runs its OWN `npm run build` into the
# SAME dist/. Two builds at once OOM the box; a pool build clearing dist/
# while we publish (rsync --delete dist/ -> WWW) is what empties live
# sections (propaganda renders last, so it is the usual casualty). Hold ONE
# lock across BOTH our build AND publish; publish_cycle.py takes the same
# lock. Bounded wait -> on timeout skip this tick (the staleness override
# forces a rebuild later). FD 201 stays open until exit, so the lock covers
# build -> publish -> smoke -> purge.
exec 201>"$BUILD_LOCK_FILE"
if ! flock -w "$BUILD_LOCK_WAIT" 201; then
  log "could not acquire astro-build lock within ${BUILD_LOCK_WAIT}s (another build busy); skipping build+publish this tick"
  exit 0
fi

# Any incremental output created by this run is disposable. The explicit
# success/fallback calls below reclaim it as early as possible; this trap is the
# failure/interruption backstop. FD 201 remains locked until after the trap.
trap cleanup_build_scratch_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Recover output stranded by an untrappable prior exit even when this tick is
# a FULL build. The EXIT trap retries if removal fails transiently.
if [ -e "$LIVE_DIR/dist-inc" ] || [ -L "$LIVE_DIR/dist-inc" ]; then
  INCREMENTAL_SCRATCH_ACTIVE=1
  cleanup_incremental_scratch
fi

build_ok=0
if [ "$MODE" = "FULL" ]; then
  if run_full_build; then
    build_search_index
    publish_full
    restart_site_service
    build_ok=1
    write_state "last_full_build_timestamp=$(date -u +%FT%TZ)" \
                "last_full_build_commit=$AFTER"
  else
    log "FULL astro build failed"
    exit 1
  fi
else
  if run_incremental_build; then
    publish_incremental
    cleanup_incremental_scratch
    build_ok=1
    log "INCREMENTAL build OK"
  else
    log "INCREMENTAL build failed — falling back to FULL"
    cleanup_incremental_scratch
    if run_full_build; then
      build_search_index
      publish_full
      restart_site_service
      build_ok=1
      MODE="FULL"
      REASON="incremental fallback"
      ARTICLES_RENDERED=0
      write_state "last_full_build_timestamp=$(date -u +%FT%TZ)" \
                  "last_full_build_commit=$AFTER"
    else
      log "FULL fallback build also failed"
      exit 1
    fi
  fi
fi

# ---------- Smoke test ----------
smoke_failed=0
smoke_check() {
  local url="$1"; local must_contain="$2"
  local body
  body=$(curl -sLk --resolve "$SMOKE_RESOLVE" --max-time 15 "$SMOKE_HOST$url" || true)
  if [ -z "$body" ]; then
    log "SMOKE FAIL: empty response for $url"; smoke_failed=1; return
  fi
  if ! grep -q "$must_contain" <<<"$body"; then
    log "SMOKE FAIL: '$must_contain' not found in $url"
    smoke_failed=1
  fi
}

smoke_check "/"          "Main Street Independent"
smoke_check "/advocacy/" "Main Street Independent"
smoke_check "/analyses/"   "Main Street Independent"
smoke_check "/propaganda/" "Main Street Independent"
if [ "$MODE" != "FULL" ] && [ "$ARTICLES_RENDERED" -gt 0 ]; then
  FIRST_SLUG=$(head -1 "$SLUGS_FILE" 2>/dev/null || true)
  if [ -n "$FIRST_SLUG" ]; then
    smoke_check "/articles/${FIRST_SLUG}/" "Main Street Independent"
  fi
fi
if [ "$VOICE_CONTENT_CHANGED" -eq 1 ] && [ -n "$FIRST_COLUMN_URL" ]; then
  smoke_check "$FIRST_COLUMN_URL" "Main Street Independent"
fi

if [ "$smoke_failed" -eq 1 ]; then
  log "SMOKE TEST FAILED — output suspect; daily full build will refresh"
fi

# ---------- Cloudflare edge purge (auto, on a clean content publish) ----------
# Only on a real publish: FULL build (republishes everything incl. regenerated
# images), or an incremental that rendered articles. Skipped on no-op runs and
# on smoke failures (don't push suspect output to the edge).
if [ "$build_ok" -eq 1 ] && [ "$smoke_failed" -eq 0 ] \
   && { [ "$MODE" = "FULL" ] || [ "$ARTICLES_RENDERED" -gt 0 ] || [ "$VOICE_CONTENT_CHANGED" -eq 1 ]; }; then
  purge_cloudflare
fi

if [ "$build_ok" -eq 1 ] && [ "$smoke_failed" -eq 0 ] && [ "$VOICE_CONTENT_CHANGED" -eq 1 ]; then
  MSI_PUBLIC_SITE_URL="$SMOKE_HOST" \
    python3 "$LIVE_DIR/ora-project/tools/column_delivery.py" --days 3 --verify-live \
    >> "$LOG_FILE" 2>&1 || log "column live audit FAILED for recent columns"
fi

# ---------- Social poster: Bluesky + curated Substack Notes ----------
# Runs after a successful publish, so the cartoons' MSI pages are live before we
# post links back to them. The poster is idempotent (its own posted ledger) and
# re-checks liveness per cartoon, so running it on every deploy tick is safe:
# each cartoon posts once (only after it's live), and the daily curated Notes
# best-of fires once. It STAYS IN DRY-RUN until MSI_SOCIAL_DRY_RUN=false is set
# in ora.env, and each Bluesky account stays silent until its own enable flag is
# on. Set MSI_SOCIAL_POSTER_ENABLE=false in ora.env to bypass this block.
if [ "$build_ok" -eq 1 ] && [ "$smoke_failed" -eq 0 ]; then
  SOCIAL_LOG_DIR="$LIVE_DIR/ora-project/state/cartoon-social"
  # `|| true` so a log-dir creation failure can't trip errexit and abort an
  # otherwise-successful deploy (poster problems must never break publishing).
  mkdir -p "$SOCIAL_LOG_DIR" || true
  # Run DETACHED so the deploy never waits on liveness polls / post pacing (a
  # busy day can take minutes). The poster holds its own single-instance lock,
  # so overlapping deploy ticks can't double-post; it logs to its own file. The
  # enable flag + secrets come from ora.env, sourced inside the subshell so the
  # main deploy environment is untouched.
  (
    cd "$LIVE_DIR/scripts" || exit 0
    source "$HOME/.config/ora/ora.env" 2>/dev/null || true
    [ "${MSI_SOCIAL_POSTER_ENABLE:-true}" = "true" ] || exit 0
    setsid "${MSI_SOCIAL_PY:-/home/oracle/ora/.venv/bin/python3}" -m cartoon_social \
      >> "$SOCIAL_LOG_DIR/deploy-hook.log" 2>&1 &
  ) < /dev/null
  log "cartoon-social hook fired (detached; see cartoon-social/deploy-hook.log)"
fi

# ---------- State + final log ----------
write_state "last_deploy_timestamp=$(date -u +%FT%TZ)" \
            "last_deploy_commit=$AFTER" \
            "last_mode=$MODE" \
            "last_articles_rendered=$ARTICLES_RENDERED" \
            "last_smoke_ok=$((1 - smoke_failed))"

if [ "$BEFORE" != "$AFTER" ]; then
  log "deployed $BEFORE -> $AFTER (mode=$MODE, articles=$ARTICLES_RENDERED, voice_content_changed=$VOICE_CONTENT_CHANGED, smoke_ok=$((1 - smoke_failed)))"
else
  log "no-code-change deploy (mode=$MODE, articles=$ARTICLES_RENDERED, voice_content_changed=$VOICE_CONTENT_CHANGED, smoke_ok=$((1 - smoke_failed)))"
fi
