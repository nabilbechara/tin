`parse-number-f64.txt.gz` contains the finite f64 cases from five files in
[Nigel Tao's parse-number-fxx-test-data](https://github.com/nigeltao/parse-number-fxx-test-data)
at the commit recorded in `parse-number-f64.json`. That manifest records the original
file SHA-256 hashes and retained case counts. Each row retains the original f64 bits
and decimal input. Comments and the f16/f32 columns are omitted; the gzip timestamp is
zero. The upstream data is under Apache 2.0; see `notes/licenses/parse-number-fxx.txt`.

These cases cover more-test-cases, google-wuffs, freetype-2-7, tencent-rapidjson and
lemire-fast-float. CI checks every retained case, without network access, against the
original expected bits. `bench/ref/number` adds an independently generated Go corpus,
random hexadecimal/decimal values, long tails, signed zero, f32 subnormals and exact
formatting/flag comparisons.
