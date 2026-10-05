# Giving the compiler real types (#228, milestone "Typed compiler")

Status: design, 2026-10-05. Owner: #228. This note is the plan for step 1 (the typed data model)
and the rules every later step follows. It decides nothing about the language: it is how the
compiler's own source moves from the untyped internal dialect to typed edition 1.

## 1. What the dialect is, and what "done" means

`selfhost/`, `lib/std.tin` and the shared runtime files (`lib/runtime/memory.tin`, `number.tin`,
`*_fast.tin`) are written in an untyped dialect: every value is a 64-bit word, records are word
arrays indexed by constants (`t[T_KIND]`, `s[LET_NAME]`), strings are C strings, parameters have no
types, and `ck_legacy` / `F_LEGACY` switch typing off in `check.tin` and change code generation in
`gen.tin` and `gen_x64.tin`. About 38,000 lines.

Done when (from #228): the compiler is typed edition 1, `make bootstrap` is a fixed point on all
three targets, the seeds are refreshed, and the dialect, `F_LEGACY`, `ck_legacy` and the legacy
parser paths are gone.

A translator cannot do this mechanically, because it needs the compiler's data model written down as
types. So the work is a sequence of steps, each leaving the compiler building and bootstrapping, with
typed and untyped code in the same program until the last step.

## 2. The fact that makes it incremental (measured)

A typed struct whose fields are all 8 bytes wide has exactly the layout of an untyped word record:
`layout_struct` (selfhost/types.tin) orders fields by width, widest first, and by declaration order
within a width, so a struct of 8-byte fields keeps its declaration order at offsets 0, 8, 16, ...
A slice header is `[len, cap, data]`, which is the layout of the untyped vectors (`VEC_LEN`,
`VEC_CAP`, `VEC_DATA`).

Measured on `bin/tinc` (2026-10-05): an untyped file and a typed edition 1 file compile into one
program; the untyped code allocates a record with `malloc`, stores words with `t[0] = 7`, and passes
it to a typed function `fn tok_sum(t Tok) i64`, which reads `t.kind + t.val` and returns the right
answer. The reverse works too once the typed file may use `cast` (rule 6): a typed function takes a
record an untyped function allocated, `cast(Tok, legacy_mk())`, reads its fields and calls untyped
functions with plain words. So a record can be typed while code that has not been converted yet keeps
using word indices on the same object.

## 3. Rules for typed records

1. **One struct per record, fields in the order of the constants.** `T_KIND = 0, T_TEXT = 1, ...`
   becomes `kind, text, ...` in that order. The constants stay (untyped code still uses them) and a
   check in the test suite compares each constant with the struct's field offset, so the two cannot
   drift.
2. **Every field is 8 bytes.** Fields are `i64` for words, a struct type for a reference to another
   typed record, `[]T` for a vector. Narrow integer types and 16-byte values are not used in a record
   that untyped code still reads.
3. **A field changes from `i64` to a richer type only when no untyped code reads it any more.** The
   consequence: the migration unit is a field, not a file. `T_TEXT` stays an `i64` C-string pointer
   until every reader of `.text` is typed, then becomes `str`.
4. **Unions are structs per variant over the same words.** A node's first words (`N_KIND`, `N_POS`,
   `N_TYPE`) are common; each node kind has its own struct (`LetStmt`, `Call`, ...) and typed code
   gets one from a `Node` with a `kind` check and `cast`. The kind constants stay the source of
   truth for the check.
5. **Allocation stays untyped until the last step.** Records are still created by the untyped
   `node_new` and friends, which `malloc`; typed code receives them. Replacing the constructors with
   struct literals comes after every reader of the record is typed.
6. **Typed compiler files are trusted.** A typed file needs `cast` and raw words to receive untyped
   records, which only trusted files may use (E802). Files under `selfhost/` are read trusted, like the
   runtime and the standard library (`load_file` in `selfhost/main.tin`). This is the one compiler
   change before the first typed file; it affects no user program.
7. **No behavior changes.** Each step must leave `tinc -S` output of a fixed corpus identical, in
   addition to the bootstrap fixed point. That is the proof a conversion did not change the compiler.

## 4. The steps, in order

Every step is a small PR (`Part of #228`) with `make bootstrap`, the strict suite, the regression
cases and a byte-identical `-S` comparison. The seed is not touched until step 6.

