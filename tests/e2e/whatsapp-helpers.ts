// Shared steps of the WhatsApp inbox e2e (whatsapp-*.spec.ts). What erplora.com pushes — a customer's message,
// Meta's statuses, the channel's state and its templates — is pushed here by running the same system operation
// its doors run (`whatsapp_inbox.message.receive`, `whatsapp_inbox.message.update_status`,
// `whatsapp_inbox.channel.sync`) as the platform, in the hub `a`, through `manage.py shell`. The doors themselves
// (`/internal/whatsapp/*`, mounted by `base`) are proven over signed HTTP by whatsapp-internal.spec.ts; these
// helpers test the inbox, not the doors, and stay synchronous because the inbox specs call them without awaiting.
// Never Meta, never a row written by hand: the operation commits and notifies, and the open pages update live.
// What a run creates is named `e2e.…` and deleted in the spec's `afterAll`.
//
// The seed's push replaces `a`'s photo with erplora.com's, plan included (Free: one device), and writes the row of its
// WhatsApp channel with the photo's version: `seedErplora` keeps both as they were and `restorePhoto`, last in the
// `afterAll` of every spec that seeds (whatsapp-photo.test.ts), puts them back, so no spec run after it on the same
// database finds `a` on erplora.com's plan, nor a channel whose version a later erplora.com, made afresh, never
// exceeds (whatsapp-photo.spec.ts).
//
// The run's real erplora.com (`SAAS_URL`) also takes part: `seedErplora` gives the hub `a` its WhatsApp number there
// with erplora.com's own test seed (`tests/e2e/panel/whatsapp_hub_seed.py` of its checkout: `a` and `b` with this
// Hub's ids, a number with a made-up Meta permission, the photo pushed to this Hub), so the Hub's doors to it (5, 6,
// 8, 9, 12) reach Meta, which refuses that permission; and `meta` posts to erplora.com's webhook what Meta would,
// signed with the e2e Meta app's secret, so that erplora.com hands it to this Hub through its doors 1 and 2. Only Meta
// is played, and never the real one: erplora.com reaches Meta only through the run's Graph (whatsapp-graph.ts), which
// the first spec awaiting `metaGraph()` starts and which lives until the run ends. Every spec that seeds erplora.com
// awaits it right after the seed: it stops the run in seconds, naming what is missing, unless erplora.com goes through
// it. erplora.com runs from its checkout on SAAS_URL, started once for the whole run, on its own database created
// fresh by its tests/e2e/database.ts (the seed refuses one whose `a` has another id), with (`erploraEnv`):
//   HUB_INTERNAL_URL=http://127.0.0.1:<hub port>      this Hub's doors (<hub port>: E2E_HUB_PORT);
//   WHATSAPP_MEDIA_BASE_URL=<SAAS_URL's origin>       where it links a customer's attachments: this Hub takes only that
//                                                     origin (unset: http://localhost:8001; `metaHandsOver` says so
//                                                     when this Hub refuses one);
//   WHATSAPP_REDIRECT_URI=<SAAS_URL's origin>/whatsapp/return   its page Meta's window brings the code back to;
//   WHATSAPP_APP_ID=1234567890 WHATSAPP_APP_SECRET=e2e-meta-app-secret WHATSAPP_VERIFY_TOKEN=e2e-meta-verify-token
//   WHATSAPP_CONFIG_ID=987654321                      the e2e Meta app (`WHATSAPP_E2E` of its panel/project.ts);
//   HTTPS_PROXY=http://127.0.0.1:<hub port + 9>       the run's Graph: the only Meta it reaches;
//   SSL_CERT_FILE=<this checkout>/tests/e2e/.artifacts/meta-graph-<hub port>/ca.pem   the authority it trusts the
//                                                     Graph with (made again whenever the Graph starts; read per call);
// besides its own DB_NAME, VITE_DEV_PORT, HUB_CALLBACK_TEMPLATE, HUB_ADMIN_CALLBACK_URL and EMAIL_FILE_PATH
// (tests/e2e/README.md, «Varias ejecuciones a la vez»). `E2E_SAAS_DIR` (that checkout; by default `../saas` beside
// this one) and `E2E_SAAS_DB` (by default `saas_e2e_<SAAS_URL's port>`) say where it is.
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

import type { APIRequestContext, Page } from '@playwright/test';

