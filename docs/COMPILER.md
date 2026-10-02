# The Tin compiler (tinc): how it works

`tinc` is about 17,000 lines of Tin in `selfhost/`, written in the legacy syntax
(LANGUAGE.md §20: untyped 64-bit words, `fn`, `let`, `while`). It compiles itself:
`make bootstrap` builds it three times and the last two binaries must be byte-identical.
It produces finished executables with its own assembler and linker (Mach-O for macOS,
ELF for Linux); no external toolchain is involved.

## 1. Files

| file | role |
|---|---|
| `util.tin` | vectors (`vec_*`), byte buffers (`buf_*`), errors (`err_begin`/`err_end`/`fatal`), byte-order helpers, target flags `tgt_linux`/`tgt_x64` |
| `lex.tin` | tokens; semicolon insertion; number, string and character literals |
| `types.tin` | type records, interning (slices, maps, funcs), struct layout |
| `parse.tin` | AST for both syntaxes; node/field constants (the source of truth for every node layout) |
| `check.tin` | declarations, packages, scopes, statements, the region bookkeeping fields, `try`/`defer`/`switch`/`range` lowering, `keep` generation, program start |
| `lower.tin` | expression checking and lowering: strict typing, conversions, constant folding, builtins, `say`, `argo.Put`/`argo.Get` generation, map reads |
| `generics.tin` | type parameters, inference, instantiation by re-parsing |
| `region.tin` | the compile-time memory-region check (LANGUAGE.md §10) |
| `inline.tin` | inline `append` fast paths, short-literal stores, small-function inlining, libm calls to instructions |
| `opt.tin` | analysis (leaf functions, uses, address-taken), loop-invariant code motion, strided prefetch |
| `gen.tin` | the arm64 code generator; hand-assembled SHA-256 |
| `asm.tin` | the arm64 instruction list, its text printer (`-S`) and its encoder |
| `asm_x64.tin` | the x86-64 instruction list, printer and encoder (fuzzed against objdump) |
| `gen_x64.tin`, `elf_x64.tin` | the x86-64 backend and linker (in progress) |
| `sha256.tin` | SHA-256 for code signatures and the Mach-O UUID |
| `macho.tin` | the macOS linker: layout, import stubs, GOT binding, symbols, ad-hoc signature |
| `elf.tin` | the Linux arm64 linker: PIE, dynamic section, GLOB_DAT relocations, `_start` |
| `main.tin` | the driver: arguments, targets, file loading, package resolution |
| `host_darwin.tin`, `host_linux.tin` | the compiler's own OS calls (the build picks the host's) |

`lib/std.tin` (legacy helpers: `strlen`, `streq`, `calloc` externs...) is part of every
compiler build.

## 2. Pipeline

```
main: parse arguments (-o, -S, -target), detect the host (uname)
  for each file: lex -> parse                      (lex.tin, parse.tin)
  if any file is strict: load lib/runtime (+ _os, _os_arch), then imports transitively
check()                                             (check.tin)
  generics_init: register generic types, attach their method templates
  named types: structs first (so fields can refer to any struct), then aliases; layout
  declare functions (templates only register their names), then pending generic methods
  constants, then globals (per-core globals get __core_init statements)
  check every function body (instances and generated functions are appended and checked
  in the same loop): typing, lowering, say/argo/keep generation, defer finishing
  make_start: __start = rt_init, shared initializers, __core_init, rt_main_begin,
  main.main, rt_exit; mark reachable functions
region_check()                                      (region.tin)
generate()                                          (gen.tin; generate_x64 for amd64)
  inline_small_calls over the whole program
  per reachable function: inline_appends, licm_fn (prefetch, invariant hoisting),
  analyze_fn, assign_homes, statement codegen, cold stubs, finish_fn (prologue,
  epilogue, peephole)
write_executable (Mach-O) | write_elf (ELF arm64) | write_elf_x64
```

Everything is in memory; the output is written once at the end.

## 3. Data structures

All structures are word arrays allocated with `calloc`; their field indexes are
constants. The authoritative lists are in the files named below.

**Tokens** (`lex.tin`): `[kind, text, value, pos]`. `pos` packs file, line and column.

