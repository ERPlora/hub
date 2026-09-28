// Selección del transporte de HARDWARE por entorno (ADR-0196 §3, cliente fino).
//
//   - App instalada (Tauri: escritorio · Android · iOS): `IpcBridgeTransport` — `invoke`
//     in-process sobre `erplora-peripherals` (la app ES el acceso al hardware, §2.7): sin
//     servidor local, sin token, sin device-code.
//   - Navegador a secas: NO hay hardware — `UnavailableBridgeTransport`. Antes había aquí un
//     segundo camino (`BridgeClient`, WS a `localhost:12321` contra el bridge standalone, con su
//     token de emparejamiento); ADR-0196 §3 lo retira y con él PNA, mixed-content y la clave
//     pública del emparejamiento. El precio explícito: la PWA deja de imprimir tiques térmicos.
//
// Modules consume `erplora.peripherals` without knowing which transport they got (one contract),
// and since hub#524 the shell's own SCREENS ask at that same door ({@link detectPeripherals}).
import {
  ANDROID_LOCAL_NETWORK_PERMISSION,
  ANDROID_NOTIFICATIONS_PERMISSION,
  IpcBridgeTransport,
  LocalNetworkPermissionDeniedError,
  UnavailableBridgeTransport,
  type BridgeStatus,
  type BridgeTransport,
  type TauriBridge,
} from '@erplora/module-sdk';

import { invokeTauri, isTauri } from './device';
import { checkDevicePermissions } from './device-permission';
import { i18n } from '../i18n';
import {
  ensureLocalNetworkPermission,
  localNetworkPrimerLabelsFrom,
} from './local-network-permission';
import { hardwareUnavailableMessage, printerDiscoveryMessage } from './printer-discovery';

/** The plugin call that puts a runtime-permission dialog on the screen. */
const REQUEST_PERMISSIONS = 'plugin:erplora-android|request_permissions';

/**
 * Puts OUR sentence in front of Android's local-network dialog (hub#1773).
 *
 * The transport asks for `ACCESS_LOCAL_NETWORK` itself, right before every operation that needs
 * the LAN (hub#758's scope) — but it asks COLD, and what Android shows describes the mechanism
 * («find, connect to and determine the relative position of nearby devices»), never the purpose.
 * Read cold that is a request to know what is around you, and the normal answer is no; after two
 * noes the system stops presenting the dialog for the life of the install and the printer is
 * simply never found again.
 *
 * **The interception is here, at the adapter, and not around `discoverPrinters`**, because the
 * cold ask is inside the SDK's own `ensurePermissions` — patching the method from outside would
 * put our sheet in front of a dialog that then pops anyway. The adapter is the seam the shell
 * OWNS: every permission dialog this app shows leaves through it, so explaining one before it
 * appears is the shell doing its job (ADR-0196 §3, thin client; ADR-0055, the words live here),
 * and it covers scanning, printing, the test sheet and the drawer with one rule instead of four.
 *
 * At most ONE sheet per install: `ensureLocalNetworkPermission` only opens it when the permission
 * really is refused and the user has not answered yet, so a till that prints all day never sees
 * it. A «no» resolves normally — the operation behind it carries on and reports what is true
 * (hub#338 makes a blocked scan a typed refusal, not an empty list).
 *
 * **One sheet, one system dialog, one answer** (hub#1923). Discovery asks for the LAN and for
 * bonded Bluetooth together (ADR-0204); on Android 17 both are «nearby devices» and the system
 * words them identically. So the batch travels WHOLE behind the sheet, in a single
 * `request_permissions` — Android shows one dialog for it — and the rest of the batch follows the
 * LAN's fate: a «no», to our sheet or to Android's, is not answered with a second, cold ask for
 * Bluetooth. Where this Android has no LAN permission (API < 37) the rest is asked as before.
 * The notices have their own primer at their own moment (hub#1732).
 */
async function askWithLocalNetworkPrimer(
  args: Record<string, unknown> | undefined,
  requested: string[],
): Promise<Record<string, boolean>> {
  let before: Record<string, boolean> = {};
  // Set from inside the request seam, so it is a holder: TS does not see closure writes.
  const asked = { done: false, answer: {} as Record<string, boolean> };
  const lanState = await ensureLocalNetworkPermission({
    // Resolved at call time, not at construction: the hub's language can change while the app is
    // open, and the sheet has to come out in the one that is active now.
    labels: localNetworkPrimerLabelsFrom((key) => i18n.global.t(key)),
    check: async () => {
      before = (await checkDevicePermissions()) ?? {};
      return before;
    },
    // The user said yes to our sentence: ONE ask for everything the operation needs.
    request: async () => {
      asked.done = true;
      const answer = await invokeTauri<Record<string, boolean>>(REQUEST_PERMISSIONS, {
        ...args,
        permissions: requested,
      });
      asked.answer = answer ?? {};
      return answer;
    },
  });
  // Android has been asked for the whole batch already: never a second dialog behind it.
  if (asked.done) return { ...before, ...asked.answer };

  const current = { ...before, [ANDROID_LOCAL_NETWORK_PERMISSION]: lanState === 'granted' };
  if (lanState === 'denied') {
    // Ours or Android's, the answer was no: the rest of the batch does not get a cold dialog.
    return current;
  }
  const missing = requested.filter(
    (p) => p !== ANDROID_LOCAL_NETWORK_PERMISSION && before[p] !== true,
  );
  if (missing.length === 0) return current;
  const others = await invokeTauri<Record<string, boolean>>(REQUEST_PERMISSIONS, {
    ...args,
    permissions: missing,
  });
  return { ...current, ...(others ?? {}) };
}

