// The own certificates of VeriFactu's e2e (apps/verifactu/WORKBOOK.md, VERIFACTU-F02–F04), made here and never a
// real one: a .p12 an authority of the test issued, the issuer's NIF as its organisation identifier, valid for a year.
// The Hub refuses it on upload, as it refuses any certificate no authority of Spain's trusted list issued
// (`makeP12`); the screen of a business whose certificate counts is reached by keeping one in `a`'s database as an
// upload of a recognised one leaves it (`keepCertificate`), since no test can hold a recognised authority's key.
import { execFileSync, spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { HUB_DIR } from './helpers';

/** The holder the certificates say. */
export const HOLDER = 'E2E PELUQUERIA ANA SL';

/** Python that builds `p12` (and `cert`) for `nif` with `password`. */
const P12_PY = `import datetime as dt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

def make(nif, password):
    key, authority_key = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))
    authority = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "E2E TEST AUTHORITY")])
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "${HOLDER}"),
        x509.NameAttribute(NameOID.ORGANIZATION_IDENTIFIER, "VATES-" + nif),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, "12345678Z"),
    ])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(authority).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    p12 = pkcs12.serialize_key_and_certificates(b"e2e", key, cert, None, serialization.BestAvailableEncryption(password.encode()))
    return p12, cert
`;

/** Writes to `path` a .p12 of the test for `nif`, opened by `password`. */
export function makeP12(dir: string, path: string, nif: string, password: string): void {
  const script = join(dir, 'make_p12.py');
  writeFileSync(script, `${P12_PY}\nimport sys\nopen(sys.argv[1], "wb").write(make(sys.argv[3], sys.argv[2])[0])\n`);
  execFileSync('uv', ['run', 'python', script, path, password, nif], { cwd: HUB_DIR, stdio: 'pipe' });
}

/** Keeps in `a`'s database a certificate of the test for `nif`, sealed with the server's key and marked as checked
 *  against the kept trusted list, as the upload of a recognised one leaves it. */
export function keepCertificate(nif: string, password: string): void {
  const code = `${P12_PY}
from apps.verifactu import certificates, trust
from apps.verifactu.models import OwnCertificate
p12, cert = make(${JSON.stringify(nif)}, ${JSON.stringify(password)})
OwnCertificate.objects.update_or_create(singleton=True, defaults={
    "holder": "${HOLDER}", "holder_tax_id": ${JSON.stringify(nif)}, "kind": "representative",
    "expires_at": cert.not_valid_after_utc, "uploaded_by": "e2e",
    "sealed_blob": certificates.seal(p12, ${JSON.stringify(password)}),
    "issuer_recognised": True, "checked_list": trust.sequence(),
})
`;
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', code], {
    cwd: HUB_DIR,
    env: process.env,
    encoding: 'utf8',
  });
  if (out.status !== 0) throw new Error(`Could not keep the test's certificate in a: ${out.stderr}`);
}