**AST nodes** (`parse.tin`): `N_SIZE` = 10 words: `N_KIND`, `N_POS`, kind-specific fields
from index 2, `N_TYPE` (6) the checked type, `N_REGION` (9). Expression kinds (`EX_*`):
INT, STR, IDENT, UNARY, BINARY, CALL, INDEX, CONV, FLOAT, NIL, SELECT, SLICE, COMPOSITE,
TYPE, SEQ (statements then a value, made by lowering), FUNCREF, FUNCLIT, MEM (a sized
load/store at base + index*scale + off), ELEM (a bounds-checked element), TRY. Statement
kinds (`ST_*`): BLOCK, LET, ASSIGN, EXPR, IF, WHILE (every loop and switch), RETURN,
BREAK, CONTINUE, MULTI, RANGE, SWITCH, LIST, CALLMULTI, GO, DEFER. Type expressions
(`TX_*`): NAME (with `TX_ARGS` for generic arguments), SLICE, MAP, PTR, FUNC, STRUCT,
ARRAY, CHAN, OPT.

Lowering rewrites nodes in place (`replace_node`), so after `check` the tree holds only
the lowered forms: field accesses are MEM, indexing is ELEM, map operations are calls to
`rt_map_*`, composite literals are SEQ nodes that allocate and store, `range` and
`switch` are WHILE loops, `try` is a CALLMULTI plus an IF.

**Function declarations** (`F_*`, 36 words): name, qualified name (`pkg.Name`,
`Type.Method`, `Name[T1,T2]` for instances), params, param types (expressions until
declared, then types), result types, body, locals, slots, flags (extern, legacy,
variadic, reachable, leaf, lifted), mut flags per parameter, type parameters and
bindings, tokens to re-parse (generics), region summary.

**Symbols** (`S_*`, 24 words, `check.tin`): kind (local, global, const, func), name,
type, slot/register home, use counts, address-taken, constant value and "big" flag,
per-core global slot (`S_TLS`), region bits, mut.

**Types** (`types.tin`, 12 words): kind (`K_INT`, `K_BOOL`, `K_FLOAT`, `K_STRING`,
`K_STRUCT`, `K_SLICE`, `K_MAP`, `K_FUNC`, `K_VOID`, `K_TUPLE`, `K_NIL`, untyped kinds,
`K_ERROR` for fault, `K_OPT`), element/key, fields (`[name, type, offset, array len,
row len]`), results, name, width and signedness for integers, struct size, generic
arguments and declaration. Slice, map and func types are interned (one record per
structure), so type identity is pointer equality.

## 4. Checking and lowering (strict files)

- Untyped constants adapt to the expected type and must fit (`adapt_int`); integer
  constant expressions are folded exactly (`fold_const`, `fold_compare`), with values
  above 2^63-1 treated as unsigned.
- Binary operators require identical operand types; `&&` narrows optionals for its right
  side; conditions must be `bool`.
- Calls: argument types must be assignable; untyped arguments are converted; variadic C
  functions take extra arguments as words.
- Generated functions: `keep$N` (deep copy per type), `argo$N` (JSON encoder per type),
  `argo$dN` (decoder per type), `func$N` (lifted literals), `__core_init` (per-core
  globals), `__start` (the program entry, linked as `main`).
- `defer` is lowered by `finish_defers`: flags initialized at entry, argument temps at
  each defer, and the flagged calls appended before every return (in reverse order).
- `try` (`lower_try_stmt`) becomes a multi-result call into temps and
  `if err != nil { return zero..., err }`, with real zero values for references.
- Map reads (`map_read`) substitute the value type's zero on a miss.
- String interpolation (`chk_interp`) becomes a `say.Fmt` call. Where the expected type is
  the runtime's `query` (`is_query_t`), `chk_query` instead builds the composite
  `query{Parts: []str{...}, Args: []qarg{qarg.Int(i64(x)), ...}}` from the literal's pieces
  and values and checks that; `check_assignable` gives the query-specific error for a `str`.
- Faults that are never read and calls whose fault result is dropped are errors
  (`check_fn`, `check_stmt`).

## 5. Generics (`generics.tin`)

