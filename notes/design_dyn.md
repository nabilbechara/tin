# Design: `dyn` and multi-word values

This note is the implementation design for the `dyn` sub-item of #141 (notes/roadmap.md,
"`dyn` fat reference (data pointer plus table) for open sets, with region rules"). The
decision that `dyn S` exists and what it means is in notes/design_foundations.md section 2;
this note fixes the representation the compiler will build, because the acceptance test —
`[]dyn Writer` of different types, conversion allocates nothing, and storing a `dyn` of
request memory in a global is a region error — cannot be met without an allocation or a
global type registry.

**Need.** `io.Writer`, `hash.Hash`, `fmt.Stringer` and the driver shapes have no Tin form
that an open set of types can share; the static form (a type parameter) is monomorphized and
cannot hold a heterogeneous slice. Go pays two words plus an itab for the same capability;
Tin's target is two words, no allocation and one indirect call, with no runtime type
information beyond the table the shape needs.

**Decision.** A `dyn S` value is a **two-word value**: `[object, table]`. **Replaces:**
nothing new; it inherits design_foundations section 2 (`interface`, `any`, type assertions).

- `object` is the concrete value as it is today (a struct is already a reference, so one
  word). Only structs and enums (structs underneath) can be objects today, because methods
  require a struct receiver; that is also what makes `object == 0` a safe nil test. If
  methods ever move to other types, this encoding is revisited.
- `table` is the address of a static table for the pair (concrete type, shape). The table is
  `[keep, method0, method1, ...]`: entry 0 is the concrete type's deep-copy routine, so
  `keep(dyn)` can copy the object without runtime type information, and the methods follow in
  the shape's flatten order (`shape_collect`'s: listed shapes first, then the shape's own
  methods), deduplicated by name by the table build (the flattening itself keeps identical
  duplicates from different listed shapes). Entries are **function descriptor addresses**, so
  a call reuses the existing indirect-call convention (load the code word from the descriptor,
  pass it in the environment register). Building a table marks every method and the keep entry
  reachable, so their descriptors are initialized like any called function's.
