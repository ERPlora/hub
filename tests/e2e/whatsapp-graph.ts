// Meta's Graph API as the run's erplora.com meets it: the only Meta of the WhatsApp e2e (whatsapp-helpers.ts, «The
// run's real erplora.com»). erplora.com calls `https://graph.facebook.com/<version>/…` and nothing else of Meta; started
// with `HTTPS_PROXY=http://127.0.0.1:<hub port + 9>` and `SSL_CERT_FILE=<this checkout>/tests/e2e/.artifacts/
// meta-graph-<hub port>/ca.pem` (`erploraEnv`), every one of those calls reaches this Graph instead and never leaves
// the machine: its proxy tunnels `graph.facebook.com:443` (and refuses any other host) to a TLS server that answers as
// Meta does (`graphAnswer`) with a certificate of the run's own authority. Its code is not touched: environment only.
//
// One Graph per run: the first WhatsApp spec of a Playwright worker starts it (`metaGraph` of whatsapp-helpers.ts) and
// it lives until the worker ends, so every door that reaches Meta finds it, whichever spec runs. It runs in its own
// thread (`startGraphThread`): a spec waiting on a synchronous child process (a relay pass of the Hub that hands a
// message to erplora.com, which asks Meta) would otherwise hold the very Graph that child waits on. Before a spec uses
// erplora.com, `configProblem` and `graphProblem` read what erplora.com answered to the Hub's doors 10 and 11 (the
// latter with `PROBE_CODE`, which only this Graph receives) and name the variable it was started without: a run whose
// erplora.com would call the real Meta stops there, in seconds (FIX-HUB-WHATSAPP-E2E-STACK-RECIPE-MISSING-META-ENV).
// Each call is kept in `calls` and in `calls.jsonl` beside the certificates: what erplora.com asked Meta in the run.
import { execFileSync } from 'node:child_process';
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer as createHttpServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { createServer as createHttpsServer } from 'node:https';
import type { AddressInfo, Socket } from 'node:net';
import { join } from 'node:path';
import { isMainThread, parentPort, Worker, workerData } from 'node:worker_threads';

export const GRAPH_HOST = 'graph.facebook.com';
/** The Graph listens on the Hub's port + 9 (`HTTPS_PROXY` of the run's erplora.com). */
export const GRAPH_PORT_OFFSET = 9;

/** The e2e Meta app (`WHATSAPP_E2E` of erplora.com's tests/e2e/panel/project.ts): what erplora.com runs with. */
export const META_APP = { id: '1234567890', secret: 'e2e-meta-app-secret', verifyToken: 'e2e-meta-verify-token', configId: '987654321' };

/** Meta's ids of `a`'s number, its account and its portfolio (erplora.com's seed, whatsapp_hub_seed.py). */
export const NUMBER_ID = '880000000000101';
export const WABA_ID = '880000000000100';
export const BUSINESS_ID = '880000000000102';

/** The codes Meta's window gives in whatsapp-inbox-connect-return.spec.ts, and the business's token the good one
 *  is exchanged for: the only permission this Graph ever gave. */
export const CODE = 'AQBe2e-one-time-code_ok';
export const EXPIRED_CODE = 'AQBe2e-one-time-code_expired';
export const TOKEN = 'EAAGe2e-business-token';
/** The number's name and its display at Meta once connected. */
export const SHOWN_NAME = 'E2E Peluquería';
const SHOWN_DISPLAY = '+34 910 00 01 01';
/** The code of the check before a spec: only this Graph receives it, and refuses it (nothing is connected). */
export const PROBE_CODE = 'AQBe2e-probe-code';
/** A template's header sample (WHATSAPP_INBOX-F29, Meta's Resumable Upload API): the session it opens on the e2e Meta
 *  app, the handle the bytes get, and the id of the template registered with it. */
export const UPLOAD_SESSION = 'upload:ZTJlLWhlYWRlci1zYW1wbGU=';
export const HEADER_HANDLE = '4::aW1hZ2UvanBlZw==:e2e-header-handle';
export const TEMPLATE_ID = '880000000000200';

