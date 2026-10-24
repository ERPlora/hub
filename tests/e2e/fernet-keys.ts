// The Fernet keys an e2e stack's runserver seals with (config/settings.py): `FISCAL_CERTIFICATE_KEY`, a business's own
// VeriFactu certificate, and `FLOW_SECRETS_KEY`, the secrets of the automations. Without the first the Hub refuses
// every upload (409 verifactu.certificate_storage_unavailable), and «Mi certificado» of verifactu-config.spec.ts failed
// on every stack whose .env lacked it (2026-10-19); without the second the «Secrets» box of «Call another system» says
// the server cannot keep secrets instead of showing its fields, and FLOW-F26 of flow-steps.spec.ts timed out on every
// such stack (2026-10-24). Django reads each from the environment or else from the checkout's .env (python-decouple),
// so `database.ts`, which the recipe runs before runserver, leaves them there: generated for this checkout when the
// .env has none, or has it empty as .env.example ships it; never a fixed key. A key already in the .env or in the
// environment is kept as it is. They only seal the test certificates and secrets the specs make and remove.
import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The keys this module gives: what each seals on the stack, and what the Hub refuses without it. */
const KEYS = {
  FISCAL_CERTIFICATE_KEY: { seals: "the e2e's test certificates", refuses: 'every certificate upload' },
  FLOW_SECRETS_KEY: { seals: "the e2e's automation secrets", refuses: 'every secret of an automation' },
} as const;

export type FernetKeyName = keyof typeof KEYS;

/** How to make one by hand (`.env.example`): what apps.verifactu.certificates.generate_key() does. */
const GENERATE = 'uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"';

/** The checkout's .env: config/settings.py reads it through python-decouple, which looks for one from config/ up. */
export const ENV_FILE = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');

/** Where the run's key comes from: the environment, the .env as it was, or one generated into the .env now. */
export type KeySource = 'environment' | 'env-file' | 'generated';

/** One key of the run and where it came from. */
export type GivenKey = { name: FernetKeyName; source: KeySource };

/** Whether Fernet takes `value` as its key (apps/verifactu/certificates.py, apps/flow/vault.py): 32 bytes in padded
 *  base64, in the URL-safe alphabet or the standard one (Python's decoder takes both). */
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

/** The checkout's .env, split in lines to fill, with the lines to append at its end. */
function readEnvFile(envFile: string): { lines: string[]; appended: string[] } {
  if (!existsSync(envFile)) {
    throw new Error(
      `No .env at ${envFile}: runserver would read another one further up the tree. Create it ` +
        '(README.md, «Desarrollo local») and rerun.',
    );
  }
  return { lines: readFileSync(envFile, 'utf8').split('\n'), appended: [] };
}

/**
 * Leaves runserver a usable key for each of `names`, said in that order: the environment's (Django reads it before
 * the .env, even empty) or the .env's, as they are; otherwise a new one, written into the .env's empty line for it or
 * appended to it. Throws, writing nothing at all, on a value that is no key, or on a checkout without its .env when a
 * key has to come from it (runserver would read one further up the tree, and a new .env holding only the keys would
 * hide it).
 */
export function ensureFernetKeys(names: readonly FernetKeyName[], envFile: string, env: NodeJS.ProcessEnv): GivenKey[] {
  const given: GivenKey[] = [];
  let file: { lines: string[]; appended: string[] } | undefined;
  for (const name of names) {
    const exported = env[name];
    if (exported !== undefined) {
      if (!isFernetKey(exported.trim())) {
        throw new Error(
          `${name} in the environment is no Fernet key (32 bytes, URL-safe base64), and Django reads it before the .env: ` +
            `the Hub would refuse ${KEYS[name].refuses}. Unset it, or export a key (\`${GENERATE}\`).`,
        );
      }
      given.push({ name, source: 'environment' });
      continue;
    }
    file ??= readEnvFile(envFile);
    // python-decouple keeps the last line that sets it (spaces allowed around `=`).
    const at = file.lines.findLastIndex((line) => new RegExp(`^\\s*${name}\\s*=`).test(line));
    if (at < 0) {
      file.appended.push(`# The key of ${KEYS[name].seals}, made for this checkout by tests/e2e/database.ts.`, `${name}=${newFernetKey()}`);
      given.push({ name, source: 'generated' });
      continue;
    }
    const value = valueOf(file.lines[at]);
    if (isFernetKey(value)) {
      given.push({ name, source: 'env-file' });
      continue;
    }
    if (value !== '') {
      throw new Error(
        `${name} in ${envFile} is no Fernet key (32 bytes, URL-safe base64): the Hub would refuse ${KEYS[name].refuses}. ` +
          `Fix it, or empty it and rerun to get one made for this checkout (by hand: \`${GENERATE}\`).`,
      );
    }
    file.lines[at] = `${name}=${newFernetKey()}`;
    given.push({ name, source: 'generated' });
  }
  if (file && given.some(({ source }) => source === 'generated')) {
    const filled = file.lines.join('\n');
    if (file.appended.length === 0) writeFileSync(envFile, filled);
    else {
      const separator = filled === '' || filled.endsWith('\n') ? '' : '\n';
      writeFileSync(envFile, `${filled}${separator}${file.appended.join('\n')}\n`);
    }
  }
  return given;
}
