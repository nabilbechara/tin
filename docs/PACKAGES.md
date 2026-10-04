# Packages

Tin resolves a non-relative import in this order:

1. `vendor/<import path>` below the program's project directory.
2. The standard library under `TIN_ROOT/lib/`.
3. A package next to the program's first source file.

Relative imports continue to resolve next to the importing file. Vendored packages are ordinary
Tin source trees; the compiler does not execute build hooks or fetch packages from the network.

## Lock File

If the project directory contains `tin.lock`, every non-standard-library source file loaded by the
compiler must have an exact entry in it:

```
<64 lowercase hexadecimal SHA-256> <path relative to the project directory>
```

Entries are newline-terminated. Paths use `/`, and `vendor/` is part of a vendored path. The
compiler rejects a missing entry or a changed hash before code generation. A project without a lock
file remains unlocked, which keeps existing single-file programs usable.

Generate entries with a tool that hashes the checked-in source files in deterministic path order;
the compiler intentionally only verifies the file content and does not rewrite the lock file.
