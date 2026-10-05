# squash

`lib/squash/` compresses and decompresses whole strings: DEFLATE (RFC 1951) with its gzip (RFC 1952)
and zlib (RFC 1950) wrappers, Snappy, LZ4 (block and frame formats) and Zstandard (RFC 8878). It was
written for the Kafka client (`notes/design_kafka.md`, section 6), which needs all four Kafka codecs,
and is a standard package so other code can use it. API: `docs/STDLIB.md`.

| File | Holds |
|---|---|
| `flate.tin` | bit reader, canonical Huffman decoding (a 9-bit table, then bit by bit as zlib's puff), `Inflate` |
| `deflate.tin` | LZ77 with hash chains (lazy matching from level 4), length-limited Huffman codes, each block written as the smallest of stored, fixed and dynamic; `Deflate` |
| `gzip.tin` | `Gzip`, `Gunzip` (several members; FEXTRA, FNAME, FCOMMENT, FHCRC read), `Zlib`, `Unzlib` |
| `snappy.tin` | `Snappy`, `Unsnappy` (block format, 64 KiB fragments) |
| `lz4.tin` | xxHash32; `Lz4`, `Lz4NoChecksum`, `Unlz4` (frames: independent and linked blocks, block and content checksums, content size, skippable frames), `Lz4BlockOf`, `UnLz4Block` |
| `zstd.tin` | `Unzstd`: raw, RLE and compressed blocks, Huffman literals (1 or 4 streams, direct and FSE-coded weights), sequences in every table mode, repeat offsets, skippable frames, the content checksum |
| `zstdenc.tin` | `Zstd`: blocks of up to 128 KiB, hash-chain matches over a 1 MiB window, Huffman literals (4 streams) when smaller, sequences with the predefined FSE tables, a raw block when compression does not help, the content checksum |

Every decoder takes the most bytes it may produce and fails with `fault.LimitExceeded` past it.

## Verified

- `tests/v2/squash.tin` and its Go twin `bench/ref/squash/main.go` print the same 117 lines: vectors Go
  wrote (two gzip members, a gzip header with name, comment and extra, zlib, stored and level-5
  DEFLATE) and vectors this package wrote, each decoded by both; round trips of 7 inputs at levels 0,
  1, 6 and 9 in all three formats; ratios; damaged, cut and foreign input; output limits. Changing one
  constant of the DEFLATE length table changes 18 lines.
- `tests/v2/squash_formats.tin` (86 lines; Go's standard library has no Snappy, LZ4 or Zstandard, so
  there is no twin): vectors written by the zstd 1.5 command at levels 19 and 1, the lz4 1.10 command
  with independent and with linked blocks and a content size, and github.com/golang/snappy decode to
  inputs whose CRC-32s Go prints in `tests/v2/squash.tin`; round trips of 8 inputs; checksums, cut
  data, wrong magic numbers and limits.
- By hand, in both directions on 6 inputs (empty, one byte, text, random, zeros, mixed): Go's
  compress packages read every Tin output at levels 0, 1, 6 and 9 and Tin reads Go's; the zstd command
  and github.com/klauspost/compress/zstd read every Tin zstd frame (24) and Tin reads theirs (levels
  19, 1 and klauspost's best); the lz4 command reads every Tin frame; github.com/golang/snappy reads
  every Tin block. Through Kafka: Java producers' gzip, snappy, lz4 and zstd batches decode in Tin,
  and Java consumers read Tin's (`notes/stdlib_kafka.md`).

## Known gaps

- Whole strings only: no streaming readers and writers, no preset dictionaries (zlib, zstd, LZ4).
- The zstd encoder uses the format's predefined FSE tables and no repeat offsets, so it compresses less
  than the reference encoder (a 70 KB text: 10.8 KB at level 6 where gzip gives 7.2 KB); its literal
  Huffman code is used only when no literal byte is above 128 (the direct weight description;
  binary literals go raw). Every frame it writes is
  valid and read by the reference decoders.
- The DEFLATE encoder is not tuned for speed.
