// The AI provider of the assistant's e2e: a real HTTP server on 127.0.0.1 that speaks OpenAI's API
// (`/v1/models`, streamed `/v1/chat/completions`, `/v1/embeddings`, `/v1/audio/transcriptions`). erplora.com's gateway
// of the run's SaaS talks to it (`assistant_seed.py gateway http://127.0.0.1:<port>/v1`, README «El asistente»): no test
// reaches a real provider nor writes a real key. It answers in the language the Hub asks for, as a real model does: the
// Hub's system message says «Answer in English» or «Answer in Spanish» (base/assistant.py `instructions`, the person's
// language or, for an automation, the one it was saved in); each text is exported in both (`DONE.en`, `DONE.es`), English
// its source and the language of a turn that says none (hub#1025). What it answers depends on the question, by a marker
// the spec writes:
// - `E2E-FORMAT`: an answer with a heading, bold, a list, a table and a screen of the hub;
// - `E2E-CREATE <name>`: asks for the write `demo.item.create` with that name, then says it is done;
// - `E2E-DELETE <id>`: asks for the dangerous write `demo.item.delete` of that item, then says it is done;
// - `E2E-ASK <tool> <JSON>`: asks for any write by its tool's name with those data as written, then says how it went
//   (the card of a datum outside the screen's own list);
// - `E2E-CHAIN <name>`: reads the items (`demo.item.list`), then asks to create one with that name, then says so;
// - `E2E-STEPS <name>`: the same chain, speaking in every round (`STEPS_SAID` before the read, then before the write):
//   each round's words, their own paragraph of the one bubble (BASE-F101);
// - `E2E-CLOSE-CASH <cents>`: closes the drawer as CASH_REGISTER-F09 asks — reads the close's summary
//   (`cash_register.session.closing_summary`) with that count, then says it (`closeCashSummary`) and, in the same answer,
//   asks for the dangerous write `cash_register.session.close` of the session it named, then says how it went;
// - `E2E-RECTIFY <number> … porque <reason>`: rectifies that invoice as INVOICE-F08 asks — reads the rectification's
//   preview (`invoice.invoice.rectification_preview`) with that reason, then says it (`rectifyPreview`) and, in the same
//   answer, asks for the dangerous write `invoice.invoice.rectify` of the invoice it named; a preview refused, it says
//   why and asks for nothing;
// - `E2E-OFFER <line> | <line> | …`: answers with those lines, one under the other (a numbered list of options); a write
//   named in it as `E2E-ASK` is only asked by the next question that hears the list (WHATSAPP_INBOX-F19: the guest's
//   «the 2nd» comes with what the business last wrote them);
// - `E2E-CLAIM`: says it created something without running anything;
// - `E2E-DOWN`: the provider fails (500);
// - `E2E-SLOW`: a long answer, piece by piece, to stop it half-way;
// - anything else: a short greeting. A dictation is always `DICTATION` (below).
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';

export const DICTATION = 'E2E-CREATE Mesa dictada';

/** The languages it answers in (the Hub's), English the source. */
export const LANGUAGES = ['en', 'es'] as const;
export type Language = (typeof LANGUAGES)[number];
/** A text as it says it in each language. */
export type Said = Readonly<Record<Language, string>>;

/** Each language by the name the Hub's system message gives it (Django's `get_language_info(language)["name"]`). */
const NAMED: Readonly<Record<string, Language>> = { English: 'en', Spanish: 'es' };

