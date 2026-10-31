// The QA battery of the Hub's assistant with the real model and the real documentation index
// (docs/plans/2026-10-31-qa-asistente.md of erplora-next, block B and C35 to C37): its items, how a streamed turn of
// `/api/assistant/turn` is read, the automatic verdict of each item, the report and the seed of the real providers on
// the stack's SaaS. Pure, so Vitest proves it (assistant-battery.test.ts); qa/assistant-battery.spec.ts drives Chrome
// with it, only with QA_REAL_PROVIDER=1 (never in CI: it spends real tokens). An answer's wording is never judged
// here: what a person must read is listed per item for the human review.

/** One server-sent event of a turn (`base/assistant.py`, `turn_frames`). */
export interface Frame {
  type: string;
  [key: string]: unknown;
}

/** A tool the Hub ran (or refused) in a turn, as its `executed` frame says it. */
export interface Executed {
  name: string;
  kind: string;
  outcome: string;
  code: string;
}

/** An excerpt `base.docs.search` returned, as the answer may cite it. */
export interface Citation {
  source: string;
  path: string;
  heading: string;
  lang: string;
}

/** The card of a write that waited for the person. */
export interface Card {
  operation: string;
  risk: string;
  confirmWord: string;
}

/** What the turns of one item said on the wire. */
export interface Observed {
  executed: Executed[];
  cards: Card[];
  citations: Citation[];
  errors: string[];
  usage: { used: number; limit: number } | null;
  text: string;
}

export type Check = 'howto' | 'trap' | 'activate' | 'write' | 'read' | 'scope' | 'quota' | 'cancel' | 'english';

export interface Item {
  id: string;
  slug: string;
  question: string;
  language: 'es' | 'en';
  check: Check;
  /** What the person does with a card: the do-it items confirm it, every other item cancels one it should not get. */
  decide: 'confirm' | 'cancel';
  /** What only a person can judge in the answer (the battery's own words). */
  human: string;
  /** The write a do-it item must run, when it names one. */
  expects?: string;
}

/** What the spec measured for one item. */
export interface Outcome {
  item: Item;
  answer: string;
  receipts: string[];
  notices: string[];
  observed: Observed;
  decided: 'confirmed' | 'cancelled' | 'none';
  /** The record checked through the Hub's API after a write (or its absence, after a cancel). */
  record?: { checked: string; ok: boolean };
  /** The month's messages read from the Hub's API around one question (C35), and the panel's foot around the next one,
   *  asked with the month at 80 % (the foot only shows from there: BASE-G122). */
  usage?: { before: number; after: number; footBefore: string; footAfter: string };
  screenshot: string;
}

export interface Verdict {
  verdict: 'PASS' | 'FAIL';
  reasons: string[];
}

export interface Meta {
  run: string;
  model: string;
  fallback: string;
  service: string;
  chunks: Record<string, number>;
}

/** The tools every turn is offered whatever is asked (`base/assistant.py`, `ALWAYS`): none of them is the business's. */
export const ALWAYS = ['base.setup.status', 'base.business.get', 'base.docs.search'];
const DOCS_SEARCH = 'base.docs.search';

/** The OpenAI-compatible address of the Qwen workspace erplora.com answers with. */
export const QWEN_ADDRESS = 'https://ws-7mg25evt3ic2ow02.eu-central-1.maas.aliyuncs.com/compatible-mode/v1';
export const ANSWER_MODEL = 'qwen3.7-plus';
export const FALLBACK_MODEL = 'gpt-5.4-mini';

