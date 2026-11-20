// The model that answers a run of the assistant's QA with the real provider, and the seed that sets it on the stack's
// SaaS. With no QA_ANSWER_* variable it is production's: Qwen with OpenAI's model as the fallback. With QA_ANSWER_MODEL
// it is the model under test, on a provider of its own and without a fallback, so a turn it fails is scored as its
// failure and never as another model's answer. The SaaS reads each provider's key from its own environment, so the
// keys stay in the shell that starts the stack and never reach its database. Pure, so Vitest proves it
// (assistant-seed.test.ts).
import { guardSaasDatabase, QA_STAFF_EMAIL } from './assistant-battery.ts';

type Env = Record<string, string | undefined>;

/** The OpenAI-compatible address of the Qwen workspace erplora.com answers with. */
export const QWEN_ADDRESS = 'https://ws-7mg25evt3ic2ow02.eu-central-1.maas.aliyuncs.com/compatible-mode/v1';
const ANSWER_MODEL = 'qwen3.7-plus';
const FALLBACK_MODEL = 'gpt-5.4-mini';
/** The variable the SaaS reads OpenAI's key from: the documentation search's embeddings and the fallback model. */
const OPENAI_KEY = 'OPENAI_API_KEY';
/** The APIs the gateway speaks (`assistant.models.AIProvider.Kind`). */
const KINDS = ['openai', 'anthropic', 'gemini', 'deepseek'];
const REQUIRED = ['QA_ANSWER_KIND', 'QA_ANSWER_KEY_ENV', 'QA_ANSWER_PRICE_IN', 'QA_ANSWER_PRICE_OUT'];
const VARIABLE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export interface AnswerChoice {
  /** The provider's identifier in the SaaS: `qwen`, or `qa-answer` for a model under test. */
  provider: string;
  name: string;
  kind: string;
  /** Empty: the kind's own address. */
  baseUrl: string;
  /** The NAME of the variable of the SaaS's environment the provider reads its key from; the key is never copied. */
  keyEnv: string;
  model: string;
  /** USD per million tokens, or null when the run gives none (its cost is then unknown, not zero). */
  priceIn: number | null;
  priceOut: number | null;
  /** OpenAI's model in reserve, or null: a model under test answers alone. */
  fallback: string | null;
  /** Whether it sees images (`AIModel.supports_vision`): only when QA_ANSWER_VISION=1 says so. */
  vision: boolean;
}

const PRODUCTION: AnswerChoice = {
  provider: 'qwen',
  name: 'Qwen',
  kind: 'openai',
  baseUrl: QWEN_ADDRESS,
  keyEnv: 'DASHSCOPE_API_KEY',
  model: ANSWER_MODEL,
  priceIn: null,
  priceOut: null,
  fallback: FALLBACK_MODEL,
  vision: false,
};

const given = (env: Env, name: string): string => env[name]?.trim() ?? '';

function price(env: Env, name: string): number {
  const value = Number(given(env, name));
  if (!given(env, name) || !Number.isFinite(value) || value < 0) {
    throw new Error(`${name} is a price in USD per million tokens, 0 or more (tests/e2e/README.md).`);
  }
  return value;
}

function vision(env: Env): boolean {
  const value = given(env, 'QA_ANSWER_VISION');
  if (value && value !== '1' && value !== '0') throw new Error('QA_ANSWER_VISION is 1 or 0: whether the model under test sees images.');
  return value === '1';
}

/** The model that answers the run, from the QA_ANSWER_* variables (tests/e2e/README.md, «Comparar modelos»). */
export function answerChoice(env: Env): AnswerChoice {
  const model = given(env, 'QA_ANSWER_MODEL');
  if (!model) {
    const stray = Object.keys(env).filter((name) => name.startsWith('QA_ANSWER_') && given(env, name));
    if (stray.length) throw new Error(`${stray.join(', ')} without QA_ANSWER_MODEL: name the model under test, or unset them.`);
    return { ...PRODUCTION };
  }
  const missing = REQUIRED.filter((name) => !given(env, name));
  if (missing.length) throw new Error(`a model under test needs ${missing.join(', ')} (tests/e2e/README.md).`);
  const kind = given(env, 'QA_ANSWER_KIND');
  if (!KINDS.includes(kind)) throw new Error(`QA_ANSWER_KIND «${kind}» is none of ${KINDS.join(', ')}.`);
  const keyEnv = given(env, 'QA_ANSWER_KEY_ENV');
  if (!VARIABLE.test(keyEnv)) throw new Error('QA_ANSWER_KEY_ENV is the NAME of the variable that holds the key, not the key.');
  return {
    provider: 'qa-answer',
    name: 'QA answer',
    kind,
    baseUrl: given(env, 'QA_ANSWER_BASE_URL'),
    keyEnv,
    model,
    priceIn: price(env, 'QA_ANSWER_PRICE_IN'),
    priceOut: price(env, 'QA_ANSWER_PRICE_OUT'),
    fallback: null,
    vision: vision(env),
  };
}

