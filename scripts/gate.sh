#!/bin/sh
# Final verification gate: tests (browser tests required), lint, JS syntax,
# and a check that no ignored files exist beyond local data and caches.
set -eu

cd "$(dirname "$0")/.."

CUBS_REQUIRE_E2E=1 python3 -m pytest -q
echo "ok: pytest (end-to-end tests required)"

python3 -m flake8 -j1 cubs_edge_lab tests
echo "ok: flake8"

find web -name "*.js" -exec node --check {} +
echo "ok: node --check"

ignored=$(git ls-files --others --ignored --exclude-standard --directory)
offending=""
for path in $ignored; do
    case "$path" in
        data/ | .pytest_cache/ | __pycache__/ | */__pycache__/) ;;
        *) offending="$offending $path" ;;
    esac
done
if [ -n "$offending" ]; then
    echo "error: ignored paths other than data/ and caches:" >&2
    for path in $offending; do
        echo "  $path" >&2
    done
    exit 1
fi
echo "ok: no stray ignored paths"
