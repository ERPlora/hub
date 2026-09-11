// hub#1731 — the translation between the runtime's answer and the print door, which is the link
// the whole silent-failure fix hangs from.
//
// It used to live inline in `main.ts` as `return body?.ok === true`, so it threw away the one fact
// that tells «this comes out late» from «this never comes out»: how many devices are registered
// and reporting for the station the job landed in. With it thrown away, `via:'queue'` read exactly
// like `via:'bridge'`, and a hub with no printer set up took the money in silence.
//
// It is out of `main.ts` and in here BECAUSE of that: the bootstrap file has no tests, so the one
// line that carries the answer across was also the one line nothing could catch regressing.
import { describe, expect, it, vi } from 'vitest';

import { createEnqueuePrintJob } from './print-enqueue';

const JOB = {
  jobId: 'sale-42',
  role: 'receipt',
  documentType: 'receipt',
  document: { items: [] },
};

/** `fetch`, answering one canned HTTP response. */
function fakeFetch(status: number, body: unknown) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })) as unknown as typeof fetch;
}

describe('what the runtime answered when we queued a job', () => {
  it('carries the coverage across: queued, and nobody is going to take it out', async () => {
    // THE case of the issue: the job is safe, and no paper is coming out of anywhere.
    const enqueue = createEnqueuePrintJob(fakeFetch(200, { ok: true, liveHosts: 0 }));

    await expect(enqueue(JOB)).resolves.toEqual({ queued: true, liveHosts: 0 });
  });

  it('carries the coverage across when somebody IS draining the station', async () => {
    const enqueue = createEnqueuePrintJob(fakeFetch(200, { ok: true, liveHosts: 2 }));

    await expect(enqueue(JOB)).resolves.toEqual({ queued: true, liveHosts: 2 });
  });

  it('a runtime that did not answer the question leaves it UNANSWERED, never zero', async () => {
    // An older runtime does not send the key. Turning that into `0` would put a warning on every
    // ticket of a perfectly set-up hub, and a warning everybody sees is a warning nobody reads.
    const enqueue = createEnqueuePrintJob(fakeFetch(200, { ok: true }));

    await expect(enqueue(JOB)).resolves.toEqual({ queued: true, liveHosts: undefined });
  });

  it('ignores a coverage that is not a number (a payload we do not understand is not an answer)', async () => {
    const enqueue = createEnqueuePrintJob(fakeFetch(200, { ok: true, liveHosts: 'lots' }));

    await expect(enqueue(JOB)).resolves.toEqual({ queued: true, liveHosts: undefined });
  });

  it('a refused job is not queued — the door falls back to the browser', async () => {
    const enqueue = createEnqueuePrintJob(fakeFetch(500, { ok: false }));

    await expect(enqueue(JOB)).resolves.toEqual({ queued: false });
  });

  it('a 200 that says ok:false is not queued either', async () => {
    const enqueue = createEnqueuePrintJob(fakeFetch(200, { ok: false }));

    await expect(enqueue(JOB)).resolves.toMatchObject({ queued: false });
  });

  it('a body that is not JSON does not throw: a sale never falls over printing', async () => {
    const brokenBody = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error('not JSON');
      },
    })) as unknown as typeof fetch;
    const enqueue = createEnqueuePrintJob(brokenBody);

    await expect(enqueue(JOB)).resolves.toMatchObject({ queued: false });
  });

  it('posts the job to the runtime print queue', async () => {
    const f = fakeFetch(200, { ok: true, liveHosts: 1 });
    await createEnqueuePrintJob(f)({ ...JOB, format: 'receipt' });

    const [url, init] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(String(url)).toContain('/api/print/jobs');
    expect((init as RequestInit).method).toBe('POST');
    // The role travels AS THE CALLER SAID IT (hub#987): the shell naming the merchant's peripheral
    // would send every kitchen docket to the till roll.
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      jobId: 'sale-42',
      role: 'receipt',
      documentType: 'receipt',
      format: 'receipt',
    });
  });
});
