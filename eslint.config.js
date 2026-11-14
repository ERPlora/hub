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
    files: ['frontend/**/*.{ts,vue}', 'base/frontend/**/*.{ts,vue}', 'apps/*/frontend/**/*.{ts,vue}'],
    rules: { 'no-restricted-globals': ['error', ...restricted] },
  },
  {
    // Functions small enough for a person to follow. What already broke a limit when it came in is in
    // eslint-suppressions.json, and `eslint` fails when one of those suppressions is no longer needed.
    rules: {
      complexity: ['error', 15],
      'max-depth': ['error', 4],
      'max-params': ['error', 3],
      'max-lines-per-function': ['error', { max: 50, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // In tests each describe is a function, and a test's helpers take what they need.
    // The extensions are spelled out: a pattern such as `**/*.test.*` would make ESLint lint the shell scripts too.
    files: ['**/tests/**', '**/e2e/**', '**/*.{test,spec}.{ts,tsx,js,mjs,cjs,vue}'],
    rules: { 'max-params': 'off', 'max-lines-per-function': 'off' },
  },
];
