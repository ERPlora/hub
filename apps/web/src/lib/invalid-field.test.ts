// The core refuses a field; the SCREEN says it in the user's language (hub#1190, hub#1241).
//
// #1185 gave every refusal of the core's own doors `invalid_field` + `field` + `reason` and, doing
// that, wrote the sentences in English (the code-language rule). Nothing translated them, so a hub
// in Spanish answered «the name is required» to an empty name — a visible regression against
// ADR-0055 and the sixteenth repetition of the same defect family (hub#1241).
//
// The translation branches on DATA (`field`, `reason`), never on prose. `reason` is a closed set
// (`required` · `too_long` · `format` · `length` · `unknown` · `immutable` · `inactive` ·
// `duplicate`) and so is `field`, which is what makes a table possible at all.
import { describe, expect, it } from 'vitest';

import { fieldRefusalOf, invalidFieldMessage } from './invalid-field';
import { HubUsersError, RoleActivationError } from './hub-users';

/** A `t`/`te` pair over a flat catalogue, the same contract vue-i18n exposes. */
function catalogue(entries: Record<string, string>) {
  return {
    t: (key: string, params: Record<string, unknown> = {}) =>
      (entries[key] ?? key).replace(/\{(\w+)\}/g, (_m, name: string) => String(params[name] ?? '')),
    te: (key: string) => key in entries,
  };
}

const ES = catalogue({
  'invalidField.byField.name.required': 'Escribe el nombre.',
  'invalidField.byField.pin.format': 'El PIN debe tener {length} dígitos.',
  'invalidField.byField.role_key.immutable':
    'Este rol es de los que trae el hub: está siempre activo y no se puede apagar.',
  'invalidField.byReason.too_long': 'Este dato es demasiado largo.',
});

describe('traducción de `invalid_field` (hub#1190)', () => {
  it('lee `field` y `reason` del rechazo del runtime, no la frase', () => {
    const refusal = new HubUsersError('the name is required', 'invalid_field', 'name', 'required');
    expect(fieldRefusalOf(refusal)).toEqual({ field: 'name', reason: 'required' });
  });

  it('un rechazo de rol también llega con su campo y su motivo', () => {
    const refusal = new RoleActivationError(
      'role `admin` is a base role of the hub: base roles are always active and cannot be switched off',
      'invalid_field',
      'role_key',
      'immutable',
    );
    expect(fieldRefusalOf(refusal)).toEqual({ field: 'role_key', reason: 'immutable' });
  });

  it('un error que no es `invalid_field` no finge tener campo', () => {
    expect(fieldRefusalOf(new HubUsersError('network down'))).toBeUndefined();
    expect(fieldRefusalOf(new Error('network down'))).toBeUndefined();
    expect(fieldRefusalOf(undefined)).toBeUndefined();
  });

  // 🔴 El bug: la pantalla en español enseñaba la frase inglesa del runtime.
  it('devuelve la frase traducida, NUNCA el `message` inglés que llegó', () => {
    const refusal = new HubUsersError('the name is required', 'invalid_field', 'name', 'required');
    const message = invalidFieldMessage(refusal, ES.t, ES.te);
    expect(message).toBe('Escribe el nombre.');
    expect(message).not.toContain('the name is required');
  });

  it('el rol base de Ajustes → Roles se lee en español', () => {
    const refusal = new RoleActivationError(
      'role `admin` is a base role of the hub: base roles are always active and cannot be switched off',
      'invalid_field',
      'role_key',
      'immutable',
    );
    expect(invalidFieldMessage(refusal, ES.t, ES.te)).toBe(
      'Este rol es de los que trae el hub: está siempre activo y no se puede apagar.',
    );
  });

  it('interpola lo que la frase necesita y el rechazo no trae (la longitud del PIN)', () => {
    const refusal = new HubUsersError('the PIN must be 4 digits', 'invalid_field', 'pin', 'format');
    expect(invalidFieldMessage(refusal, ES.t, ES.te, { length: 4 })).toBe(
      'El PIN debe tener 4 dígitos.',
    );
  });

  it('cae al motivo a secas cuando el par (campo, motivo) no tiene frase propia', () => {
    const refusal = new HubUsersError('the role exceeds 50 characters', 'invalid_field', 'role', 'too_long');
    expect(invalidFieldMessage(refusal, ES.t, ES.te)).toBe('Este dato es demasiado largo.');
  });

  // Regla 2 de `platformFailureMessage` (hub#1102), aquí también: una frase inventada para un
  // motivo desconocido diría MENOS que la que vino. Sin traducción → el llamador se queda con
  // el `message` del runtime, que al menos es concreto.
  it('no inventa nada para un motivo que no está en el catálogo', () => {
    const refusal = new HubUsersError('the badge must be between 4 and 64 characters', 'invalid_field', 'badge', 'length');
    expect(invalidFieldMessage(refusal, ES.t, ES.te)).toBeUndefined();
  });
});
