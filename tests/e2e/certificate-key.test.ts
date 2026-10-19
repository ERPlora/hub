// The key that seals a business's own VeriFactu certificate (`FISCAL_CERTIFICATE_KEY`, config/settings.py) on the
// e2e's stack. Without it the Hub refuses every upload (409 verifactu.certificate_storage_unavailable), and
// verifactu-config.spec.ts failed at «Mi certificado» on every stack whose .env lacked it (2026-10-19, seen in the
// run of hub#34). `node tests/e2e/database.ts`, which the recipe runs before runserver, now leaves one in the
// checkout's .env: generated for that checkout when missing or empty, never a fixed one, and the one already there
// (or in the environment) kept as it is.
// flow: ninguno — FIX tests/e2e
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';

import { ENV_FILE, ensureCertificateKey, isFernetKey, newFernetKey } from './certificate-key';

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const NAME = 'FISCAL_CERTIFICATE_KEY';
/** One Django start per probe (`server`): seconds, not milliseconds. */
const PROBE_TIMEOUT_MS = 60_000;

const folders: string[] = [];
afterEach(() => {
  for (const folder of folders.splice(0)) rmSync(folder, { recursive: true, force: true });
});

/** The path of a checkout's .env holding `content`, in a folder of its own; with `null`, a checkout without one. */
function envFile(content: string | null): string {
  const folder = mkdtempSync(join(tmpdir(), 'e2e-certificate-key-'));
  folders.push(folder);
  const path = join(folder, '.env');
  if (content !== null) writeFileSync(path, content);
  return path;
}

/** The lines of the .env at `path` that set the key. */
function keyLines(path: string): string[] {
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((line) => new RegExp(`^\\s*${NAME}\\s*=`).test(line));
}

/**
 * What the Hub's server makes of each .env: the `FISCAL_CERTIFICATE_KEY` python-decouple reads from it, as
 * config/settings.py does, and whether apps.verifactu.certificates keeps a certificate with that key (the check
 * behind the 409).
 */
function server(paths: string[]): { key: string | null; storage: boolean }[] {
  const script = [
    'import json, sys',
    'import django',
    'django.setup()',
    'from decouple import RepositoryEnv',
    'from django.conf import settings',
    'from apps.verifactu import certificates',
    'seen = []',
    'for path in json.loads(sys.argv[1]):',
    `    key = RepositoryEnv(path).data.get("${NAME}")`,
    `    settings.${NAME} = key or ""`,
    '    seen.append({"key": key, "storage": certificates.storage_available()})',
    'print(json.dumps(seen))',
  ].join('\n');
  const env: NodeJS.ProcessEnv = { ...process.env, DEBUG: 'True', DJANGO_SETTINGS_MODULE: 'config.settings' };
  delete env[NAME];
  const run = spawnSync('uv', ['run', 'python', '-c', script, JSON.stringify(paths)], { cwd: HUB_DIR, encoding: 'utf8', env });
  expect(run.status, `${run.stdout}\n${run.stderr}`).toBe(0);
  return JSON.parse(run.stdout.trim().split('\n').at(-1) ?? '');
}

