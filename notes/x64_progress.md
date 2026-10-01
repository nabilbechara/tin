# linux-amd64 backend: progress

Files: `selfhost/asm_x64.tin` (encoder, fuzzed against objdump: `tools/x64fuzz/run.sh`),
`selfhost/gen_x64.tin` (code generator), `selfhost/elf_x64.tin` (ELF writer),
`lib/runtime_linux_amd64.tin`, `lib/anvil_linux_amd64.tin`, `tools/x64fuzz/linuxtest_amd64.sh`
(tests/v2 on amd64). Tests run in the emulated `tin-debian-amd64` container.

## Design (gen_x64.tin)

- System V: args rdi, rsi, rdx, rcx, r8, r9 / xmm0-7, extras on the stack; results rax / xmm0;
  several results (Tin-to-Tin only) travel in rax, rdx, rcx, rsi, rdi, r8, r9, r10 as bits.
- Scratch, never allocated: rax, rcx, rdx, r11, xmm15. So `idiv` (rdx:rax), shifts by `cl` and
  call results never collide with live values. r15 = thread context (`__ctx`/`__set_ctx`),
  rbp = frame pointer (`__fp`, backtraces walk [rbp], [rbp+8] as on arm64).
- Homes: rbx, r12, r13, r14 (callee-saved); float homes xmm8-14 in leaf functions, frame slots
  otherwise (no callee-saved xmm registers). Temps: rsi, rdi, r8, r9, r10 + leftover homes,
  xmm1-14; depth-indexed as in gen.tin.
- Calls: live caller-saved temps are saved first; then the callee (if indirect) and every
  argument are evaluated left to right and pushed, and popped in reverse into their registers
  (stack arguments are copied into a 16-byte aligned area reserved below the pushes). Extern
  calls set `al` to the number of xmm argument registers.
- Every spill slot is 16 bytes (`sub rsp,16; mov [rsp],r`), so rsp is 16-byte aligned at every
  call without tracking. Frame: `push rbp; mov rbp,rsp; sub rsp,frame`; slots at [rbp-8(i+1)],
  saved registers below them; frameless leaves when nothing needs saving.
- Division (x_divide): `x / 0 == 0`, `x % 0 == x`, `MIN / -1 == MIN` via explicit checks
  before idiv/div (the legacy semantics). Float compares: `<`/`<=` use swapped `ucomisd` with
  ja/jae, `==`/`!=` add a parity check, so NaN compares like Go. cmov if-conversion for
  integer selects only.
- Bounds checks: `cmp idx, len; jae stub`; per-site cold stubs pass index and length through the
  stack into rdi/rsi, realign rsp and call `rt_bounds_fail2`.
- Symbols in instructions are indices into `x_syms` (sym_ref words; the packed memory operand only
  holds 32 bits), resolved by `x64_sym_hook` in elf_x64.tin; imports resolve to 6-byte stubs
  `jmp [rip+got]`, so `call rel32` works for Tin and C functions alike. ELF: e_machine 62,
  4 KiB segments, `/lib64/ld-linux-x86-64.so.2`, R_X86_64_GLOB_DAT, DT_HASH, no symbol
  versions (unversioned references bind to the oldest glibc versions, which notes/linux_abi.md
  4.6 shows is fine for everything Tin calls), 34-byte hand-written `_start`.

## Milestones

