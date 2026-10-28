// The AI provider of the assistant's e2e (APP-BASE-9): a real HTTP server on 127.0.0.1 that speaks OpenAI's API
// (`/v1/models`, streamed `/v1/chat/completions`, `/v1/embeddings`, `/v1/audio/transcriptions`). erplora.com's gateway
// of the run's SaaS talks to it (`assistant_seed.py gateway http://127.0.0.1:<port>/v1`, README «El asistente»): no test
// reaches a real provider nor writes a real key. What it answers depends on the question, by a marker the spec writes:
// - `E2E-FORMAT`: an answer with a heading, bold, a list, a table and a screen of the hub;
// - `E2E-CREATE <name>`: asks for the write `demo.item.create` with that name, then says it is done;
// - `E2E-DELETE <id>`: asks for the dangerous write `demo.item.delete` of that item, then says it is done;
// - `E2E-ASK <tool> <JSON>`: asks for any write by its tool's name with those data as written, then says how it went
//   (the card of a datum outside the screen's own list, FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH);
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
// - `E2E-CLAIM`: says it created something without running anything;
// - `E2E-DOWN`: the provider fails (500);
// - `E2E-SLOW`: a long answer, piece by piece, to stop it half-way;
// - anything else: a short greeting. A dictation is always `DICTATION` (below).
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';

export const DICTATION = 'E2E-CREATE Mesa dictada';
export const GREETING = 'Hola, soy el asistente de prueba.';
export const FORMAT_ANSWER = [
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
].join('\n');
export const CLAIM_ANSWER = 'Listo: he creado la mesa 9 y la he guardado.';
/** What `E2E-STEPS` says before its read and before its write: one round each. */
export const STEPS_SAID = ['Miro primero qué mesas tienes.', 'Ninguna se llama así: te pido crearla.'];

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

const euros = (cents: number, signed = false) => `${signed && cents > 0 ? '+' : ''}${(cents / 100).toFixed(2)} €`;
const named = (count: number, labels: string[]) => (labels.length ? `${count} (${labels.join(' · ')})` : String(count));

/** What the model says of the close's summary before its card: only what the summary carries (never an expected
 *  that a blind count left out), and what is still pending at the close. */
export function closeCashSummary(summary: CloseCashSummary): string {
  const lines = [`Vas a cerrar la sesión **${summary.number}**:`, ''];
  if (summary.closing_balance !== null) lines.push(`- Contado: ${euros(summary.closing_balance)}`);
  if (summary.expected_hidden || summary.expected_balance === null) {
    lines.push('- Arqueo ciego: el cierre lo comparará al confirmar.');
  } else {
    lines.push(`- Esperado: ${euros(summary.expected_balance)}`);
    if (summary.difference !== null) lines.push(`- Diferencia: ${euros(summary.difference, true)}`);
  }
  const review = summary.pending;
  if (review.open_checks) lines.push(`- Cuentas abiertas: ${named(review.open_checks, review.open_check_labels)}`);
  if (review.unserved) lines.push(`- Comandas sin servir: ${named(review.unserved, review.unserved_labels)}`);
  if (review.prints) lines.push(`- Impresiones sin salir: ${review.prints}`);
  if (review.incomplete) lines.push('- No se ha podido comprobar todo lo pendiente.');
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

/** What the model says of the rectification's preview before its card: the invoice it rectifies, the rectifying invoice
 *  that would be born (its number as the series' next one, never as reserved) and what was left of the original. */
export function rectifyPreview(preview: RectificationPreview): string {
  const original = preview.original;
  const whom = original.customer_name ? ` (${original.customer_name})` : '';
  const lines = [`Vas a rectificar la factura **${original.number}** del ${day(original.issue_date)}${whom} con esta rectificativa:`, ''];
  lines.push(`- Tipo: ${preview.invoice_type}`, `- Motivo: ${preview.reason}`);
  lines.push(`- Número: ${preview.next_number} (el siguiente de la serie ${preview.series_code}; se asigna al emitirla)`);
  lines.push(`- Fecha: ${day(preview.issue_date)}`);
  if (!preview.whole) lines.push(`- Rectifica lo que queda: ${euros(original.remaining)} de ${euros(original.total_amount)}`);
  for (const line of preview.lines) lines.push(`- ${line.description} × ${Number(line.quantity)}: ${euros(line.total_amount)}`);
  lines.push(`- Base: ${euros(preview.base_amount)}`, `- Impuestos: ${euros(preview.tax_amount)}`, `- Total: ${euros(preview.total_amount)}`);
  return lines.join('\n');
}

type Message = { role: string; content?: unknown; tool_calls?: { function?: { name?: string } }[] };

function textOf(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map((part) => (part && typeof part === 'object' && 'text' in part ? String(part.text) : '')).join(' ');
  }
  return '';
}