import { ARTIFACTS, capture, HUB_DIR, psql, REPO_DIR, SAAS } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';
import {
  BUSINESS_ID,
  configProblem,
  type DoorAnswer,
  type ErploraRun,
  GRAPH_PORT_OFFSET,
  graphProblem,
  type GraphThread,
  META_APP,
  NUMBER_ID,
  PROBE_CODE,
  startGraphThread,
  WABA_ID,
} from './whatsapp-graph';
import { messageIds, type Push, pushProblem } from './whatsapp-pushes';
import { type ErploraSeed, SEED_TEMPLATES, seedArguments } from './whatsapp-seed';

export { NUMBER_ID, SEED_TEMPLATES, WABA_ID };

/** Every WhatsApp id, template and card name of a run starts like this. */
export const PREFIX = 'e2e.';

/** A Spanish mobile number of the 699 00x xxx range, unique enough per run (E.164). */
export const e2ePhone = (): string => `+3469900${String(Math.floor(Math.random() * 1e4)).padStart(4, '0')}`;

/** A channel version above any real one: what the spec pushes always wins, and cleanUp finds it. */
let version = 900_000_000 + Math.floor(Date.now() / 1000) % 1_000_000;

const RUN = `
import json, os
from live.context import Scope, system_context
from live.operations import get
op = get(os.environ["WA_OP"])
out = op(system_context(Scope("host", "a")), op.input.model_validate(json.loads(os.environ["WA_PAYLOAD"])))
print(out.model_dump_json())
`;

/** Runs a system operation of the inbox in the hub `a`, as erplora.com's doors will; its output. */
export function system<T = unknown>(op: string, payload: unknown): T {
  const out = execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', RUN], {
    cwd: HUB_DIR,
    encoding: 'utf8',
    env: { ...process.env, WA_OP: op, WA_PAYLOAD: JSON.stringify(payload) },
  });
  const line = out.trim().split('\n').at(-1) ?? '';
  return JSON.parse(line) as T;
}

/** Python that goes first in a one-shot `manage.py shell` playing the worker's relay (this stack runs no worker).
 *  What a reaction hands erplora.com after its COMMIT goes to `base.outbound`'s threads, which in the worker outlive
 *  the tick but here would die with this process (daemon threads) before erplora.com is called: this process makes
 *  those calls at once, as the suite's `conftest.py` does (FIX-HUB-WHATSAPP-INBOX-SLOW-SEND-BLOCKS-RELAY). */
export const OUTBOUND_AT_ONCE = `
from base import outbound
class _AtOnce:
    def submit(self, job):
        job.run()
        return True
    def stop(self, grace):
        return True
outbound._pool = _AtOnce()
`;

/** A WhatsApp id of this run. */
export const waId = (): string => `${PREFIX}wamid.${Date.now()}.${Math.floor(Math.random() * 1e6)}`;

/** A customer's text arriving now from `phone` (E.164), as erplora.com pushes it; `over` changes the
 *  message (an attachment, the echo of the owner's phone, an option tapped…). */
export function receive(
  phone: string,
  text: string,
  contactName: string,
  over: Record<string, unknown> = {},
): { id: string; conversation_id: string } {
  return system('whatsapp_inbox.message.receive', {
    wa_message_id: waId(),
    from: phone.replace('+', ''),
    contact_name: contactName,
    direction: 'inbound',
    source: 'live',
    type: 'text',
    text,
    sent_at: new Date().toISOString(),
    ...over,
  });
}

/** The key the Hub sent its last message to `phone` with (what erplora.com's statuses carry). */
export function lastSentKey(phone: string): string {
  return psql(
    `select m.client_message_id from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone.replace(/'/g, '')}' and m.origin = 'hub' order by m.created_at desc limit 1`,
  );
}

/** A delivery status of Meta for the Hub's message sent with `key`, as erplora.com pushes it. */
export function pushStatus(key: string, status: 'sent' | 'delivered' | 'read', wamid: string): void {
  system('whatsapp_inbox.message.update_status', {
    wa_message_id: wamid,
    client_message_id: key,
    status,
    status_at: new Date().toISOString(),
  });
}

/** The business's number of `a` as Meta writes it (erplora.com's seed, whatsapp_hub_seed.py; its Meta ids: NUMBER_ID
 *  and WABA_ID of whatsapp-graph.ts). */
export const BUSINESS_PHONE = '34910000101';

const SAAS_DIR = resolve(process.env.E2E_SAAS_DIR || join(REPO_DIR, 'saas'));
const SAAS_DB = process.env.E2E_SAAS_DB || `saas_e2e_${new URL(SAAS).port || '80'}`;

/** The Hub's ids of `a` and `b` (the ones erplora.com's seed gives them). */
const hubIds = (): Record<string, string> =>
  Object.fromEntries(
    psql("select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug")
      .split('\n')
      .map((row) => row.split('=')),
  );

