#!/bin/sh
# bump-version.sh X.Y.Z: Kimera's one version (the VERSION file), then the commit and tag to make.
# Tan, 2026-10-13: Kimera is versioned in SemVer, like AIDEN. Pre-1.0: the minor number counts a shipped
# road or limb (a merged slice), a patch is a fix, 1.0.0 is Tan's call. Every release has a CHANGELOG.md entry
# and an annotated tag vX.Y.Z on the commit.
set -eu
v="${1:?usage: scripts/bump-version.sh X.Y.Z}"
case "$v" in [0-9]*.[0-9]*.[0-9]*) ;; *) echo "not X.Y.Z: $v" >&2; exit 1;; esac
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
grep -q "^## $v " "$root/CHANGELOG.md" || { echo "CHANGELOG.md has no '## $v' entry yet" >&2; exit 1; }
printf '%s\n' "$v" >"$root/VERSION"
echo "VERSION: $v"
echo "now: git add -A && git commit -m \"release: v$v\" && git tag -a v$v -m \"Kimera v$v\""
