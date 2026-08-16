// **La placa por NFC: el segundo origen del MISMO camino** (hub#988, secuela de hub#658/#993).
//
// En un mostrador la tarjeta entra por un lector USB de 15 € que se comporta como un teclado, y la
// ráfaga la caza `badge-scanner.ts` por su velocidad. En una tablet no hay lector USB — y el lector
// lleva dentro del aparato desde el primer día, sin usar: una peluquería que trabaja con tablet
// sencillamente no podía dar de alta ni leer una tarjeta.
//
// La condición de diseño de la issue es **un solo camino de placa, dos orígenes**, y es lo que
// gobierna este fichero: el toque sale por `deliverBadge`, la misma puerta que la ráfaga del
// teclado. Ni el login, ni el diálogo de aprobación, ni la ficha de personal saben de dónde vino la
// tarjeta, y por eso ninguno de los tres tuvo que cambiar.
//
// Tres decisiones que no son obvias y que aquí sí lo son:
//
//  1. **Se lee por SONDEO, no por suscripción.** El comando abre el modo lector una ventana
//     acotada y contesta con la tarjeta o con nada. Un `invoke` que no vuelve nunca dejaría al
//     shell sin forma de enterarse de que la pantalla que esperaba la tarjeta ya se fue.
//  2. **Solo mientras alguien espera.** El modo lector es una radio. Abierto bajo una pantalla que
//     nadie mira, gasta la batería de una tablet que se pasa el día en el mostrador.
//  3. **`nfc_unavailable` PARA el bucle.** Es un hecho del hardware, no un fallo pasajero: en un
//     escritorio y en toda tablet sin chip, reintentarlo es un bucle infinito para todo el turno.
import { deliverBadge, onBadgeWaiting } from './badge-scanner';
import { invokeTauri } from './device';
import { ref } from 'vue';

/** El comando del shell que espera una tarjeta en el lector del propio aparato (hub#988). */
export const NFC_READ_COMMAND = 'erplora_nfc_read';

/**
 * Lo que contesta una lectura: un OBJETO, nunca la placa a pelo.
 *
 * `invokeTauri` devuelve `null` cuando **no hay shell** —un navegador—, así que una placa suelta
 * dejaría ese caso indistinguible de «la ventana se cerró sin tarjeta», y son lo contrario: uno
 * significa dejar de preguntar para siempre y el otro, volver a preguntar ya. Un objeto nunca es
 * `null`, así que la forma de la respuesta lleva la diferencia dentro.
 */
interface NfcReadOutcome {
  badge?: string | null;
}

/**
 * Cuánto tiene abierto el lector cada lectura.
 *
 * 15 s es lo que se tarda en pulsar «dar de alta» y encontrar la tarjeta en un bolsillo. El Kotlin
 * lo acota por su cuenta (`NfcBadge.clampTimeout`); esto es lo que se pide.
 */
const READ_WINDOW_MS = 15_000;

/** Lo que se espera tras un fallo que no sabemos nombrar, antes de volver a molestar a la radio. */
const BACKOFF_MS = 3_000;

/**
 * Suelo entre dos lecturas. Es un antibucle, no una pausa.
 *
 * El ritmo del sondeo lo pone el propio comando: una ventana dura segundos, así que reencadenar al
 * volver es correcto. Pero un shell que contestara **al instante** —una versión vieja sin el
 * comando, un plugin que devuelve nada— convertiría ese encadenamiento en un bucle cerrado que se
 * come el hilo. Una ventana que se cerró en menos de esto no llegó a ocurrir.
 */
const SPIN_GUARD_MS = 250;

/** Qué clase de negativa llegó del shell. Cada una lleva a hacer algo distinto. */
export type NfcRefusal = 'unavailable' | 'disabled' | 'random-uid' | 'failed';

/**
 * Lee la negativa venga en el envoltorio que venga.
 *
 * Tauri devuelve el `ShellError` ya serializado (`"nfc_disabled"`), pero un fallo del plugin puede
 * llegar además renderizado como `[código] - mensaje`. Los dos tienen que reconocerse, o el shell
 * se queda sondeando un aparato que no tiene lector.
 *
 * Y las tres se mantienen separadas a propósito: comprar un lector, encender el NFC y usar otra
 * tarjeta son tres cosas distintas que hacer. Un «no ha funcionado» común mandaría a los ajustes a
 * quien no tiene chip que encender (la lección de hub#338).
 */
export function classifyNfcRefusal(cause: unknown): NfcRefusal {
  const text = cause instanceof Error ? cause.message : String(cause ?? '');
  if (text.includes('nfc_unavailable')) return 'unavailable';
  if (text.includes('nfc_disabled')) return 'disabled';
  if (text.includes('nfc_random_uid')) return 'random-uid';
  return 'failed';
}

/**
 * ¿Puede este aparato leer una tarjeta acercándola?
 *
 * Lo consume la ficha de personal para decir «o acerca la tarjeta al aparato» **solo donde eso es
 * verdad**. No se deduce de `isTauri()`: eso lo prometería en cada instalación de escritorio. Se
 * enciende cuando una lectura real ha sido atendida, que es la única prueba que hay.
 */
export const nfcBadgeReady = ref(false);

/** Lo que el lector necesita del mundo, inyectable para poder probarlo sin un aparato. */
export interface NfcBadgeReaderDeps {
  /** El puente al shell. Por defecto `invokeTauri`, que contesta `null` en un navegador. */
  invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
  /** Entrega de la tarjeta. Por defecto, la puerta común de `badge-scanner`. */
  deliver?: (badge: string) => boolean;
  /** Una frase para el usuario, por su clave i18n. */
  notify?: (key: 'badge.nfcDisabled' | 'badge.nfcRandomUid') => void;
}

