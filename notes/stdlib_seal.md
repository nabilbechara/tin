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

## Signatures and certificates (#124 phase 2)

API: `VerifyPKCS1v15`, `VerifyPSS`, `VerifyECDSA`, `RSAKeyBits`, `ParseRSAPublicKeyDER`, `DecodePEM`
(`PEMBlock`), `ParseCertificate`, `ParseCertificatesPEM`, `Certificate` (with `Name`,
`SignatureAlgorithm`, `PublicKeyAlgorithm`, the `KeyUsage*` and `ExtKeyUsage*` constants),
`Certificate.Verify` (`VerifyOptions`), `CheckSignature`, `CheckSignatureFrom`,
`CheckTLSSignature`, `VerifyHostname`, `ParseIP`, `CertPool` (`NewCertPool`, `Add`, `AddPEM`,
`Len`, `Certificates`), `SystemRoots`.

- `der.tin` is a strict DER reader (minimal lengths and integers, one-byte tags); `x509.tin`
  rejects every byte-flipped certificate Go rejects and a few more (Go ignores trailing bytes
  inside names, after the TBS and after the signature).
- RSA runs on `field.tin`'s `monty`; `bignum.tin`'s `monty_new` computes the Montgomery
  constants of a modulus at run time. Keys of 2048 to 8192 bits, odd exponents up to 2^32.
- Stricter than Go, on purpose: chains of at most 8 certificates, RSA keys of at least 2048
  bits, a wildcard needs two labels after `*.`, a host name containing `*` never matches.
- ECDSA: P-256 on `p256.tin`'s points and `p256n`; P-384 on `p384.tin`, the same complete
  formulas written once over a curve value with a `monty_new` field. u1*G + u2*Q uses 4-bit
  windows skipping zero digits (public data). P-521 is not supported (no Web PKI root uses it).
- Gaps: Ed25519 (waits for the 25519 field of X25519),
  name constraints on email, URI and directory names (a CA with them is refused when the leaf
  has such names), CRLs and OCSP. Speed: RSA-2048 verification takes about 0.9 ms on Linux
  x86-64 against Go's 30 us; a faster `monty.mul` (one pass per row over raw words) halves it.

Tests: `tests/v2/seal_wycheproof.tin` (13 Wycheproof RSA files), `seal_wycheproof_ecdsa.tin`
(5 ECDSA files), `tests/v2/seal_x509.tin`
(46 chain cases), `tests/v2/seal_certinfo.tin` (fields, IP parsing, PEM, host names), each
with a Go twin, and `tools/ci/x509_check.py` (fresh PKI, mutated certificates, system roots).
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

## AES-GCM (#124 phase 1)

API: `NewAESGCM(key)` (16-, 24- or 32-byte keys) returning the same `AEAD` as ChaCha20-Poly1305.
Nonces are 12 bytes only, like Go's `cipher.NewGCM`.

- Software path (every CPU): bitsliced AES, four blocks in eight u64 planes. The S-box is
  computed, not looked up: x^254 in GF(2^8) plus the affine map, generated as straight-line
  ANDs and XORs by `tools/gen_aes_sbox.py` into `aes_sbox.tin`. The key schedule uses the same
  circuit. GHASH uses 32x32 integer multiplications on operands with holes (BearSSL's
  ctmul idea) and Karatsuba.
- Performance gap: the software path is a constant-time fallback; on Linux x86-64 it runs at
  about 8 MB/s (ChaCha20-Poly1305 about 38 MB/s), partly because the x86-64 backend keeps
  only four locals in registers. The AES-NI/PCLMULQDQ and ARMv8 AES/PMULL paths come in
  their own PR (they need hand-assembled functions in the code generators).

Tests: `tests/v2/seal_aes.tin` (NIST GCM cases, every length class for all key sizes,
tampering; Go twin `bench/ref/seal_aes`), and Wycheproof `aes_gcm` in `tools/ci/crypto_check.py`.

## Private keys and signing (#124 phase 5 prerequisites)

API: `ParsePrivateKeyPEM`, `ParsePrivateKeyDER` (`PrivateKey` with `RSA ?RSAPrivateKey` and
`EC ?ECPrivateKey`), `PrivateKey.MatchesCertificate`, `PrivateKey.SignTLS(scheme, msg)`,
`SignPKCS1v15`, `SignPSS`, `SignECDSA`.

- Formats: PKCS #8 (RSA, EC), PKCS #1 RSA (two primes), SEC 1 EC; P-256 and P-384. Refused:
  RSA outside 2048–8192 bits, P-521, Ed25519 keys, encrypted keys, inconsistent keys (p*q must
  be n, a test signature must verify, a SEC 1 public key must match the scalar).
- The private parts are `secret` fields readable only inside seal.
- RSA: CRT with base blinding; every signature is checked with the public key before it is
  returned. ECDSA: RFC 6979 deterministic nonces (equal to Go's `Sign(nil, ...)` byte for byte).
- Speed on Linux x86-64: RSA-2048 signing about 27 ms, P-256 about 2 ms, P-384 about 6 ms; Go
  is about 1 ms, 20 us and 300 us. All of it is `monty.mul`; see the FIOS proposal in #124.

Tests: `tests/v2/seal_sign.tin` (Go twin `bench/ref/seal_sign`, test keys in `tests/data/keys`
labelled "TESTING KEY"), and `tools/ci/x509_check.py`, where Go verifies TLS signatures Tin made.
## AES-GCM on the CPU's instructions (#124 phase 1)
- `tools/arch/aes-gcm-{arm64,amd64}.S` hold three leaves (CTR with GCM's 32-bit counter,
  GHASH, and on x86-64 the CPUID check); `tools/gen_aes_hw.py` assembles them with clang into
  `selfhost/aes_hw.tin`, and `gen.tin` / `gen_x64.tin` emit those bytes for the placeholders
  `seal.aes_hw_ctr`, `seal.ghash_hw` and `seal.aes_hw_cpu`, as they do for `seal.hw_blocks`.
- GHASH bit-reverses each byte (RBIT, or PSHUFB on nibbles on x86-64) so the carry-less
  multiply works on a plain polynomial; the reduction is two more multiplies by 0x87. The same
  steps on both CPUs.
- Detection: `aes_hw()` in seal_linux.tin (AT_HWCAP bits 3 and 4 on arm64, CPUID on x86-64)
  and seal_darwin.tin (always). `TIN_SEAL_SOFT=1` forces the software path.
- One block at a time today: about 780 MB/s for AES-128-GCM on Linux x86-64 in a shared
  container, against several GB/s for Go's interleaved assembly; interleaving four blocks is
  the next step.