/** Meta's refusal of an expired code (erplora.com's tests: `OAUTH_ERROR`). */
const OAUTH_ERROR = {
  error: { message: 'This authorization code has expired.', type: 'OAuthException', code: 100, error_subcode: 36007, fbtrace_id: 'A1' },
};
/** What Meta answers a permission it never gave, such as the seed's made-up one (seen from the real Meta: 401, 190). */
const INVALID_TOKEN = {
  error: { message: 'Invalid OAuth access token - Cannot parse access token', type: 'OAuthException', code: 190, fbtrace_id: 'A2' },
};
const PROBE_REFUSED = {
  error: { message: 'e2e probe: this run’s Meta Graph never exchanges this code.', type: 'OAuthException', code: 100, error_subcode: 36007 },
};

/** What erplora.com asked Meta's Graph: the method, the path without its version, the query and the bearer token;
 *  how many bytes its body had and, for a JSON body, the body itself. */
export interface GraphCall {
  method: string;
  path: string;
  query: Record<string, string>;
  token: string;
  bytes?: number;
  json?: unknown;
}

/** The permission an `Authorization` header carries: `Bearer <token>`, or `OAuth <token>` (the upload's bytes). */
export const graphToken = (authorization: string): string => authorization.replace(/^(Bearer|OAuth) /, '');

/** Meta's Graph for the run: door 11's exchange and calls with the business's token (connect-return), the probe's
 *  code refused, and any other permission refused as Meta refuses one it never gave — the seed's, with which every
 *  other door (a reply, a template, an attachment, a disconnection) reaches Meta. */
export function graphAnswer(call: GraphCall): [number, unknown] {
  const route = `${call.method} ${call.path}`;
  if (route === 'GET /oauth/access_token') {
    if (call.query.code === PROBE_CODE) return [400, PROBE_REFUSED];
    return call.query.code === CODE ? [200, { access_token: TOKEN, token_type: 'bearer' }] : [400, OAUTH_ERROR];
  }
  if (route === 'GET /debug_token') {
    return call.query.input_token === TOKEN ? [200, { data: { is_valid: true, expires_at: 0 } }] : [401, INVALID_TOKEN];
  }
  if (call.token !== TOKEN) return [401, INVALID_TOKEN];
  if (route === `GET /${WABA_ID}/phone_numbers`) {
    return [200, { data: [{ id: NUMBER_ID, display_phone_number: SHOWN_DISPLAY, verified_name: SHOWN_NAME }] }];
  }
  if (route === `POST /${WABA_ID}/subscribed_apps` || route === `POST /${NUMBER_ID}/register`) return [200, { success: true }];
  if (route === `POST /${META_APP.id}/uploads`) return [200, { id: UPLOAD_SESSION }];
  if (route === `POST /${UPLOAD_SESSION}`) return [200, { h: HEADER_HANDLE }];
  if (route === `POST /${WABA_ID}/message_templates`) return [200, { id: TEMPLATE_ID, status: 'PENDING', category: 'UTILITY' }];
  return [400, { error: { message: `Unsupported request: ${route}.`, type: 'GraphMethodException', code: 100 } }];
}

/** Where the run's erplora.com is (`SAAS_URL`), this Hub's port, the Graph's and the authority erplora.com trusts. */
export interface ErploraRun {
  saas: string;
  hubPort: number;
  graphPort: number;
  ca: string;
}

/** How the run's erplora.com is started (besides its database and ports): this Hub, its own origin for attachments
 *  and Meta's return page, the e2e Meta app and this run's Graph. whatsapp-helpers.ts's header names each one. */
export function erploraEnv(run: ErploraRun): Record<string, string> {
  const origin = new URL(run.saas).origin;
  return {
    HUB_INTERNAL_URL: `http://127.0.0.1:${run.hubPort}`,
    WHATSAPP_MEDIA_BASE_URL: origin,
    WHATSAPP_REDIRECT_URI: `${origin}/whatsapp/return`,
    WHATSAPP_APP_ID: META_APP.id,
    WHATSAPP_APP_SECRET: META_APP.secret,
    WHATSAPP_VERIFY_TOKEN: META_APP.verifyToken,
    WHATSAPP_CONFIG_ID: META_APP.configId,
    HTTPS_PROXY: `http://127.0.0.1:${run.graphPort}`,
    SSL_CERT_FILE: run.ca,
  };
}

const startWith = (run: ErploraRun, ...names: string[]): string => {
  const env = erploraEnv(run);
  return `start it with ${names.map((name) => `${name}=${env[name]}`).join(' ')} (whatsapp-helpers.ts)`;
};

