#!/usr/bin/env python3
"""Derives the APK signing key from a passphrase, so CI signs every build with the same key
without a keystore file (Android only installs an update over the previous version when both are
signed with the same certificate, and reinstalling wipes the app's data).

    APP_SIGNING_SEED='<long passphrase>' python3 signing-key.py <out.p12>

The passphrase is stretched with scrypt; its bytes feed a SHAKE-256 stream from which the RSA-2048
primes are drawn. The self-signed certificate has fixed fields and an RSA PKCS#1 v1.5 signature
(deterministic), so the same passphrase always yields the same key *and* the same certificate.
Anyone with the passphrase can sign updates for the installed app: use a long random one and keep
it only in the repository secret. Prints the keystore password and alias as GITHUB_ENV lines.
"""
import datetime
import hashlib
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

ALIAS = "app"
E = 65537
SMALL_PRIMES = [p for p in range(3, 2000) if all(p % d for d in range(2, int(p ** 0.5) + 1))]


class Stream:
    """Deterministic byte stream (SHAKE-256 over a counter) keyed by the stretched passphrase."""

    def __init__(self, key: bytes):
        self.key, self.counter = key, 0

    def read(self, n: int) -> bytes:
        self.counter += 1
        return hashlib.shake_256(self.key + self.counter.to_bytes(8, "big")).digest(n)

    def int_below(self, bound: int) -> int:
        return int.from_bytes(self.read((bound.bit_length() + 7) // 8 + 8), "big") % bound


def is_probable_prime(n: int, rng: Stream, rounds: int = 48) -> bool:
    if any(n % p == 0 for p in SMALL_PRIMES):
        return n in SMALL_PRIMES
    d, s = n - 1, 0
    while d % 2 == 0:
        d, s = d // 2, s + 1
    for _ in range(rounds):
        x = pow(2 + rng.int_below(n - 3), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def prime(bits: int, rng: Stream) -> int:
    while True:
        # Top two bits set (so p*q has exactly 2*bits bits) and odd.
        c = int.from_bytes(rng.read(bits // 8), "big") | (0b11 << (bits - 2)) | 1
        if (c - 1) % E and is_probable_prime(c, rng):
            return c


def derive_key(seed: str) -> rsa.RSAPrivateKey:
    stretched = hashlib.scrypt(seed.encode(), salt=b"proot-app-apk-signing-v1", n=2 ** 15, r=8, p=1, maxmem=64 << 20, dklen=32)
    rng = Stream(stretched)
    p = prime(1024, rng)
    q = prime(1024, rng)
    while q == p:
        q = prime(1024, rng)
    p, q = max(p, q), min(p, q)
    d = pow(E, -1, (p - 1) * (q - 1))
    numbers = rsa.RSAPrivateNumbers(p, q, d, rsa.rsa_crt_dmp1(d, p), rsa.rsa_crt_dmq1(d, q), rsa.rsa_crt_iqmp(p, q),
                                    rsa.RSAPublicNumbers(E, p * q))
    return numbers.private_key()


def certificate(key: rsa.RSAPrivateKey) -> x509.Certificate:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PRoot App"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PRoot App")])
    serial = int.from_bytes(hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)).digest()[:16], "big") >> 1
    return (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(serial)
            .not_valid_before(datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
            .not_valid_after(datetime.datetime(2076, 1, 1, tzinfo=datetime.timezone.utc))
            .sign(key, hashes.SHA256(), rsa_padding=padding.PKCS1v15()))


def main() -> int:
    seed = os.environ.get("APP_SIGNING_SEED", "")
    if len(seed) < 16:
        print("APP_SIGNING_SEED ausente ou curto demais (mínimo 16 caracteres).", file=sys.stderr)
        return 1
    out = sys.argv[1]
    key = derive_key(seed)
    cert = certificate(key)
    password = hashlib.sha256(b"proot-app-keystore:" + seed.encode()).hexdigest()[:32]
    with open(out, "wb") as f:
        f.write(pkcs12.serialize_key_and_certificates(ALIAS.encode(), key, cert, None, serialization.BestAvailableEncryption(password.encode())))
    os.chmod(out, 0o600)
    fingerprint = cert.fingerprint(hashes.SHA256()).hex(":").upper()
    print(f"Certificado SHA-256: {fingerprint}", file=sys.stderr)
    print(f"APP_KEYSTORE_FILE={os.path.abspath(out)}")
    print(f"APP_KEYSTORE_PASSWORD={password}")
    print(f"APP_KEY_ALIAS={ALIAS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