/**
 * Arranca el lector NFC de placas. Se llama **una vez**, desde el shell (`App.vue`), junto al
 * lector-teclado, y devuelve el desmontaje.
 *
 * No lee nada por su cuenta: se engancha a `onBadgeWaiting` y solo sondea mientras hay alguna
 * pantalla esperando una tarjeta.
 */
export function installNfcBadgeReader(deps: NfcBadgeReaderDeps = {}): () => void {
  // Sin ramificar por `isTauri()` a propósito: se llama desde el `setup` de `App.vue`, así que
  // preguntarlo AQUÍ obliga a todo test que monte el shell a conocer ese detalle. Y no hace falta:
  // `invokeTauri` ya contesta `null` donde no hay shell, y eso es exactamente lo que el bucle
  // necesita saber.
  const invoke =
    deps.invoke ?? ((cmd: string, args?: Record<string, unknown>) => invokeTauri<NfcReadOutcome>(cmd, args));
  const deliver = deps.deliver ?? deliverBadge;
  const notify = deps.notify ?? defaultNotify;

  let waiting = false;
  let running = false;
  /** El aparato no tiene lector: no se vuelve a preguntar en toda la sesión. */
  let impossible = false;
  /** «Enciende el NFC» se dice UNA vez, no en cada ventana que se cierra sin tarjeta. */
  let toldDisabled = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const later = (ms: number): void => {
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      void loop();
    }, ms);
  };

  async function loop(): Promise<void> {
    if (stopped || impossible || !waiting || running) return;
    running = true;
    const openedAt = Date.now();
    try {
      const outcome = (await invoke(NFC_READ_COMMAND, { timeoutMs: READ_WINDOW_MS })) as
        | NfcReadOutcome
        | null
        | undefined;
      running = false;
      // `null` = no hay shell (un navegador). No es una ventana vacía: es que no hay nada que
      // preguntar, ni ahora ni luego. La placa sigue entrando por el lector USB, igual que siempre.
      if (!outcome) {
        impossible = true;
        return;
      }
      // Una lectura atendida es la prueba de que el lector existe, la haya usado alguien o no.
      nfcBadgeReady.value = true;
      toldDisabled = false;
      const badge = outcome.badge;
      if (typeof badge === 'string' && badge && !deliver(badge)) {
        // La ventana seguía abierta cuando la última pantalla se fue: alguien acercó la tarjeta y
        // no la recogió nadie. No es un error —el gesto simplemente llegó tarde—, pero se dice en
        // la consola, porque «he pasado la tarjeta y no ha hecho nada» es justo lo que se reporta.
        console.warn('nfc: badge read with nobody waiting for it');
      }
      // Nada tocado es el desenlace NORMAL de cada ventana: darlo por final dejaría al usuario una
      // sola oportunidad de encontrar la tarjeta en el bolsillo. Se reencadena de inmediato para no
      // dejar la radio cerrada justo cuando alguien acerca la tarjeta — salvo que la ventana se
      // haya cerrado tan rápido que no llegara a abrirse (ver SPIN_GUARD_MS).
      if (!waiting || stopped) return;
      if (Date.now() - openedAt < SPIN_GUARD_MS) later(SPIN_GUARD_MS);
      else void loop();
      return;
    } catch (cause) {
      running = false;
      switch (classifyNfcRefusal(cause)) {
        case 'unavailable':
          // Un hecho del hardware. Ni se reintenta ni se anuncia: la placa sigue entrando por el
          // lector USB exactamente igual que antes, y decirlo sería un aviso sobre nada.
          impossible = true;
          nfcBadgeReady.value = false;
          return;
        case 'disabled':
          // Hay lector y está apagado: la única de las tres que el usuario puede arreglar, y la que
          // se repite en cada ventana hasta que lo haga. Se dice una vez y se sigue leyendo — en
          // cuanto toque el interruptor, la siguiente ventana lee.
          if (!toldDisabled) {
            toldDisabled = true;
            notify('badge.nfcDisabled');
          }
          break;
        case 'random-uid':
          // Darla de alta funcionaría… y no volvería a coincidir jamás: el empleado se queda fuera
          // con una tarjeta que demostrablemente funcionó el día que se configuró. Necesita otra
          // tarjeta, así que el lector se queda abierto para ella.
          notify('badge.nfcRandomUid');
          break;
        case 'failed':
          break;
      }
      if (waiting && !stopped) later(BACKOFF_MS);
    }
  }

  const stopWatching = onBadgeWaiting((isWaiting) => {
    waiting = isWaiting;
    if (!waiting) {
      // No se cancela la ventana en vuelo: el comando ya tiene su plazo y se cerrará solo. Lo que
      // se corta es la SIGUIENTE.
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      return;
    }
    // Una pantalla nueva merece que se le vuelva a decir si el NFC está apagado.
    toldDisabled = false;
    void loop();
  });

  return () => {
    stopped = true;
    stopWatching();
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
}

/** El aviso de verdad. Se importa perezosamente para no arrastrar Ionic a un test de lógica. */
function defaultNotify(key: 'badge.nfcDisabled' | 'badge.nfcRandomUid'): void {
  void (async () => {
    const [{ toastError }, { i18n }] = await Promise.all([import('./toast'), import('../i18n')]);
    await toastError(i18n.global.t(key));
  })();
}
