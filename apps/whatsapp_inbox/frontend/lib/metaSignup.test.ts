// Meta's window (WhatsApp Embedded Signup) without Facebook's SDK (WHATSAPP_INBOX-F01): the dialog's address from
// what erplora.com gave (door 10), the session Meta's window posts to this page (only from facebook.com), and the
// one-time code erplora.com's return page posts back (only from its own origin, only with this attempt's state).
import { describe, expect, it } from 'vitest';

import { dialogUrl, newState, readReturn, readSession, type SignupOptions } from './metaSignup';

const OPTIONS: SignupOptions = {
  app_id: '1481226093843982',
  config_id: '1101452998214123',
  graph_version: 'v25.0',
  redirect_uri: 'https://erplora.com/whatsapp/return',
};
const STATE = 'a.0123456789abcdef0123456789abcdef';

const fromFacebook = (data: unknown, origin = 'https://www.facebook.com') => new MessageEvent('message', { data, origin });
const session = (event: string, data: Record<string, unknown> = {}) =>
  JSON.stringify({ type: 'WA_EMBEDDED_SIGNUP', event, data, version: 3 });

describe('dialogUrl', () => {
  it('opens Facebook Login for Business with the configuration, a code, erplora.com’s return page and the state', () => {
    const url = new URL(dialogUrl(OPTIONS, STATE));
    expect(`${url.origin}${url.pathname}`).toBe('https://www.facebook.com/v25.0/dialog/oauth');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      client_id: '1481226093843982',
      config_id: '1101452998214123',
      response_type: 'code',
      override_default_response_type: 'true',
      redirect_uri: 'https://erplora.com/whatsapp/return',
      state: STATE,
      display: 'popup',
      extras: '{"setup":{}}',
    });
  });
});

describe('newState', () => {
  it('names the business (the first label of its host) and a fresh secret for each attempt', () => {
    const one = newState('a.localhost');
    const two = newState('peluqueria-ana.erplora.com');
    expect(one).toMatch(/^a\.[0-9a-f]{32}$/);
    expect(two).toMatch(/^peluqueria-ana\.[0-9a-f]{32}$/);
    expect(newState('a.localhost')).not.toBe(one);
  });
});

describe('readSession', () => {
  it('reads the account and the number the window chose, and how it finished', () => {
    const finished = readSession(
      fromFacebook(session('FINISH', { phone_number_id: '106540352242922', waba_id: '102290129340398', business_id: '2729063490586005' })),
    );
    expect(finished).toEqual({
      finished: true,
      event: 'FINISH',
      waba_id: '102290129340398',
      phone_number_id: '106540352242922',
      business_id: '2729063490586005',
    });
    // A number of the WhatsApp Business app (coexistence) may come without its number id.
    expect(readSession(fromFacebook(session('FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', { waba_id: '1' })))).toMatchObject({
      finished: true,
      event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING',
      waba_id: '1',
      phone_number_id: '',
    });
  });

  it('a window cancelled says where, or Meta’s own error', () => {
    expect(readSession(fromFacebook(session('CANCEL', { current_step: 'PHONE_NUMBER_SETUP' })))).toEqual({
      finished: false,
      event: 'CANCEL',
      error: '',
    });
    expect(readSession(fromFacebook(session('CANCEL', { error_message: 'Number already in use' })))).toEqual({
      finished: false,
      event: 'CANCEL',
      error: 'Number already in use',
    });
    expect(readSession(fromFacebook(session('ERROR', { error_message: 'Something went wrong' })))).toEqual({
      finished: false,
      event: 'ERROR',
      error: 'Something went wrong',
    });
  });

  it('only believes facebook.com over https, and only Embedded Signup’s messages', () => {
    const finish = session('FINISH', { waba_id: '1', phone_number_id: '2' });
    expect(readSession(fromFacebook(finish, 'https://evil-facebook.com'))).toBeNull();
    expect(readSession(fromFacebook(finish, 'http://www.facebook.com'))).toBeNull();
    expect(readSession(fromFacebook(finish, 'https://facebook.com.evil.example'))).toBeNull();
    expect(readSession(fromFacebook(finish, 'https://web.facebook.com'))).not.toBeNull();
    expect(readSession(fromFacebook('{"type":"OTHER"}'))).toBeNull();
    expect(readSession(fromFacebook('not json'))).toBeNull();
    expect(readSession(fromFacebook({ type: 'WA_EMBEDDED_SIGNUP', event: 'FINISH' }))).toBeNull();
    // Ids that are not Meta's (digits) are no account at all.
    expect(readSession(fromFacebook(session('FINISH', { waba_id: '1; drop' })))).toBeNull();
  });
});

describe('readReturn', () => {
  const RETURN = 'https://erplora.com';
  const back = (data: unknown, origin = RETURN) => new MessageEvent('message', { data, origin });

  it('takes the code erplora.com’s page brought back for this attempt', () => {
    expect(readReturn(back({ type: 'erplora.whatsapp.signup', state: STATE, code: 'AQD-one-time' }), OPTIONS, STATE)).toEqual({
      code: 'AQD-one-time',
      error: '',
    });
    expect(
      readReturn(back({ type: 'erplora.whatsapp.signup', state: STATE, error: 'access_denied', error_description: 'Permissions error' }), OPTIONS, STATE),
    ).toEqual({ code: '', error: 'Permissions error' });
  });

  it('ignores a code from another origin, another attempt or another shape', () => {
    const message = { type: 'erplora.whatsapp.signup', state: STATE, code: 'AQD' };
    expect(readReturn(back(message, 'https://evil.example'), OPTIONS, STATE)).toBeNull();
    expect(readReturn(back(message, 'http://erplora.com'), OPTIONS, STATE)).toBeNull();
    expect(readReturn(back({ ...message, state: 'a.ffff' }), OPTIONS, STATE)).toBeNull();
    expect(readReturn(back({ ...message, type: 'other' }), OPTIONS, STATE)).toBeNull();
    expect(readReturn(back(JSON.stringify(message)), OPTIONS, STATE)).toBeNull();
    expect(readReturn(back({ type: 'erplora.whatsapp.signup', state: STATE }), OPTIONS, STATE)).toBeNull();
  });
});
