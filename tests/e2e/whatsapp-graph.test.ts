// @vitest-environment node
// The run's Meta Graph (whatsapp-graph.ts): the only Meta of the WhatsApp e2e, alive for the whole run, and the check
// that refuses a run whose erplora.com does not go through it (FIX-HUB-WHATSAPP-E2E-STACK-RECIPE-MISSING-META-ENV):
// before, an erplora.com started without HTTPS_PROXY called the real graph.facebook.com with the e2e's made-up
// credentials (8 calls in one pass of the inbox), and one started with it failed the specs whose Graph had gone.
// flow: WHATSAPP_INBOX-F01
import { execFileSync } from 'node:child_process';
import { closeSync, existsSync, mkdtempSync, openSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { createServer, type Server } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { connect as tlsConnect } from 'node:tls';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import {
  CODE,
  configProblem,
  type DoorAnswer,
  erploraEnv,
  EXPIRED_CODE,
  type Graph,
  graphAnswer,
  type GraphCall,
  graphProblem,
  graphToken,
  HEADER_HANDLE,
  MEDIA_ID,
  messageSends,
  META_APP,
  NUMBER_ID,
  PROBE_CODE,
  runCli,
  startGraph,
  startGraphThread,
  TEMPLATE_ID,
  TOKEN,
  SENT_WAMID,
  UPLOAD_SESSION,
  WABA_ID,
} from './whatsapp-graph';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_DIR = join(HERE, '..', '..');
const SEED_TOKEN = 'EAAG-e2e-made-up';
const RUN = { saas: 'http://localhost:8241', hubPort: 8240, graphPort: 8249, ca: '/hub/tests/e2e/.artifacts/meta-graph-8240/ca.pem' };

const call = (method: string, path: string, over: Partial<GraphCall> = {}): GraphCall => ({ method, path, query: {}, token: '', ...over });
const metaCode = ([, body]: [number, unknown]) => (body as { error?: { code?: number } }).error?.code;

describe('graphAnswer', () => {
  it('exchanges connect-return’s code for the business’s token and refuses the expired one as Meta does', () => {
    expect(graphAnswer(call('GET', '/oauth/access_token', { query: { code: CODE } }))).toEqual([200, { access_token: TOKEN, token_type: 'bearer' }]);
    const expired = graphAnswer(call('GET', '/oauth/access_token', { query: { code: EXPIRED_CODE } }));
    expect(expired[0]).toBe(400);
    expect(expired[1]).toMatchObject({ error: { code: 100, error_subcode: 36007, message: 'This authorization code has expired.' } });
  });

  it('answers door 11’s calls made with the business’s token', () => {
    expect(graphAnswer(call('GET', '/debug_token', { query: { input_token: TOKEN } }))).toEqual([200, { data: { is_valid: true, expires_at: 0 } }]);
    const numbers = graphAnswer(call('GET', `/${WABA_ID}/phone_numbers`, { token: TOKEN }));
    expect(numbers[0]).toBe(200);
    expect(numbers[1]).toMatchObject({ data: [{ id: NUMBER_ID }] });
    expect(graphAnswer(call('POST', `/${WABA_ID}/subscribed_apps`, { token: TOKEN }))).toEqual([200, { success: true }]);
    expect(graphAnswer(call('POST', `/${NUMBER_ID}/register`, { token: TOKEN }))).toEqual([200, { success: true }]);
  });

  it('takes a template’s header sample and the template made with it, with the business’s token (WHATSAPP_INBOX-F29)', () => {
    // Meta's Resumable Upload API: a session on the e2e Meta app (Bearer), the bytes to it (OAuth), then the template.
    const session = graphAnswer(call('POST', `/${META_APP.id}/uploads`, { token: TOKEN, query: { file_type: 'image/jpeg' } }));
    expect(session).toEqual([200, { id: UPLOAD_SESSION }]);
    expect(graphAnswer(call('POST', `/${UPLOAD_SESSION}`, { token: TOKEN }))).toEqual([200, { h: HEADER_HANDLE }]);
    const made = graphAnswer(call('POST', `/${WABA_ID}/message_templates`, { token: TOKEN }));
    expect(made).toEqual([200, { id: TEMPLATE_ID, status: 'PENDING', category: 'UTILITY' }]);
    // The upload's second hop carries the token as OAuth, the others as Bearer: both are the token.
    expect(graphToken('OAuth EAAGe2e-business-token')).toBe(TOKEN);
    expect(graphToken(`Bearer ${TOKEN}`)).toBe(TOKEN);
  });

  it('refuses every call made with a permission it never gave (the seed’s made-up one) as Meta does: 401, code 190', () => {
    const asked = [
      call('POST', `/${NUMBER_ID}/messages`, { token: SEED_TOKEN }),
      call('POST', `/${WABA_ID}/message_templates`, { token: SEED_TOKEN }),
      call('POST', '/880000000000201', { token: SEED_TOKEN }),
      call('DELETE', `/${WABA_ID}/message_templates`, { token: SEED_TOKEN }),
      call('GET', `/${WABA_ID}/message_templates`, { token: SEED_TOKEN }),
      call('DELETE', `/${WABA_ID}/subscribed_apps`, { token: SEED_TOKEN }),
      call('GET', '/e2e.media.photo', { token: SEED_TOKEN }),
      call('GET', `/${WABA_ID}/phone_numbers`, { token: SEED_TOKEN }),
      call('POST', `/${META_APP.id}/uploads`, { token: SEED_TOKEN }),
      call('POST', `/${UPLOAD_SESSION}`, { token: SEED_TOKEN }),
      call('GET', '/debug_token', { query: { input_token: SEED_TOKEN } }),
    ];
    for (const one of asked) {
      const answer = graphAnswer(one);
      expect(answer[0], `${one.method} ${one.path}`).toBe(401);
      expect(answer[1]).toMatchObject({ error: { type: 'OAuthException', code: 190 } });
    }
  });

  it('takes a header’s file on `a`’s number and the template message naming it, with the business’s token (WHATSAPP_INBOX-F33)', () => {
    expect(graphAnswer(call('POST', `/${NUMBER_ID}/media`, { token: TOKEN }))).toEqual([200, { id: MEDIA_ID }]);
    const sent = graphAnswer(call('POST', `/${NUMBER_ID}/messages`, { token: TOKEN }));
    expect(sent[0]).toBe(200);
    expect((sent[1] as { messages: { id: string }[] }).messages[0].id).toBe(SENT_WAMID);
  });

  it('refuses the probe’s code with its own reason, and what Meta does not serve as unsupported', () => {
    const probe = graphAnswer(call('GET', '/oauth/access_token', { query: { code: PROBE_CODE } }));
    expect(probe[0]).toBe(400);
    expect(metaCode(probe)).toBe(100);
    expect(JSON.stringify(probe[1])).toContain('probe');
    const unknown = graphAnswer(call('GET', '/me', { token: TOKEN }));
    expect(unknown[0]).toBe(400);
    expect(metaCode(unknown)).toBe(100);
  });
});

describe('messageSends', () => {
  it('keeps the messages erplora.com asked Meta to send from `a`’s number, and nothing else it asked', () => {
    const sent = call('POST', `/${NUMBER_ID}/messages`, { token: SEED_TOKEN });
    const calls = [
      call('GET', '/oauth/access_token', { query: { code: PROBE_CODE } }),
      sent,
      call('GET', `/${NUMBER_ID}/messages`, { token: SEED_TOKEN }),
      call('POST', `/${WABA_ID}/message_templates`, { token: SEED_TOKEN }),
      call('POST', '/880000000000999/messages', { token: SEED_TOKEN }),
    ];
    expect(messageSends(calls)).toEqual([sent]);
    expect(messageSends([])).toEqual([]);
  });
});

describe('erploraEnv', () => {
  it('is how the run’s erplora.com starts: this Hub, its own origin, the e2e Meta app and this run’s Graph', () => {
    expect(erploraEnv(RUN)).toEqual({
      HUB_INTERNAL_URL: 'http://127.0.0.1:8240',
      WHATSAPP_MEDIA_BASE_URL: 'http://localhost:8241',
      WHATSAPP_REDIRECT_URI: 'http://localhost:8241/whatsapp/return',
      WHATSAPP_APP_ID: META_APP.id,
      WHATSAPP_APP_SECRET: META_APP.secret,
      WHATSAPP_VERIFY_TOKEN: META_APP.verifyToken,
      WHATSAPP_CONFIG_ID: META_APP.configId,
      HTTPS_PROXY: 'http://127.0.0.1:8249',
      SSL_CERT_FILE: RUN.ca,
    });
  });

  it('is named, every variable, by the recipe in the header of whatsapp-helpers.ts', () => {
    const source = readFileSync(join(HERE, 'whatsapp-helpers.ts'), 'utf8');
    const header = source.slice(0, source.indexOf('\nimport '));
    for (const name of Object.keys(erploraEnv(RUN))) expect(header, name).toContain(`${name}=`);
  });
});

// The command erplora.com is started with (FIX-HUB-E2E-SAAS-ASSISTANT-502-BEFORE-META-CA-EXISTS): an erplora.com started
// with SSL_CERT_FILE naming an authority that is not there yet (the Graph makes one only when the first WhatsApp spec
// starts it) fails every outgoing call, even a plain http one: its assistant answered the Hub 502 and the assistant
// specs fell without saying why.
describe('runCli', () => {
  const artifacts = mkdtempSync(join(tmpdir(), 'meta-graph-cli-'));
  const ca = join(artifacts, 'meta-graph-8240', 'ca.pem');
  const said = { lines: [] as string[], errors: [] as string[] };
  const deps = { artifacts, hubDir: HUB_DIR, print: (line: string) => said.lines.push(line), fail: (line: string) => said.errors.push(line) };

  afterAll(() => {
    rmSync(artifacts, { recursive: true, force: true });
  });

  it('makes the run’s authority before it names it: erplora.com never starts trusting a file that is not there', () => {
    expect(existsSync(ca)).toBe(false);
    expect(runCli(['8240', 'http://localhost:8241'], deps)).toBe(0);
    expect(said.lines).toEqual(Object.entries(erploraEnv({ ...RUN, ca })).map(([name, value]) => `${name}=${value}`));
    expect(readFileSync(ca, 'utf8')).toMatch(/^-----BEGIN CERTIFICATE-----\n/);
  }, 60_000);

  it('keeps the authority already there', () => {
    const before = readFileSync(ca, 'utf8');
    said.lines.length = 0;
    expect(runCli(['8240', 'http://localhost:8241/'], deps)).toBe(0);
    expect(said.lines).toContain(`SSL_CERT_FILE=${ca}`);
    expect(readFileSync(ca, 'utf8')).toBe(before);
  });

  it('refuses what it does not understand, saying how it is called, and makes nothing', () => {
    const wrong = [[], ['8240'], ['8240', 'http://localhost:8241', 'more'], ['8a', 'http://localhost:8241'], ['0', 'http://localhost:8241'], ['65530', 'http://localhost:8241'], ['8250', 'localhost:8251']];
    for (const args of wrong) {
      said.errors.length = 0;
      expect(runCli(args, deps), args.join(' ')).toBe(2);
      expect(said.errors.join('\n'), args.join(' ')).toContain('node tests/e2e/whatsapp-graph.ts <hub port> <SAAS_URL>');
    }
    expect(existsSync(join(artifacts, 'meta-graph-8250'))).toBe(false);
    expect(said.errors.join('\n')).toContain('tests/e2e/README.md, «WhatsApp»');
    expect(readFileSync(join(HERE, 'README.md'), 'utf8')).toMatch(/^## WhatsApp /m);
  });

  it('names nothing when the authority cannot be made: env $(…) never gets an SSL_CERT_FILE without it', () => {
    const blocked = join(artifacts, 'a-file');
    writeFileSync(blocked, '');
    said.lines.length = 0;
    said.errors.length = 0;
    expect(runCli(['8260', 'http://localhost:8261'], { ...deps, artifacts: blocked })).toBe(1);
    expect(said.lines).toEqual([]);
    expect(said.errors).toHaveLength(1);
    expect(said.errors[0]).toContain(`the authority ${join(blocked, 'meta-graph-8260', 'ca.pem')} could not be made: NotADirectoryError`);
    expect(said.errors[0]).not.toContain('\n');
  }, 60_000);

  it('makes the authority the Graph trusts again in one step: a reader of the old one never finds it half written', async () => {
    const before = readFileSync(ca);
    const reader = openSync(ca, 'r');
    const graph = await startGraph({ port: 0, certs: dirname(ca), hubDir: HUB_DIR });
    try {
      expect(readFileSync(reader)).toEqual(before);
      expect(readFileSync(ca)).not.toEqual(before);
    } finally {
      closeSync(reader);
      await graph.close();
    }
  }, 60_000);

  it('does nothing when a spec or Vitest imports it, whatever the process was started with', () => {
    const folder = join(HERE, '.artifacts', 'meta-graph-64970');
    const importer = join(artifacts, 'imports-it.mjs');
    writeFileSync(importer, `await import(${JSON.stringify(pathToFileURL(join(HERE, 'whatsapp-graph.ts')).href)});\n`);
    rmSync(folder, { recursive: true, force: true });
    try {
      expect(execFileSync('node', [importer, '64970', 'http://localhost:64971'], { cwd: tmpdir(), encoding: 'utf8' })).toBe('');
      expect(existsSync(folder)).toBe(false);
    } finally {
      rmSync(folder, { recursive: true, force: true });
    }
  });

  it('runs as a script through a symlinked path too (macOS reaches its tmp folder through one): it never prints nothing', () => {
    const folder = join(HERE, '.artifacts', 'meta-graph-64980');
    const linked = join(artifacts, 'linked-e2e');
    symlinkSync(HERE, linked);
    rmSync(folder, { recursive: true, force: true });
    try {
      const out = execFileSync('node', [join(linked, 'whatsapp-graph.ts'), '64980', 'http://localhost:64981'], { cwd: tmpdir(), encoding: 'utf8' });
      expect(out.trim().split('\n')).toContain(`SSL_CERT_FILE=${join(folder, 'ca.pem')}`);
      expect(existsSync(join(folder, 'ca.pem'))).toBe(true);
    } finally {
      rmSync(folder, { recursive: true, force: true });
    }
  }, 60_000);

  it('runs as a script from erplora.com’s checkout, its authority in this checkout’s .artifacts', () => {
    const folder = join(HERE, '.artifacts', 'meta-graph-64990');
    rmSync(folder, { recursive: true, force: true });
    try {
      const out = execFileSync('node', [join(HERE, 'whatsapp-graph.ts'), '64990', 'http://localhost:64991'], { cwd: tmpdir(), encoding: 'utf8' });
      expect(out.trim().split('\n')).toContain(`SSL_CERT_FILE=${join(folder, 'ca.pem')}`);
      expect(existsSync(join(folder, 'ca.pem'))).toBe(true);
    } finally {
      rmSync(folder, { recursive: true, force: true });
    }
  }, 60_000);
});

const config = (body: Record<string, unknown>, status = 200): DoorAnswer => ({ status, body });
const OPENS = { configured: true, app_id: META_APP.id, config_id: META_APP.configId, redirect_uri: `${RUN.saas}/whatsapp/return` };

describe('configProblem', () => {
  it('is empty when erplora.com opens Meta’s window with the e2e Meta app and its return page on SAAS_URL', () => {
    expect(configProblem(config(OPENS), RUN)).toBe('');
  });

  it('names SAAS_URL when erplora.com does not answer', () => {
    expect(configProblem({ status: 0, body: 'connect ECONNREFUSED 127.0.0.1:8241' }, RUN)).toContain('SAAS_URL');
  });

  it('names INTERNAL_SHARED_SECRET when erplora.com refuses this Hub’s signature', () => {
    expect(configProblem(config({ error: { code: 'unauthorized' } }, 401), RUN)).toContain('INTERNAL_SHARED_SECRET');
  });

  it('says to seed erplora.com when it does not know the hub a', () => {
    expect(configProblem(config({ error: { code: 'hub_unknown' } }, 404), RUN)).toContain('seedErplora');
  });

  it('names the e2e Meta app and its return page when erplora.com has no Meta app', () => {
    const problem = configProblem(config({ ...OPENS, configured: false, app_id: '', redirect_uri: '' }), RUN);
    expect(problem).toContain(`WHATSAPP_APP_ID=${META_APP.id}`);
    expect(problem).toContain(`WHATSAPP_APP_SECRET=${META_APP.secret}`);
    expect(problem).toContain(`WHATSAPP_CONFIG_ID=${META_APP.configId}`);
    expect(problem).toContain(`WHATSAPP_REDIRECT_URI=${RUN.saas}/whatsapp/return`);
  });

  it('names WHATSAPP_APP_ID when erplora.com opens Meta’s window with another app', () => {
    expect(configProblem(config({ ...OPENS, app_id: '555' }), RUN)).toContain(`WHATSAPP_APP_ID=${META_APP.id}`);
  });

  it('names WHATSAPP_REDIRECT_URI when erplora.com brings Meta’s code back elsewhere', () => {
    const problem = configProblem(config({ ...OPENS, redirect_uri: 'http://localhost:8001/whatsapp/return' }), RUN);
    expect(problem).toContain(`WHATSAPP_REDIRECT_URI=${RUN.saas}/whatsapp/return`);
  });
});

const PROBED = call('GET', '/oauth/access_token', {
  query: { client_id: META_APP.id, client_secret: META_APP.secret, code: PROBE_CODE, redirect_uri: `${RUN.saas}/whatsapp/return` },
});
const refused = (status: number, code: string, message: string): DoorAnswer => ({ status, body: { error: { code, message } } });

describe('graphProblem', () => {
  it('is empty when erplora.com exchanged the probe’s code through this run’s Graph with the e2e Meta app', () => {
    const answer = refused(409, 'whatsapp.meta_rejected', 'probe');
    expect(graphProblem(answer, { calls: [PROBED], tunnels: ['graph.facebook.com:443'] }, RUN)).toBe('');
  });

  it('names HTTPS_PROXY when erplora.com went to the real Meta, which answered', () => {
    const answer = refused(409, 'whatsapp.meta_rejected', 'Error validating application. Invalid application ID.');
    const problem = graphProblem(answer, { calls: [], tunnels: [] }, RUN);
    expect(problem).toContain('HTTPS_PROXY=http://127.0.0.1:8249');
    expect(problem).toContain(`SSL_CERT_FILE=${RUN.ca}`);
    expect(problem).toContain('real graph.facebook.com');
    expect(problem).toContain('Error validating application. Invalid application ID.');
  });

  it('names HTTPS_PROXY when erplora.com reached no Meta at all', () => {
    const answer = refused(503, 'whatsapp.meta_unreachable', 'Meta could not be reached: nothing was saved. Try again.');
    expect(graphProblem(answer, { calls: [], tunnels: [] }, RUN)).toContain('HTTPS_PROXY=http://127.0.0.1:8249');
  });

  it('names SSL_CERT_FILE when erplora.com came through the proxy but did not trust the Graph', () => {
    const answer = refused(503, 'whatsapp.meta_unreachable', 'Meta could not be reached: nothing was saved. Try again.');
    const problem = graphProblem(answer, { calls: [], tunnels: ['graph.facebook.com:443'] }, RUN);
    expect(problem).toContain(`SSL_CERT_FILE=${RUN.ca}`);
    expect(problem).not.toContain('HTTPS_PROXY=');
  });

  it('names WHATSAPP_APP_SECRET when erplora.com exchanged the code with another secret', () => {
    const other = { ...PROBED, query: { ...PROBED.query, client_secret: 'another' } };
    const problem = graphProblem(refused(409, 'whatsapp.meta_rejected', 'probe'), { calls: [other], tunnels: [] }, RUN);
    expect(problem).toContain(`WHATSAPP_APP_SECRET=${META_APP.secret}`);
  });
});

describe('the WhatsApp specs', () => {
  const specs = readdirSync(HERE).filter((name) => name.endsWith('.spec.ts'));

  it('prove the run’s Graph before using erplora.com: every spec that seeds it awaits metaGraph()', () => {
    const seeding = specs.filter((name) => readFileSync(join(HERE, name), 'utf8').includes('seedErplora('));
    expect(seeding.length).toBeGreaterThan(0);
    for (const name of seeding) expect(readFileSync(join(HERE, name), 'utf8'), name).toContain('await metaGraph()');
  });

  it('never start a Graph of their own: the run has one, whatsapp-graph.ts', () => {
    for (const name of specs) expect(readFileSync(join(HERE, name), 'utf8'), name).not.toMatch(/on\('connect'|node:https/);
  });
});

/** A request through `graph`'s proxy to `host`:443 over TLS trusting `graph.ca`: its status and body. */
function throughProxy(graph: Graph, host: string, method: string, path: string, token: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const tunnel = httpRequest({ host: '127.0.0.1', port: graph.port, method: 'CONNECT', path: `${host}:443` });
    tunnel.on('connect', (answer, socket) => {
      if (answer.statusCode !== 200) {
        socket.destroy();
        resolve({ status: answer.statusCode ?? 0, body: '' });
        return;
      }
      const tls = tlsConnect({ socket, servername: host, ca: readFileSync(graph.ca) }, () => {
        // HTTP/1.0: the answer comes whole, never chunked, and the connection closes after it.
        tls.write(`${method} ${path} HTTP/1.0\r\nHost: ${host}\r\nAuthorization: Bearer ${token}\r\n\r\n`);
      });
      let raw = '';
      tls.on('data', (chunk) => (raw += chunk));
      tls.on('end', () => resolve({ status: Number(raw.split(' ')[1]), body: raw.slice(raw.indexOf('\r\n\r\n') + 4) }));
      tls.on('error', reject);
    });
    tunnel.on('error', reject);
    tunnel.end();
  });
}

describe('startGraph', () => {
  const certs = mkdtempSync(join(tmpdir(), 'meta-graph-'));
  let graph: Graph;

  beforeAll(async () => {
    graph = await startGraph({ port: 0, certs, hubDir: HUB_DIR });
  }, 60_000);

  afterAll(async () => {
    await graph?.close();
    rmSync(certs, { recursive: true, force: true });
  });

  it('answers erplora.com through its proxy over TLS, as graph.facebook.com, and keeps each call', async () => {
    const answer = await throughProxy(graph, 'graph.facebook.com', 'POST', `/v25.0/${NUMBER_ID}/messages`, SEED_TOKEN);
    expect(answer.status).toBe(401);
    expect(JSON.parse(answer.body)).toMatchObject({ error: { code: 190 } });
    expect(graph.calls.at(-1)).toEqual({ method: 'POST', path: `/${NUMBER_ID}/messages`, query: {}, token: SEED_TOKEN });
    expect(graph.tunnels.at(-1)).toBe('graph.facebook.com:443');
    expect(readFileSync(join(certs, 'calls.jsonl'), 'utf8')).toContain(`/${NUMBER_ID}/messages`);
  });

  it('tunnels nowhere else: any other host is refused and kept', async () => {
    expect((await throughProxy(graph, 'example.com', 'GET', '/', '')).status).toBe(403);
    expect(graph.tunnels.at(-1)).toBe('example.com:443');
  });

  it('says which port is taken when another process holds it', async () => {
    const holder: Server = createServer();
    await new Promise<void>((resolve) => holder.listen(0, '127.0.0.1', () => resolve()));
    const port = (holder.address() as { port: number }).port;
    try {
      await expect(startGraph({ port, certs, hubDir: HUB_DIR, busyFor: 300 })).rejects.toThrow(`127.0.0.1:${port}`);
    } finally {
      await new Promise((resolve) => holder.close(resolve));
    }
  });
});

describe('startGraphThread', () => {
  const certs = mkdtempSync(join(tmpdir(), 'meta-graph-thread-'));

  afterAll(() => {
    rmSync(certs, { recursive: true, force: true });
  });

  it('answers erplora.com while the spec that started it waits on a synchronous child process', async () => {
    // A spec's relay pass (spawnSync of the Hub's shell) hands a message to erplora.com, which asks Meta and waits:
    // a Graph living in the spec's own event loop could not answer until the child ended (flow-send-message.spec.ts).
    const graph = await startGraphThread({ port: 0, certs, hubDir: HUB_DIR });
    try {
      const out = execFileSync(
        'curl',
        ['-sS', '--max-time', '5', '--proxy', `http://127.0.0.1:${graph.port}`, '--cacert', graph.ca, '-X', 'POST', '-H',
          `Authorization: Bearer ${SEED_TOKEN}`, `https://graph.facebook.com/v25.0/${NUMBER_ID}/messages`],
        { encoding: 'utf8' },
      );
      expect(JSON.parse(out)).toMatchObject({ error: { code: 190 } });
      const seen = await graph.seen();
      expect(seen.calls.at(-1)).toEqual({ method: 'POST', path: `/${NUMBER_ID}/messages`, query: {}, token: SEED_TOKEN });
      expect(seen.tunnels).toEqual(['graph.facebook.com:443']);
      await graph.forget();
      expect(await graph.seen()).toEqual({ calls: [], tunnels: [] });
    } finally {
      await graph.close();
    }
  }, 60_000);

  it('says why it could not start', async () => {
    const holder: Server = createServer();
    await new Promise<void>((resolve) => holder.listen(0, '127.0.0.1', () => resolve()));
    const port = (holder.address() as { port: number }).port;
    try {
      await expect(startGraphThread({ port, certs, hubDir: HUB_DIR, busyFor: 300 })).rejects.toThrow(`127.0.0.1:${port}`);
    } finally {
      await new Promise((resolve) => holder.close(resolve));
    }
  }, 60_000);
});
