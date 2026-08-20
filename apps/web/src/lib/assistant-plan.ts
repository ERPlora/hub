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

export interface AssistantPlan {
  tier?: string;
  used?: number;
  limit?: number;
}

/** El plan y el consumo del mes. `null` si no se puede leer — nunca un plan inventado: el consumo
 *  es un número con el que el dueño decide si paga, y enseñarlo mal es peor que no enseñarlo. */
export async function assistantPlan(): Promise<AssistantPlan | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/assistant/config`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    const body = (await res.json()) as {
      tier?: string;
      usage?: { messages_used?: number; messages_limit?: number };
    };
    return {
      tier: body.tier,
      used: body.usage?.messages_used,
      limit: body.usage?.messages_limit,
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
