// @vitest-environment node
// flow: ninguno — e2e harness (hub#997)
// A fresh owner on the stack's SaaS, shared by every spec that signs one up (saas-owner.ts): the sign-up and the business
// were copied in five specs. Its POST to the SaaS's API carries the SaaS's own CSRF token, read from the cookie of the
// SaaS's host (never a hub's), and without one it says so at once instead of a 403 later. The specs that sign up an
// owner take it from there and keep no copy of their own.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { BrowserContext } from '@playwright/test';
import { describe, expect, it } from 'vitest';

import { SAAS } from './helpers';
import { joinsAsEmployee, type SaasOwner, saasPost } from './saas-owner';

const HERE = dirname(fileURLToPath(import.meta.url));

/** A browser context with `cookies` on its jar, whose POSTs are recorded instead of sent. */
function contextWith(cookies: { name: string; value: string; domain: string }[]) {
  const posted: { url: string; options: unknown }[] = [];
  const context = {
    cookies: async () => cookies,
    request: {
      post: async (url: string, options: unknown) => {
        posted.push({ url, options });
        return { status: () => 201 };
      },
    },
  } as unknown as BrowserContext;
  return { context, posted };
}

describe('saasPost', () => {
  it("posts to the SaaS's API with the SaaS's own CSRF token", async () => {
    const host = new URL(SAAS).hostname;
    const { context, posted } = contextWith([
      { name: 'csrftoken', value: 'of-a-hub', domain: `a.${host}` },
      { name: 'csrftoken', value: 'of-the-saas', domain: host },
    ]);

    await saasPost(context, '/hubs/businesses', { name: 'Bar', country: 'ES' });

    expect(posted).toEqual([
      {
        url: `${SAAS}/api/hubs/businesses`,
        options: { headers: { 'X-CSRFToken': 'of-the-saas' }, data: { name: 'Bar', country: 'ES' } },
      },
    ]);
  });

  it('says it has no token before posting anything when the account is not signed in there', async () => {
    const { context, posted } = contextWith([]);

    await expect(saasPost(context, '/hubs/businesses', {})).rejects.toThrow(
      'POST /hubs/businesses: no csrftoken of the SaaS (sign in first)',
    );
    expect(posted).toEqual([]);
  });
});

/** An account signed in on the SaaS whose POSTs are recorded, each answered 200 with `answer`. */
function accountAnswering(email: string, answer: unknown) {
  const posted: { url: string; data: unknown }[] = [];
  const context = {
    cookies: async () => [{ name: 'csrftoken', value: 'of-the-saas', domain: new URL(SAAS).hostname }],
    request: {
      post: async (url: string, options: { data: unknown }) => {
        posted.push({ url, data: options.data });
        return { status: () => 200, text: async () => JSON.stringify(answer), json: async () => answer };
      },
    },
  } as unknown as BrowserContext;
  return { account: { context, credentials: { email, password: '' } } as SaasOwner, posted };
}

describe('joinsAsEmployee', () => {
  it("has the owner invite the person as an employee and the person accept, through the SaaS's API", async () => {
    const owner = accountAnswering('owner@example.com', { id: 'invitation-1' });
    const person = accountAnswering('person@example.com', {});

    const id = await joinsAsEmployee(owner.account, person.account, { id: 'hub-1', slug: 'bar' });

    expect(id).toBe('invitation-1');
    expect(owner.posted).toEqual([
      {
        url: `${SAAS}/api/hubs/members/invite`,
        data: { hub_id: 'hub-1', email: 'person@example.com', role: 'hub_employee', message: '' },
      },
    ]);
    expect(person.posted).toEqual([{ url: `${SAAS}/api/hubs/invitations/accept`, data: { id: 'invitation-1' } }]);
  });
});

describe('the specs that sign up an owner on the SaaS', () => {
  it('take it from saas-owner.ts and keep no copy of their own', () => {
    const specs = readdirSync(HERE).filter((name) => name.endsWith('.spec.ts'));
    const copies = specs.filter((name) => readFileSync(join(HERE, name), 'utf8').includes('/launch?tab=signup'));

    expect(copies).toEqual([]);
  });
});
