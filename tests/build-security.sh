#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/electricity_tracker
builddir=$(mktemp -d /tmp/powertrack-security-build.XXXXXX)
tar -xf tmp/security/build-context.tar -C "$builddir"
printf '%s\n' "$builddir" > tmp/security/build-context-path.txt
docker build -f "$builddir/Dockerfile.production" --target runtime -t powertrack:security-reviewed "$builddir"
docker build -f "$builddir/Dockerfile.production" --target test -t powertrack:security-test "$builddir"
