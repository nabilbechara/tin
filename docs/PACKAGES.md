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

```
// github.com/ana/geo/tin.mod
module github.com/ana/geo
caps net files
```

| line | meaning |
|---|---|
| `module PATH` | the package's own import path |
| `require PATH SOURCE` | a dependency: its import path, and the local directory `tin vendor` copies it from (relative to this `tin.mod`, or absolute) |
| `caps CAP...` | the capabilities the package may use (see below); none when there is no `caps` line |

Any other line in a vendored `tin.mod` is `E114 MANIFEST`.

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
by path, then one line per vendored package with the capabilities its manifest declares:

```
caps example.com/units
caps github.com/ana/geo net files
```

A diff of `tin.lock` therefore shows a reviewer when an upgrade asks for more. Lines it did
not write for `vendor/` (entries you keep for files of the project itself) are kept.
Entries are newline-terminated and paths use `/`.

When the project directory has a `tin.lock`, the compiler checks each file before parsing
it:

- every vendored source file must have an entry with its hash;
- every other file the lock lists must still have the hash it records;
- a vendored package with a `tin.mod` must have a `caps` line naming exactly the
  capabilities the manifest declares (`E115 LOCK_CAPS` otherwise).

A mismatch is `E111 LOCK_MISMATCH`, naming the file, the hash the lock records and the hash
the file has:

```
error E111 LOCK_MISMATCH: tin.lock hash mismatch for vendor/example.com/units/units.tin: the lock records sha256 c620…, the file has e74e…
```

A project without a lock file is unlocked, so single-file programs work as before. The
compiler only verifies the lock and never rewrites it. `tinc -hash FILE...` prints the
lines `tin vendor` writes.

## Capabilities

A language written to be generated will pull in code nobody read, so the compiler says what
that code may touch. A vendored package's `tin.mod` declares its capabilities:

| capability | allows |
|---|---|
| `net` | opening connections and listening: `wire`, `anvil`, `redis`, `mysql`, `postgres`, `websocket`, DNS |
| `files` | opening, creating, renaming and removing files and directories: `quarry`'s file functions, `flume` files |
| `spawn` | starting another process |
| `exec` | replacing the process with another program |
| `unsafe` | the raw operations and runtime functions of trusted code (`cast`, `load8`, `rt_*`, LANGUAGE.md §18), as in `lib/` |

The standard library's entry points to the operating system are tagged with the capability
they need: the runtime's `rt_sys_*` calls and the C functions `lib/` declares `extern` that
open a socket (`socket`, `connect`, `bind`, `listen`, `accept`, `getaddrinfo`) or a file
(`open`, `creat`, `opendir`, `mkdir`, `rmdir`, `unlink`, `rename`, `stat`, `lstat`,
`chdir`, `readlink`), start a process (`fork`, `posix_spawn`) or replace it (`execve`).
Today no standard function starts or replaces a process, so `spawn` and `exec` have no
users yet. A few library functions are sealed with what they do: the DNS resolver
(`wire.resolve`) reads `/etc/hosts` and `/etc/resolv.conf` as part of `net`, and a server
(`anvil`) keeps a spare descriptor on `/dev/null` to shed connections. The runtime's own
startup reads (cgroup limits, `/proc`) belong to no package.

After type checking, the compiler builds the call graph of the whole program. Calls,
function values and the methods behind a `dyn` conversion all count, through every
package. It computes what each function can reach. Every function of a vendored package
is checked, called or not, and so are its package-level initializers. A call that leaves
the package for code needing a capability the manifest does not declare is
`E804 CAPABILITY`, reported at that call with the path to the entry point:

```
vendor/example.com/peek/peek.tin:6:16: error E804 CAPABILITY: wire.Dial needs capability net (wire.Dial -> wire.DialTimeout -> wire.resolve), which package example.com/peek does not declare in its tin.mod (caps: none)
```

Capabilities are transitive. A package that calls another package's function that dials
needs `net` too, while calling that package's pure functions needs nothing. A package
declaring `unsafe` passes `unsafe` on to the packages that call it. A package without a
`tin.mod` declares nothing. The program's own package and packages next to it (`./x`,
`util`) are not restricted. A relative import inside a vendored package is part of that
package.

`tin caps main.tin` (`tinc -caps`) prints, for each package, the capabilities its exported
functions can reach. It is useful for writing a manifest and for review:

```
$ tin caps main.tin
example.com/peek net
main net files
quarry files
wire net
```

The pass runs only when a vendored package is loaded. On Linux x86-64 (Xeon 2.1 GHz,
4 cores, kernel 6.18), it adds about 13.5 ms of checking to a 650 ms build of a program
that imports all 36 standard packages.

Not covered yet: a function value handed in by the caller, such as a callback the program
passes to the package, is the caller's capability and is not followed. A package granted
`unsafe` can reach the operating system without going through a tagged entry point, so
review `unsafe` as granting everything.
