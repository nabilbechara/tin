# toolchain/std: the standard library

Everything here is Tin. **A package is a directory**: `toolchain/std/gauge/` is the package `gauge`, and
`import "gauge"` loads every `.tin` file in it as one package, sorted by name, so the files of a
package share one namespace and can be split by topic as the package grows.

```
toolchain/
  runtime/        the runtime every strict program gets (memory, tasks, panics, the OS layer)
  std/            the standard library (this directory): say, fault, io, task, tide, seal, ...
packages/         the ecosystem: anvil (HTTP), postgres, mysql, redis, kafka, tls, wire, websocket, ...
  postgres/       the PostgreSQL client
    md5/          a nested package, imported as "postgres/md5"
    sasl/         imported as "postgres/sasl"
```
An import name is looked up in `toolchain/std/` and then `packages/`; the layout is the same for both.

## Rules

- **One package per directory**, and every file in it starts with the same `package` clause.
  A package never needs a file outside its directory.
- **Split by topic, not by size alone.** Name files for what they hold (`trig.tin`, `exp.tin`,
  `router.tin`), not for how they were added. Aim for files a reviewer can read in one sitting.
- **Platform parts end in the platform name.** `name_darwin.tin` and `name_linux.tin` are used
  only on that OS, and `name_linux_arm64.tin` / `name_linux_amd64.tin` only on that CPU. Shared
  code never hard-codes system call numbers, errno values or struct layouts: they live in these
  files (toolchain/docs/PORTING.md).
- **Test files are never part of the package.** The loader skips `*_test.tin` in a package
  directory, so tests may sit next to the code they check (`tin test DIR` runs a directory's
  tests; see toolchain/docs/TOOLING.md). The suites for the standard library are in `toolchain/tests/v2/`.
- **Nested packages** are subdirectories: `packages/postgres/sasl/` is imported as
  `"postgres/sasl"`. The parent package does not include them.
- **Documentation comes from the code.** `tools/gen/gendoc.py` writes `toolchain/docs/STDLIB.md` from the doc
  comments of every file of each package; the comment on the `package` clause is the package's
  description.
- A package may import any package that does not import it back. The runtime imports nothing.

## Adding a package

Create `toolchain/std/NAME/NAME.tin` (or `packages/NAME/NAME.tin`) starting with `package NAME`, add the name and a one-line role to
`ORDER` and `ROLE` in `tools/gen/gendoc.py`, run it, and add a test under `toolchain/tests/v2/`.