/** What one of erplora.com's doors answered the Hub: its status (0: no answer, `body` the reason) and its body. */
export interface DoorAnswer {
  status: number;
  body: unknown;
}

const errorOf = (answer: DoorAnswer): { code: string; message: string } => {
  const error = (answer.body as { error?: { code?: unknown; message?: unknown } } | null)?.error;
  return { code: String(error?.code ?? ''), message: String(error?.message ?? '') };
};

/** Why door 10 (what opens Meta's window) shows the run's erplora.com is not the one the WhatsApp specs need — no
 *  answer, another secret, the hub `a` not seeded, no Meta app or another one, Meta's code brought back elsewhere —
 *  naming what to start it with; `''` when it opens the window with the e2e Meta app and its page on SAAS_URL. */
export function configProblem(answer: DoorAnswer, run: ErploraRun): string {
  const at = `erplora.com at ${run.saas} (SAAS_URL)`;
  if (answer.status === 0) return `${at} does not answer (${String(answer.body)}): start it as whatsapp-helpers.ts says.`;
  if (answer.status === 401) return `${at} refused this Hub's signature: start it with this stack's INTERNAL_SHARED_SECRET.`;
  if (answer.status === 404 && errorOf(answer).code === 'hub_unknown') {
    return `${at} does not know the hub a: seed it first (seedErplora, whatsapp-helpers.ts).`;
  }
  if (answer.status !== 200) return `${at} answered HTTP ${answer.status} to door 10: ${JSON.stringify(answer.body)}.`;
  const opens = (answer.body ?? {}) as { configured?: boolean; app_id?: string; redirect_uri?: string };
  const back = erploraEnv(run).WHATSAPP_REDIRECT_URI;
  if (!opens.configured) {
    return (
      `${at} has no Meta app to open Meta's window with: ` +
      startWith(run, 'WHATSAPP_APP_ID', 'WHATSAPP_APP_SECRET', 'WHATSAPP_VERIFY_TOKEN', 'WHATSAPP_CONFIG_ID', 'WHATSAPP_REDIRECT_URI') +
      '.'
    );
  }
  if (opens.app_id !== META_APP.id) {
    return `${at} opens Meta's window with the app ${opens.app_id}, not the e2e Meta app: ${startWith(run, 'WHATSAPP_APP_ID', 'WHATSAPP_APP_SECRET')}.`;
  }
  if (opens.redirect_uri !== back) {
    return `${at} brings Meta's code back to ${opens.redirect_uri}, not to its page on SAAS_URL: ${startWith(run, 'WHATSAPP_REDIRECT_URI')}.`;
  }
  return '';
}

/** The messages erplora.com asked Meta to send from `a`'s number (`POST /<NUMBER_ID>/messages`) among `calls`. */
export const messageSends = (calls: GraphCall[]): GraphCall[] =>
  calls.filter((call) => call.method === 'POST' && call.path === `/${NUMBER_ID}/messages`);

/** Why door 11 with `PROBE_CODE` shows the run's erplora.com does not reach Meta only through this run's Graph — it
 *  went to the real graph.facebook.com (or to no Meta at all), came through the proxy without trusting the Graph, or
 *  exchanged the code with another app secret — naming what to start it with; `''` when this Graph got the code. */
export function graphProblem(answer: DoorAnswer, seen: { calls: GraphCall[]; tunnels: string[] }, run: ErploraRun): string {
  const at = `erplora.com at ${run.saas} (SAAS_URL)`;
  const probe = seen.calls.find((call) => call.path === '/oauth/access_token' && call.query.code === PROBE_CODE);
  if (probe) {
    if (probe.query.client_secret !== META_APP.secret) {
      return `${at} asks Meta with another app secret than the e2e Meta app's: ${startWith(run, 'WHATSAPP_APP_SECRET')}.`;
    }
    return '';
  }
  if (seen.tunnels.includes(`${GRAPH_HOST}:443`)) {
    return `${at} reached this run's Meta Graph through HTTPS_PROXY but did not trust its certificate: ${startWith(run, 'SSL_CERT_FILE')}.`;
  }
  const { message } = errorOf(answer);
  const said = answer.status === 409 ? `the real ${GRAPH_HOST}, which answered «${message}»` : `no Meta at all (HTTP ${answer.status}: «${message}»)`;
  return (
    `${at} did not go through this run's Meta Graph: it reached ${said}. No e2e call may reach the real Meta: ` +
    `${startWith(run, 'HTTPS_PROXY', 'SSL_CERT_FILE')}.`
  );
}

