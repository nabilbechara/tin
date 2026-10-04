# seal: notes

## SHA-384/512, HMAC, HKDF (#124 phase 1)

API: `Sha512`, `Sha384`, `type Hash enum { SHA256, SHA384, SHA512 }`, `Sum`, `Size`,
`BlockSize`, `Hmac`, `HkdfExtract`, `HkdfExpand`, `HkdfExpandLabel`.

- One file per algorithm (`sha512.tin`, `hkdf.tin`), so the TLS phases rarely touch the same
  file. SHA-512 is portable code: x86-64 has no SHA-512 instructions and the ARMv8.2 SHA512
  extension is optional; TLS hashes little data with it.
- `Hmac` and HKDF take the hash as a `Hash` value; `HmacSha256` stays as it was.
- `HkdfExpandLabel` takes the label without its `tls13 ` prefix, like RFC 8446's notation.
- Gaps: no streaming (incremental) hash yet; TLS hashes the transcript it keeps.

Tests: `tests/v2/seal_hkdf.tin` (FIPS 180-4, RFC 4231, RFC 5869, RFC 8448 values; Go twin
`bench/ref/seal_hkdf`), and `tools/ci/crypto_check.py` (Wycheproof `hmac_sha*` and `hkdf_sha*`,
and hashlib on every length from 0 to 299 bytes).