export const GREETING: Said = { en: 'Hi, I am the test assistant.', es: 'Hola, soy el asistente de prueba.' };
export const FORMAT_ANSWER: Said = {
  en: [
    '## Today’s sales',
    '',
    'You have sold **€120** in *3 tickets*. Check the data in [Settings](/settings#business).',
    '',
    '- Coffee: 12',
    '- Toast: 5',
    '',
    '| Product | Units | Amount |',
    '|---|---|---|',
    '| White coffee | 12 | €18.00 |',
    '| Toast with tomato and extra virgin olive oil | 5 | €12.50 |',
  ].join('\n'),
  es: [
    '## Ventas de hoy',
    '',
    'Has vendido **120 €** en *3 tickets*. Revisa los datos en [Ajustes](/settings#business).',
    '',
    '- Café: 12',
    '- Tostadas: 5',
    '',
    '| Producto | Unidades | Importe |',
    '|---|---|---|',
    '| Café con leche | 12 | 18,00 € |',
    '| Tostada con tomate y aceite de oliva virgen extra | 5 | 12,50 € |',
  ].join('\n'),
};
export const CLAIM_ANSWER: Said = { en: 'Done: I created table 9 and saved it.', es: 'Listo: he creado la mesa 9 y la he guardado.' };
/** What it says once a write's result comes back: it ran, or it did not (cancelled, refused or failed). */
export const DONE: Said = { en: 'Done.', es: 'Hecho.' };
export const NOT_DONE: Said = { en: 'I have not done it.', es: 'No lo he hecho.' };
/** What it says before why a rectification's preview was refused (the Hub's message, after it). */
export const CANNOT_RECTIFY: Said = { en: 'It cannot be rectified:', es: 'No se puede rectificar:' };
/** The reason `E2E-RECTIFY` gives the rectification when its question says none. */
export const NO_REASON: Said = { en: 'error in the invoice', es: 'error en la factura' };
/** `E2E-SLOW`'s answer, which comes piece by piece. */
export const SLOW_ANSWER: Said = {
  en: 'This answer is long and comes slowly, piece by piece. '.repeat(20),
  es: 'Esta respuesta es larga y llega despacio, trozo a trozo. '.repeat(20),
};
/** What `E2E-STEPS` says before its read and before its write: one round each. */
export const STEPS_SAID: Readonly<Record<Language, readonly [string, string]>> = {
  en: ['First I look at which tables you have.', 'None is called that: I ask you to create it.'],
  es: ['Miro primero qué mesas tienes.', 'Ninguna se llama así: te pido crearla.'],
};

export interface Seen {
  path: string;
  body: Record<string, unknown> | null;
}

/** The close's summary as the Hub's `cash_register.session.closing_summary` answers it (the fields the model says). */
export interface CloseCashSummary {
  number: string;
  closing_balance: number | null;
  expected_balance: number | null;
  difference: number | null;
  expected_hidden: boolean;
  pending: {
    open_checks: number;
    open_check_labels: string[];
    unserved: number;
    unserved_labels: string[];
    prints: number;
    print_usages: string[];
    incomplete: boolean;
  };
}

/** The words of the close's summary (`closeCashSummary`), in each language. */
const CLOSE_WORDS = {
  en: {
    title: (number: string) => `You are about to close session **${number}**:`,
    counted: 'Counted',
    blind: 'Blind count: the close compares it when you confirm.',
    expected: 'Expected',
    difference: 'Difference',
    openChecks: 'Open checks',
    unserved: 'Orders not served',
    prints: 'Prints not out',
    incomplete: 'Not everything pending could be checked.',
  },
  es: {
    title: (number: string) => `Vas a cerrar la sesión **${number}**:`,
    counted: 'Contado',
    blind: 'Arqueo ciego: el cierre lo comparará al confirmar.',
    expected: 'Esperado',
    difference: 'Diferencia',
    openChecks: 'Cuentas abiertas',
    unserved: 'Comandas sin servir',
    prints: 'Impresiones sin salir',
    incomplete: 'No se ha podido comprobar todo lo pendiente.',
  },
} as const;

const euros = (cents: number, signed = false) => `${signed && cents > 0 ? '+' : ''}${(cents / 100).toFixed(2)} €`;
const named = (count: number, labels: string[]) => (labels.length ? `${count} (${labels.join(' · ')})` : String(count));

/** What the model says of the close's summary before its card, in `language`: only what the summary carries (never an
 *  expected that a blind count left out), and what is still pending at the close. */