/** Where `a`'s photo (`state` and its version) and the row of its WhatsApp channel (`channel`, as JSON; none, `[]`)
 *  wait from a spec's first `seedErplora` until `restorePhoto` puts them back: a table of the run's database, so a
 *  shell's quoting never touches them. */
const PHOTO_BACKUP = 'e2e_backup_whatsapp_photo';

/** Gives `a` its WhatsApp number in the run's erplora.com, with erplora.com's own test seed, and has it push the
 *  photo to this Hub: what the seed printed (`delivered` true when this Hub took it). The seed also keeps `a`'s
 *  templates as erplora.com does after reading Meta's list (`SEED_TEMPLATES`) and sets the month's usage to `used`
 *  (whatsapp-seed.ts).
 *  That photo replaces `a`'s with erplora.com's, plan included (Free: one device), and writes its channel's row, so
 *  the spec's first seed keeps both as they were until `restorePhoto`, the last step of the spec's `afterAll`
 *  (whatsapp-photo.test.ts says so).
 *  Running it again keeps what exists, connects the number again (a reconnect asked by Meta is cleared), sets the
 *  usage again and pushes once more; what is kept stays the first seed's. */
export function seedErplora(seed: ErploraSeed = {}): { delivered: boolean; hub_error: string } {
  const script = join(SAAS_DIR, 'tests', 'e2e', 'panel', 'whatsapp_hub_seed.py');
  if (!existsSync(script)) {
    throw new Error(`erplora.com's checkout with ${script} is needed (E2E_SAAS_DIR): see whatsapp-helpers.ts.`);
  }
  const ids = hubIds();
  psql(
    `set client_min_messages = warning; create table if not exists ${PHOTO_BACKUP} as select h.id, h.state, h.state_version, ` +
      "(select coalesce(json_agg(c), '[]') from whatsapp_inbox_channel c where c.host = 'a') as channel from base_hub h where h.slug = 'a'",
  );
  const out = execFileSync('uv', ['run', 'python', script, ids.a, ids.b, ...seedArguments(seed)], {
    cwd: SAAS_DIR,
    encoding: 'utf8',
    env: { ...process.env, DEBUG: 'True', DB_NAME: SAAS_DB, HUB_INTERNAL_URL: `http://127.0.0.1:${STACK.hubPort}` },
  });
  return JSON.parse(out.trim().split('\n').at(-1) ?? '{}');
}

/** Puts back `a`'s photo as it was before the spec's first `seedErplora`, its version too, and the row of its WhatsApp
 *  channel (none, if it had none): a spec run after it on the same database finds `a` as it was, never on
 *  erplora.com's Free plan, whose one device ends another device's session (BASE-G57), nor with a channel whose
 *  version stops the photos of an erplora.com made afresh (`whatsapp_inbox.channel.sync` ignores an equal or older
 *  one). It goes last in the `afterAll` of every spec that seeds, after anything else there that pushes a photo (a
 *  seed again, erplora.com's plan put back). With nothing seeded since the last one, it changes nothing. */
export function restorePhoto(): void {
  if (psql(`select to_regclass('${PHOTO_BACKUP}') is not null`) !== 't') return;
  psql(
    [
      `update base_hub h set state = b.state, state_version = b.state_version from ${PHOTO_BACKUP} b where b.id = h.id`,
      "delete from whatsapp_inbox_channel where host = 'a'",
      `insert into whatsapp_inbox_channel select * from json_populate_recordset(null::whatsapp_inbox_channel, (select channel from ${PHOTO_BACKUP}))`,
      `drop table ${PHOTO_BACKUP}`,
    ].join('; '),
  );
}

const GRAPH_RUN: ErploraRun = {
  saas: SAAS,
  hubPort: STACK.hubPort,
  graphPort: STACK.hubPort + GRAPH_PORT_OFFSET,
  ca: join(ARTIFACTS, `meta-graph-${STACK.hubPort}`, 'ca.pem'),
};
let graph: Promise<GraphThread> | undefined;
let proven: Promise<void> | undefined;

/** The run's Meta Graph (whatsapp-graph.ts, in its own thread), once erplora.com is proven to reach Meta only through
 *  it. The first spec of this worker that awaits it starts it, and it stays until the worker ends; the proof runs once
 *  per worker. It asks erplora.com about the hub `a`, so it goes right after `seedErplora()`, and it throws naming the
 *  variable erplora.com was started without (whatsapp-helpers.ts's header) before any spec reaches Meta. */