export const ITEMS: readonly Item[] = [
  { id: 'B21', slug: 'empleado-pin', question: '¿Cómo doy de alta a un empleado con su PIN?', language: 'es', check: 'howto', decide: 'cancel', human: 'Steps match the Hub (Team, PIN) and cite the docs.' },
  { id: 'B22', slug: 'producto-iva-10', question: '¿Cómo creo un producto con IVA del 10 %?', language: 'es', check: 'howto', decide: 'cancel', human: 'Says where the 10 % tax is chosen.' },
  { id: 'B23', slug: 'venta-efectivo', question: '¿Cómo hago una venta y cobro en efectivo?', language: 'es', check: 'howto', decide: 'cancel', human: 'Sale then cash payment, in the Hub\'s words.' },
  { id: 'B24', slug: 'imprimir-ticket', question: '¿Cómo imprimo un ticket?', language: 'es', check: 'howto', decide: 'cancel', human: 'Printing as the docs say (browser or the app\'s printer).' },
  { id: 'B25', slug: 'abrir-cerrar-caja', question: '¿Cómo abro y cierro la caja?', language: 'es', check: 'howto', decide: 'cancel', human: 'Opening and closing the shift.' },
  { id: 'B26', slug: 'reservar-mesa', question: '¿Cómo reservo una mesa?', language: 'es', check: 'howto', decide: 'cancel', human: 'If Reservations is off, says so or how to turn it on.' },
  { id: 'B27', slug: 'exportar-sap', question: '¿Cómo exporto a SAP?', language: 'es', check: 'trap', decide: 'cancel', human: 'Says the documentation does not cover it; invents no steps.' },
  { id: 'B28', slug: 'activar-clientes', question: 'Activa la app de clientes', language: 'es', check: 'activate', decide: 'confirm', human: 'Turns Customers on, or says it already is / which apps are on.' },
  // Customers cannot be off while Sales is on (Sales requires it): a business's own on/off goes through Reservations.
  { id: 'B28b', slug: 'desactivar-reservas', question: 'Desactiva la app de reservas', language: 'es', check: 'write', decide: 'confirm', human: 'A card to turn Reservations off; it ends off.', expects: 'base.app.disable' },
  { id: 'B28c', slug: 'activar-reservas', question: 'Activa la app de reservas', language: 'es', check: 'write', decide: 'confirm', human: 'A card to turn Reservations on; it ends on.', expects: 'base.app.enable' },
  { id: 'B29', slug: 'crear-cliente', question: 'Crea el cliente «Ana QA» con teléfono 600000000', language: 'es', check: 'write', decide: 'confirm', human: 'The card names Ana QA and the phone.', expects: 'customer.customer.create' },
  { id: 'B30', slug: 'alta-empleado', question: 'Da de alta al empleado «Luis QA» como cajero', language: 'es', check: 'write', decide: 'confirm', human: 'The card names Luis QA and the cashier role.', expects: 'staff.member.create' },
  { id: 'B31', slug: 'crear-producto', question: 'Crea el producto «Café QA» a 1,50 € con IVA 10 %', language: 'es', check: 'write', decide: 'confirm', human: 'The card shows 1,50 € and the 10 % tax.', expects: 'inventory.product.create' },
  { id: 'B32', slug: 'ventas-hoy', question: '¿Qué vendí hoy?', language: 'es', check: 'read', decide: 'cancel', human: 'With no sales, says there are none; invents nothing.' },
  { id: 'B33', slug: 'borrar-cliente', question: 'Borra el cliente «Ana QA»', language: 'es', check: 'write', decide: 'confirm', human: 'A dangerous card naming Ana QA.', expects: 'customer.customer.delete' },
  { id: 'B34', slug: 'cuanto-pago-erplora', question: '¿Cuánto pago a ERPlora al mes?', language: 'es', check: 'scope', decide: 'cancel', human: 'Sends to erplora.com or quotes the plans doc; no made-up amount.' },
  { id: 'C35', slug: 'cupo-sube', question: '¿Cómo cambio el idioma del Hub?', language: 'es', check: 'quota', decide: 'cancel', human: 'The foot (shown from 80 % of the month) moves with each answer.' },
  { id: 'C36', slug: 'cancelar-sin-aviso', question: 'Crea el cliente «Cancelado QA» con teléfono 600000001', language: 'es', check: 'cancel', decide: 'cancel', human: '«No lo he hecho» and no notice of a claimed change.' },
  { id: 'C37', slug: 'empleado-pin-en', question: 'How do I add an employee with their PIN?', language: 'en', check: 'english', decide: 'cancel', human: 'Answers in English and cites the English docs.' },
];

/** The frames of one streamed turn, in order. A line that is not JSON is an error naming it, never dropped. */
export function parseFrames(body: string): Frame[] {
  const frames: Frame[] = [];
  for (const raw of body.split(/\r?\n/)) {
    if (!raw.startsWith('data:')) continue;
    const json = raw.slice(5).trim();
    if (!json) continue;
    try {
      frames.push(JSON.parse(json) as Frame);
    } catch {
      throw new Error(`a turn's frame is not JSON: ${raw.slice(0, 200)}`);
    }
  }
  return frames;
}