A generic function or type keeps its tokens. Each new combination of type arguments
re-parses the declaration with the type parameters bound (`ck_tbind`), declares it like
an ordinary function named `Name[T1,T2]`, and appends it to the program; the main check
loop checks it later. Calls infer type arguments by unifying parameter type expressions
with argument types (`tunify`), first ignoring untyped constants, then defaulting them.
Methods of a generic type are instantiated together with each instance of the type.
Constraints are checked at instantiation.

## 6. The region check (`region.tin`)

Each expression gets region bits: `RG_FRESH` (a new allocation from the request pool),
`RG_INGOT` (long-lived), `RG_UNK` (unknown, treated as long-lived when stored into),
`RG_EMB` (may point into request memory), and one bit per parameter (`RG_P0 << i`).
Locals accumulate the bits of everything assigned to them (iterated to a fixed point per
function). A store of a value with `RG_EMB` into a container with `RG_INGOT` or `RG_UNK`
is an error; into a parameter's container it marks that parameter a sink in the
function's summary. A container that is not long-lived may still hold long-lived or
parameter objects: every store into one adds the value's long-lived, unknown and
parameter bits to a per-type table of the function (`rg_hold`), and a read of that type
out of such a container takes them (`rg_load`). Summaries (sink parameters, the held
table restricted to types reachable from the parameters and results, records of where
inside each parameter it stores, result bits per result) are iterated over the whole
program until nothing changes, then a final pass reports errors (only in non-library
files). At a call, a parameter's bits stand for everything reachable from the argument,
so the caller's held entries on the way from the argument's type to a stored-into object
(`rg_deep`) count too; calls through function values use the joined summaries of all
functions used as values. Runtime calls with special meaning (`rt_map_set`, `rt_append`,
`rt_slice_sub`...) are modelled by name.

## 7. Code generation (`gen.tin`, arm64)

Registers:

