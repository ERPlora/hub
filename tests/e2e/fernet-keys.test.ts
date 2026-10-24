// The Fernet keys an e2e stack's runserver needs (config/settings.py): `FISCAL_CERTIFICATE_KEY`, which seals a
// business's own VeriFactu certificate, and `FLOW_SECRETS_KEY`, which seals the secrets of the automations. Without
// the first the Hub refuses every upload (409 verifactu.certificate_storage_unavailable), and verifactu-config.spec.ts
// failed at «Mi certificado» on every stack whose .env lacked it (2026-10-19, seen in the run of hub#34); without the
// second the «Secrets» box of «Call another system» shows that the server cannot keep secrets instead of its fields,
// and flow-steps.spec.ts timed out at FLOW-F26 on every stack whose .env lacked it (2026-10-24, seen in the run of
// hub#238). `node tests/e2e/database.ts`, which the recipe runs before runserver, leaves both in the checkout's .env:
// generated for that checkout when missing or empty, never a fixed one, and the one already there (or in the
// environment) kept as it is.
// flow: ninguno — FIX tests/e2e
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';

import { ENV_FILE, ensureFernetKeys, isFernetKey, newFernetKey } from './fernet-keys';

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const NAMES = ['FISCAL_CERTIFICATE_KEY', 'FLOW_SECRETS_KEY'] as const;
type Name = (typeof NAMES)[number];
/** One Django start per probe (`server`): seconds, not milliseconds. */
const PROBE_TIMEOUT_MS = 60_000;

const folders: string[] = [];
afterEach(() => {
  for (const folder of folders.splice(0)) rmSync(folder, { recursive: true, force: true });
});

/** The path of a checkout's .env holding `content`, in a folder of its own; with `null`, a checkout without one. */
function envFile(content: string | null): string {
  const folder = mkdtempSync(join(tmpdir(), 'e2e-fernet-keys-'));
  folders.push(folder);
  const path = join(folder, '.env');
  if (content !== null) writeFileSync(path, content);
  return path;
}

/** The lines of the .env at `path` that set `name`. */
function keyLines(path: string, name: Name): string[] {
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((line) => new RegExp(`^\\s*${name}\\s*=`).test(line));
}

/** What the Hub's server makes of one key of a .env: the value python-decouple reads, and whether it works. */
type Seen = { key: string | null; usable: boolean };

/**
 * What the Hub's server makes of each .env: each key python-decouple reads from it, as config/settings.py does, and
 * whether the app that seals with it can (apps.verifactu.certificates keeps a certificate, the check behind the 409;
 * apps.flow.vault keeps a secret, the check behind the box's «cannot keep secrets»).
 */
function server(paths: string[]): Record<Name, Seen>[] {
  const script = [
    'import json, sys',
    'import django',
    'django.setup()',
    'from decouple import RepositoryEnv',
    'from django.conf import settings',
    'from apps.flow import vault',
    'from apps.verifactu import certificates',
    'usable = {"FISCAL_CERTIFICATE_KEY": certificates.storage_available, "FLOW_SECRETS_KEY": vault.available}',
    'seen = []',
    'for path in json.loads(sys.argv[1]):',
    '    data = RepositoryEnv(path).data',
    '    entry = {}',
    '    for name, works in usable.items():',
    '        setattr(settings, name, data.get(name) or "")',
    '        entry[name] = {"key": data.get(name), "usable": works()}',
    '    seen.append(entry)',
    'print(json.dumps(seen))',
  ].join('\n');
  const env: NodeJS.ProcessEnv = { ...process.env, DEBUG: 'True', DJANGO_SETTINGS_MODULE: 'config.settings' };
  for (const name of NAMES) delete env[name];
  const run = spawnSync('uv', ['run', 'python', '-c', script, JSON.stringify(paths)], { cwd: HUB_DIR, encoding: 'utf8', env });
  expect(run.status, `${run.stdout}\n${run.stderr}`).toBe(0);
  return JSON.parse(run.stdout.trim().split('\n').at(-1) ?? '');
}

