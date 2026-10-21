// Shared steps of the WhatsApp inbox e2e (whatsapp-*.spec.ts). What erplora.com pushes — a customer's message,
// Meta's statuses, the channel's state and its templates — is pushed here by running the same system operation
// its doors run (`whatsapp_inbox.message.receive`, `whatsapp_inbox.message.update_status`,
// `whatsapp_inbox.channel.sync`) as the platform, in the hub `a`, through `manage.py shell`. The doors themselves
// (`/internal/whatsapp/*`, mounted by `base`) are proven over signed HTTP by whatsapp-internal.spec.ts; these
// helpers test the inbox, not the doors, and stay synchronous because the inbox specs call them without awaiting.
// Never Meta, never a row written by hand: the operation commits and notifies, and the open pages update live.
// What a run creates is named `e2e.…` and deleted in the spec's `afterAll`.
//
// The run's real erplora.com (`SAAS_URL`) also takes part: `seedErplora` gives the hub `a` its WhatsApp number there
// with erplora.com's own test seed (`tests/e2e/panel/whatsapp_hub_seed.py` of its checkout: `a` and `b` with this
// Hub's ids, a number with a made-up Meta permission, the photo pushed to this Hub), so the Hub's doors to it (5, 6,
// 8, 9) reach Meta, which refuses that permission; and `meta` posts to erplora.com's webhook what Meta would, signed
// with the run's Meta app secret, so that erplora.com hands it to this Hub through its doors 1 and 2. Only Meta is
// played. It needs, beside this stack, erplora.com run from its checkout on `SAAS_URL` with
// `HUB_INTERNAL_URL=http://127.0.0.1:<hub port>` and the e2e Meta app (`WHATSAPP_APP_ID=1234567890`,
// `WHATSAPP_APP_SECRET=e2e-meta-app-secret`, `WHATSAPP_VERIFY_TOKEN=e2e-meta-verify-token`,
// `WHATSAPP_CONFIG_ID=987654321`: `WHATSAPP_E2E` of its tests/e2e/panel/project.ts), on its own database created
// fresh by its tests/e2e/database.ts (the seed refuses one whose `a` has another id). `E2E_SAAS_DIR` (that
// checkout; by default `../saas` beside this one), `E2E_SAAS_DB` (by default `saas_e2e_<SAAS_URL's port>`) and
// `E2E_WHATSAPP_APP_SECRET` say where it is.
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

import type { APIRequestContext, Page } from '@playwright/test';

import { HUB_DIR, psql, REPO_DIR, SAAS, shot } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';

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

/** erplora.com's seed of the number of `a` (whatsapp_hub_seed.py): Meta's id of the number and of its account, and
 *  the business's number as Meta writes it. */
export const NUMBER_ID = '880000000000101';
export const WABA_ID = '880000000000100';
export const BUSINESS_PHONE = '34910000101';

const SAAS_DIR = resolve(process.env.E2E_SAAS_DIR || join(REPO_DIR, 'saas'));
const SAAS_DB = process.env.E2E_SAAS_DB || `saas_e2e_${new URL(SAAS).port || '80'}`;
const META_SECRET = process.env.E2E_WHATSAPP_APP_SECRET || 'e2e-meta-app-secret';

/** Gives `a` its WhatsApp number in the run's erplora.com, with erplora.com's own test seed, and has it push the
 *  photo to this Hub: what the seed printed (`delivered` true when this Hub took it). Running it again keeps what
 *  exists, connects the number again (a reconnect asked by Meta is cleared) and pushes once more. */
export function seedErplora(): { delivered: boolean; hub_error: string } {
  const script = join(SAAS_DIR, 'tests', 'e2e', 'panel', 'whatsapp_hub_seed.py');
  if (!existsSync(script)) {
    throw new Error(`erplora.com's checkout with ${script} is needed (E2E_SAAS_DIR): see whatsapp-helpers.ts.`);
  }
  const ids = Object.fromEntries(
    psql("select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug")
      .split('\n')
      .map((row) => row.split('=')),
  );
  const out = execFileSync('uv', ['run', 'python', script, ids.a, ids.b], {
    cwd: SAAS_DIR,
    encoding: 'utf8',
    env: { ...process.env, DEBUG: 'True', DB_NAME: SAAS_DB, HUB_INTERNAL_URL: `http://127.0.0.1:${STACK.hubPort}` },
  });
  return JSON.parse(out.trim().split('\n').at(-1) ?? '{}');
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
  const signature = `sha256=${createHmac('sha256', META_SECRET).update(body).digest('hex')}`;
  const answer = await request.post(`${SAAS}/webhooks/whatsapp/`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': signature },
  });
  return answer.status();
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
    await page.screenshot({ path: shot(`APP-WHATSAPP_INBOX-1-${flow}-${viewport.label}`) });
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
  psql('delete from whatsapp_inbox_channel where version >= 900000000');
}
