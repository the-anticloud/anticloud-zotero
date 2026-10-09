#!/bin/sh
# Container entrypoint. Read-only root filesystem friendly: it writes only to
# /tmp, and it never assumes a writable working directory.
set -eu

case "${1:-}" in
    bench|verify)
        # Re-run the full qualification inside the shipped image. If the image
        # cannot reproduce its own benchmarks, the build is not qualified.
        exec python /app/tools/run_bench.py --quiet
        ;;
    *)
        exec "$@"
        ;;
esac
