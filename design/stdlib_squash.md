# squash: hostile input and decided leniencies

squash decodes input it cannot trust (Kafka batches, HTTP bodies). Every decoder takes `max`, the
most bytes it may produce, and fails with `fault.LimitExceeded` past it. Since #440 its memory is
also bounded by its input and output, not only its output:

- Gunzip decodes every member into one buffer with one set of Huffman tables; the member CRCs
  are checked once at the end, on views of the result. DEFLATE builds each dynamic block's codes
  into the same tables.
- LZ4 decodes each block straight into the output. Copies may not reach before the block
  (independent blocks) or before the frame (linked blocks).
- zstd keeps one decoder state per call: the predefined FSE tables are built once per program,
  and Huffman and FSE tables are rebuilt in place, with one bit reader for every stream.
- Snappy reserves at most 22 bytes per input byte (a 3-byte copy gives 64), whatever its
  header declares, and grows past that only if the data does.
- Encoder tables are sized to the input (the next power of two, at least 256 entries, at most
  the window). Below full size a hash keeps its low bits, so large inputs compress as before.

`toolchain/tests/v2/squash_hostile.tin` decodes the inputs of #440 inside `limit memory` of 12
times the input plus 6 times the output plus 4 MiB, and calls each encoder 1000 times on 1 KiB
within 64 MiB. A hostile zstd block of 10 bytes still costs about 100 bytes of small objects
(string slices for the block, its literals and its streams); removing those needs the block
parser to work on offsets.

## Checked

- gzip: the header CRC-16 (FHCRC), as Go does.
- LZ4: a skippable frame cut short fails.
- zstd: an 8-byte content size of 2^63 or more fails with `fault.LimitExceeded`; a block that
  decompresses to more than 128 KiB fails; a Huffman tree description with more than 255
  weights fails; a repeat table mode in a frame's first block fails (there is nothing to repeat).

## Decided leniencies

- zstd: the window descriptor is read and not used. The decoder keeps the whole frame as
  history (bounded by `max`), so a window larger than the reference decoder's default limit
  (2^27) is accepted, and offsets are checked against the frame's start, not the window.
- zstd: the largest block is 128 KiB, not min(window size, 128 KiB): with a window below
  128 KiB, a block between the two sizes is accepted.
