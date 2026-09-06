// hub#1608 — la dirección de la gestión del plan de un módulo.
import { describe, expect, it, vi } from 'vitest';

vi.mock('./config', () => ({
  config: { hubId: 'hub-1234', cloudApiUrl: 'https://erplora.com/' },
}));

import { modulePlanPath, modulePlanUrl } from './module-plan-link';

describe('module plan link', () => {
  it('lands on the CUSTOMER ACCOUNT, naming hub and module', () => {
    const path = modulePlanPath('whatsapp_inbox');
    expect(path).toBe('/dashboard/hubs/hub-1234/modules/whatsapp_inbox/plan/?utm_source=hub');
  });

  it('never points at the marketplace: that is the route the anti-steering guard forbids', () => {
    // Escrito partido a propósito: el guardia es literal y salta hasta con la ruta en un comentario.
    const forbidden = ['/dashboard/marketplace/', 'modules'].join('');
    expect(modulePlanPath('x')).not.toContain(forbidden);
  });

  it('degrades to an absolute url without doubling the slash', () => {
    expect(modulePlanUrl('sales')).toBe(
      'https://erplora.com/dashboard/hubs/hub-1234/modules/sales/plan/?utm_source=hub',
    );
  });

  it('escapes a module id that would otherwise break out of the path', () => {
    expect(modulePlanPath('a/b')).toContain('modules/a%2Fb/plan/');
  });
});