/** A certificate authority of this run and `graph.facebook.com`'s certificate signed by it (what erplora.com's
 *  `SSL_CERT_FILE` trusts), made with the Hub's `cryptography`. */
const MAKE_CERTS = `
import datetime, pathlib, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.UTC)
usage = dict(content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False,
             encipher_only=False, decipher_only=False)
ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "e2e Meta Graph CA")])
def base(subject, public):
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(public)
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(hours=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(public), critical=False))
ca = (base(ca_name, ca_key.public_key())
      .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
      .add_extension(x509.KeyUsage(digital_signature=False, key_cert_sign=True, crl_sign=True, **usage), critical=True)
      .sign(ca_key, hashes.SHA256()))
leaf = (base(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "${GRAPH_HOST}")]), key.public_key())
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("${GRAPH_HOST}")]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False, **usage), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
(out / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
(out / "cert.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
(out / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()))
`;

/** The run's Graph, listening. */
/** A JSON body of up to 64 KB, read (`undefined` for any other). */
function jsonOf(request: IncomingMessage, body: Buffer): unknown {
  if (!String(request.headers['content-type'] ?? '').includes('application/json') || body.length > 64 * 1024) return undefined;
  try {
    return JSON.parse(body.toString('utf8')) as unknown;
  } catch {
    return undefined;
  }
}

export interface Graph {
  /** The port of its proxy (erplora.com's `HTTPS_PROXY`). */
  port: number;
  /** The authority erplora.com trusts it with (`SSL_CERT_FILE`). */
  ca: string;
  /** Every call erplora.com made, in order. */
  calls: GraphCall[];
  /** Every `host:port` erplora.com asked the proxy for, in order (only `graph.facebook.com:443` is tunnelled). */
  tunnels: string[];
  close(): Promise<void>;
}

const listen = (server: Server, port: number): Promise<void> =>
  new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });

/** Where the Graph listens (0: any port), the folder of its authority and calls, and the Hub checkout whose
 *  environment makes the certificates; a port still held after `busyFor` ms is an error naming it. */
export interface GraphOptions {
  port: number;
  certs: string;
  hubDir: string;
  busyFor?: number;
}