1. Legacy program (lib/std.tin + fn main calling puts): REACHED. argc/argv/exit code correct.
2. tests/v2/hello.tin: REACHED (output identical to hello.out).
3. tests/v2 on amd64 (`tools/x64fuzz/linuxtest_amd64.sh`, with `TIN_ROOT` pointing at a copy of
   the tree with `notes/patch_x64_runtime.md` + `notes/patch_x64_seal.md` applied):
   27 of 31 pass (cores defer dice fixes fixes2 flume gauge generics glyph hearth hello herald
   json jsonget mint ore regions relay seal sift stamp syntax tide trail twine wire zeros).
   Legacy tests/*.tin: 13 of 13 pass after the argument-order fix (optimizer's `deep_calls`
   needs left-to-right evaluation of effectful arguments; verified only on the old binary's
   failure, rerun is part of "next steps").
   FAILING: `cairn` (segfault), `lever` (segfault; `lever.Str("name", ...)` alone crashes, see
   scratch micro test b), `quarry` (one value: `names[len(names)-1]` as the 7th argument of
   say.Line prints names[6] instead of the last element: a 7+-argument call / stack-argument
   bug, micro test c with 7- and 8-argument functions also segfaults), `seal` passes only with
   the seal patch.
4. Self-hosting: REACHED. `bin/tinc -target linux-amd64 -o tinc_amd64 $(make -s print-SELF_LINUX)`
   (0.14 s on the Mac), then in the container tinc_amd64 rebuilt itself to s2 and s2 to s3:
   s2 == s3 == tinc_amd64 byte for byte (587384 bytes). The compiler never needs the failing
   constructs, but that run used the compiler built before the argument-order fix was used for
   the container stages' sources? No: all three stages compile the same sources with the fixed
   generator (the cross-compiler was rebuilt after the fix).

## Unverified / open

- The div-by-zero semantics change (coordinator, after these runs): strict code must PANIC on
  `/ 0` and `% 0` via `rt_div_fail` (one cold stub per function, skipped when
  `cur_gen_fn[F_LEGACY]`; constant-zero divisor jumps unconditionally). NOT YET MIRRORED in
  gen_x64.tin: `x_divide` still yields 0 / x for a zero divisor in all code. To mirror: add
  `var x_div_label`, reset it in `x_gen_fn`, in `x_divide` replace the `test b,b; je zero_l`
  path with `test b,b; je x_div_label` when `!cur_gen_fn[F_LEGACY]` (keep zero_l for legacy),
  in `x_binary_const` for c == 0 in strict code emit `jmp x_div_label`, and at the end of
  `x_gen_fn` (next to trap_label) emit `x_label(x_div_label); call rt_div_fail` (find_fn, set
  F_USED). MIN / -1 == MIN stays.
- The three failures above (cairn, lever, 7+-argument calls). Likely area: the stack-argument
  path in `x_gen_call` (slot offsets `16*i + callee_slot + 8*j`) and/or stack parameters in
  `x_entry_moves` ([rbp+16+8k]); `lever.Str` crashing with 3 args suggests something else too
  (struct return / `register` with many fields?). Debug with gdb: build an image once with
  `docker run --platform linux/amd64 --name b tin-debian-amd64 sh -c 'apt-get update -qq && apt-get install -y -qq gdb' && docker commit b x64dbg:local && docker rm b`
  then `docker run --rm --platform linux/amd64 -v DIR:/w x64dbg:local gdb -batch -ex run -ex bt /w/prog`.
- `-S` for the x64 target needs the main.tin patch (notes/patch_x64_runtime.md section 6).
- A darwin v2 build in this tree currently fails with "strlen redeclared (lib/std.tin)"; this
  appeared while another engineer was changing lib/ and main.tin and is not from these files
  (legacy darwin builds and `make -s bin/tinc` work).

## Patches to apply (not my files)

- `notes/patch_x64_runtime.md`: move rt_stat_mode and the epoll_event layout into per-arch
  files (new lib/runtime_linux_arm64.tin, lib/anvil_linux_arm64.tin; TARGET_X64 const), plus
  the optional main.tin `-S` hook. Without it, any amd64 v2 build fails with duplicate
  definitions.
- `notes/patch_x64_seal.md`: Sha256 falls back to Sha256Soft when TARGET_X64.

## Resume

```sh
make -s bin/tinc                                   # includes asm_x64/gen_x64/elf_x64
tools/x64fuzz/run.sh 20000 1                       # encoder vs objdump (0 mismatches expected)
# tests/v2 on amd64 (after the patches are applied; or TIN_ROOT=<patched copy of the tree>):
tools/x64fuzz/linuxtest_amd64.sh bin/tinc
# legacy tests: compile each tests/*.tin with lib/std.tin -target linux-amd64 and compare
# `// expect:` lines (see the scratch harness description in this note's history).
# self-hosting:
sh -c 'bin/tinc -target linux-amd64 -o /tmp/tinc_amd64 $(make -s print-SELF_LINUX)'
docker run --rm --platform linux/amd64 -v /tmp:/w -v $PWD:/src:ro tin-debian-amd64 sh -c \
  'cd /src && /w/tinc_amd64 -target linux-amd64 -o /w/s2 '"$(make -s print-SELF_LINUX)"' && /w/s2 -target linux-amd64 -o /w/s3 '"$(make -s print-SELF_LINUX)"' && cmp /w/s2 /w/s3 && echo fixed point'
```