/**
 * The asks that carry the LAN go out ONE AT A TIME (hub#1923). The Printing screen scans on open
 * and the owner taps «Find my printer» a moment later; run side by side, both read «not asked
 * yet» before the first answer was written and a second sheet stacked under the first. In a
 * queue, the one behind finds the answer already given and asks nothing.
 */
let localNetworkAsks: Promise<unknown> = Promise.resolve();

async function askForPermissions(args: Record<string, unknown> | undefined): Promise<unknown> {
  const requested = Array.isArray(args?.permissions) ? (args.permissions as string[]) : [];
  if (!requested.includes(ANDROID_LOCAL_NETWORK_PERMISSION)) {
    return invokeTauri(REQUEST_PERMISSIONS, args) as Promise<unknown>;
  }
  const turn = localNetworkAsks.then(() => askWithLocalNetworkPrimer(args, requested));
  // The queue survives a failed ask: the next one still gets its turn.
  localNetworkAsks = turn.catch(() => undefined);
  return turn;
}

/** Adaptador del shell Tauri al contrato `TauriBridge` del SDK (inyectable en tests). */
const tauriShell: TauriBridge = {
  invoke: (cmd, args) =>
    cmd === REQUEST_PERMISSIONS
      ? askForPermissions(args)
      : (invokeTauri(cmd, args) as Promise<unknown>),
  // El shell aún no emite eventos de hardware hacia la UI (los outcomes van al log del shell);
  // el contrato exige `listen`, así que se entrega una suscripción vacía.
  listen: async () => () => {},
};

/**
 * Le pone al escaneo bloqueado la frase que el usuario entiende (hub#338).
 *
 * El SDK ya distingue «no me dejan mirar» de «no hay nada», pero su mensaje está en inglés y es
 * para el log. El shell es quien tiene i18n, así que traduce el rechazo AQUÍ, una sola vez: todo
 * módulo que ya enseñaba `error.message` pasa a decir «dale permiso a la app» sin tocar una línea.
 *
 * Se parchea la instancia en vez de envolverla en otra clase porque la selección de transporte
 * (ADR-0159) se decide por `instanceof`, y un envoltorio la rompería.
 */
function withLocalisedDiscovery<T extends BridgeTransport>(transport: T): T {
  const scan = transport.discoverPrinters.bind(transport);
  transport.discoverPrinters = async () => {
    try {
      return await scan();
    } catch (e) {
      if (e instanceof LocalNetworkPermissionDeniedError) {
        throw new LocalNetworkPermissionDeniedError(
          e.permission,
          printerDiscoveryMessage('permission_denied'),
        );
      }
      throw e;
    }
  };
  return transport;
}

export type { BridgeStatus };

/**
 * **Is there hardware on THIS device?** — one question, one door: the modules' own (hub#524).
 *
 * There used to be two ways of asking it, and the screens used the one ADR-0196 walled up:
 * `GET localhost:12321/status`, the daemon hub#340 deleted. With nobody listening there the answer
 * was `{online:false}` **everywhere, always** — including inside `com.erplora.app`, where the
 * printer is plugged in and answering. And it failed **mute**: no error, no log, just a calm
 * sentence sending the owner off to install the app they already had open.
 *
 * Delegating to the transport makes the answer honest by construction: in a browser
 * `{online:false}` IS the truth (there is no hardware there — ADR-0196 §3), and in the installed
 * app it comes from `erplora_bridge_status`, the very call the `printing` module reads.
 *
 * It never rejects. Both `detect()` implementations resolve on purpose, because whoever asks is
 * painting a state — a rejection would take down the screen instead of filling in a status.
 */
export function detectPeripherals(timeoutMs?: number): Promise<BridgeStatus> {
  return makeBridgeTransport().detect(timeoutMs);
}

/** Transporte de hardware correcto para el entorno actual. */
export function makeBridgeTransport(): BridgeTransport {
  return withLocalisedDiscovery(
    isTauri()
      ? new IpcBridgeTransport(tauriShell)
      : // La frase se resuelve AQUÍ, en cada construcción del transporte, y no en el SDK: el
        // reparto es el mismo que en el escaneo bloqueado — el SDK pone el `code`, el shell (que
        // es quien tiene i18n) pone las palabras en el idioma activo del hub.
        new UnavailableBridgeTransport(hardwareUnavailableMessage()),
  );
}

/**
 * A system notice the shell can follow when it is tapped (hub#2305): `peripherals.notify` plus the
 * `id` the notification plugin hands back with the tap (`lib/notice-tap.ts` keeps where each id
 * leads). The shell's own door on purpose: the notices that lead somewhere are the shell's
 * (kitchen order, appointments, the bell's counters), and the module SDK's `notify` stays the
 * frozen kernel contract it is.
 *
 * Same rules as `IpcBridgeTransport.notify`: the notifications permission and only it asked first
 * (hub#758), best-effort all the way, and nothing in a browser — there is no system notice there.
 * An installed app older than this shell ignores the `id` and shows the notice all the same.
 */
export async function sendSystemNotice(title: string, body: string, id: number): Promise<void> {
  if (!isTauri()) return;
  try {
    await invokeTauri(REQUEST_PERMISSIONS, { permissions: [ANDROID_NOTIFICATIONS_PERMISSION] });
  } catch {
    // On desktop there is nothing to ask; on Android, the user said no. Carry on.
  }
  try {
    await invokeTauri('erplora_notify', { title, body, id });
  } catch (e) {
    console.warn('[notify] the platform could not show the notice', e);
  }
}
