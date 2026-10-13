// Lint of hub-next's TypeScript: the same presets as packages/ui (its config is not exported), and
// the rule that keeps TypeScript thin: the entry and the apps reach the server only through the SDK.
import pluginVue from 'eslint-plugin-vue';
import tseslint from 'typescript-eslint';

const restricted = ['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'].map((name) => ({
  name,
  message: 'Network access goes through the SDK (@erplora/ui/sdk).',
}));

export default [
  {
    ignores: [
      'frontend/dist/**',
      'staticfiles/**',
      'node_modules/**',
      'coverage/**',
      // The uv virtualenv (Django's admin JavaScript).
      '.venv/**',
      // live and ui submodules, linted in their repos.
      'packages/**',
    ],
  },
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    // `slot="start|end|icon-only"` on ion-* (and on HubIcon, which renders ion-icon) is the Web
    // Components slot of Ionic, not Vue 2's deprecated slot syntax.
    files: ['**/*.vue'],
    rules: { 'vue/no-deprecated-slot-attribute': ['error', { ignore: ['/^ion-/', 'HubIcon'] }] },
  },
  {
    files: ['frontend/**/*.{ts,vue}', 'apps/*/frontend/**/*.{ts,vue}'],
    rules: { 'no-restricted-globals': ['error', ...restricted] },
  },
];
