// El plan del asistente de ESTE hub, y la puerta para ampliarlo (saas#1540).
//
// El asistente solo descubría su tier cuando ya lo había AGOTADO: el hub nunca leía
// `assistant/config/`, así que no conocía ni su plan, ni su consumo, ni qué se podía contratar.
// Con eso, quedarse sin mensajes solo podía presentarse como una avería — y el único momento de
// conversión del tier gratuito moría en «No se pudo contactar con el asistente».
//
// Las dos llamadas van por el RUNTIME (`/api/assistant/*`), nunca al SaaS desde el navegador: la
// credencial hub-scoped es secreto del runtime (ADR-0003) y el web app no tiene con qué firmarlas.
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Un plan de pago tal y como lo ofrece el SaaS (`available_paid_tiers`, ADR-0033). */
export interface AssistantTierOption {
  slug: string;
  name: string;
  /** Precio mensual como cadena decimal («44.99»), tal cual lo manda el SaaS: aquí no se
   *  redondea ni se convierte de moneda — el importe que se cobra lo fija el checkout. */
  priceMonthly?: string;
}

export interface AssistantPlan {
  tier?: string;
  used?: number;
  limit?: number;
  /** ISO-8601: cuándo vuelven los mensajes (saas#1540, hub#1183). */
  resetsAt?: string;
  /** Los planes que se pueden contratar HOY. Lista vacía = no hay nada que ofrecer; nunca
   *  `undefined`, para que la pantalla no tenga que distinguir «no llegó» de «no hay». */
  paidTiers: AssistantTierOption[];
}

/** El plan y el consumo del mes. `null` si no se puede leer — nunca un plan inventado: el consumo
 *  es un número con el que el dueño decide si paga, y enseñarlo mal es peor que no enseñarlo. */
export async function assistantPlan(): Promise<AssistantPlan | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/assistant/config`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    const body = (await res.json()) as {
      tier?: string;
      usage?: { messages_used?: number; messages_limit?: number; resets_at?: string };
      available_paid_tiers?: { slug?: string; name?: string; price_monthly?: string }[];
    };
    return {
      tier: body.tier,
      used: body.usage?.messages_used,
      limit: body.usage?.messages_limit,
      resetsAt: body.usage?.resets_at,
      // Los tiers que el SaaS ofrece de verdad (hub#1183). Antes el «ver planes» no enseñaba
      // ninguno: llevaba al checkout de `basic` a ciegas, así que un hub que necesitaba `pro`
      // compraba el más barato, lo agotaba igual y volvía. Un tier sin `slug` se descarta: sin
      // él no hay checkout que abrir, y ofrecer un botón que solo puede fallar es peor que no
      // ofrecerlo.
      paidTiers: (body.available_paid_tiers ?? [])
        .filter((t): t is { slug: string; name?: string; price_monthly?: string } => !!t?.slug)
        .map((t) => ({ slug: t.slug, name: t.name || t.slug, priceMonthly: t.price_monthly })),
    };
  } catch {
    return null;
  }
}

/** Abre el checkout del tier pedido y devuelve la url de Stripe. `null` si no llega ninguna: sin
 *  url no se navega a ninguna parte, que es mejor que llevar al usuario a una página vacía. */
export async function startAssistantCheckout(tier: string): Promise<string | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/assistant/checkout`, {
      method: 'POST',
      headers: { ...runtimeHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier_slug: tier, billing_interval: 'month' }),
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { checkout_url?: string };
    return body.checkout_url ?? null;
  } catch {
    return null;
  }
}
