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

## X25519 and ChaCha20-Poly1305 (#124 phase 1)

API: `X25519`, `X25519PublicKey`, `X25519NewPrivateKey`, `ChaCha20`, `type AEAD` with
`NewChaCha20Poly1305`, `Seal`, `Open`, `NonceSize`, `Overhead`.

- X25519 uses ten signed limbs in radix 2^25.5 so products fit in 64 bits; it fails on an
  all-zero result (RFC 8446 7.4.2 requires the check). About 0.85 ms per operation on Linux
  x86-64 before tuning.
- ChaCha20 keeps the state in locals and xors eight bytes at a time; Poly1305 is the 26-bit
  limb form (poly1305-donna). AES-GCM joins `AEAD` as another kind.

Tests: `tests/v2/seal_x25519_chacha.tin` (RFC 7748, RFC 8439, every length class, tampering;
the Go twin `bench/ref/seal_x25519_chacha` uses crypto/ecdh and an independent math/big
Poly1305), and Wycheproof `x25519` and `chacha20_poly1305` in `tools/ci/crypto_check.py`.
