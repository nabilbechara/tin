# Stdlib verification against Go (bench/ref/NAME/main.go)

| package | Go reference | result |
|---|---|---|
| mint | strconv | identical on all cases |
| gauge | math, math/bits | the transcendental functions are Tin ports of Go's algorithms: see "gauge: the corpus check" below |
| tide | time | identical |
| dice | same algorithms in Go | identical |
| sift | slices/sort | identical |
| cairn | hand-written Go equivalents | identical |
| trail | path/filepath | identical |
| quarry | os | identical except stderr interleaving and naming fdopendir instead of open in one error |
| lever | flag | identical except: a value that fails to parse leaves the flag unchanged (Go overwrites it with a zero value) |
| twine, glyph | strings, unicode/utf8 | checked by hand against Go semantics |


## Deliberate difference since v0.5 (!T results)

A failing call returns zero values with its fault. Go's strconv returns the clamped value
(MaxInt64, ±Inf, MaxUint64) together with ErrRange; mint.Atoi, ParseInt, ParseUint and
ParseFloat now return 0 with the range fault. tests/v2/mint.out records this.


## gauge: the corpus check

`bench/ref/gauge/corpus.go` and `corpus.tin` run every transcendental function over the same
deterministic inputs (about 20,000 per function: 70 edge cases plus uniform, log-uniform, raw-bit
and quarter-integer values, so NaN, infinities, subnormals and arguments up to 1.8e308 are all in) and
print a hash of the result bits, or every result with `dump`. The Go side uses Go's pure algorithms for
Exp, Exp2, Sinh, Cosh, Tanh and Pow, because `math.Exp` is assembly on arm64 and amd64 and returns 0 for
Exp(-745) where the true value rounds to the smallest subnormal.

    go build -o /tmp/ref ./bench/ref/gauge && tin build bench/ref/gauge/corpus.tin -o /tmp/corpus
    /tmp/ref corpus > go.txt; /tmp/corpus corpus > tin.txt; diff go.txt tin.txt

Result (macOS arm64): bit-identical to Go for 15 of 21 hashes, over 586,156 results in all: sin, cos,
tan (with Payne-Hanek reduction up to 1.8e308), asin, acos, atan, atan2, sinh, cosh, tanh, exp, exp2,
cbrt, hypot, mod. The six that differ are log, log2, log10, log1p, pow and the pow subset: for about one
input in a thousand the result differs by exactly one ulp. The cause is the fused multiply-add. Both
compilers fuse on arm64, but not the same products. In the disassembly of Go's `math.log` the last
line `k*Ln2Hi - (...)` is one fused instruction and `hfsq = 0.5*f*f` is folded into the fused operations
that use it rather than rounded once; Tin's compiler has no `x*y - a` form, fuses the right-hand product
of an add, and rounds a product that has two uses once.
Neither is wrong, and Go's own results differ between its arm64 and amd64 builds for the same reason.

Error against exact arithmetic (Python `decimal`, 800 digits for log1p), in ulps, on the inputs where the
result is a normal number:

| function | inputs | Tin = Go | max Tin | max Go | mean Tin | mean Go |
|---|---|---|---|---|---|---|
| log | 10,110 | 99.80% | 0.718 | 0.725 | 0.2509 | 0.2510 |
| log2 | 10,110 | 95.75% | 35.1 | 34.1 | 0.2776 | 0.2767 |
| log10 | 10,110 | 99.81% | 1.76 | 1.61 | 0.3780 | 0.3780 |
| log1p | 12,875 | 99.93% | 0.707 | 0.707 | 0.2034 | 0.2034 |
| pow (4,000 sampled) | 3,476 | 99.94% | 141 | 141 | 4.209 | 4.209 |

The two large maxima are Go's algorithms, not the port: Log2 loses precision for x near 1 (it adds
Log(frac)/ln2 to an exponent of 1), and Pow's error grows with the size of the result. They are
reproduced faithfully. A more accurate Log2 and Pow would be a Tin improvement on Go, and the corpus
would then show them as deliberate differences.
