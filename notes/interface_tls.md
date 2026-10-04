# TLS (#124): files and shared names between the two sessions

Two sessions work on #124 at once. Session A owns phases 1, 3 and 4 (primitives, the TLS 1.3
client, TLS in the database clients). Session B owns phases 2 and 5 (signatures and
certificates, the TLS server). Everything below is in package `seal` unless it says `tls`.
All files of a directory package see each other's private names, so private helpers that
cross the line are listed here too. Change a name in this note only with the other
session's agreement in the PR that changes it.

## File ownership

| File | Owner | Contents |
|------|-------|----------|
| `lib/seal/seal.tin` | shared, edit sparingly | existing SHA-256, SHA-1, HMAC-SHA256, PBKDF2, base64, RSA-OAEP |
| `lib/seal/sha512.tin` | A | `Sha384`, `Sha512` |
| `lib/seal/hkdf.tin`, `hmac.tin` | A | generic HMAC, HKDF, `HKDF-Expand-Label` |
| `lib/seal/aes*.tin`, `gcm*.tin`, `chacha*.tin` | A | AEADs |
| `lib/seal/x25519.tin` | A | X25519 and the GF(2^255-19) field |
| `lib/seal/p256.tin` | A | P-256 field and point arithmetic, ECDH |
| `lib/seal/hash.tin` | B creates, A adds cases | the `Hash` enum below |
| `lib/seal/bignum.tin` | B | Montgomery bignum (RSA) |
| `lib/seal/rsa.tin` | B | RSA PKCS #1 v1.5 and PSS verification, later signing |
| `lib/seal/x509.tin` | B | DER reader, certificates, pools, chains, hostnames |
| `lib/seal/roots_linux.tin`, `roots_darwin.tin` | B | system root file paths |
| `lib/seal/ecdsa.tin`, `p384.tin` | B | ECDSA over P-256 (A's arithmetic) and P-384 |
| `lib/seal/ed25519.tin` | B | Ed25519 over A's field |
| `lib/tls/*.tin` | A (client), B (server files `server*.tin`) | the `tls` package |

## Hash identity

    type Hash enum { SHA1, SHA256, SHA384, SHA512 }
    func HashSum(h Hash, msg str) []u8     // the digest of msg
    func HashSize(h Hash) i64              // 20, 32, 48, 64

`hash.tin` starts with SHA-1 and SHA-256; until `Sha384`/`Sha512` exist, `HashSum` panics for
them and the verifiers fail with "seal: SHA-384 is not available yet". A's SHA-512 PR fills
the two cases.

## What B needs from A's P-256 (private names)

ECDSA verification needs `u1·G + u2·Q` and the order n. B owns the arithmetic modulo n.

    p256_point_decode(b []u8) !P256Point   // uncompressed SEC 1 point, checked on the curve
    p256_base_mult(k []u8) P256Point       // k·G, k 32 bytes big-endian, constant time
    p256_mult(p P256Point, k []u8) P256Point
    p256_add(p P256Point, q P256Point) P256Point
    p256_affine_x(p P256Point) []u8        // 32 bytes big-endian; the point at infinity is a fault-free 0

If A's design differs, A's names win and this section is updated in A's PR.

## What A's client uses from B (public API)

    ParseCertificate(der []u8) !Certificate
    (c Certificate) Verify(opts VerifyOptions) ![]Certificate   // leaf first, root last
    VerifyOptions{DNSName, Roots ?CertPool, Intermediates ?CertPool, Now i64 (unix seconds, 0 = clock), KeyUsage}
    NewCertPool() CertPool; (p mut CertPool) AddPEM(pem str) !i64; SystemRoots() !CertPool
    (c Certificate) CheckTLSSignature(scheme i64, signed []u8, sig []u8) !

`scheme` is the TLS 1.3 SignatureScheme code (0x0804 rsa_pss_rsae_sha256, 0x0805, 0x0806,
0x0403 ecdsa_secp256r1_sha256, 0x0503 ecdsa_secp384r1_sha384, 0x0807 ed25519). The client
builds the 64 spaces, the context string and the transcript hash; this checks the signature
over those bytes with the leaf's key. Faults start with "x509: " or "seal: ".

## What B's server uses from A

The record layer, the key schedule and the AEADs from `tls`: B's server reuses A's record
and handshake-message code, adding only the server state machine. The split of `lib/tls/`
into files is agreed in A's first `tls` PR.
