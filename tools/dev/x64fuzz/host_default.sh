#!/bin/sh
# Check that a compiler running on Linux defaults to its own CPU (issue #15): for amd64 and
# arm64, cross-build tinc, then in a container of that CPU compile a strict test and tinc
# itself with no -target, check e_machine, run the results and reach a fixed point.
cd "$(dirname "$0")/../../.." || exit 1
tinc=${1:-bin/tinc}
self=$(make -s print-SELF_LINUX)
out=$(mktemp -d "${TMPDIR:-/tmp}/tin-host-default.XXXXXX") || exit 1
trap 'rm -rf "$out"' EXIT
status=0
for arch in amd64 arm64; do
  case $arch in amd64) machine=62 ;; arm64) machine=183 ;; esac
  image=${TIN_LINUX_IMAGE:-tin-debian-$arch}
  # shellcheck disable=SC2086
  "$tinc" -target linux-$arch -o "$out/tinc-$arch" $self || { echo "FAIL $arch: cross build"; status=1; continue; }
  if docker run --rm --name "tin-agentx-host-$arch-$$" --platform linux/$arch -v "$out:/w" -v "$PWD:/src:ro" \
      -e TIN_ROOT=/src -w /src "$image" sh -c '
    set -e
    em() { od -An -tu2 -j18 -N2 "$1" | tr -d " "; }
    t=/w/tinc-'$arch'
    $t -o /w/hello-'$arch' tests/v2/hello.tin
    [ "$(em /w/hello-'$arch')" = '$machine' ] || { echo "strict e_machine $(em /w/hello-'$arch')"; exit 1; }
    /w/hello-'$arch' | LC_ALL=C sort | cmp - tests/v2/hello.out
    $t -o /w/s2-'$arch' '"$self"'
    /w/s2-'$arch' -o /w/s3-'$arch' '"$self"'
    cmp /w/s2-'$arch' /w/s3-'$arch'
    cmp /w/s2-'$arch' $t
  '; then
    echo "PASS $arch: default target is linux-$arch (e_machine $machine), self-hosts to a fixed point"
  else
    echo "FAIL $arch"
    status=1
  fi
done
exit $status
