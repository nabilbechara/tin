#!/bin/sh
# Install a verified Tin release without root, Go, or a C compiler.
# Usage: sh install.sh [0.4.0]; TIN_INSTALL_DIR defaults to ~/.tin.
set -eu
repo=${TIN_REPOSITORY:-yasserreslan/tin}
base=${TIN_RELEASE_BASE_URL:-https://github.com/$repo/releases/download}
version=${1:-}
if [ -z "$version" ]; then
  url=$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/$repo/releases/latest")
  version=${url##*/}
fi
version=${version#v}
printf '%s\n' "$version" | LC_ALL=C grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$' || {
  echo 'tin: expected a release version such as 0.4.0' >&2; exit 1;
}
case $(uname -s) in Darwin) os=darwin ;; Linux) os=linux ;; *) echo 'tin: unsupported OS' >&2; exit 1 ;; esac
case $(uname -m) in arm64|aarch64) arch=arm64 ;; x86_64|amd64) arch=amd64 ;; *) echo 'tin: unsupported architecture' >&2; exit 1 ;; esac
target=$os-$arch
case $target in darwin-arm64|linux-arm64|linux-amd64) ;; *) echo "tin: unsupported target $target" >&2; exit 1 ;; esac
name=tin-$version-$target
archive=$name.tar.gz
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
curl -fsSL "$base/v$version/SHA256SUMS" -o "$work/SHA256SUMS"
curl -fsSL "$base/v$version/$archive" -o "$work/$archive"
expected=$(awk -v name="$archive" '$2 == name { print $1 }' "$work/SHA256SUMS")
printf '%s\n' "$expected" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || {
  echo "tin: missing or ambiguous checksum for $archive" >&2; exit 1;
}
if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$work/$archive" | awk '{print $1}')
else
  actual=$(shasum -a 256 "$work/$archive" | awk '{print $1}')
fi
[ "$actual" = "$expected" ] || { echo 'tin: checksum mismatch; nothing installed' >&2; exit 1; }
tar -xzf "$work/$archive" -C "$work"
[ -x "$work/$name/bin/tinc" ] && [ -x "$work/$name/tin" ] || { echo 'tin: incomplete release' >&2; exit 1; }
# Verify the compiler can actually run (in particular, that the host supplies glibc).
printf 'package main\nimport "say"\nfunc main() { say.Line("Tin installation verified") }\n' > "$work/check.tin"
"$work/$name/tin" build "$work/check.tin" -o "$work/check"
"$work/check" >/dev/null
install_dir=${TIN_INSTALL_DIR:-$HOME/.tin}
mkdir -p "$install_dir/versions" "$install_dir/bin"
install_dir=$(cd "$install_dir" && pwd)
destination=$install_dir/versions/$name
if [ ! -d "$destination" ]; then
  mv "$work/$name" "$destination"
fi
ln -sf "$destination/tin" "$install_dir/bin/tin"
ln -sf "$destination/bin/tinc" "$install_dir/bin/tinc"
echo "Installed Tin $version ($target) in $destination"
echo "Add to PATH: export PATH=\"$install_dir/bin:\$PATH\""
