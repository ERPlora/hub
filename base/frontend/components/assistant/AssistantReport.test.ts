// BASE-G123: «Report a problem» under a finished answer. The person says what is wrong with it (wrong, harmful, did not
// do what was asked, something else) and, if it wants, why; the answer, the question it answered and the reason go to
// erplora.com's review. Sent: a thank-you and the dialog closes; refused: it stays open with the reason, nothing lost.
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../../__tests__/mount-base';
import type { Bubble } from '../../lib/assistant-history';
import AssistantReport from './AssistantReport.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const ANSWER: Bubble = {
  id: '01JASSIST0000000000000000A',
  role: 'assistant',
  text: 'Hoy has vendido 120 €.',
  files: [],
  notices: [],
  done: true,
  question: '¿Cuánto he vendido hoy?',
};

type Sent = { url: string; body: Record<string, unknown> };

async function report(answer: (sent: Sent) => Response, bubble: Bubble | null = ANSWER) {
  const sent: Sent[] = [];
  const m = await mountBase(AssistantReport, {
    locale: 'es',
    props: { bubble },
    onApi: ({ url, init }) => {
      const call = { url, body: JSON.parse(String(init.body ?? '{}')) as Record<string, unknown> };
      sent.push(call);
      return answer(call);
    },
  });
  await flush();
  return { ...m, sent };
}

const field = (testid: string) => document.querySelector<HTMLElement & { value?: unknown }>(`[data-testid="${testid}"]`);

function choose(reason: string): void {
  const group = field('assistant-report-reason')!;
  group.dispatchEvent(new CustomEvent('ionChange', { detail: { value: reason } }));
}

function write(comment: string): void {
  field('assistant-report-comment')!.dispatchEvent(new CustomEvent('ionInput', { detail: { value: comment } }));
}

async function send(): Promise<void> {
  field('assistant-report-submit')!.click();
  for (let i = 0; i < 3; i += 1) await flush();
}

beforeEach(() => {
  vi.mocked(toastSuccess).mockClear();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('AssistantReport', () => {
  it('asks what is wrong, in the person’s language, with the four reasons', async () => {
    await report(() => Response.json({ sent: true, duplicate: false }));
    const text = field('assistant-report')!.textContent ?? '';
    expect(text).toContain('Denunciar esta respuesta');
    expect(text).toContain('¿Qué le pasa?');
    for (const reason of ['Es incorrecta', 'Es dañina u ofensiva', 'No hace lo que pedí', 'Otra cosa']) {
      expect(text).toContain(reason);
    }
  });

  it('sends the answer, its question, the reason and the comment, then thanks and closes', async () => {
    const m = await report(() => Response.json({ sent: true, duplicate: false }));
    choose('harmful');
    write('  Un insulto  ');
    await flush();
    await send();
    expect(m.sent.map((s) => [s.url.replace(/^.*\/api/, '/api'), s.body])).toEqual([
      [
        '/api/assistant/report',
        {
          message_id: ANSWER.id,
          reason: 'harmful',
          comment: 'Un insulto',
          question: '¿Cuánto he vendido hoy?',
          answer: 'Hoy has vendido 120 €.',
        },
      ],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Gracias, hemos recibido tu denuncia.');
    expect(m.wrapper.emitted('close')).toHaveLength(1);
  });

  it('without a reason picked, it is «It is wrong»', async () => {
    const m = await report(() => Response.json({ sent: true, duplicate: false }));
    await send();
    expect(m.sent[0].body.reason).toBe('incorrect');
    expect(m.sent[0].body).not.toHaveProperty('comment');
  });

  it('a refusal stays in the dialog with its sentence, and nothing closes', async () => {
    const m = await report(() => Response.json({ code: 'assistant.unavailable', message: 'down' }, { status: 503 }));
    choose('other');
    await send();
    expect(field('assistant-report-error')?.textContent).toContain('No se pudo enviar la denuncia. Inténtalo de nuevo.');
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(m.wrapper.emitted('close')).toBeUndefined();
  });

  it('closed when there is nothing to report', async () => {
    await report(() => Response.json({}), null);
    expect(field('assistant-report-submit')).toBeNull();
  });
});