/** Starts the run's Graph in this thread, with a new authority (the specs use `startGraphThread`). */
export async function startGraph(options: GraphOptions): Promise<Graph> {
  execFileSync('uv', ['run', 'python', '-c', MAKE_CERTS, options.certs], { cwd: options.hubDir, encoding: 'utf8' });
  const ca = join(options.certs, 'ca.pem');
  const log = join(options.certs, 'calls.jsonl');
  writeFileSync(log, '');
  const calls: GraphCall[] = [];
  const tunnels: string[] = [];
  const graph = createHttpsServer(
    { cert: readFileSync(join(options.certs, 'cert.pem')), key: readFileSync(join(options.certs, 'key.pem')) },
    (request: IncomingMessage, response: ServerResponse) => {
      const chunks: Buffer[] = [];
      request.on('data', (chunk: Buffer) => chunks.push(chunk));
      request.on('end', () => {
        const url = new URL(request.url ?? '/', `https://${GRAPH_HOST}`);
        const received = Buffer.concat(chunks);
        const json = jsonOf(request, received);
        const call: GraphCall = {
          method: request.method ?? 'GET',
          path: url.pathname.replace(/^\/v\d+\.\d+/, ''),
          query: Object.fromEntries(url.searchParams),
          token: graphToken(request.headers.authorization ?? ''),
          // Only a call with a body says it.
          ...(received.length ? { bytes: received.length } : {}),
          ...(json === undefined ? {} : { json }),
        };
        calls.push(call);
        appendFileSync(log, `${JSON.stringify({ method: call.method, path: call.path })}\n`);
        const [status, body] = graphAnswer(call);
        response.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
      });
    },
  );
  const proxy = createHttpServer((_request, response) => response.writeHead(403).end());
  proxy.on('connect', (request: IncomingMessage, socket: Socket, head: Buffer) => {
    tunnels.push(request.url ?? '');
    if (request.url !== `${GRAPH_HOST}:443`) {
      socket.end('HTTP/1.1 403 Forbidden\r\n\r\n');
      return;
    }
    socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
    if (head.length) socket.unshift(head);
    graph.emit('connection', socket);
  });
  const until = Date.now() + (options.busyFor ?? 10_000);
  for (;;) {
    try {
      await listen(proxy, options.port);
      break;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EADDRINUSE' || Date.now() >= until) {
        throw new Error(
          `The run's Meta Graph cannot listen on 127.0.0.1:${options.port} (${(error as Error).message}): another process holds it ` +
            `(lsof -nP -iTCP:${options.port} -sTCP:LISTEN).`,
        );
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  // The worker ends when its specs do: the Graph never keeps it alive.
  proxy.unref();
  return {
    port: (proxy.address() as AddressInfo).port,
    ca,
    calls,
    tunnels,
    close: () =>
      new Promise((resolve) => {
        graph.closeAllConnections();
        graph.close();
        proxy.closeAllConnections();
        proxy.close(() => resolve());
      }),
  };
}

/** The run's Graph in its own thread, seen from the specs: what erplora.com asked it (`seen`), forgetting that
 *  (`forget`) and stopping it. The thread never keeps the worker alive and ends with it. */
export interface GraphThread {
  port: number;
  ca: string;
  seen(): Promise<Seen>;
  forget(): Promise<void>;
  close(): Promise<void>;
}

type Ask = 'seen' | 'forget' | 'close';
interface Seen {
  calls: GraphCall[];
  tunnels: string[];
}
type Told = { ready: { port: number; ca: string } } | { failed: string } | { id: number; seen?: Seen };

/** Starts the run's Graph (`startGraph`) in a thread of its own; it rejects with the thread's reason when it cannot,
 *  and once the thread is gone every question to it fails saying so. */
export function startGraphThread(options: GraphOptions): Promise<GraphThread> {
  const thread = new Worker(new URL(import.meta.url), { workerData: { metaGraph: options } });
  thread.unref();
  const waiting = new Map<number, { resolve: (told: Told) => void; reject: (error: Error) => void }>();
  let gone: Error | undefined;
  let next = 0;
  const ask = (what: Ask): Promise<Told> =>
    gone
      ? Promise.reject(gone)
      : new Promise((resolve, reject) => {
          next += 1;
          waiting.set(next, { resolve, reject });
          thread.postMessage({ id: next, ask: what });
        });
  const stop = (error: Error) => {
    gone ??= error;
    for (const { reject } of waiting.values()) reject(gone);
    waiting.clear();
  };
  return new Promise((resolve, reject) => {
    thread.on('error', (thrown: unknown) => {
      const error = thrown instanceof Error ? thrown : new Error(String(thrown));
      reject(error);
      stop(error);
    });
    thread.on('exit', (code) => {
      const error = new Error(`The run's Meta Graph stopped (its thread exited with ${code}).`);
      reject(error);
      stop(error);
    });
    thread.on('message', (told: Told) => {
      if ('failed' in told) {
        reject(new Error(told.failed));
        void thread.terminate();
      } else if ('ready' in told) {
        resolve({
          ...told.ready,
          seen: async () => ((await ask('seen')) as { seen: Seen }).seen,
          forget: async () => {
            await ask('forget');
          },
          close: async () => {
            await ask('close');
            await thread.terminate();
          },
        });
      } else {
        waiting.get(told.id)?.resolve(told);
        waiting.delete(told.id);
      }
    });
  });
}

// The thread's side: this same module, started by startGraphThread.
const threadOptions = isMainThread ? undefined : (workerData as { metaGraph?: GraphOptions } | null)?.metaGraph;
if (threadOptions && parentPort) {
  const port = parentPort;
  startGraph(threadOptions).then(
    (graph) => {
      port.on('message', ({ id, ask }: { id: number; ask: Ask }) => {
        if (ask === 'seen') port.postMessage({ id, seen: { calls: graph.calls, tunnels: graph.tunnels } });
        else if (ask === 'forget') {
          graph.calls.length = 0;
          graph.tunnels.length = 0;
          port.postMessage({ id });
        } else void graph.close().then(() => port.postMessage({ id }));
      });
      port.postMessage({ ready: { port: graph.port, ca: graph.ca } });
    },
    (error: unknown) => port.postMessage({ failed: error instanceof Error ? error.message : String(error) }),
  );
}
