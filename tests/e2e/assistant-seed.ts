// The model that answers a run of the assistant's QA with the real provider, and the seed that sets it on the stack's
// SaaS. With no QA_ANSWER_* variable it is production's: Qwen with OpenAI's model as the fallback. With QA_ANSWER_MODEL
// it is the model under test, on a provider of its own and without a fallback, so a turn it fails is scored as its
// failure and never as another model's answer. Pure, so Vitest proves it (assistant-seed.test.ts).
import { guardSaasDatabase, QA_STAFF_EMAIL } from './assistant-battery.ts';

type Env = Record<string, string | undefined>;

/** The OpenAI-compatible address of the Qwen workspace erplora.com answers with. */
export const QWEN_ADDRESS = 'https://ws-7mg25evt3ic2ow02.eu-central-1.maas.aliyuncs.com/compatible-mode/v1';
const ANSWER_MODEL = 'qwen3.7-plus';
const FALLBACK_MODEL = 'gpt-5.4-mini';
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
  /** The NAME of the variable that holds the key; the key itself is never copied anywhere. */
  keyEnv: string;
  model: string;
  /** USD per million tokens, or null when the run gives none (its cost is then unknown, not zero). */
  priceIn: number | null;
  priceOut: number | null;
  /** OpenAI's model in reserve, or null: a model under test answers alone. */
  fallback: string | null;
}

const PRODUCTION: AnswerChoice = {
  provider: 'qwen',
  name: 'Qwen',
  kind: 'openai',
  baseUrl: QWEN_ADDRESS,
  keyEnv: 'QA_QWEN_API_KEY',
  model: ANSWER_MODEL,
  priceIn: null,
  priceOut: null,
  fallback: FALLBACK_MODEL,
};

const given = (env: Env, name: string): string => env[name]?.trim() ?? '';

function price(env: Env, name: string): number {
  const value = Number(given(env, name));
  if (!given(env, name) || !Number.isFinite(value) || value < 0) {
    throw new Error(`${name} is a price in USD per million tokens, 0 or more (tests/e2e/README.md).`);
  }
  return value;
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
  };
}

/**
 * The SaaS side of the seed (`manage.py shell -c` in the stack's SaaS, DEBUG only): the real providers set through the
 * gateway's own operations, as ERPlora's staff does in the admin. `openai` (the services' provider: embeddings, and the
 * fallback model when there is one) by `assistant.credential.import` as the platform; the answering provider is added
 * as the admin's form adds it (validated; no operation adds a provider) and its key, model and the policy go through
 * `credential_save`, `model_select` and `policy_update` as a member of the staff. Its prices are typed on the model as
 * the admin does (no operation sets them). The keys come from the environment and are never printed; it prints the
 * models and the services' provider as one line of JSON.
 */
export const SEED_PY = `
import json, os
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from live.context import OperationContext, Scope
from assistant import services
from assistant.models import AIModel, AIProvider, AIProviderCredential
from assistant.schemas import CredentialImportIn, CredentialIn, ModelSelectIn, PolicyIn

if not settings.DEBUG:
    raise SystemExit("the real-provider seed only runs with DEBUG=True")
answer_secret = os.environ[os.environ["QA_SEED_KEY_ENV"]].strip()
openai_secret = os.environ["QA_OPENAI_API_KEY"].strip()
services.credential_import(
    services.platform_context(), CredentialImportIn(kind="openai", api_key=openai_secret, label="qa", force=True)
)
User = get_user_model()
staff = User.objects.filter(email="${QA_STAFF_EMAIL}").first()
if staff is None:
    staff = User.objects.create_user(email="${QA_STAFF_EMAIL}", password=None, is_staff=True, language="en")
staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="assistant"))
staff = User.objects.get(pk=staff.pk)
ctx = OperationContext(scope=Scope("user", str(staff.pk)), actor=staff, permissions=frozenset({"assistant.manage"}), language="en")
answering = AIProvider.objects.filter(slug=os.environ["QA_SEED_PROVIDER"]).first() or AIProvider(slug=os.environ["QA_SEED_PROVIDER"])
answering.name = os.environ["QA_SEED_PROVIDER_NAME"]
answering.kind = os.environ["QA_SEED_KIND"]
answering.base_url = os.environ["QA_SEED_BASE_URL"]
answering.is_enabled = True
answering.full_clean()
answering.save()
kept = AIProviderCredential.objects.filter(provider=answering, label="qa").first()
services.credential_save(ctx, CredentialIn(provider=answering.pk, id=kept.pk if kept else None, label="qa", is_active=True, api_key=answer_secret))


def chosen(provider, model):
    services.model_select(ctx, ModelSelectIn(provider=provider.pk, listed=[{"model_id": model, "display_name": model}], selected=[model]))
    return AIModel.objects.get(provider=provider, model_id=model)


answer = chosen(answering, os.environ["QA_SEED_MODEL"])
prices = {"price_input_per_1m": os.environ["QA_SEED_PRICE_IN"], "price_output_per_1m": os.environ["QA_SEED_PRICE_OUT"]}
prices = {field: Decimal(value) for field, value in prices.items() if value}
if prices:
    AIModel.objects.filter(pk=answer.pk).update(**prices)
openai = AIProvider.objects.get(slug="openai")
fallback = chosen(openai, os.environ["QA_SEED_FALLBACK_MODEL"]) if os.environ["QA_SEED_FALLBACK_MODEL"] else None
services.policy_update(ctx, PolicyIn(active_model=answer.pk, fallback_model=fallback.pk if fallback else None))
print(json.dumps({
    "model": answering.slug + "/" + answer.model_id,
    "fallback": "openai/" + fallback.model_id if fallback else "",
    "service": settings.ASSISTANT_SERVICE_PROVIDER,
}))
`;

const asText = (value: number | null): string => (value === null ? '' : String(value));

/** How the seed runs from the stack's SaaS checkout: on `saasDatabase`, the keys only in the environment. */
export function seedCommand(env: Env, saasDatabase: string): { file: string; args: string[]; env: Record<string, string> } {
  guardSaasDatabase(saasDatabase);
  const choice = answerChoice(env);
  for (const name of [choice.keyEnv, 'QA_OPENAI_API_KEY']) {
    if (!env[name]?.trim()) throw new Error(`${name} is not set: export it before a run with the real provider (tests/e2e/README.md).`);
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
    },
  };
}