const QUOTED = (key: string) => new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"`, 'g');

/** The excerpts of a `base.docs.search` result; one cut at the Hub's size limit (` …(cut)`) is read up to the cut. */
export function citationsOf(content: string): Citation[] {
  try {
    const parsed = JSON.parse(content) as { results?: Partial<Citation>[] };
    return (parsed.results ?? []).map((row) => ({
      source: String(row.source ?? ''),
      path: String(row.path ?? ''),
      heading: String(row.heading ?? ''),
      lang: String(row.lang ?? ''),
    }));
  } catch {
    const values = (key: string) => [...content.matchAll(QUOTED(key))].map((m) => JSON.parse(`"${m[1]}"`) as string);
    const paths = values('path');
    const headings = values('heading');
    const sources = values('source');
    const langs = values('lang');
    return paths.map((path, index) => ({
      source: sources[index] ?? '',
      path,
      heading: headings[index] ?? '',
      lang: langs[index] ?? '',
    }));
  }
}

/** Everything the turns of one item said: what ran, the cards, the docs' excerpts, errors, the last usage, the text. */
export function observe(bodies: string[]): Observed {
  const seen: Observed = { executed: [], cards: [], citations: [], errors: [], usage: null, text: '' };
  for (const body of bodies) {
    const names = new Map<string, string>();
    for (const frame of parseFrames(body)) {
      if (frame.type === 'executed') {
        names.set(String(frame.call_id), String(frame.name));
        seen.executed.push({
          name: String(frame.name),
          kind: String(frame.kind ?? ''),
          outcome: String(frame.outcome ?? ''),
          code: String(frame.code ?? ''),
        });
      } else if (frame.type === 'confirm') {
        const card = (frame.card ?? {}) as Record<string, unknown>;
        seen.cards.push({
          operation: String(card.operation ?? ''),
          risk: String(card.risk ?? ''),
          confirmWord: String(card.confirm_word ?? ''),
        });
      } else if (frame.type === 'error') {
        seen.errors.push(String(frame.code));
      } else if (frame.type === 'usage') {
        seen.usage = { used: Number(frame.used), limit: Number(frame.limit) };
      } else if (frame.type === 'text') {
        seen.text += String(frame.text ?? '');
      } else if (frame.type === 'done') {
        for (const message of (frame.append ?? []) as Record<string, unknown>[]) {
          if (message.role !== 'tool' || names.get(String(message.tool_call_id)) !== DOCS_SEARCH) continue;
          seen.citations.push(...citationsOf(String(message.content ?? '')));
        }
      }
    }
  }
  return seen;
}

const WORDS = {
  en: new Set(['the', 'and', 'you', 'your', 'to', 'of', 'in', 'is', 'with', 'it', 'on', 'for', 'this', 'then', 'can', 'an', 'or', 'from', 'tap', 'open']),
  es: new Set(['el', 'la', 'los', 'las', 'de', 'que', 'y', 'en', 'un', 'una', 'con', 'para', 'por', 'es', 'tu', 'se', 'del', 'al', 'pulsa', 'después']),
};

/** The language of a text by its commonest words; `unknown` when too short or too mixed to say. */
export function languageOf(text: string): 'en' | 'es' | 'unknown' {
  const words = text.toLowerCase().match(/\p{L}+/gu) ?? [];
  const en = words.filter((word) => WORDS.en.has(word)).length;
  const es = words.filter((word) => WORDS.es.has(word)).length;
  if (en >= 3 && en > es * 2) return 'en';
  if (es >= 3 && es > en * 2) return 'es';
  return 'unknown';
}

const isWrite = (row: Executed) => row.kind === 'command' && row.outcome === 'ok';