describe('ensureFernetKeys', () => {
  it(
    'gives a .env without each key, or with it empty as .env.example has it, one the Hub works with',
    () => {
      const made: { name: Name; path: string }[] = [];
      for (const name of NAMES) {
        const missing = envFile('# local\nDEBUG=True\n');
        const unterminated = envFile('DEBUG=True');
        const empty = envFile(`DEBUG=True\n${name}=\nSAAS_URL=http://localhost:8021\n`);

        for (const path of [missing, unterminated, empty]) {
          expect(ensureFernetKeys([name], path, {}), name).toEqual([{ name, source: 'generated' }]);
        }

        expect(readFileSync(missing, 'utf8')).toMatch(/^# local\nDEBUG=True\n/);
        expect(readFileSync(unterminated, 'utf8')).toMatch(/^DEBUG=True\n/);
        // The empty line is filled where it was: one line for the key, the rest of the file as it was.
        const lines = readFileSync(empty, 'utf8').split('\n');
        expect(lines[0]).toBe('DEBUG=True');
        expect(lines[1]).toMatch(new RegExp(`^${name}=\\S+$`));
        expect(lines.slice(2)).toEqual(['SAAS_URL=http://localhost:8021', '']);
        for (const path of [missing, unterminated, empty]) {
          expect(keyLines(path, name), name).toHaveLength(1);
          made.push({ name, path });
        }
      }

      const seen = server(made.map(({ path }) => path));
      made.forEach(({ name }, at) => {
        expect(seen[at][name].usable, name).toBe(true);
        expect(seen[at][name].key).toMatch(/^[A-Za-z0-9_-]{43}=$/);
      });
    },
    PROBE_TIMEOUT_MS,
  );

  it('gives a .env without either both at once, each its own, saying where each came from in the order asked', () => {
    const path = envFile('DEBUG=True\n');

    expect(ensureFernetKeys(NAMES, path, {})).toEqual([
      { name: 'FISCAL_CERTIFICATE_KEY', source: 'generated' },
      { name: 'FLOW_SECRETS_KEY', source: 'generated' },
    ]);
    const [fiscal] = keyLines(path, 'FISCAL_CERTIFICATE_KEY');
    const [flow] = keyLines(path, 'FLOW_SECRETS_KEY');
    expect(fiscal.split('=', 2)[1]).not.toBe(flow.split('=', 2)[1]);

    // One already there, the other missing: the first is kept byte for byte, the second added.
    const kept = `DEBUG=True\nFISCAL_CERTIFICATE_KEY=${newFernetKey()}\n`;
    const half = envFile(kept);
    expect(ensureFernetKeys(NAMES, half, {})).toEqual([
      { name: 'FISCAL_CERTIFICATE_KEY', source: 'env-file' },
      { name: 'FLOW_SECRETS_KEY', source: 'generated' },
    ]);
    expect(readFileSync(half, 'utf8').startsWith(kept)).toBe(true);
    expect(keyLines(half, 'FLOW_SECRETS_KEY')).toHaveLength(1);
  });

  it('generates one per checkout, never a fixed key', () => {
    for (const name of NAMES) {
      const first = envFile('DEBUG=True\n');
      const second = envFile('DEBUG=True\n');

      ensureFernetKeys([name], first, {});
      ensureFernetKeys([name], second, {});

      expect(keyLines(first, name)[0], name).not.toBe(keyLines(second, name)[0]);
    }
    expect(newFernetKey()).not.toBe(newFernetKey());
  });

  it('keeps the key the .env already has, byte for byte, quoted or not', () => {
    for (const name of NAMES) {
      for (const line of [`${name}=${newFernetKey()}`, `${name} = "${newFernetKey()}"`]) {
        const content = `DEBUG=True\n${line}\n`;
        const path = envFile(content);

        expect(ensureFernetKeys([name], path, {})).toEqual([{ name, source: 'env-file' }]);
        expect(readFileSync(path, 'utf8')).toBe(content);
      }
    }
  });

  it('fills the last line that sets it, the one python-decouple reads, when an earlier one holds a key', () => {
    for (const name of NAMES) {
      const earlier = newFernetKey();
      const path = envFile(`${name}=${earlier}\nDEBUG=True\n${name}=\n`);

      expect(ensureFernetKeys([name], path, {})).toEqual([{ name, source: 'generated' }]);

      const lines = readFileSync(path, 'utf8').split('\n');
      expect(lines[0]).toBe(`${name}=${earlier}`);
      expect(lines[2]).toMatch(new RegExp(`^${name}=[A-Za-z0-9_-]{43}=$`));
      expect(lines[2]).not.toBe(`${name}=${earlier}`);
      expect(lines.slice(3)).toEqual(['']);
    }
  });

  it("keeps the environment's key, which Django reads before the .env, and writes nothing", () => {
    for (const name of NAMES) {
      const path = envFile('DEBUG=True\n');

      expect(ensureFernetKeys([name], path, { [name]: newFernetKey() })).toEqual([{ name, source: 'environment' }]);
      expect(readFileSync(path, 'utf8')).toBe('DEBUG=True\n');
    }
  });

  it('refuses a value that is no Fernet key, in the .env or in the environment, touching nothing', () => {
    for (const name of NAMES) {
      const inFile = envFile(`DEBUG=True\n${name}=not-a-key\n`);
      expect(() => ensureFernetKeys([name], inFile, {})).toThrow(new RegExp(`^${name} in ${inFile.replaceAll('.', '\\.')}`));
      expect(readFileSync(inFile, 'utf8')).toBe(`DEBUG=True\n${name}=not-a-key\n`);

      // Exported, even empty, it is what Django reads (python-decouple looks at the environment first).
      for (const exported of ['not-a-key', '']) {
        const inEnvironment = envFile(`DEBUG=True\n${name}=${newFernetKey()}\n`);
        const before = readFileSync(inEnvironment, 'utf8');
        expect(() => ensureFernetKeys([name], inEnvironment, { [name]: exported })).toThrow(new RegExp(`^${name} in the environment`));
        expect(readFileSync(inEnvironment, 'utf8')).toBe(before);
      }
    }
  });

  it('writes neither when one of them is no key, even with the other one missing', () => {
    const inFile = envFile('DEBUG=True\nFLOW_SECRETS_KEY=not-a-key\n');
    expect(() => ensureFernetKeys(NAMES, inFile, {})).toThrow(/^FLOW_SECRETS_KEY in /);
    expect(readFileSync(inFile, 'utf8')).toBe('DEBUG=True\nFLOW_SECRETS_KEY=not-a-key\n');

    const inEnvironment = envFile('DEBUG=True\n');
    expect(() => ensureFernetKeys(NAMES, inEnvironment, { FLOW_SECRETS_KEY: 'not-a-key' })).toThrow(/^FLOW_SECRETS_KEY in the environment/);
    expect(readFileSync(inEnvironment, 'utf8')).toBe('DEBUG=True\n');
  });

  it('refuses a checkout without its .env: runserver would read one further up the tree, and none is made', () => {
    for (const name of NAMES) {
      const path = envFile(null);

      expect(() => ensureFernetKeys([name], path, {})).toThrow(new RegExp(`^No \\.env at ${path.replaceAll('.', '\\.')}`));
      expect(existsSync(path)).toBe(false);
    }
  });

  it("works on the checkout's own .env, the one config/settings.py reads", () => {
    expect(ENV_FILE).toBe(join(HUB_DIR, '.env'));
  });
});

describe('isFernetKey', () => {
  it(
    'says of each value what the Hub says, for the certificates and for the secrets',
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
      const seen = server(values.map((value) => envFile(NAMES.map((name) => `${name}=${value}\n`).join(''))));

      for (const name of NAMES) {
        const said = seen.map((entry) => entry[name].usable);
        expect(values.map((value) => isFernetKey(value)), name).toEqual(said);
        expect(said.slice(0, 3), name).toEqual([true, true, true]);
      }
    },
    PROBE_TIMEOUT_MS,
  );
});

describe('.env.example', () => {
  it('documents each key with no value: none is ever committed', () => {
    for (const name of NAMES) expect(keyLines(join(HUB_DIR, '.env.example'), name), name).toEqual([`${name}=`]);
  });
});