0. **Trust and the seed.** The checked-in seeds predate edition 1: they cannot read a typed file, and
   they would have to read `selfhost/` files as trusted to allow `cast` in them (rule 6). So before any
   typed file: (a) the trust rule lands in `selfhost/main.tin` (a small PR, no user-visible change); (b)
   the seeds are refreshed from that commit for darwin-arm64, linux-arm64 and linux-amd64, announced in
   the milestone and merged alone (AGENTS.md rule 8); (c) a script, `tools/compare_compilers.sh`, compiles
   a fixed corpus with two compilers and compares the `-S` listings, the proof for rule 7. Measured
   2026-10-05: the current seed stops at the first `mut` of an edition 1 file.
0d. **The compiler becomes a strict program.** Measured 2026-10-05 with the new compiler: adding a
   single typed file to the compiler build fails with about sixty E101 REDECLARED errors, because any
   strict file makes the driver load the real runtime (`lib/runtime`), and the compiler's own build
   already carries its private copies of the same things: `lib/std.tin` (`malloc`, `free`, `calloc`,
   `realloc`, `mem_failpoint`, `print*`), `lib/runtime/memory.tin` and `number.tin`, and the
   `rt_sys_*` wrappers in `selfhost/host_*.tin`. A typed compiler therefore means the compiler runs on
   the real runtime like every other Tin program: the duplicates go (the runtime's allocator, syscalls
   and number code serve the compiler, `host_*.tin` keeps only what the runtime lacks: `realpath`,
   `getenv`, `uname`, `dirent`, the executable path), `std.tin` shrinks to the helpers the untyped files
   still call, and the entry point and start-up sequence become the strict program's. This is its own PR
   (the compiler still untyped, built as a strict program), measured for compile time, binary size and
   memory use before and after, and it is the real gate for every typed file.
   Measured as a feasibility probe (2026-10-05, darwin-arm64, not committed): drop `lib/runtime/memory.tin`
   and `number.tin` from the compiler's file list, drop the heap and `rt_sys_*` duplicates from `std.tin`
   and `host_darwin.tin` (keeping `opendir`, `readdir`, `closedir`, `creat`, `unlink`, `uname`), rename the
   untyped `main` to `compiler_main(argc, argv)` and add one typed `fn main() { compiler_main(rtArgc,
   rtArgv) }`. The result builds (805 KB against 750 KB), compiles the test programs with output
   byte-identical to the untyped compiler, takes the same time to compile itself (0.48 s against 0.47 s),
   and reaches the bootstrap fixed point (stage 2 equals stage 3 when both are written to the same file
   name: the code signature embeds it).
1. **Records.** Tokens (`lex.tin`), positions and errors (`util.tin`), then the remaining small
   records. Each is a struct with the layout check of rule 1, and `lex.tin` is converted to typed
   edition 1 because it owns the token record and is the smallest pass (about 640 lines).
2. **Vectors and buffers.** `vec_*` and `buf_*` become typed slice operations: `[]i64` first, then
   `[]Node`, `[]Type`, `[]str` as the element types become typed.
3. **Strings.** C strings (`T_TEXT`, names, file paths, error text) become `str`: `strlen`, `streq`,
   `str_cat3` and the message builders move to `twine`-style functions, one record field at a time.
4. **Nodes, types and symbols.** The node kinds of `parse.tin` (the source of truth for node
   layouts), the type records of `types.tin`, the symbols of `check.tin`. One struct per kind or
   record, readers converted pass by pass: `parse`, `check`, `lower`, `generics`, `region`, `inline`,
   `opt`, then the code generators and linkers.
5. **The shared runtime files and `lib/std.tin`.** The files the compiler shares with every program
   (`memory.tin`, `number.tin`, the `*_fast.tin` stubs) move to typed edition 1.
6. **Remove the dialect.** Delete `F_LEGACY`, `ck_legacy`, the untyped-word paths of the checker and
   both code generators, and the edition 0 parser code; then refresh the seeds for all three targets
   in their own PR (AGENTS.md rule 8: announced, done alone, merged alone).

## 5. What can go wrong

- **Silent layout drift.** A field added in the middle of a struct moves every later offset for
  untyped readers. The constant-versus-offset check (rule 1) is a test that fails the build.
- **Region rules on typed code.** Typed code is checked for escapes. The compiler allocates with
  `malloc` and never calls `keep`, so records are plain references from the checker's point of view;
  a step that makes a typed function return a pool-allocated value must say where it lives.
- **A pass converted but its callers not.** Typed functions called from untyped code receive words;
  a typed parameter of struct type accepts any word. That is the point of the scheme and its
  weakness: a wrong word is not caught until the caller is typed too. Convert callers in the same PR
  where they are few; otherwise add a debug assertion on the kind field at the boundary.
- **Compile time and binary size.** Typed code costs more to compile and may produce larger code than
  the hand-tuned words. Measure `make bootstrap` time and the size of `bin/tinc` before and after each
  step and record both in the PR.