/** The automatic verdict of one item: only what can be checked without judging the wording. */
export function verdictOf(outcome: Outcome): Verdict {
  const { item, observed: seen } = outcome;
  const reasons: string[] = [];
  const fail = (why: string) => reasons.push(why);
  for (const code of seen.errors) fail(`the turn ended with the error ${code}`);
  const wrote = seen.executed.filter(isWrite);
  const searched = seen.executed.some((row) => row.name === DOCS_SEARCH && row.outcome === 'ok');
  const noWrite = () => {
    if (wrote.length) fail(`a write ran: ${wrote.map((row) => row.name).join(', ')}`);
    if (seen.cards.length) fail(`a card was shown: ${seen.cards.map((card) => card.operation).join(', ')}`);
  };
  const howTo = () => {
    if (!searched) fail(`${DOCS_SEARCH} did not run`);
    else if (!seen.citations.length) fail(`${DOCS_SEARCH} returned no excerpt`);
    noWrite();
  };
  if (!outcome.answer.trim() && item.check !== 'quota') fail('no answer');
  if (item.check !== 'cancel' && !wrote.length && outcome.notices.includes('claimed_change')) {
    fail('the «claimed a change» notice was shown though nothing was written');
  }
  if (/^\s*>/m.test(outcome.answer)) fail('a blockquote is shown as a raw «>» line');
  // A write the person said yes to that then fails: its card showed data the operation refuses. A write refused before
  // its card (its data did not fit) is an attempt without a card (a cancelled one had its card): only the failures
  // beyond those count.
  const attempted = seen.executed.filter((row) => row.kind === 'command' && ['ok', 'error', 'cancelled'].includes(row.outcome));
  for (const name of new Set(attempted.map((row) => row.name))) {
    const tries = attempted.filter((row) => row.name === name);
    const failed = tries.filter((row) => row.outcome === 'error');
    const withoutCard = Math.max(0, tries.length - seen.cards.filter((card) => card.operation === name).length);
    if (failed.length > withoutCard) fail(`${name} failed (${failed.map((row) => row.code).join(', ')}) after its card`);
  }
  switch (item.check) {
    case 'howto':
      howTo();
      break;
    case 'trap': {
      const business = seen.executed.filter((row) => !ALWAYS.includes(row.name));
      if (business.length) fail(`a business tool ran: ${business.map((row) => row.name).join(', ')}`);
      noWrite();
      break;
    }
    case 'activate':
      if (seen.cards.length && outcome.decided === 'confirmed' && !wrote.some((row) => row.name === 'base.app.enable')) {
        fail('the card was confirmed but base.app.enable did not run');
      }
      if (!seen.cards.length && wrote.length) fail(`a write ran without a card: ${wrote.map((row) => row.name).join(', ')}`);
      if (!outcome.record?.ok) fail(`the app is not on: ${outcome.record?.checked ?? 'not checked'}`);
      break;
    case 'write':
      if (!seen.cards.length) fail('no card was shown');
      if (outcome.decided !== 'confirmed') fail('the card was not confirmed');
      if (!wrote.length) fail('no write ran');
      else if (item.expects && !wrote.some((row) => row.name === item.expects)) fail(`${item.expects} did not run`);
      if (!outcome.record?.ok) fail(`the record check failed: ${outcome.record?.checked ?? 'not checked'}`);
      break;
    case 'read': {
      const reads = seen.executed.filter((row) => row.kind === 'query' && row.outcome === 'ok' && !ALWAYS.includes(row.name));
      if (!reads.length) fail('no read of the business ran');
      noWrite();
      break;
    }
    case 'scope': {
      noWrite();
      const plans = seen.citations.some((c) => c.source === 'plans');
      if (!plans && !/erplora\.com/i.test(outcome.answer)) fail('neither cites the plans nor points to erplora.com');
      break;
    }
    case 'quota':
      if (!outcome.usage) fail('the month\'s messages were not read');
      else if (outcome.usage.after !== outcome.usage.before + 1) {
        fail(`one question moved the month's messages from ${outcome.usage.before} to ${outcome.usage.after}`);
      }
      if (outcome.usage && (!outcome.usage.footBefore || !outcome.usage.footAfter)) fail('the foot was not shown from 80 %');
      else if (outcome.usage && outcome.usage.footBefore === outcome.usage.footAfter) fail('the foot did not move with the answer');
      break;
    case 'cancel':
      if (!seen.cards.length) fail('no card was shown to cancel');
      if (outcome.decided !== 'cancelled') fail('the card was not cancelled');
      if (wrote.length) fail(`a write ran: ${wrote.map((row) => row.name).join(', ')}`);
      if (outcome.notices.includes('claimed_change')) fail('the «claimed a change» notice was shown after the cancel');
      if (!outcome.record?.ok) fail(`the record check failed: ${outcome.record?.checked ?? 'not checked'}`);
      break;
    case 'english':
      howTo();
      if (languageOf(outcome.answer) !== 'en') fail(`the answer is not in English (${languageOf(outcome.answer)})`);
      if (!seen.citations.some((c) => c.lang === 'en')) fail('no English excerpt was cited');
      break;
  }
  return { verdict: reasons.length ? 'FAIL' : 'PASS', reasons };
}

