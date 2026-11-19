// @vitest-environment node
// The model that answers a run with the real provider (`answerChoice`, from the QA_ANSWER_* variables) and the seed
// that sets it on the stack's SaaS (`seedCommand`, `SEED_PY`). The seed itself only runs with QA_REAL_PROVIDER=1.
import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { QA_STAFF_EMAIL } from './assistant-battery';
import { answerChoice, QWEN_ADDRESS, SEED_PY, seedCommand } from './assistant-seed';

const KEYS = { QA_QWEN_API_KEY: 'sk-qwen-secret', QA_OPENAI_API_KEY: 'sk-openai-secret', PATH: '/bin' };
const COMPARED = {
  QA_ANSWER_KIND: 'anthropic',
  QA_ANSWER_MODEL: 'claude-test-model',
  QA_ANSWER_KEY_ENV: 'QA_ANTHROPIC_API_KEY',
  QA_ANSWER_PRICE_IN: '3',
  QA_ANSWER_PRICE_OUT: '15.5',
};

describe('answerChoice', () => {
  it('answers with Qwen and keeps the OpenAI fallback when no QA_ANSWER_* is set, as production does', () => {
    expect(answerChoice({ PATH: '/bin' })).toEqual({
      provider: 'qwen',
      name: 'Qwen',
      kind: 'openai',
      baseUrl: QWEN_ADDRESS,
      keyEnv: 'QA_QWEN_API_KEY',
      model: 'qwen3.7-plus',
      priceIn: null,
      priceOut: null,
      fallback: 'gpt-5.4-mini',
    });
  });

  it('answers with the model under test on a provider of its own, without a fallback, when QA_ANSWER_MODEL is set', () => {
    expect(answerChoice({ ...COMPARED, QA_ANSWER_BASE_URL: 'https://models.example.com/v1' })).toEqual({
      provider: 'qa-answer',
      name: 'QA answer',
      kind: 'anthropic',
      baseUrl: 'https://models.example.com/v1',
      keyEnv: 'QA_ANTHROPIC_API_KEY',
      model: 'claude-test-model',
      priceIn: 3,
      priceOut: 15.5,
      fallback: null,
    });
  });

  it('leaves the address to the kind when QA_ANSWER_BASE_URL is not set', () => {
    expect(answerChoice(COMPARED).baseUrl).toBe('');
  });

  it('names every variable a model under test is missing', () => {
    expect(() => answerChoice({ QA_ANSWER_MODEL: 'm' })).toThrow(/QA_ANSWER_KIND, QA_ANSWER_KEY_ENV, QA_ANSWER_PRICE_IN, QA_ANSWER_PRICE_OUT/);
  });

  it('refuses the other variables without QA_ANSWER_MODEL instead of answering with Qwen', () => {
    expect(() => answerChoice({ QA_ANSWER_KIND: 'openai' })).toThrow(/QA_ANSWER_MODEL/);
  });

  it('refuses a kind the gateway does not speak and a price that is not a number of USD', () => {
    expect(() => answerChoice({ ...COMPARED, QA_ANSWER_KIND: 'mistral' })).toThrow(/openai, anthropic, gemini, deepseek/);
    expect(() => answerChoice({ ...COMPARED, QA_ANSWER_PRICE_IN: 'cheap' })).toThrow(/QA_ANSWER_PRICE_IN/);
    expect(() => answerChoice({ ...COMPARED, QA_ANSWER_PRICE_OUT: '-1' })).toThrow(/QA_ANSWER_PRICE_OUT/);
  });

  it('refuses a key variable that is no variable name', () => {
    expect(() => answerChoice({ ...COMPARED, QA_ANSWER_KEY_ENV: 'sk-a-real-key' })).toThrow(/QA_ANSWER_KEY_ENV/);
  });
});

