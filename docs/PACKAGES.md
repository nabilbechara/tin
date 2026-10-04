# Packages

A Tin dependency is source code, imported by path, copied into the project's `vendor/`
directory and pinned by content hash in `tin.lock`. There is no registry, no semantic
version resolution and no binary package format, and the build never uses the network
(notes/design_foundations.md §8).

## Imports

Tin resolves an import in this order:

1. A path starting with `./` or `../`: next to the importing file.
2. A **path import**, whose first element contains a dot (`github.com/ana/geo`): only
   `vendor/<path>` below the project directory, the directory of the program's first
   source file. If that directory is missing, the build fails with
   `E112 NOT_VENDORED`. A path import never falls back to the standard library or the
   program's directory.
3. Any other path: `vendor/<path>`, then the standard library under `TIN_ROOT/lib/`, then
   a package next to the program's first source file.

A package is a `name.tin` file or a directory of `.tin` files (LANGUAGE.md §1). Its name
is the last element of the import path, so `github.com/ana/geo` is used as `geo.Area`.
If two import paths load different packages under one name, the build fails with
`E113 PACKAGE_CONFLICT`. Rename one or import only one.

Vendored packages are ordinary Tin source trees. A path import inside a vendored package
also resolves to the project's `vendor/`, so a dependency's own dependencies are vendored
next to it.

## The manifest: `tin.mod`

Each package can have a `tin.mod` next to its source files. It is line based: blank lines
and lines starting with `//` are ignored.

```
module example.com/app
require github.com/ana/geo ../geo
require example.com/units /src/mirror/units
```

| line | meaning |
|---|---|
| `module PATH` | the package's own import path |
| `require PATH SOURCE` | a dependency: its import path, and the local directory `tin vendor` copies it from (relative to this `tin.mod`, or absolute) |

`SOURCE` is any directory on the local disk: a checkout, a mirror or a sibling directory.
Fetching from a URL (`tin get`) is a separate step, and the lock makes the source
irrelevant to trust.

## `tin vendor`

`tin vendor [DIR]` (DIR defaults to `.`) reads `DIR/tin.mod`. It copies each required
package's `.tin` files (not `*_test.tin`) and its `tin.mod` into `DIR/vendor/<path>`,
then does the same for the packages those manifests require, and so on. A path required
from two different sources is an error. `vendor/` is rebuilt from scratch, so a package
that is no longer required disappears. Then `tin vendor` writes `DIR/tin.lock`.

Commit `vendor/` and `tin.lock`. A build needs nothing else.

## The lock file: `tin.lock`

```
<64 lowercase hexadecimal SHA-256> <path relative to the project directory>
```

`tin vendor` writes one line for every file under `vendor/` (sources and manifests), sorted
by path. Lines it did not write for `vendor/` (entries you keep for files of the project
itself) are kept. Entries are newline-terminated and paths use `/`.

When the project directory has a `tin.lock`, the compiler checks each file before parsing
it:

- every vendored source file must have an entry with its hash;
- every other file the lock lists must still have the hash it records.

A mismatch is `E111 LOCK_MISMATCH`, naming the file, the hash the lock records and the hash
the file has:

```
error E111 LOCK_MISMATCH: tin.lock hash mismatch for vendor/example.com/units/units.tin: the lock records sha256 c620…, the file has e74e…
```

A project without a lock file is unlocked, so single-file programs work as before. The
compiler only verifies the lock and never rewrites it. `tinc -hash FILE...` prints the
lines `tin vendor` writes.