export function closeCashSummary(summary: CloseCashSummary, language: Language): string {
  const words = CLOSE_WORDS[language];
  const lines = [words.title(summary.number), ''];
  if (summary.closing_balance !== null) lines.push(`- ${words.counted}: ${euros(summary.closing_balance)}`);
  if (summary.expected_hidden || summary.expected_balance === null) {
    lines.push(`- ${words.blind}`);
  } else {
    lines.push(`- ${words.expected}: ${euros(summary.expected_balance)}`);
    if (summary.difference !== null) lines.push(`- ${words.difference}: ${euros(summary.difference, true)}`);
  }
  const review = summary.pending;
  if (review.open_checks) lines.push(`- ${words.openChecks}: ${named(review.open_checks, review.open_check_labels)}`);
  if (review.unserved) lines.push(`- ${words.unserved}: ${named(review.unserved, review.unserved_labels)}`);
  if (review.prints) lines.push(`- ${words.prints}: ${review.prints}`);
  if (review.incomplete) lines.push(`- ${words.incomplete}`);
  return lines.join('\n');
}

/** The rectification's preview as the Hub's `invoice.invoice.rectification_preview` answers it (what the model says). */
export interface RectificationPreview {
  original: { number: string; issue_date: string; customer_name: string; total_amount: number; remaining: number };
  invoice_type: string;
  reason: string;
  series_code: string;
  next_number: string;
  issue_date: string;
  whole: boolean;
  base_amount: number;
  tax_amount: number;
  total_amount: number;
  lines: { description: string; quantity: string; total_amount: number }[];
}

const day = (iso: string) => iso.split('-').reverse().join('/');

/** The words of the rectification's preview (`rectifyPreview`), in each language. */
const RECTIFY_WORDS = {
  en: {
    title: (number: string, issued: string, whom: string) => `You are about to rectify invoice **${number}** of ${issued}${whom} with this rectifying invoice:`,
    type: 'Type',
    reason: 'Reason',
    number: (next: string, series: string) => `${next} (the next one of series ${series}; it is assigned when issued)`,
    numberLabel: 'Number',
    date: 'Date',
    left: (remaining: string, total: string) => `Rectifies what is left: ${remaining} of ${total}`,
    base: 'Base',
    tax: 'Taxes',
    total: 'Total',
  },
  es: {
    title: (number: string, issued: string, whom: string) => `Vas a rectificar la factura **${number}** del ${issued}${whom} con esta rectificativa:`,
    type: 'Tipo',
    reason: 'Motivo',
    number: (next: string, series: string) => `${next} (el siguiente de la serie ${series}; se asigna al emitirla)`,
    numberLabel: 'Número',
    date: 'Fecha',
    left: (remaining: string, total: string) => `Rectifica lo que queda: ${remaining} de ${total}`,
    base: 'Base',
    tax: 'Impuestos',
    total: 'Total',
  },
} as const;

/** What the model says of the rectification's preview before its card, in `language`: the invoice it rectifies, the
 *  rectifying invoice that would be born (its number as the series' next one, never as reserved) and what was left of
 *  the original. */
export function rectifyPreview(preview: RectificationPreview, language: Language): string {
  const words = RECTIFY_WORDS[language];
  const original = preview.original;
  const whom = original.customer_name ? ` (${original.customer_name})` : '';
  const lines = [words.title(original.number, day(original.issue_date), whom), ''];
  lines.push(`- ${words.type}: ${preview.invoice_type}`, `- ${words.reason}: ${preview.reason}`);
  lines.push(`- ${words.numberLabel}: ${words.number(preview.next_number, preview.series_code)}`);
  lines.push(`- ${words.date}: ${day(preview.issue_date)}`);
  if (!preview.whole) lines.push(`- ${words.left(euros(original.remaining), euros(original.total_amount))}`);
  for (const line of preview.lines) lines.push(`- ${line.description} × ${Number(line.quantity)}: ${euros(line.total_amount)}`);
  lines.push(`- ${words.base}: ${euros(preview.base_amount)}`, `- ${words.tax}: ${euros(preview.tax_amount)}`, `- ${words.total}: ${euros(preview.total_amount)}`);
  return lines.join('\n');
}

type Message = { role: string; content?: unknown; tool_calls?: { function?: { name?: string } }[] };

/** The language the conversation's system message asks the answer in («Answer in Spanish, …»); without one, or with
 *  one it does not speak, English (the source). */
export function languageOf(messages: Message[]): Language {
  for (const message of messages) {
    if (message.role !== 'system') continue;
    const asked = /\bAnswer in (\w+)/.exec(textOf(message.content))?.[1];
    if (asked && asked in NAMED) return NAMED[asked];
  }
  return 'en';
}