export async function metaGraph(): Promise<GraphThread> {
  graph ??= startGraphThread({ port: GRAPH_RUN.graphPort, certs: dirname(GRAPH_RUN.ca), hubDir: HUB_DIR }).catch((error: unknown) => {
    graph = undefined;
    throw error;
  });
  const started = await graph;
  proven ??= proveErplora(started).catch((error: unknown) => {
    proven = undefined;
    throw error;
  });
  await proven;
  return started;
}

/** Door 10 opens Meta's window with the e2e Meta app and erplora.com's page on SAAS_URL, and door 11 exchanges the
 *  probe's code — which only the run's Graph receives, and refuses — through that Graph: nothing is connected. */
async function proveErplora(started: GraphThread): Promise<void> {
  const config = configProblem(await door('config', { hub: 'a' }), GRAPH_RUN);
  if (config) throw new Error(config);
  const before = await started.seen();
  const window = { code: PROBE_CODE, event: 'FINISH', waba_id: WABA_ID, phone_number_id: NUMBER_ID, business_id: BUSINESS_ID };
  const answer = await door('connect', { hub: 'a', ...window });
  const after = await started.seen();
  const seen = { calls: after.calls.slice(before.calls.length), tunnels: after.tunnels.slice(before.tunnels.length) };
  const problem = graphProblem(answer, seen, GRAPH_RUN);
  if (problem) throw new Error(problem);
}

/** The secret this stack signs `/internal` with (the local default unless the run exports another). */
const INTERNAL_SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';

const parsed = (text: string): unknown => {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
};

/** Calls erplora.com's WhatsApp door `name` as this Hub does (apps/whatsapp_inbox/gateway.py: JSON signed with
 *  HMAC-SHA256 of `<timestamp>.<body>`): its status and body, or status 0 and why nothing answered. */
async function door(name: 'config' | 'connect', payload: Record<string, string>): Promise<DoorAnswer> {
  const body = JSON.stringify(payload);
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', INTERNAL_SECRET).update(`${timestamp}.${body}`).digest('hex');
  try {
    const response = await fetch(`${SAAS}/internal/whatsapp/${name}`, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
      signal: AbortSignal.timeout(30_000),
    });
    return { status: response.status, body: parsed(await response.text()) };
  } catch (error) {
    const cause = (error as { cause?: { message?: string } }).cause?.message;
    return { status: 0, body: cause ? `${(error as Error).message}: ${cause}` : (error as Error).message };
  }
}

/** One change of Meta's webhook for `a`'s number (`messages` or `smb_message_echoes`), as Meta posts it. */
export function notice(field: 'messages' | 'smb_message_echoes', value: Record<string, unknown>): string {
  return JSON.stringify({
    object: 'whatsapp_business_account',
    entry: [
      {
        id: WABA_ID,
        changes: [
          {
            field,
            value: { messaging_product: 'whatsapp', metadata: { display_phone_number: BUSINESS_PHONE, phone_number_id: NUMBER_ID }, ...value },
          },
        ],
      },
    ],
  });
}

/** Posts `body` to erplora.com's webhook signed as Meta signs it (`X-Hub-Signature-256`): its HTTP status. */
export async function meta(request: APIRequestContext, body: string): Promise<number> {
  const signature = `sha256=${createHmac('sha256', META_APP.secret).update(body).digest('hex')}`;
  const answer = await request.post(`${SAAS}/webhooks/whatsapp/`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': signature },
  });
  return answer.status();
}

/** Forgets at erplora.com the templates a spec made from this Hub (named `prefix…`). `cleanUp` deletes this Hub's
 *  rows by hand, never erplora.com's copy: the next seed's push would bring that copy back as a new row made in
 *  WhatsApp Manager, without the file it was made with (WHATSAPP_INBOX-F28). Never the seed's own (`e2e_seed_…`). */
export function erploraForgetsTemplates(prefix: string): void {
  const safe = prefix.replace(/[^a-z0-9_]/g, '');
  if (!safe || safe.startsWith('e2e_seed')) throw new Error(`erploraForgetsTemplates: refusing the prefix «${prefix}».`);
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', SAAS_DB, '-At', '-c', `delete from whatsapp_template where name like '${safe}%'`], {
    cwd: REPO_DIR,
    encoding: 'utf8',
  });
}

/** What erplora.com's database recorded of its push of each of `ids` to this Hub (whatsapp-pushes.ts). */
function pushesOf(ids: string[]): Push[] {
  const list = ids.map((id) => `'${id.replace(/'/g, '')}'`).join(',');
  const sql =
    "select coalesce(json_agg(json_build_object('waMessageId', wa_message_id, 'attachment', media_id <> '', " +
    "'delivered', delivered_at is not null, 'error', last_error)), '[]') " +
    `from whatsapp_delivery where kind = 'message' and wa_message_id in (${list})`;
  const out = execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', SAAS_DB, '-At', '-c', sql], {
    cwd: REPO_DIR,
    encoding: 'utf8',
  });
  return JSON.parse(out.trim()) as Push[];
}