| registers | use |
|---|---|
| x0–x7, d0–d7 | arguments and results (Tin calls use the C convention; up to 8 results in x0–x7) |
| x9–x15, d16–d30 | temporaries in leaf functions |
| x16, x17, d31 | scratch (also used by import stubs) |
| x18 | never touched (platform register on macOS) |
| x19–x27, d8–d15 | homes for locals (callee-saved), chosen by loop-weighted use counts |
| x28 | the core context (like Go's g): pool pointers, per-core globals at x28 + 8·(32+i) |
| x29, x30, sp | frame pointer (kept for backtraces), link register, stack |

- Expressions evaluate into a stack of temporary registers indexed by depth; calls use
  three strategies (direct into argument registers, nested with live-depth tracking, or
  push-all) depending on the arguments.
- Globals: per-core globals are `ldr x, [x28, #off]`; process-wide (`shared`) globals use
  `adrp`/`ldr` to the data segment.
- Bounds checks: `cmp idx, len; b.hs stub`, where each site's cold stub passes index and
  length to `rt_bounds_fail2`. Division checks the divisor with `cbz` to a stub calling
  `rt_div_fail`.
- Optimizations here: leaf functions without frames, early-exit base cases of recursive
  functions inlined at call sites, rotated loops, `csel`/`fcsel` if-conversion, `madd`,
  branch inversion, constant materialization, shift-and-add strength reduction, signed
  division by powers of two, sized loads and stores.
- `seal.hw_blocks` is emitted as hand-assembled words using the SHA-256 instructions
  (`gen_raw_fn`, op `I_RAW`).

## 8. Optimizations before codegen

| pass | file | does |
|---|---|---|
| `inline_small_calls` | inline.tin | inlines functions whose body is one `return expr` (≤ 40 nodes), substituting simple arguments (and pure single-use ones when the whole call is pure), temps in order otherwise |
| float intrinsics | inline.tin | `sqrt`, `fabs`, `floor`, `ceil`, `trunc`, `round`, `rint` externs become single instructions |
| `inline_appends` | inline.tin | `append(s, v)` and `append(b, str...)` get an inline capacity check and store; short literal appends become constant stores |
| `licm_fn` | opt.tin | hoists loop-invariant expressions (including slice headers when the loop makes no calls) and rewrites `x[a+b]` row addressing |
| prefetch | opt.tin | strided prefetch ahead of indexed loads in loops |
| `analyze_fn` | opt.tin | leaf detection, loop-weighted use counts, address-taken locals |

## 9. Linking

**Mach-O** (`macho.tin`): `__PAGEZERO`, `__TEXT` (headers, code, import stubs, C strings,
Tin strings, constants), `__DATA` (GOT, globals), `__LINKEDIT` (bind opcodes for the
imports, the symbol table, an ad-hoc code signature with a SHA-256 page hash per 4 KiB).
Import calls go through 12-byte stubs (`adrp x16, got; ldr x16, [x16]; br x16`). The UUID
is a hash of the code, so builds are reproducible.

**ELF arm64** (`elf.tin`): a PIE (`ET_DYN`) with segments aligned to 64 KiB (any kernel
page size): R (headers, interpreter, `.dynsym`, `.dynstr`, SysV hash, relocations), RX
(`_start`, code, stubs, strings), RW (dynamic section, GOT, globals). `PT_PHDR`,
`PT_INTERP` (`/lib/ld-linux-aarch64.so.1`), `PT_DYNAMIC`, `PT_GNU_STACK`. Imports are
bound at load time by one `R_AARCH64_GLOB_DAT` relocation per GOT slot (`BIND_NOW`, no
PLT). Tin functions are exported as `tin.<name>` with their sizes, so `dladdr` names
backtrace frames. `_start` calls `__libc_start_main(main, argc, argv, 0, 0, rtld_fini,
stack_end)`. No section headers are written (none are needed to run).

Differences the backend handles per target: variadic C arguments are on the stack on
macOS and in registers on Linux (`arg_regs`, `gen_call`); C symbols have a leading
underscore only in Mach-O.

## 10. The runtime interface

The compiler emits calls to these `lib/runtime.tin` functions (others are reached from
them): `rt_init`, `rt_main_begin`, `rt_exit`, `rt_alloc`, `rt_panic`, `rt_bounds_fail`,
`rt_bounds_fail2`, `rt_div_fail`, `rt_fail`, `rt_str_*` (cat, eq, cmp, sub, from_bytes,
from_rune), `rt_utf8`, `rt_bytes_from_str`, `rt_copy_str`, `rt_slice_make`,
`rt_slice_make_str`, `rt_slice_make_nest`, `rt_slice_make_grid`, `rt_slice_sub`,
`rt_slice_copy`, `rt_append`, `rt_slice_appendn`, `rt_append_str`, `rt_map_*` (make,
get, found, set, del, slots, live, key, val), `rt_keep_*`, `rt_fmt_*` (the say
machinery), `rt_err_str`. Intrinsics compiled inline: `load8`, `store8`, `__ld`, `__st`,
`__ctx`, `__set_ctx`, `__fp`, `__empty`, `__yield`, `__atomic_*`, `__prefetchw`,
`__fsqrt`, `__fabs`, `__frint*`.

## 11. Changing the compiler

1. Edit `selfhost/` (legacy syntax; comments are one sentence ending with a period).
2. `make -s bin/tinc` builds it with the seed; for faster iteration build with the
   current compiler: `bin/tinc -o bin/tincL $(make -s print-SELF)`.
3. Test with `tools/try.sh bin/tincL tests/v2/x.tin` and `tools/v2test.sh bin/tincL`.
4. `make bootstrap` must reach the fixed point; then `make test`, `make linux-test`, and
   `make linux-bootstrap` if the ELF writer or Linux codegen changed.
5. `make seed` (and `make linux-bootstrap`) refresh the seeds once everything passes.

Adding a builtin: handle its name in `chk_builtin` (lower.tin), lowering it to runtime
calls or intrinsics; add a runtime function if needed and mark it reachable when the
backend calls it. Adding an intrinsic: `intrinsic_arity` (check.tin), code in
`gen_intrinsic` / `gen_runtime_intrinsic` (gen.tin). Adding a statement form: parse it in
`parse_stmt`, check/lower it in `check_stmt`, and make every later pass (region, inline,
opt, gen) see only existing lowered forms if possible.

Common failure modes: a node referenced from two places and rewritten twice (clone
nodes you reuse), an identifier left unresolved after lowering (`ID_REF` 0 crashes
`analyze_fn`), a function the backend calls that reachability did not mark (it links to
address 0 and jumps into the Mach-O header), a legacy file using a name that became a
keyword.
