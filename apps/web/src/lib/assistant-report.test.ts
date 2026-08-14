// Tests for the assistant "report an issue" call (hub#946, Microsoft Store policy 11.16:
// users must be able to report inappropriate AI-generated content). The report goes to the
// hub runtime (`POST /api/assistant/report`), authenticated with the SAME header helper as
// the chat stream (`runtimeHeaders()` → the local session `X-Hub-Session` is the runtime's
// permission authority).

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'session' }),
}));

import { reportAssistantMessage } from './assistant-report';

function mockFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('reportAssistantMessage', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs the report to the runtime with the session headers and the wire body shape', async () => {
    const fetchMock = mockFetch(200, { ok: true });

    await reportAssistantMessage({
      messageId: 'msg-1',
      assistantMessage: 'a harmful answer',
      userMessage: 'the question before it',
      comment: 'this looks wrong',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/assistant/report');
    expect(opts.method).toBe('POST');
    // Same helper as the chat call: the local session header must travel with the report.
    expect(opts.headers).toMatchObject({
      'X-Hub-Session': 'session',
      'X-Hub-Id': 'h1',
      'Content-Type': 'application/json',
    });
    expect(JSON.parse(String(opts.body))).toEqual({
      message_id: 'msg-1',
      assistant_message: 'a harmful answer',
      user_message: 'the question before it',
      comment: 'this looks wrong',
    });
  });

  it('sends empty strings when there is no preceding user message and no comment', async () => {
    const fetchMock = mockFetch(200, { ok: true });

    await reportAssistantMessage({ messageId: 'msg-2', assistantMessage: 'answer' });

    const [, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(opts.body))).toEqual({
      message_id: 'msg-2',
      assistant_message: 'answer',
      user_message: '',
      comment: '',
    });
  });

  it('throws on a non-200 response', async () => {
    mockFetch(500, { ok: false });

    await expect(
      reportAssistantMessage({ messageId: 'msg-3', assistantMessage: 'answer' }),
    ).rejects.toThrow(/500/);
  });
});