- A `dyn S` is never nil; `?dyn S` is the same two words with `object == 0` meaning absent.
  `== nil` on a `?dyn` tests the object word only. `==` between two `dyn` values is rejected
  (a shape's identity is a method on the shape, as design_foundations section 2 requires);
  function values are comparable today, so this is an explicit new rejection, not an inherited
  rule.
- **The table layout is internal to a whole-program build.** There is no cross-package binary
  ABI and no promise of one; a package is source (design_foundations section 8), so the table
  is rebuilt with the program. This answers the open question at notes/roadmap.md section 11.

## 1. Where two-word values appear

`dyn` is the first multi-word type; value arrays (`[N]T` with copy semantics, any N),
`complex128` and SIMD vectors need the same type-system and layout work (their ABIs differ:
`complex128` uses FP registers, SIMD uses vector registers; only the layout half is shared).

| context | today (one word) | with two words |
|---|---|---|
| local | one home slot | two adjacent slots; a size-16 local occupies both |
| parameter / result | one register each (x0..x7, d0..d7) | two consecutive integer registers; when fewer than two remain, both words go to the stack (16-byte aligned) under the same rule in caller and callee; a result consumes two words, so later results shift |
| stack argument | 8-byte slot | two 8-byte slots, 16-byte aligned; arm64 gains callee-side stack-parameter loading (x64 has it) |
| struct field | 8-byte slot | 16-byte slot, 8-byte aligned; `layout_struct` starts its width walk at 16 |
| slice element | scale 1/2/4/8 | address `base + idx*16` with two loads/stores at +0 and +8; size-16 `append` lowers to the grow check plus two stores (the existing inline path, extended), so the one-word `rt_append`/`rt_store_elem` is not used for it; `keep_each` uses the same address rule |
| map value | one word | **later step**: the runtime map ABI (header value size, 16-byte slots) changes with it |
| `?dyn` | nil check | `object == 0` |

The size of a type comes from `type_width` (extended with a `K_DYN` case), not `TY_SIZE`,
which stays the struct object size. A bare `dyn` declaration with no initializer is an error,
like a struct or a map.

## 2. Conversions and calls

- A conversion from a concrete type `T` to `dyn S` is checked where it is written (the
  existing structural satisfaction check) and lowers to a pair: the object unchanged, the
  table address materialized as a constant. It is a dedicated pair node, not two statements,
  so the region pass sees one value whose bits are the object's.
- A method call on a `dyn S` value loads the descriptor address from the table at the
  method's compile-time index and calls it indirectly with the object as the receiver: no
  lookup by name, no hashing, no allocation.
- **Tables are writable data filled at startup**, exactly like the existing function
  descriptors: the object writer zero-fills the slots and the entry code stores each
  descriptor address into them. No new relocation machinery is needed, and the note does not
  claim one; if whole-program static initialization ever moves to real data relocations, the
  tables move with it.
- A conversion whose object is statically known keeps a direct `keep$T` entry; the table's
  keep entry is what makes `keep(dyn)` and `keep` of a struct or slice containing a `dyn`
  work (the struct's or slice's `keep$T` calls the field's or element's table entry, and
  `keep_each`'s address rule is the size-16 one). A `dyn` may not be a map key.

## 3. Regions

The region bits of a `dyn S` value are those of its `object`; the table is static. Storing a
`dyn` built from request memory into a global, a map reachable from one, or a `keep`ed
structure is an error exactly as storing the object itself is, with the same message. The
region pass needs, in one PR: `has_ptr` includes `K_DYN`; `rg_key` keeps a `dyn`'s held bits;
the conversion's pair node is the only new case and takes the object's bits (no
`RG_FRESH|RG_EMB`); a method call through a table is summarized conservatively by joining the
summaries of every method that can appear in any table for that shape; and any new runtime
call name is added to `rg_runtime_call`. `keep(dyn)` calls the table's keep entry; the region
error's `keep` suggestion keeps working.

## 4. Not decided here (rejected or deferred, with the rule)

- `say`/`argo` of a `dyn`: rejected with a clear error ("give the shape a method that
  formats"); a shape's method is the way to render an open set.
- A closure capturing a `dyn`: rejected until cells can be two words; the diagnostic names
  the capture.
- `map[K]dyn` values and `!dyn` results: deferred to the map-ABI and fault-return steps;
  `!dyn` returns the zero pair `(0, 0)` when it does land.
- `dyn` as a map key: rejected (it does not compare).

## 5. Rejected alternatives

- **Boxed one-word record**: allocates at every conversion and adds an indirection to every
  call; the acceptance test rejects it.
- **Per-object type header**: changes every struct's layout and leaks type information into
  values that do not need it.
- **Table chosen by the call site**: the concrete type is unknown at an open-set call.
- **One table per shape with a global type index**: needs a registry and a lookup; the
  per-pair table needs neither.

## 6. Staging

Each step keeps `make bootstrap` a fixed point and adds its own tests. Positive `dyn` tests
can only run once both backends emit size-16 values, because CI runs the strict suite on
amd64 and arm64; steps 2 and 3 add negative tests, and the
positive tests and the table `_asm` check land with step 4.

1. **This note** (no compiler change).
2. **Size-16 in the type system**: `K_DYN` interned by (shape, bindings), `type_width`,
   `?dyn`, `[]dyn`, conversion checking, region bits, and a gate at the top of
   `generate`/`generate_x64` that refuses a program in which the checker built any `K_DYN`
   type, with one clear message per target. The gate is whole-program (an uncalled function's
   signature and an unused shape's signature both resolve `dyn`), so the two existing `_bad`
   tests that assert "dyn shapes are not usable yet" (`shapes_dyn_bad`, `shapes_dyn_unused_bad`)
   stay negative with the gate's message.
3. **arm64 codegen**: homes, parameters, results, fields, element access, tables and the
   startup fill, method calls. No `_asm` check yet: the strict suite compiles `*_asm.tin` on
   both CPUs, and the amd64 gate would fail one here.
4. **amd64 codegen** and the positive suite tests, `[]dyn`, the table's `_asm` check, and the
   Go twin of the acceptance program.
5. **Region and lifetime tests**: storing a `dyn` of request memory in a global is an error;
   `keep(dyn)` survives pool resets; `[]dyn` of two types works.
6. **Map values and the library ports that need `dyn`** (`io.ReaderFrom`/`WriterTo`,
   `MultiReader`, the driver shapes).

## 7. What this unlocks

The layout and type-system half generalizes to value arrays (`[N]T` with copy semantics,
which today's `[N]T` is not: UUIDs and hashes as map keys), and to `complex128` (FP registers)
and SIMD vectors (vector registers) when those exist, so the language gets one reviewed
multi-word layout instead of three ad-hoc ones.