describe('ensureCertificateKey', () => {
  it(
    'gives a .env without the key, or with it empty as .env.example has it, one the Hub keeps certificates with',
    () => {
      const missing = envFile('# local\nDEBUG=True\n');
      const unterminated = envFile('DEBUG=True');
      const empty = envFile('DEBUG=True\nFISCAL_CERTIFICATE_KEY=\nSAAS_URL=http://localhost:8021\n');

      for (const path of [missing, unterminated, empty]) expect(ensureCertificateKey(path, {})).toBe('generated');

      expect(readFileSync(missing, 'utf8')).toMatch(/^# local\nDEBUG=True\n/);
      expect(readFileSync(unterminated, 'utf8')).toMatch(/^DEBUG=True\n/);
      // The empty line is filled where it was: one line for the key, the rest of the file as it was.
      const lines = readFileSync(empty, 'utf8').split('\n');
      expect(lines[0]).toBe('DEBUG=True');
      expect(lines[1]).toMatch(new RegExp(`^${NAME}=\\S+$`));
      expect(lines.slice(2)).toEqual(['SAAS_URL=http://localhost:8021', '']);
      for (const path of [missing, unterminated, empty]) expect(keyLines(path)).toHaveLength(1);

      for (const seen of server([missing, unterminated, empty])) {
        expect(seen.storage).toBe(true);
        expect(seen.key).toMatch(/^[A-Za-z0-9_-]{43}=$/);
      }
    },
    PROBE_TIMEOUT_MS,
  );

  it('generates one per checkout, never a fixed key', () => {
    const first = envFile('DEBUG=True\n');
    const second = envFile('DEBUG=True\n');

    ensureCertificateKey(first, {});
    ensureCertificateKey(second, {});

    expect(keyLines(first)[0]).not.toBe(keyLines(second)[0]);
    expect(newFernetKey()).not.toBe(newFernetKey());
  });

  it('keeps the key the .env already has, byte for byte, quoted or not', () => {
    for (const line of [`${NAME}=${newFernetKey()}`, `${NAME} = "${newFernetKey()}"`]) {
      const content = `DEBUG=True\n${line}\n`;
      const path = envFile(content);

      expect(ensureCertificateKey(path, {})).toBe('env-file');
      expect(readFileSync(path, 'utf8')).toBe(content);
    }
  });

  it('fills the last line that sets it, the one python-decouple reads, when an earlier one holds a key', () => {
    const earlier = newFernetKey();
    const path = envFile(`${NAME}=${earlier}\nDEBUG=True\n${NAME}=\n`);

    expect(ensureCertificateKey(path, {})).toBe('generated');

    const lines = readFileSync(path, 'utf8').split('\n');
    expect(lines[0]).toBe(`${NAME}=${earlier}`);
    expect(lines[2]).toMatch(new RegExp(`^${NAME}=[A-Za-z0-9_-]{43}=$`));
    expect(lines[2]).not.toBe(`${NAME}=${earlier}`);
    expect(lines.slice(3)).toEqual(['']);
  });

  it("keeps the environment's key, which Django reads before the .env, and writes nothing", () => {
    const path = envFile('DEBUG=True\n');

    expect(ensureCertificateKey(path, { [NAME]: newFernetKey() })).toBe('environment');
    expect(readFileSync(path, 'utf8')).toBe('DEBUG=True\n');
  });

  it('refuses a value that is no Fernet key, in the .env or in the environment, touching nothing', () => {
    const inFile = envFile(`DEBUG=True\n${NAME}=not-a-key\n`);
    expect(() => ensureCertificateKey(inFile, {})).toThrow(new RegExp(`${NAME} in ${inFile.replaceAll('.', '\\.')}`));
    expect(readFileSync(inFile, 'utf8')).toBe(`DEBUG=True\n${NAME}=not-a-key\n`);

    // Exported, even empty, it is what Django reads (python-decouple looks at the environment first).
    for (const exported of ['not-a-key', '']) {
      const inEnvironment = envFile(`DEBUG=True\n${NAME}=${newFernetKey()}\n`);
      const before = readFileSync(inEnvironment, 'utf8');
      expect(() => ensureCertificateKey(inEnvironment, { [NAME]: exported })).toThrow(new RegExp(`${NAME} in the environment`));
      expect(readFileSync(inEnvironment, 'utf8')).toBe(before);
    }
  });

  it('refuses a checkout without its .env: runserver would read one further up the tree, and none is made', () => {
    const path = envFile(null);

    expect(() => ensureCertificateKey(path, {})).toThrow(new RegExp(`No \\.env at ${path.replaceAll('.', '\\.')}`));
    expect(existsSync(path)).toBe(false);
  });

  it("works on the checkout's own .env, the one config/settings.py reads", () => {
    expect(ENV_FILE).toBe(join(HUB_DIR, '.env'));
  });
});

describe('isFernetKey', () => {
  it(
    'says of each value what the Hub says',
    () => {
      const ones = Buffer.alloc(32, 0xff);
      const values = [
        newFernetKey(),
        `${ones.toString('base64url')}=`, // URL-safe alphabet, padded: what generate_key() gives
        ones.toString('base64'), // the standard alphabet, which Python's decoder also takes
        ones.toString('base64url'), // no padding
        `${randomBytes(31).toString('base64url')}==`, // 31 bytes
        randomBytes(33).toString('base64url'), // 33 bytes
        'not-a-key',
        '',
      ];
      const said = server(values.map((value) => envFile(`${NAME}=${value}\n`))).map((seen) => seen.storage);

      expect(values.map((value) => isFernetKey(value))).toEqual(said);
      expect(said.slice(0, 3)).toEqual([true, true, true]);
    },
    PROBE_TIMEOUT_MS,
  );
});

describe('.env.example', () => {
  it('documents the key with no value: none is ever committed', () => {
    expect(keyLines(join(HUB_DIR, '.env.example'))).toEqual([`${NAME}=`]);
  });
});
