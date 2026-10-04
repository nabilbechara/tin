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

## Phase 2 to phase 3: certificate verification

Session B's `notes/interface_tls.md` (#304) defines the certificate API the client uses:
`ParseCertificate`, `Certificate.Verify(VerifyOptions{DNSName, Roots, Intermediates, Now})`,
`NewCertPool`/`AddPEM`/`SystemRoots` and `Certificate.CheckTLSSignature(scheme, signed, sig)`.
The client calls them from one place, `verify_peer` in `lib/tls/verify.tin`, with the chain as
received (DER, leaf first), the server name, the SignatureScheme and the CertificateVerify
content (64 spaces, the context string, a zero byte, the transcript hash). Until that API is on
main, `verify_peer` refuses every server unless `InsecureSkipVerify` is set.

Phase 2's files: `der.tin` (strict DER reader), `bignum.tin` (`monty_new`: Montgomery constants
computed at run time, so `field.tin`'s `monty` serves RSA moduli), `rsa.tin` (PKCS #1 v1.5 and
PSS verification), `x509.tin` (PEM, certificates, pools, chains, host names),
`roots_linux.tin` / `roots_darwin.tin` (system bundle paths), `ecdsa.tin` (`VerifyECDSA`),
`p384.tin` (P-384 over a curve value); later `ed25519.tin`. All exported, in `seal`.

## lib/tls (phase 3)

| file | contents | used by the server (phase 5) |
|---|---|---|
| `tls.tin` | Config, Dial, Client, the public Conn methods | Conn methods |
| `record.tin` | Conn state, socket I/O and waits, record protection, alerts, KeyUpdate | yes |
| `schedule.tin` | cipher suites, key schedule, Finished MACs | yes |
| `messages.tin` | wire-format reader/writer, ClientHello, parsers of the server's messages | the reader/writer |
| `client.tin` | the client handshake | no |
| `verify.tin` | the bridge to X.509 | no |

Decisions:
- A Conn changes only in place after the handshake (`seal.AEAD.Rekey`, copies into its own
  slices), so the same Conn works in a request pool, a websocket's per-message pools and
  `keep()`'s heap (the database clients, phase 4).
- No middlebox-compatibility change_cipher_spec is sent; the server's is ignored during the
  handshake. The session id is 32 random bytes (servers expect it).
- The client offers only X25519 in its first key share and supported_groups lists P-256, so a
  P-256-only server costs one HelloRetryRequest.
- Signature schemes offered: ECDSA P-256/P-384, RSA-PSS SHA-256/384/512, Ed25519, and PKCS #1
  v1.5 (for certificates only; a CertificateVerify with it is refused).
- A server's CertificateRequest gets an empty Certificate (no client certificates yet).
- After 2^24 records under one key the client sends KeyUpdate.

Tests: `tools/ci/tls_check.py` (CI.md).
The client parses the Certificate message's entries with `ParseCertificate`, puts all but the
first into an `Intermediates` pool, and calls `leaf.Verify` with `DNSName` set to the server
name (an IP literal is checked against the IP SANs). `Roots` nil means `SystemRoots()` (read
once per core; `SSL_CERT_FILE` overrides the path); `Config.RootCAs` PEM goes into a pool with
`AddPEM`. `Now` 0 means the clock; `KeyUsages` empty means server authentication. `Verify`
returns the chain, leaf first. Then `leaf.CheckTLSSignature(scheme, signed, sig)` checks
CertificateVerify, `signed` being the 64 spaces, the context string, a zero byte and the
transcript hash, as RFC 8446 §4.4.3 builds it. `scheme` is the SignatureScheme code
(0x0804-0x0806 RSA-PSS, 0x0403 ECDSA P-256 and 0x0503 ECDSA P-384, each checking that the
certificate's key is on the scheme's curve; 0x0807 when Ed25519 lands). Faults start
with "x509: " and name the reason: expired or not yet valid, the names the certificate is
valid for, unknown authority, not a CA, bad signature, SHA-1, chain too long, path length,
key usage, name constraints, unhandled critical extension.
