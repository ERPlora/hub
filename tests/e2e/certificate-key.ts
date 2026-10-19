// The key that seals a business's own VeriFactu certificate (`FISCAL_CERTIFICATE_KEY`, config/settings.py) on an e2e
// stack. Without one the Hub refuses every upload (409 verifactu.certificate_storage_unavailable), and «Mi
// certificado» of verifactu-config.spec.ts failed on every stack whose .env lacked it (2026-10-19). Django reads it
// from the environment or else from the checkout's .env (python-decouple), so `database.ts`, which the recipe runs
// before runserver, leaves one there: generated for this checkout when the .env has none, or has it empty as
// .env.example ships it; never a fixed key. A key already in the .env or in the environment is kept as it is. It only
// seals the test certificates the specs make and remove.
import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const NAME = 'FISCAL_CERTIFICATE_KEY';
/** A line of a .env that sets the key (python-decouple allows spaces around `=`). */
const KEY_LINE = new RegExp(`^\\s*${NAME}\\s*=`);
/** How to make one by hand (`.env.example`): what apps.verifactu.certificates.generate_key() does. */
const GENERATE = 'uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"';

/** The checkout's .env: config/settings.py reads it through python-decouple, which looks for one from config/ up. */
export const ENV_FILE = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');

/** Where the run's key comes from: the environment, the .env as it was, or one generated into the .env now. */
export type KeySource = 'environment' | 'env-file' | 'generated';

/** Whether Fernet takes `value` as its key (apps/verifactu/certificates.py): 32 bytes in padded base64, in the
 *  URL-safe alphabet or the standard one (Python's decoder takes both). */
export function isFernetKey(value: string): boolean {
  return /^[A-Za-z0-9_\-+/]{43}=$/.test(value);
}

/** A new key, as apps.verifactu.certificates.generate_key() makes one: 32 random bytes, URL-safe base64. */
export function newFernetKey(): string {
  return `${randomBytes(32).toString('base64url')}=`;
}

/** The value python-decouple reads from a line `NAME=value`: spaces around it and one pair of quotes off. */
function valueOf(line: string): string {
  const value = line.slice(line.indexOf('=') + 1).trim();
  const quoted = value.length >= 2 && (value[0] === '"' || value[0] === "'") && value.at(-1) === value[0];
  return quoted ? value.slice(1, -1) : value;
}

/**
 * Leaves runserver a usable key: the environment's (Django reads it before the .env, even empty) or the .env's, as
 * they are; otherwise a new one, written into the .env's empty `FISCAL_CERTIFICATE_KEY=` line or appended to it.
 * Throws, touching nothing, on a value that is no key, or on a checkout without its .env (runserver would read one
 * further up the tree, and a new .env holding only the key would hide it).
 */
export function ensureCertificateKey(envFile: string, env: NodeJS.ProcessEnv): KeySource {
  const exported = env[NAME];
  if (exported !== undefined) {
    if (isFernetKey(exported.trim())) return 'environment';
    throw new Error(
      `${NAME} in the environment is no Fernet key (32 bytes, URL-safe base64), and Django reads it before the .env: ` +
        `the Hub would refuse every certificate upload. Unset it, or export a key (\`${GENERATE}\`).`,
    );
  }
  if (!existsSync(envFile)) {
    throw new Error(
      `No .env at ${envFile}: runserver would read another one further up the tree. Create it ` +
        '(README.md, «Desarrollo local») and rerun.',
    );
  }
  const content = readFileSync(envFile, 'utf8');
  const lines = content.split('\n');
  // python-decouple keeps the last line that sets it.
  const at = lines.findLastIndex((line) => KEY_LINE.test(line));
  if (at >= 0) {
    const value = valueOf(lines[at]);
    if (isFernetKey(value)) return 'env-file';
    if (value !== '') {
      throw new Error(
        `${NAME} in ${envFile} is no Fernet key (32 bytes, URL-safe base64): the Hub would refuse every certificate ` +
          `upload. Fix it, or empty it and rerun to get one made for this checkout (by hand: \`${GENERATE}\`).`,
      );
    }
    lines[at] = `${NAME}=${newFernetKey()}`;
    writeFileSync(envFile, lines.join('\n'));
    return 'generated';
  }
  const separator = content === '' || content.endsWith('\n') ? '' : '\n';
  const block = `# The key of the e2e's test certificates, made for this checkout by tests/e2e/database.ts.\n${NAME}=${newFernetKey()}\n`;
  writeFileSync(envFile, `${content}${separator}${block}`);
  return 'generated';
}