describe('seedCommand', () => {
  it('runs the seed in the SaaS on its database with the keys in the environment, never in the arguments', () => {
    const command = seedCommand(KEYS, 'saas_e2e_8895');
    expect(command.file).toBe('uv');
    expect(command.args.slice(0, 5)).toEqual(['run', 'python', 'manage.py', 'shell', '-c']);
    expect(command.args.join(' ')).not.toMatch(/sk-qwen-secret|sk-openai-secret/);
    expect(command.env).toMatchObject({ DB_NAME: 'saas_e2e_8895', ASSISTANT_SERVICE_PROVIDER: 'openai', ...KEYS });
  });

  it('seeds Qwen with the OpenAI fallback by default, without prices', () => {
    expect(seedCommand(KEYS, 'saas_e2e_8895').env).toMatchObject({
      QA_SEED_PROVIDER: 'qwen',
      QA_SEED_PROVIDER_NAME: 'Qwen',
      QA_SEED_KIND: 'openai',
      QA_SEED_BASE_URL: QWEN_ADDRESS,
      QA_SEED_KEY_ENV: 'QA_QWEN_API_KEY',
      QA_SEED_MODEL: 'qwen3.7-plus',
      QA_SEED_PRICE_IN: '',
      QA_SEED_PRICE_OUT: '',
      QA_SEED_FALLBACK_MODEL: 'gpt-5.4-mini',
    });
  });

  it('seeds the model under test with its prices and no fallback, its key read from the variable named', () => {
    const env = { ...COMPARED, QA_ANTHROPIC_API_KEY: 'sk-ant-secret', QA_OPENAI_API_KEY: 'sk-openai-secret' };
    const command = seedCommand(env, 'saas_e2e_8895');
    expect(command.env).toMatchObject({
      QA_SEED_PROVIDER: 'qa-answer',
      QA_SEED_KIND: 'anthropic',
      QA_SEED_BASE_URL: '',
      QA_SEED_KEY_ENV: 'QA_ANTHROPIC_API_KEY',
      QA_SEED_MODEL: 'claude-test-model',
      QA_SEED_PRICE_IN: '3',
      QA_SEED_PRICE_OUT: '15.5',
      QA_SEED_FALLBACK_MODEL: '',
    });
    expect(command.args.join(' ')).not.toContain('sk-ant-secret');
  });

  it('refuses without a key, naming the variable and never a value', () => {
    expect(() => seedCommand({ QA_OPENAI_API_KEY: 'sk-openai-secret' }, 'saas_e2e_8895')).toThrow(/QA_QWEN_API_KEY/);
    expect(() => seedCommand({ QA_QWEN_API_KEY: 'sk-qwen-secret' }, 'saas_e2e_8895')).toThrow(/QA_OPENAI_API_KEY/);
    expect(() => seedCommand({ ...COMPARED, QA_OPENAI_API_KEY: 'sk-openai-secret' }, 'saas_e2e_8895')).toThrow(/QA_ANTHROPIC_API_KEY/);
  });

  it('refuses the shared SaaS database and any database that is not an e2e one', () => {
    expect(() => seedCommand(KEYS, 'saas')).toThrow(/shared SaaS database «saas»/);
    expect(() => seedCommand(KEYS, 'saas_dev')).toThrow(/not an e2e database/);
  });
});

describe('SEED_PY', () => {
  it('sets the providers only through the SaaS operations, prints no key and is Python', () => {
    for (const op of ['credential_import', 'credential_save', 'model_select', 'policy_update']) expect(SEED_PY).toContain(`services.${op}(`);
    expect(SEED_PY).not.toMatch(/print\([^)]*(secret|key|KEY)/);
    expect(SEED_PY).not.toMatch(/cursor|raw\(/);
    const parsed = spawnSync('python3', ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: SEED_PY, encoding: 'utf8' });
    expect(parsed.status, parsed.stderr).toBe(0);
  });

  it('reads the answering model from the seed variables, validates its provider and keeps its key labelled qa', () => {
    for (const name of ['PROVIDER', 'PROVIDER_NAME', 'KIND', 'BASE_URL', 'KEY_ENV', 'MODEL', 'PRICE_IN', 'PRICE_OUT', 'FALLBACK_MODEL']) {
      expect(SEED_PY).toContain(`os.environ["QA_SEED_${name}"]`);
    }
    expect(SEED_PY).toContain('full_clean()');
    expect(SEED_PY).toContain(`"${QA_STAFF_EMAIL}"`);
    expect(SEED_PY.match(/label="qa"/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it('leaves the fallback empty when none is asked, so a failing model is never answered for', () => {
    expect(SEED_PY).toContain('fallback_model=fallback.pk if fallback else None');
  });
});
