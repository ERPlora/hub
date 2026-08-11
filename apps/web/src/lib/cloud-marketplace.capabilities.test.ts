/**
 * El catálogo Cloud trae los permisos que declara cada módulo (pm#132, saas del mismo día).
 *
 * Hasta hoy no viajaban: el diálogo de consentimiento solo podía preguntarle al runtime local, que
 * en una PRIMERA instalación todavía no conoce el módulo. Esa lista vacía se leía como «no pide
 * nada» y el módulo entraba con todo denegado.
 */
import { describe, expect, it } from 'vitest';

import { normalizeMarketplaceModule } from './cloud';

describe('capabilities del catálogo marketplace', () => {
  it('lee los ids del bloque `capabilities` del manifest', () => {
    expect(normalizeMarketplaceModule({
      module_id: 'flows',
      name: 'Automations',
      module_type: 'free',
      capabilities: { manage_flows: {} },
    }).capabilities).toEqual(['manage_flows']);
  });

  it('un módulo que no pide permisos trae la lista vacía', () => {
    // Los 24 publicados hasta hoy. Vacío ≠ ausente: aquí los dos acaban igual, pero por
    // caminos distintos, y ninguno puede convertirse en «no lo sé».
    expect(normalizeMarketplaceModule({
      module_id: 'customers',
      name: 'Customers',
      module_type: 'free',
      capabilities: {},
    }).capabilities).toEqual([]);
  });

  it('un SaaS viejo que aún no expone el campo no rompe nada', () => {
    // Contrato aditivo: el hub tiene que seguir instalando contra la imagen anterior del SaaS.
    expect(normalizeMarketplaceModule({
      module_id: 'customers',
      name: 'Customers',
      module_type: 'free',
    }).capabilities).toEqual([]);
  });

  it('varios permisos salen todos', () => {
    expect(normalizeMarketplaceModule({
      module_id: 'x',
      name: 'X',
      capabilities: { network: { allow: ['api.example.com'] }, notify: {} },
    }).capabilities.sort()).toEqual(['network', 'notify']);
  });

  it('aguanta una forma inesperada sin inventarse permisos', () => {
    // Nunca fabricar un permiso a partir de basura: el modal enseñaría algo que el módulo no pide.
    expect(normalizeMarketplaceModule({
      module_id: 'x',
      name: 'X',
      capabilities: 'manage_flows',
    }).capabilities).toEqual([]);
    expect(normalizeMarketplaceModule({
      module_id: 'x',
      name: 'X',
      capabilities: null,
    }).capabilities).toEqual([]);
  });
});
