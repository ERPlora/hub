// Normalización del `status` de una sección del informe de import (enum serde `SectionStatus`
// del runtime Rust). Lo que se prueba aquí no es cosmético: el informe es lo ÚNICO que le dice al
// usuario qué entró y qué no en su hub, así que no puede mentir ni en un sentido ni en el otro.
import { describe, it, expect } from 'vitest';

import { sectionDiscardCode, sectionStatusInfo } from './runtime';

describe('sectionStatusInfo · formas serde del enum', () => {
  it('Applied y Skipped llegan como string', () => {
    expect(sectionStatusInfo('Applied')).toEqual({ kind: 'applied' });
    expect(sectionStatusInfo('Skipped')).toEqual({ kind: 'skipped' });
  });

  it('Failed(motivo) llega como objeto y conserva el motivo', () => {
    expect(sectionStatusInfo({ Failed: 'módulo `taxes` no instalado' })).toEqual({
      kind: 'failed',
      reason: 'módulo `taxes` no instalado',
    });
  });

  // ADR-0195 / hub#305: el import DESCARTA las identidades de un bundle `template`. Ese estado es
  // propio —ni «aplicado» ni «lo saltaste tú»— y viaja como `{"Ignored": motivo}`.
  it('Ignored(motivo) NO es un fallo, y arrastra su motivo', () => {
    const motivo = 'una plantilla no aplica identidades: la sección `hub_users` se ha descartado';
    expect(sectionStatusInfo({ Ignored: motivo })).toEqual({ kind: 'ignored', reason: motivo });
  });

  // ADR-0195 §4 / hub#405: `hub_settings` es la única sección que mezcla lo que SÍ puede viajar
  // (país, moneda, idioma) con lo que no (el NIF y la razón social de UN negocio), así que de un
  // bundle ajeno se aplica en parte. Ni «Aplicado» —diría que entró todo— ni «Descartado» —diría
  // que no entró nada, y la configuración sí entró—: estado propio, con su motivo.
  it('PartiallyApplied(motivo) es un estado propio, no un aplicado ni un descarte', () => {
    expect(sectionStatusInfo({ PartiallyApplied: 'settings_not_portable' })).toEqual({
      kind: 'partial',
      reason: 'settings_not_portable',
    });
  });

  // La razón por la que este test existe: antes de #305 una forma desconocida caía a `failed` con
  // el JSON crudo de motivo. Pintar un ✗ rojo con `{"Ignored":"…"}` delante de un hostelero es
  // exactamente el tipo de informe deshonesto que el resto de esta pantalla evita.
  it('una forma DESCONOCIDA sigue cayendo a fallo, sin inventar un éxito', () => {
    const info = sectionStatusInfo({ Vaporware: 'algo' } as unknown as Record<string, unknown>);
    expect(info.kind).toBe('failed');
  });
});

