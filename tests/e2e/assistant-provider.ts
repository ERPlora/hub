// The AI provider of the assistant's e2e (APP-BASE-9): a real HTTP server on 127.0.0.1 that speaks OpenAI's API
// (`/v1/models`, streamed `/v1/chat/completions`, `/v1/embeddings`, `/v1/audio/transcriptions`). erplora.com's gateway
// of the run's SaaS talks to it (`assistant_seed.py gateway http://127.0.0.1:<port>/v1`, README «El asistente»): no test
// reaches a real provider nor writes a real key. What it answers depends on the question, by a marker the spec writes:
// - `E2E-FORMAT`: an answer with a heading, bold, a list, a table and a screen of the hub;
// - `E2E-CREATE <name>`: asks for the write `demo.item.create` with that name, then says it is done;
// - `E2E-DELETE <id>`: asks for the dangerous write `demo.item.delete` of that item, then says it is done;
// - `E2E-CHAIN <name>`: reads the items (`demo.item.list`), then asks to create one with that name, then says so;
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

export interface Seen {
  path: string;
  body: Record<string, unknown> | null;
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
  const call = (name: string, args: Record<string, unknown>) => ({
    status: 200,
    delayMs: 0,
    frames: [
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
  if (last?.role === 'tool') {
    const result = textOf(last.content);
    return text(/error|refused|cancel|not_confirmed|denied/i.test(result) ? 'No lo he hecho.' : 'Hecho.');
  }
  const create = /E2E-CREATE (.+)$/m.exec(question);
  if (create) return call('demo__item__create', { name: create[1].trim() });
  const remove = /E2E-DELETE (\S+)/.exec(question);
  if (remove) return call('demo__item__delete', { id: remove[1] });
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
