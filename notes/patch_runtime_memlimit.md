# Patch for lib/runtime.tin: memory-limit-aware request pool chunk

`hearth.Run(n, …)` now calls `pool_tune(n)` (lib/hearth.tin) before any core starts. When the
container's memory limit (`rt_mem_limit()`, cgroup v2 `memory.max` / v1 `memory.limit_in_bytes`,
implemented in lib/runtime_linux.tin; 0 on macOS) is set and `n × chunkSize` (4 MiB per core) would
exceed a quarter of it, `pool_tune` stores a smaller per-core chunk size (a multiple of 64 KiB, at
least 64 KiB) in the shared variable `rtPoolChunk`, declared in both runtime OS files:

```
shared var rtPoolChunk i64   // request pool chunk size once a memory limit lowered it (0: the default)
```

Everything compiles and runs today; the only missing piece is that `lib/runtime.tin` still reads the
constant `chunkSize` directly, so `rtPoolChunk` has no effect yet. Apply the following edits to
`lib/runtime.tin` (five replacements plus one new function). They only ever *shrink* the chunk, and
`pool_tune` runs before cores 1..n-1 exist, so a pool core 0 may already own (allocated with the full
4 MiB) is simply used up to the smaller size: `rt_pool_reset` writing `base + rt_chunk()` into
`ctxEnd` stays inside the allocated block.

## 1. Add, right after `const slabSize = 1048576`

```tin
// rt_chunk is the request pool chunk size: chunkSize, or less when hearth lowered rtPoolChunk
// to fit the memory limit (see pool_tune in lib/hearth.tin).
func rt_chunk() i64 {
	if rtPoolChunk != 0 {
		return rtPoolChunk
	}
	return chunkSize
}
```

## 2. In `rt_alloc_slow`

```
-		chunk := calloc(1, chunkSize)
-		c[ctxPoolBase] = chunk
-		c[ctxBump] = chunk + n
-		c[ctxEnd] = chunk + chunkSize
+		chunk := calloc(1, rt_chunk())
+		c[ctxPoolBase] = chunk
+		c[ctxBump] = chunk + n
+		c[ctxEnd] = chunk + rt_chunk()
```

and further down in the same function

```
-	chunk := calloc(1, chunkSize)
+	chunk := calloc(1, rt_chunk())
 	chunk[0] = c[ctxPoolExtra]
 	c[ctxPoolExtra] = chunk
 	c[ctxBump] = chunk + 16 + n
-	c[ctxEnd] = chunk + chunkSize
+	c[ctxEnd] = chunk + rt_chunk()
```

Note: today a request of `n >= bigAlloc` (256 KiB) gets its own block and anything smaller is
assumed to fit a 4 MiB chunk. With a chunk that may be as small as 64 KiB, a 200 KiB request would
not fit, so the big-block test must also cover "does not fit the chunk":

```
-	if n >= bigAlloc {
+	if n >= bigAlloc || n+16 > rt_chunk() {
```

## 3. In `rt_pool_reset`

```
-	c[ctxEnd] = base + chunkSize
+	c[ctxEnd] = base + rt_chunk()
```

## 4. In `rt_pool_used`

```
-		return c[ctxPoolMark] - c[ctxPoolBase] + chunkSize
+		return c[ctxPoolMark] - c[ctxPoolBase] + rt_chunk()
```

## Verification after applying

```sh
make -s bin/tinc && tools/v2test.sh                       # macOS: "v2 tests pass"
TIN_ROOT=$PWD bin/tinc -target linux-arm64 -o bin/linux/coresprobe bin/agentA/coresprobe.tin
docker run --rm --memory=64m -v $PWD/bin/linux:/w tin-debian-arm64 /w/coresprobe
# expect: memlimit 67108864, poolchunk 1507328 (16 MiB / 11 cores rounded down to 64 KiB), and
# the probe's 1 MiB allocation per core still succeeding.
```

`hearth.PoolChunk()` reports the size in use; `tests/v2/hearth.tin` checks the invariants.
