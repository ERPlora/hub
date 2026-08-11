// **The link that turns the print queue on** (hub#749, ADR-0196 §6).
//
// The queue, the host registry and the drain channel were all built (hub#341/#342/#343) and the
// product could not reach any of it: `POST /api/print/hosts` had **no caller** — not the shell, not
// the installed app, not a module. Without that registration the hub answers every drain with
// `print.host_not_registered`, the drain treats it as a fact of configuration and stops, and
// everything queued stays queued for ever with nobody the wiser.
//
// What is pinned here is the rule that makes the registration honest: **a device registers for the
// roles it can actually print, and only those.** A phone that registered for `kitchen` would claim
// ticket after ticket and fail every one, burning the job's hand-outs and dead-lettering work a
// real till was about to print — and the hub cannot catch that, because as far as it knows that
// device is a legitimate host.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPrintHostRegistration } from './print-host-registration';

/** A registration wired to fakes: no fetch, no timers, no hardware. */
function harness(
  roles: string[][],
  over: Partial<Parameters<typeof createPrintHostRegistration>[0]> = {},
) {
  let call = 0;
  const rolesOnThisDevice = vi.fn(async () => roles[Math.min(call++, roles.length - 1)]);
  const register = vi.fn(async () => ({ heartbeatSeconds: 30 }));
  const heartbeat = vi.fn(async () => ({ refreshed: 1, heartbeatSeconds: 30 }));
  const registration = createPrintHostRegistration({
    rolesOnThisDevice,
    register,
    heartbeat,
    session: () => 'session-token',
    ...over,
  });
  return { registration, rolesOnThisDevice, register, heartbeat };
}

describe('createPrintHostRegistration — quién dice «este equipo imprime»', () => {
  beforeEach(() => vi.clearAllMocks());

  it('el equipo con la impresora de recibos SE DA DE ALTA para ese rol', async () => {
    // El eslabón que faltaba entero: sin esta llamada la cola es inalcanzable desde el producto.
    const { registration, register } = harness([['receipt']]);

    await registration.tick();

    expect(register).toHaveBeenCalledWith('receipt');
  });

  it('un equipo SIN impresora no se da de alta de nada', async () => {
    // El móvil con la PWA no puede sacar papel: darlo de alta sería reclamar tiques para fallarlos
    // todos y dejar en dead-letter trabajo que un TPV de verdad iba a imprimir.
    const { registration, register, heartbeat } = harness([[]]);

    await registration.tick();

    expect(register).not.toHaveBeenCalled();
    expect(heartbeat).not.toHaveBeenCalled();
  });

  it('se da de alta UNA vez por rol: el segundo latido solo late', async () => {
    const { registration, register, heartbeat } = harness([['receipt'], ['receipt']]);

    await registration.tick();
    await registration.tick();

    expect(register).toHaveBeenCalledTimes(1);
    expect(heartbeat).toHaveBeenCalledTimes(2);
  });

  it('un rol asignado DESPUÉS se da de alta sin reiniciar la app', async () => {
    // El dueño entra en Ajustes → Impresoras y le pone el rol `kitchen` a la segunda impresora.
    // Si el alta solo ocurriera en el boot, eso no imprimiría hasta cerrar y abrir la aplicación.
    const { registration, register } = harness([['receipt'], ['receipt', 'kitchen']]);

    await registration.tick();
    await registration.tick();

    expect(register).toHaveBeenCalledTimes(2);
    expect(register).toHaveBeenLastCalledWith('kitchen');
  });

  it('si el hub dice que aquí no aloja nada (`refreshed: 0`), se vuelve a dar de alta', async () => {
    // `refreshed: 0` es un éxito con significado: las filas de este equipo se fueron (un reset, una
    // retirada) y latir contra la nada para siempre dejaría la cola sin quien la drene.
    const heartbeat = vi.fn(async () => ({ refreshed: 0, heartbeatSeconds: 30 }));
    const { registration, register } = harness([['receipt'], ['receipt']], { heartbeat });

    await registration.tick();
    await registration.tick();

    expect(register).toHaveBeenCalledTimes(2);
  });

  it('sin sesión no llama a nada: se reintenta en el siguiente latido', async () => {
    // `bootPrintHost` arranca en el boot del shell, que puede ser la pantalla de login. Machacar
    // el hub con 401 cada 30 s no da de alta a nadie y esconde el problema real.
    const { registration, register } = harness([['receipt']], { session: () => null });

    await registration.tick();

    expect(register).not.toHaveBeenCalled();
  });

  it('la cadencia la manda el HUB, no una constante del cliente', async () => {
    // El hub decide la ventana con la que resuelve quién está vivo; un intervalo fijado aquí puede
    // separarse de ella y dejar hosts «muertos» que en realidad están delante de la impresora.
    // Las DOS puertas publican la misma cadencia (es la misma constante del hub), así que el falso
    // las contesta iguales: un hub que dijera 7 en una y 30 en la otra no existe.
    const register = vi.fn(async () => ({ heartbeatSeconds: 7 }));
    const heartbeat = vi.fn(async () => ({ refreshed: 1, heartbeatSeconds: 7 }));
    const { registration } = harness([['receipt']], { register, heartbeat });

    await registration.tick();

    expect(registration.heartbeatSeconds()).toBe(7);
  });

  it('avisa de que este equipo YA DRENA un rol, para que el drenaje pueda arrancar', async () => {
    // El drenaje no reintenta una negativa de configuración: si conecta antes del alta se lleva
    // `print.host_not_registered` y para para siempre. Así que el alta es quien lo enciende.
    const onRegistered = vi.fn();
    const { registration } = harness([['receipt']], { onRegistered });

    await registration.tick();

    expect(onRegistered).toHaveBeenCalledTimes(1);
  });

  it('un alta rechazada no se da por hecha: se reintenta', async () => {
    const register = vi.fn(async () => { throw new Error('401'); });
    const { registration } = harness([['receipt'], ['receipt']], { register });

    await registration.tick();
    await registration.tick();

    expect(register).toHaveBeenCalledTimes(2);
  });
});
