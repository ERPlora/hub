// hub#1980 — every open shell tab names itself to the hub, so the live frame of a sale says which
// till charged it and only that till prints the ticket.
import { describe, expect, it } from 'vitest';

import { CLIENT_INSTANCE } from './client-instance';
import { runtimeHeaders } from './runtime';

describe('the shell tab names itself on every call to the runtime (hub#1980)', () => {
  it('is a plain short id the hub accepts (letters, digits, dashes; at most 64)', () => {
    // The hub DROPS anything else (`auth::client_instance`), and then no till would ever print.
    expect(CLIENT_INSTANCE).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });

  it('travels as X-Client-Instance on the headers every command is sent with', () => {
    expect(runtimeHeaders()['X-Client-Instance']).toBe(CLIENT_INSTANCE);
  });
});
