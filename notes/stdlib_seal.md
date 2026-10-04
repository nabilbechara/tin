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

## P-256 (#124 phase 1)

API: `P256NewPrivateKey`, `P256PublicKey`, `P256ECDH`; internal field and point functions for
ECDSA are listed in notes/tls.md.

- `field.tin` is generic Montgomery arithmetic over 32-bit limbs (no 64x64->128 multiply is
  needed), constant-time; `p256.tin` uses the complete formulas of Renes-Costello-Batina and a
  4-bit fixed window with a full-table scan.
- Performance gap: about 3.4 ms per ECDH on Linux x86-64 against Go's 70 us (assembly). The
  next step is a P-256-specific unrolled multiplication; the internal API does not change.

Tests: `tests/v2/seal_p256.tin` (Go twin `bench/ref/seal_p256`), and Wycheproof
`ecdh_secp256r1_ecpoint` in `tools/ci/crypto_check.py`.