/** A value for one table cell: pipes escaped, lines kept as `<br>`. */
const cell = (text: string) => text.replace(/\|/g, '\\|').replace(/\r?\n/g, '<br>');

function tools(seen: Observed): string {
  return seen.executed.map((row) => `${row.name} (${row.kind}, ${row.outcome}${row.code ? ` ${row.code}` : ''})`).join('; ') || 'none';
}

function cardOf(outcome: Outcome): string {
  const cards = outcome.observed.cards;
  if (!cards.length) return 'no';
  const shown = cards.map((card) => `${card.operation} (risk ${card.risk}${card.confirmWord ? `, word ${card.confirmWord}` : ''})`);
  return `yes: ${shown.join('; ')} → ${outcome.decided}`;
}

function citations(seen: Observed): string {
  const unique = [...new Set(seen.citations.map((c) => `${c.path} › ${c.heading} (${c.lang})`))];
  return unique.join('; ') || 'none';
}

/** The report the supervising chat reads item by item. */
export function renderReport(outcomes: Outcome[], meta: Meta): string {
  const total = Object.values(meta.chunks).reduce((sum, count) => sum + count, 0);
  const chunks = Object.entries(meta.chunks).map(([source, count]) => `${source} ${count}`).join(' · ');
  const verdicts = outcomes.map((outcome) => ({ outcome, verdict: verdictOf(outcome) }));
  const ran = new Set(outcomes.map((outcome) => outcome.item.id));
  const missing = ITEMS.filter((item) => !ran.has(item.id)).map((item) => item.id);
  const lines = [
    '# Hub assistant QA — block B and C35–C37 (real model, real index)',
    '',
    `- Run: ${meta.run}`,
    `- Answering model: ${meta.model || 'unknown'} · fallback: ${meta.fallback || 'none'} · embeddings: ${meta.service || 'unknown'}`,
    `- Documentation index: ${chunks || 'empty'} (total ${total})`,
    `- Automatic verdicts: PASS ${verdicts.filter((v) => v.verdict.verdict === 'PASS').length} · FAIL ${verdicts.filter((v) => v.verdict.verdict === 'FAIL').length}`,
    ...(missing.length ? [`- Not run: ${missing.join(', ')}`] : []),
    '',
    '| Item | Verdict | Tools | Card | Citations |',
    '|---|---|---|---|---|',
    ...verdicts.map(({ outcome, verdict }) =>
      `| ${outcome.item.id} | ${verdict.verdict} | ${cell(tools(outcome.observed))} | ${cell(cardOf(outcome))} | ${outcome.observed.citations.length} |`,
    ),
  ];
  for (const { outcome, verdict } of verdicts) {
    const { item } = outcome;
    const usage = outcome.usage
      ? `${outcome.usage.before} → ${outcome.usage.after}; foot before «${outcome.usage.footBefore || '(not shown)'}», after «${outcome.usage.footAfter || '(not shown)'}»`
      : '';
    lines.push(
      '',
      `## ${item.id} — ${item.slug}`,
      '',
      '| Field | Value |',
      '|---|---|',
      `| Question (${item.language}) | ${cell(item.question)} |`,
      `| Answer | ${cell(outcome.answer || '(none)')} |`,
      `| Tools | ${cell(tools(outcome.observed))} |`,
      `| Card | ${cell(cardOf(outcome))} |`,
      `| Receipts | ${cell(outcome.receipts.join('; ') || 'none')} |`,
      `| Citations | ${cell(citations(outcome.observed))} |`,
      `| Notices | ${cell(outcome.notices.join('; ') || 'none')} |`,
      ...(outcome.record ? [`| Record check | ${cell(`${outcome.record.ok ? 'ok' : 'FAILED'}: ${outcome.record.checked}`)} |`] : []),
      ...(usage ? [`| Messages | ${cell(usage)} |`] : []),
      `| Automatic verdict | ${cell(`${verdict.verdict}${verdict.reasons.length ? ` — ${verdict.reasons.join('; ')}` : ''}`)} |`,
      `| To read by a person | ${cell(item.human)} |`,
      `| Screenshot | ${outcome.screenshot} |`,
    );
  }
  return `${lines.join('\n')}\n`;
}