const chunk = (delta: Record<string, unknown>, finish: string | null = null) => ({
  object: 'chat.completion.chunk',
  choices: [{ index: 0, delta, finish_reason: finish }],
});
const usage = { object: 'chat.completion.chunk', choices: [], usage: { prompt_tokens: 900, completion_tokens: 60 } };

/** The answer to a conversation, as the frames of a stream (or a status for a failure). */
export function answerTo(messages: Message[]): { status: number; frames: unknown[]; delayMs: number } {
  const last = messages.at(-1);
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
    if (results === 0) return call('demo__item__list', {}, STEPS_SAID[0]);
    if (results === 1) return call('demo__item__create', { name: steps[1].trim() }, STEPS_SAID[1]);
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
        return call('cash_register__session__close', { session: summary.number, closing_balance: counted }, closeCashSummary(summary));
      }
    }
  }
  const rectify = /E2E-RECTIFY (\S+)(?:.*?porque (.+))?$/m.exec(question);
  if (rectify) {
    const reason = rectify[2]?.trim() || 'error en la factura';
    // The results of this request only: a conversation may have rectified (or cancelled) before.
    const asked = messages.findLastIndex((message) => message.role === 'user');
    const results = messages.slice(asked + 1).filter((message) => message.role === 'tool');
    if (results.length === 0) return call('invoice__invoice__rectification_preview', { number: rectify[1], reason });
    if (results.length === 1) {
      const preview = JSON.parse(textOf(results[0].content)) as RectificationPreview & { error?: { message?: string } };
      if (preview.error) return text(`No se puede rectificar: ${preview.error.message ?? ''}`);
      return call('invoice__invoice__rectify', { number: preview.original.number, reason }, rectifyPreview(preview));
    }
    // The rectification's own result names the original, now «cancelled»: only an error is a refusal.
    const outcome = JSON.parse(textOf(results.at(-1)!.content) || '{}') as { error?: unknown };
    return text(outcome.error ? 'No lo he hecho.' : 'Hecho.');
  }
  if (last?.role === 'tool') {
    const result = textOf(last.content);
    return text(/error|refused|cancel|not_confirmed|denied/i.test(result) ? 'No lo he hecho.' : 'Hecho.');
  }
  const create = /E2E-CREATE (.+)$/m.exec(question);
  if (create) return call('demo__item__create', { name: create[1].trim() });
  const remove = /E2E-DELETE (\S+)/.exec(question);
  if (remove) return call('demo__item__delete', { id: remove[1] });
  const named = /E2E-ASK (\S+) (\{.*\})$/m.exec(question);
  if (named) return call(named[1], JSON.parse(named[2]) as Record<string, unknown>);
  if (question.includes('E2E-FORMAT')) return text(FORMAT_ANSWER);
  if (question.includes('E2E-CLAIM')) return text(CLAIM_ANSWER);
  if (question.includes('E2E-DOWN')) return { status: 500, frames: [], delayMs: 0 };
  if (question.includes('E2E-SLOW')) return text('Esta respuesta es larga y llega despacio, trozo a trozo. '.repeat(20), 250);
  return text(GREETING);
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