function textOf(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map((part) => (part && typeof part === 'object' && 'text' in part ? String(part.text) : '')).join(' ');
  }
  return '';
}

/** Whether a tool's result says it did not run: the Hub's envelope for a tool cancelled, refused or failed
 *  (`error_content` of base/assistant.py, `{"error": {"code": …, "message": …}}`). What ran answers its own output,
 *  whatever words its data carry (a print job is `cancellable`), or comes cut for the model (` …(cut)`). */
function refused(result: string): boolean {
  try {
    const answer = JSON.parse(result) as { error?: { code?: unknown } } | null;
    return typeof answer?.error?.code === 'string';
  } catch {
    return false;
  }
}

const chunk = (delta: Record<string, unknown>, finish: string | null = null) => ({
  object: 'chat.completion.chunk',
  choices: [{ index: 0, delta, finish_reason: finish }],
});
const usage = { object: 'chat.completion.chunk', choices: [], usage: { prompt_tokens: 900, completion_tokens: 60 } };

/** The answer to a conversation, as the frames of a stream (or a status for a failure). */
export function answerTo(messages: Message[]): { status: number; frames: unknown[]; delayMs: number } {
  const last = messages.at(-1);
  const language = languageOf(messages);
  const outcome = (result: unknown) => (refused(textOf(result)) ? NOT_DONE : DONE)[language];
  const question = textOf([...messages].reverse().find((message) => message.role === 'user')?.content);
  const text = (value: string, delayMs = 0) => ({
    status: 200,
    delayMs,
    frames: [...value.match(/[\s\S]{1,24}/g)!.map((piece) => chunk({ content: piece })), chunk({}, 'stop'), usage],
  });
  /** A tool call in fragments, after what is said first (`said`, in pieces), as OpenAI streams both in one answer. */
  const call = (name: string, args: Record<string, unknown>, said = '') => ({
    status: 200,
    delayMs: 0,
    frames: [
      ...(said.match(/[\s\S]{1,24}/g) ?? []).map((piece) => chunk({ content: piece })),
      chunk({ tool_calls: [{ index: 0, id: `call_${Date.now().toString(36)}`, type: 'function', function: { name, arguments: '' } }] }),
      chunk({ tool_calls: [{ index: 0, function: { arguments: JSON.stringify(args) } }] }),
      chunk({}, 'tool_calls'),
      usage,
    ],
  });
  const chain = /E2E-CHAIN (.+)$/m.exec(question);
  if (chain) {
    const results = messages.filter((message) => message.role === 'tool').length;
    if (results === 0) return call('demo__item__list', {});
    if (results === 1) return call('demo__item__create', { name: chain[1].trim() });
  }
  const steps = /E2E-STEPS (.+)$/m.exec(question);
  if (steps) {
    // The results of this request only: the conversation may have run a chain before.
    const results = messages.slice(messages.findLastIndex((message) => message.role === 'user') + 1).filter((message) => message.role === 'tool').length;
    if (results === 0) return call('demo__item__list', {}, STEPS_SAID[language][0]);
    if (results === 1) return call('demo__item__create', { name: steps[1].trim() }, STEPS_SAID[language][1]);
  }
  const closeCash = /E2E-CLOSE-CASH (\d+)/.exec(question);
  if (closeCash) {
    const counted = Number(closeCash[1]);
    // The results of this request only: a conversation may have closed (or cancelled) a drawer before.
    const asked = messages.findLastIndex((message) => message.role === 'user');
    const results = messages.slice(asked + 1).filter((message) => message.role === 'tool');
    if (results.length === 0) return call('cash_register__session__closing_summary', { closing_balance: counted });
    if (results.length === 1) {
      const summary = JSON.parse(textOf(results[0].content)) as CloseCashSummary & { error?: unknown };
      if (!summary.error) {
        return call('cash_register__session__close', { session: summary.number, closing_balance: counted }, closeCashSummary(summary, language));
      }
    }
  }
  const rectify = /E2E-RECTIFY (\S+)(?:.*?porque (.+))?$/m.exec(question);
  if (rectify) {
    const reason = rectify[2]?.trim() || NO_REASON[language];
    // The results of this request only: a conversation may have rectified (or cancelled) before.
    const asked = messages.findLastIndex((message) => message.role === 'user');
    const results = messages.slice(asked + 1).filter((message) => message.role === 'tool');
    if (results.length === 0) return call('invoice__invoice__rectification_preview', { number: rectify[1], reason });
    if (results.length === 1) {
      const preview = JSON.parse(textOf(results[0].content)) as RectificationPreview & { error?: { message?: string } };
      if (preview.error) return text(`${CANNOT_RECTIFY[language]} ${preview.error.message ?? ''}`);
      return call('invoice__invoice__rectify', { number: preview.original.number, reason }, rectifyPreview(preview, language));
    }
    // The rectification's own result names the original, now «cancelled»: only an error is a refusal.
    return text(outcome(results.at(-1)!.content));
  }
  if (last?.role === 'tool') return text(outcome(last.content));
  const offer = /E2E-OFFER (.+)$/m.exec(question);
  if (offer) return text(offer[1].split(' | ').join('\n'));
  const create = /E2E-CREATE (.+)$/m.exec(question);
  if (create) return call('demo__item__create', { name: create[1].trim() });
  const remove = /E2E-DELETE (\S+)/.exec(question);
  if (remove) return call('demo__item__delete', { id: remove[1] });
  const named = /E2E-ASK (\S+) (\{.*\})$/m.exec(question);
  if (named) return call(named[1], JSON.parse(named[2]) as Record<string, unknown>);
  if (question.includes('E2E-FORMAT')) return text(FORMAT_ANSWER[language]);
  if (question.includes('E2E-CLAIM')) return text(CLAIM_ANSWER[language]);
  if (question.includes('E2E-DOWN')) return { status: 500, frames: [], delayMs: 0 };
  if (question.includes('E2E-SLOW')) return text(SLOW_ANSWER[language], 250);
  return text(GREETING[language]);
}