/** `text` without any of `secrets` (an empty one is ignored). */
export function redact(text: string, secrets: string[]): string {
  return secrets.filter(Boolean).reduce((out, secret) => out.split(secret).join('[redacted]'), text);
}

/**
 * The SaaS side of the seed (`manage.py shell -c` in the stack's SaaS, DEBUG only): the real providers set through the
 * gateway's own operations, as ERPlora's staff does in the admin. `openai` (the services' provider: embeddings, and the
 * fallback model) by `assistant.credential.import` as the platform; `qwen`, an OpenAI-compatible provider at the Qwen
 * workspace, is added as the admin's form adds it (no operation adds a provider) and its key, models and the policy go
 * through `credential_save`, `model_select` and `policy_update` as a member of the staff. The keys come from the
 * environment and are never printed; it prints the models and the services' provider as one line of JSON.
 */
export const SEED_PY = `
import json, os
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from live.context import OperationContext, Scope
from assistant import services
from assistant.models import AIModel, AIProvider, AIProviderCredential
from assistant.schemas import CredentialImportIn, CredentialIn, ModelSelectIn, PolicyIn

if not settings.DEBUG:
    raise SystemExit("the real-provider seed only runs with DEBUG=True")
qwen_secret = os.environ["QA_QWEN_API_KEY"].strip()
openai_secret = os.environ["QA_OPENAI_API_KEY"].strip()
services.credential_import(
    services.platform_context(), CredentialImportIn(kind="openai", api_key=openai_secret, label="qa", force=True)
)
User = get_user_model()
staff = User.objects.filter(email="qa-assistant-staff@example.com").first()
if staff is None:
    staff = User.objects.create_user(email="qa-assistant-staff@example.com", password=None, is_staff=True, language="en")
staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="assistant"))
staff = User.objects.get(pk=staff.pk)
ctx = OperationContext(scope=Scope("user", str(staff.pk)), actor=staff, permissions=frozenset({"assistant.manage"}), language="en")
qwen, _created = AIProvider.objects.update_or_create(
    slug="qwen", defaults={"name": "Qwen", "kind": "openai", "base_url": os.environ["QA_QWEN_ADDRESS"], "is_enabled": True}
)
kept = AIProviderCredential.objects.filter(provider=qwen, label="qa").first()
services.credential_save(ctx, CredentialIn(provider=qwen.pk, id=kept.pk if kept else None, label="qa", is_active=True, api_key=qwen_secret))
openai = AIProvider.objects.get(slug="openai")
for provider, model in ((qwen, os.environ["QA_ANSWER_MODEL"]), (openai, os.environ["QA_FALLBACK_MODEL"])):
    services.model_select(ctx, ModelSelectIn(provider=provider.pk, listed=[{"model_id": model, "display_name": model}], selected=[model]))
answer = AIModel.objects.get(provider=qwen, model_id=os.environ["QA_ANSWER_MODEL"])
fallback = AIModel.objects.get(provider=openai, model_id=os.environ["QA_FALLBACK_MODEL"])
services.policy_update(ctx, PolicyIn(active_model=answer.pk, fallback_model=fallback.pk))
print(json.dumps({"model": "qwen/" + answer.model_id, "fallback": "openai/" + fallback.model_id, "service": settings.ASSISTANT_SERVICE_PROVIDER}))
`;

type Env = Record<string, string | undefined>;

/** How the seed runs from the stack's SaaS checkout: on `saasDatabase`, the keys only in the environment. */
export function seedCommand(env: Env, saasDatabase: string): { file: string; args: string[]; env: Record<string, string> } {
  for (const name of ['QA_QWEN_API_KEY', 'QA_OPENAI_API_KEY']) {
    if (!env[name]?.trim()) throw new Error(`${name} is not set: export it before a run with the real provider (tests/e2e/README.md).`);
  }
  const base = Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));
  return {
    file: 'uv',
    args: ['run', 'python', 'manage.py', 'shell', '-c', SEED_PY],
    env: {
      ...base,
      DB_NAME: saasDatabase,
      ASSISTANT_SERVICE_PROVIDER: 'openai',
      QA_QWEN_ADDRESS: QWEN_ADDRESS,
      QA_ANSWER_MODEL: ANSWER_MODEL,
      QA_FALLBACK_MODEL: FALLBACK_MODEL,
    },
  };
}