// hub#331: los descartes nuevos viajan como CÓDIGO ESTABLE y la frase la pone el shell traducida
// (inglés fuente + su `es`), en vez de prosa fabricada en el runtime. Los motivos anteriores siguen
// llegando como texto, así que el mapeo tiene que saber cuál es cuál: traducir es sustituir el
// texto, y sustituir un motivo que NO es un código lo borraría.
describe('sectionDiscardCode · motivo traducible vs prosa heredada', () => {
  it('reconoce el código de un descarte de identidades', () => {
    expect(sectionDiscardCode('identity_not_portable')).toBe('identity_not_portable');
  });

  it('reconoce el código de un descarte de ajustes no portables', () => {
    expect(sectionDiscardCode('settings_not_portable')).toBe('settings_not_portable');
  });

  // hub#354 — la plantilla pidió activar roles que este hub no puede encender (los trae un módulo
  // que no está instalado, o son los administrativos). Es un descarte con su código, no prosa.
  it('reconoce el código de unos roles que el hub no puede activar', () => {
    expect(sectionDiscardCode('roles_not_activatable')).toBe('roles_not_activatable');
  });

  // hub#753 — la numeración fiscal de OTRA instalación (serie + libro de números ya entregados)
  // no aterriza en este hub. Sin código, la fila del informe le enseñaría al hostelero la cadena
  // cruda `numbering_not_portable`, que es peor que no decir nada.
  it('reconoce el código de una numeración fiscal que no es de este hub', () => {
    expect(sectionDiscardCode('numbering_not_portable')).toBe('numbering_not_portable');
  });

  // hub#473 — un bundle de OTRO hub traía los permisos que su dueño había concedido a sus módulos
  // (`certificate`, `network`…). Se descartan enteros: un fichero descargado no concede acceso al
  // certificado de firma de este hub. Con su código, para que la fila no enseñe la cadena cruda.
  it('reconoce el código de unos permisos de módulo que no son de este hub', () => {
    expect(sectionDiscardCode('capability_grants_not_portable')).toBe(
      'capability_grants_not_portable',
    );
  });

  // hub#473 — el backup DE ESTE hub pidió reconceder permisos que ya no se pueden conceder: el
  // módulo se actualizó y dejó de pedirlos, o no está instalado. El resto sí entró.
  it('reconoce el código de unos permisos que ya no se pueden conceder', () => {
    expect(sectionDiscardCode('capabilities_not_grantable')).toBe('capabilities_not_grantable');
  });

  // ADR-0273 D8 / hub#560 — el runtime ya emitía este código y el shell no lo conocía: se pintaba
  // en crudo. Mismo contrato que los demás.
  it('reconoce el código de una sección sobre una tabla de sistema del hub', () => {
    expect(sectionDiscardCode('system_table_not_portable')).toBe('system_table_not_portable');
  });

  // hub#380 — el motivo dejó de ser prosa que nombraba VeriFactu: ahora es el código del flag
  // `installation_bound_data` del module.json, así que sirve igual para TicketBai o NF525 y la
  // frase la pone el shell traducida.
  it('reconoce el código de unos datos ligados a otra instalación', () => {
    expect(sectionDiscardCode('installation_bound_data')).toBe('installation_bound_data');
  });

  // hub#1947 — la plantilla se publicó contra una versión de la app que todavía guardaba esa
  // tabla, y la que el hub instala hoy ya no la tiene. Sin código, la fila del informe le
  // enseñaría a la peluquera la cadena cruda `table_gone_in_installed_version`.
  it('reconoce el código de unas filas de una tabla que la app ya no tiene', () => {
    expect(sectionDiscardCode('table_gone_in_installed_version')).toBe(
      'table_gone_in_installed_version',
    );
  });

  // hub#986 — un bundle de OTRO hub trae las automatizaciones del negocio (los documentos SÍ
  // aterrizan), pero no lo que se les permitía hacer: qué comandos ejecutan, a qué URLs salen. Eso
  // lo aprueba el dueño de ESTE despliegue, así que llegan en pausa y la fila lo dice.
  it('reconoce el código de unos permisos de flujo que no son de este hub', () => {
    expect(sectionDiscardCode('flow_grants_not_portable')).toBe('flow_grants_not_portable');
  });

  // hub#986 — el backup DE ESTE hub pidió devolverle a un flujo un permiso que aquí ya no existe
  // (el módulo no volvió, o renombró el comando). El flujo se restaura DESHABILITADO: armado sin
  // su permiso moriría en cada ejecución, de madrugada y sin nadie mirando.
  it('reconoce el código de unos flujos restaurados en pausa', () => {
    expect(sectionDiscardCode('flows_paused_without_grants')).toBe('flows_paused_without_grants');
  });

  // hub#986 — el import guarda por la MISMA puerta que `POST /flows`, así que un documento que el
  // hub rechazaría en la pantalla tampoco entra por un zip. Se cuenta y el resto sí aterriza.
  it('reconoce el código de un documento de flujo que este hub no puede guardar', () => {
    expect(sectionDiscardCode('flows_not_restorable')).toBe('flows_not_restorable');
  });

  it('un motivo en prosa NO es un código: se pinta tal cual', () => {
    const prosa = 'una plantilla no aplica identidades: la sección `hub_users` se ha descartado';
    expect(sectionDiscardCode(prosa)).toBeNull();
  });

  it('sin motivo no hay nada que traducir', () => {
    expect(sectionDiscardCode(undefined)).toBeNull();
    expect(sectionDiscardCode('')).toBeNull();
  });
});
