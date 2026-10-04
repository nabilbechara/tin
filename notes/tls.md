# TLS 1.3 (#124): design notes and the interfaces between phases

Two sessions work on #124: session A owns phases 1, 3 and 4 (primitives, the client, the
database clients), session B phases 2 and 5 (signatures and X.509, the server). Each
algorithm lives in its own file in `lib/seal/`, the protocol in `lib/tls/`.

## Phase 1 to phase 2: P-256 and SHA-2 (agreed in #124 before either side builds on it)

All in package `seal`, so phase 2's `ecdsa.tin` calls these lower-case functions directly.
Every function is constant-time in secret inputs unless it says otherwise.

Prime fields (`field.tin`): `monty` holds a prime modulus and its Montgomery constants. An
element is a `[]u64` of n 32-bit limbs, least significant first, in Montgomery form.

| function | meaning |
|---|---|
| `new_monty(m, rr, one, minv)` | a modulus (limbs), R^2 mod m, R mod m, -m^-1 mod 2^32 |
| `f.elem()` | a new zero element |
| `f.mul(mut z, x, y)`, `f.add`, `f.sub` | z = x·y, x+y, x−y (z may alias x or y) |
| `f.inv(mut z, x)` | z = x^(m−2) (0 for 0) |
| `f.exp(mut z, x, e)` | z = x^e, e big-endian bytes, public |
| `f.from_bytes(mut z, b) u64` | big-endian bytes into Montgomery form; 0 when not 4n bytes or ≥ m |
| `f.to_bytes(x) []u8` | out of Montgomery form, big-endian |
| `f.sel(mut z, a, b, bit)`, `f.is_zero(x) u64`, `f.equal(x, y) u64`, `f.set(mut z, x)` | constant-time helpers |

P-256 (`p256.tin`): `p256f` (the field), `p256n` (scalars mod n), points `p256pt{x, y, z}`
projective with complete formulas.

| function | meaning |
|---|---|
| `p256_decode(b) !p256pt` | uncompressed (65 bytes) or compressed (33 bytes); checks the curve equation |
| `p256_encode(p) ![]u8` | uncompressed; fails for the identity |
| `p256_generator()`, `p256_identity()` | G and the identity (0:1:0) |
| `p256_add(mut r, p, q)`, `p256_double(mut r, p)` | complete addition and doubling |
| `p256_mul(mut r, p, k)` | r = k·p, k 32 big-endian bytes, constant-time in k |
| `p256_affine(p) ([]u8, []u8, u64)` | affine x, y (32 bytes each) and 1, or 0 for the identity |
| `p256_scalar_ok(k) u64` | 1 when k is 32 bytes in [1, n−1] |

ECDSA P-256 verification (phase 2) needs: s⁻¹ mod n with `p256n.inv`, u1 and u2 with
`p256n.mul` (convert with `p256n.from_bytes`, reducing a hash ≥ n first), then
`p256_mul(G, u1) + p256_mul(Q, u2)` and `p256_affine`. P-384 is a second `monty` with its
own constants and the same point code over it (phase 2).

Exported: `P256NewPrivateKey`, `P256PublicKey`, `P256ECDH`, `Sha384`, `Sha512`, `Hmac`,
`HkdfExtract`, `HkdfExpand`, `HkdfExpandLabel` (docs/STDLIB.md).

## Phase 2 to phase 3: certificate verification (proposed; session B decides the names)

The client calls, after the server's Certificate and CertificateVerify:

    verify_chain(chain [][]u8, host str, roots ?Roots, now_unix i64) !PublicKey
    verify_signature(scheme u16, key PublicKey, msg []u8, sig []u8) !

`chain` is the DER certificates in the order received; `scheme` is the TLS
SignatureScheme code (0x0403 ecdsa_secp256r1_sha256, 0x0804 rsa_pss_rsae_sha256, 0x0807
ed25519, ...). Until these land, phase 3 runs its tests with `InsecureSkipVerify`.