function read(request: IncomingMessage): Promise<Record<string, unknown> | null> {
  return new Promise((resolve) => {
    const parts: Buffer[] = [];
    request.on('data', (part: Buffer) => parts.push(part));
    request.on('end', () => {
      const raw = Buffer.concat(parts).toString('utf8');
      if (!raw) return resolve(null);
      try {
        resolve(JSON.parse(raw) as Record<string, unknown>);
      } catch {
        // A multipart dictation: what matters is that it came.
        resolve({ raw: raw.slice(0, 200) });
      }
    });
  });
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export interface Provider {
  url: string;
  seen: Seen[];
  close(): Promise<void>;
}

/** Starts the provider on `port` (0: any free one). */
export async function startProvider(port: number): Promise<Provider> {
  const seen: Seen[] = [];
  const server: Server = createServer(async (request: IncomingMessage, response: ServerResponse) => {
    const path = (request.url ?? '').split('?', 1)[0];
    const body = await read(request);
    seen.push({ path, body });
    const json = (status: number, value: unknown) => {
      response.writeHead(status, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify(value));
    };
    if (request.method === 'GET' && path === '/v1/models') {
      return json(200, { object: 'list', data: [{ id: 'gpt-e2e-large', object: 'model' }, { id: 'gpt-e2e-mini', object: 'model' }] });
    }
    if (path === '/v1/embeddings') {
      const inputs = Array.isArray(body?.input) ? body.input : [body?.input];
      return json(200, {
        object: 'list',
        data: inputs.map((_, index) => ({ index, embedding: [0.1, 0.2, 0.3] })),
        usage: { prompt_tokens: 4, total_tokens: 4 },
      });
    }
    if (path === '/v1/audio/transcriptions') return json(200, { text: DICTATION });
    if (path === '/v1/chat/completions') {
      const answer = answerTo((body?.messages as Message[] | undefined) ?? []);
      if (answer.status !== 200) return json(answer.status, { error: { message: 'e2e: the provider is down' } });
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      for (const frame of answer.frames) {
        response.write(`data: ${JSON.stringify(frame)}\n\n`);
        if (answer.delayMs) await sleep(answer.delayMs);
      }
      response.end('data: [DONE]\n\n');
      return;
    }
    json(404, { error: { message: `No route ${request.method} ${path}` } });
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  const bound = typeof address === 'object' && address ? address.port : port;
  return {
    url: `http://127.0.0.1:${bound}/v1`,
    seen,
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}