/** The WhatsApp messages erplora.com counts for `a` this calendar month (UTC), as its plan's allowance reads them. */
export function erploraUsage(): number {
  const sql =
    "select coalesce(max(used), 0) from whatsapp_usage where month = to_char(now() at time zone 'utc', 'YYYY-MM') " +
    `and hub_id = '${hubIds().a.replace(/'/g, '')}'`;
  const out = execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', SAAS_DB, '-At', '-c', sql], {
    cwd: REPO_DIR,
    encoding: 'utf8',
  });
  return Number(out.trim());
}

/** Posts `body` to erplora.com's webhook as Meta does (`meta`) and fails saying why unless erplora.com took it and
 *  handed this Hub every message it carries: an attachment refused for its origin names `WHATSAPP_MEDIA_BASE_URL`. */
export async function metaHandsOver(request: APIRequestContext, body: string): Promise<void> {
  const status = await meta(request, body);
  if (status !== 200) throw new Error(`erplora.com's webhook answered ${status} to Meta's notice.`);
  const ids = messageIds(body);
  const problem = ids.length ? pushProblem(ids, pushesOf(ids), { saas: SAAS, database: SAAS_DB }) : '';
  if (problem) throw new Error(problem);
}

/** Meta's time now, in seconds. */
export const metaNow = (): string => String(Math.floor(Date.now() / 1000));

/** The screen of `flow` in the three sizes (APP-WHATSAPP_INBOX-1-<flow>-390|834|1440), once it settles and
 *  nothing scrolls sideways; `ready` waits for what the capture must show. Back to 1280×860 after. */
export async function flowShots(page: Page, flow: string, ready: (page: Page) => Promise<void> = async () => {}): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${flow} ${viewport.label}`);
    await capture(page, `APP-WHATSAPP_INBOX-1-${flow}-${viewport.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

export interface ChannelPush {
  status: 'not_connected' | 'connected' | 'reconnect_needed';
  monthly_limit?: number;
  monthly_usage?: number;
  templates?: unknown[] | null;
}

/** erplora.com's state of the number (and, when given, the templates Meta holds). */
export function pushChannel(state: ChannelPush): void {
  version += 1;
  const month = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' }).slice(0, 7);
  system('whatsapp_inbox.channel.sync', {
    version,
    status: state.status,
    phone_number: state.status === 'not_connected' ? '' : '+34910000000',
    display_name: state.status === 'not_connected' ? '' : 'e2e. Peluquería',
    monthly_limit: state.monthly_limit ?? 150,
    monthly_usage: state.monthly_usage ?? 12,
    usage_month: month,
    templates: state.templates ?? null,
  });
}

/** A template as erplora.com reports it. */
export const template = (name: string, over: Record<string, unknown> = {}) => ({
  name,
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header: '',
  body: 'Hola {{1}}, te esperamos mañana.',
  footer: '',
  variables: 1,
  rejected_reason: '',
  meta_id: name,
  ...over,
});

/** Deletes what the specs created: their conversations (erased ones too) with their messages and notes,
 *  their templates and the channel row they pushed. Raw SQL has no Django cascade: children first. */
export function cleanUp(): void {
  const byMessage = psql(`select string_agg(distinct conversation_id::text, ',') from whatsapp_inbox_message where wa_message_id like '${PREFIX}%'`);
  const byPhone = psql("select string_agg(id::text, ',') from whatsapp_inbox_conversation where phone like '+3469900%'");
  const ids = [...new Set([...byMessage.split(','), ...byPhone.split(',')].filter(Boolean))];
  if (ids.length) {
    const list = ids.map((id) => `'${id.replace(/'/g, '')}'`).join(',');
    psql(`delete from whatsapp_inbox_note where conversation_id in (${list})`);
    psql(`delete from whatsapp_inbox_message where conversation_id in (${list})`);
    psql(`delete from whatsapp_inbox_conversation where id in (${list})`);
  }
  psql("delete from whatsapp_inbox_template where name like 'e2e_%'");
  // The files of their photo, video or document headers (F29), once no template of theirs is left.
  psql("delete from whatsapp_inbox_templatesample where name like 'e2e%' and id not in (select header_sample_id from whatsapp_inbox_template where header_sample_id is not null)");
  psql('delete from whatsapp_inbox_channel where version >= 900000000');
}