/**
 * The SaaS side of the seed (`manage.py shell -c` in the stack's SaaS, DEBUG only): the real providers, as ERPlora's
 * staff sets them in the admin. The answering provider and `openai` (the services' provider: embeddings, and the
 * fallback model when there is one) are added as the admin's form adds them (validated; no operation adds a
 * provider), each naming the variable of the SaaS's environment it reads its key from. Their models and the policy go
 * through `model_select` and `policy_update` as a member of the staff, and the prices are typed on the model as the
 * admin does (no operation sets them). It never reads nor writes a key; it prints the models and the services'
 * provider as one line of JSON.
 */
export const SEED_PY = `
import json, os
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from live.context import OperationContext, Scope
from assistant.models import AIModel, AIProvider
from assistant.schemas import ModelSelectIn, PolicyIn
from assistant.services.model_choice import model_select, policy_update

if not settings.DEBUG:
    raise SystemExit("the real-provider seed only runs with DEBUG=True")
User = get_user_model()
staff = User.objects.filter(email="${QA_STAFF_EMAIL}").first()
if staff is None:
    staff = User.objects.create_user(email="${QA_STAFF_EMAIL}", password=None, is_staff=True, language="en")
staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="assistant"))
staff = User.objects.get(pk=staff.pk)
ctx = OperationContext(scope=Scope("user", str(staff.pk)), actor=staff, permissions=frozenset({"assistant.manage"}), language="en")


def provider(slug, name, kind, base_url, key_variable):
    found = AIProvider.objects.filter(slug=slug).first() or AIProvider(slug=slug)
    found.name, found.kind, found.base_url, found.key_variable = name, kind, base_url, key_variable
    found.is_enabled = True
    found.full_clean()
    found.save()
    return found


def chosen(provider, model):
    model_select(ctx, ModelSelectIn(provider=provider.pk, listed=[{"model_id": model, "display_name": model}], selected=[model]))
    return AIModel.objects.get(provider=provider, model_id=model)


answering = provider(
    os.environ["QA_SEED_PROVIDER"],
    os.environ["QA_SEED_PROVIDER_NAME"],
    os.environ["QA_SEED_KIND"],
    os.environ["QA_SEED_BASE_URL"],
    os.environ["QA_SEED_KEY_ENV"],
)
openai = provider("openai", "OpenAI", "openai", "", "${OPENAI_KEY}")


answer = chosen(answering, os.environ["QA_SEED_MODEL"])
prices = {"price_input_per_1m": os.environ["QA_SEED_PRICE_IN"], "price_output_per_1m": os.environ["QA_SEED_PRICE_OUT"]}
prices = {field: Decimal(value) for field, value in prices.items() if value}
if prices:
    AIModel.objects.filter(pk=answer.pk).update(**prices)
AIModel.objects.filter(pk=answer.pk).update(supports_vision=os.environ["QA_SEED_VISION"] == "1")
fallback = chosen(openai, os.environ["QA_SEED_FALLBACK_MODEL"]) if os.environ["QA_SEED_FALLBACK_MODEL"] else None
policy_update(ctx, PolicyIn(active_model=answer.pk, fallback_model=fallback.pk if fallback else None))
print(json.dumps({
    "model": answering.slug + "/" + answer.model_id,
    "fallback": "openai/" + fallback.model_id if fallback else "",
    "service": settings.ASSISTANT_SERVICE_PROVIDER,
}))
`;

const asText = (value: number | null): string => (value === null ? '' : String(value));

/** The keys of a run, read from `env` to be taken out of everything it writes: Qwen's, OpenAI's and a model under
 *  test's. */
export function seedSecrets(env: Env): string[] {
  return [PRODUCTION.keyEnv, OPENAI_KEY, given(env, 'QA_ANSWER_KEY_ENV')].map((name) => given(env, name)).filter(Boolean);
}

/** How the seed runs from the stack's SaaS checkout, on `saasDatabase`. It refuses a run whose shell lacks a key the
 *  run needs: the stack's SaaS, started from that same shell, reads them from its environment. */
export function seedCommand(env: Env, saasDatabase: string): { file: string; args: string[]; env: Record<string, string> } {
  guardSaasDatabase(saasDatabase);
  const choice = answerChoice(env);
  for (const name of new Set([choice.keyEnv, OPENAI_KEY])) {
    if (!given(env, name)) {
      throw new Error(`${name} is not set: export it, also for the stack's SaaS, before a run with the real provider (tests/e2e/README.md).`);
    }
  }
  const base = Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));
  return {
    file: 'uv',
    args: ['run', 'python', 'manage.py', 'shell', '-c', SEED_PY],
    env: {
      ...base,
      DB_NAME: saasDatabase,
      ASSISTANT_SERVICE_PROVIDER: 'openai',
      QA_SEED_PROVIDER: choice.provider,
      QA_SEED_PROVIDER_NAME: choice.name,
      QA_SEED_KIND: choice.kind,
      QA_SEED_BASE_URL: choice.baseUrl,
      QA_SEED_KEY_ENV: choice.keyEnv,
      QA_SEED_MODEL: choice.model,
      QA_SEED_PRICE_IN: asText(choice.priceIn),
      QA_SEED_PRICE_OUT: asText(choice.priceOut),
      QA_SEED_FALLBACK_MODEL: choice.fallback ?? '',
      QA_SEED_VISION: choice.vision ? '1' : '0',
    },
  };
}
