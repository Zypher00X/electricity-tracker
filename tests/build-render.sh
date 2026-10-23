#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
builddir=$(mktemp -d /tmp/powertrack-render-build.XXXXXX)
tar -xf tmp/security/render-source.tar -C "$builddir"
printf '%s\n' "$builddir/source" > tmp/security/render-build-path.txt
docker build -f "$builddir/source/Dockerfile.render" -t powertrack:render "$builddir/source"
docker build -f "$builddir/source/Dockerfile.render" --target test -t powertrack:render-test "$builddir/source"
