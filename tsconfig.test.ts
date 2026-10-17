// @vitest-environment node
// The SPA runs in the browser, so the type project that checks it must not see Node's types: with them, a
// `process.env` in a page passes `pnpm typecheck` and throws in the browser. Until 2026-10-17 the root
// tsconfig.json held the SPA, its Vitest tests and the root config together, and `vite` and `vitest` brought
// @types/node into all of them. These tests read the projects the `typecheck` script checks (one per chained
// `vue-tsc` run), plant a `process.env` in SPA files in memory and prove the SPA's project reports it, and prove
// the split left nothing the single project checked out of `pnpm typecheck`.
import { readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));
// vue-tsc's own extension: without it a project lists no .vue file.
const VUE: ts.FileExtensionInfo[] = [{ extension: '.vue', isMixedContent: true, scriptKind: ts.ScriptKind.Deferred }];

/** Each `vue-tsc` run chained in the `typecheck` script, parsed as that run reads its tsconfig. */
function typecheckProjects(extensions: ts.FileExtensionInfo[] = []): ts.ParsedCommandLine[] {
  const script: string = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).scripts.typecheck;
  return script.split('&&').map((command) => {
    const [bin, ...args] = command.trim().split(/\s+/);
    const { options, fileNames, errors } = ts.parseCommandLine(args);
    if (bin !== 'vue-tsc' || errors.length || fileNames.length) {
      throw new Error(`"${command.trim()}" in the typecheck script is not a plain vue-tsc run`);
    }
    const project = resolve(root, options.project ?? 'tsconfig.json');
    const parsed = ts.getParsedCommandLineOfConfigFile(
      project.endsWith('.json') ? project : join(project, 'tsconfig.json'),
      options,
      {
        ...ts.sys,
        onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
          throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'));
        },
      },
      undefined,
      undefined,
      extensions,
    );
    if (!parsed) throw new Error(`${project} could not be read`);
    return parsed;
  });
}

const checked = (project: ts.ParsedCommandLine) => new Set(project.fileNames.map((file) => resolve(file)));

it('reports a process.env planted in the shell entry and in an app of the SPA', () => {
  const planted = ['frontend/main.ts', 'apps/demo/frontend/routes.ts'].map((name) => join(root, name));
  const spa = typecheckProjects().find((candidate) => checked(candidate).has(planted[0]));
  if (!spa) throw new Error('no project of the typecheck script holds frontend/main.ts');
  expect(planted.filter((file) => !checked(spa).has(file)).map((file) => relative(root, file))).toEqual([]);

  const host = ts.createCompilerHost(spa.options);
  const readFile = host.readFile.bind(host);
  host.readFile = (file) => {
    const text = readFile(file);
    return planted.includes(resolve(file)) ? `${text}\nexport const planted = process.env.VITE_DEV_PORT;\n` : text;
  };
  const program = ts.createProgram({ rootNames: spa.fileNames, options: spa.options, host });

  const errors = planted.flatMap((file) => {
    const source = program.getSourceFile(file);
    if (!source) throw new Error(`${relative(root, file)} is not in the program`);
    return program.getSemanticDiagnostics(source).map((diagnostic) => [relative(root, file), diagnostic.code]);
  });
  // TS2591: Cannot find name 'process' (Node's types are not in the project's `types`).
  expect(errors).toEqual([
    ['frontend/main.ts', 2591],
    ['apps/demo/frontend/routes.ts', 2591],
  ]);
}, 60_000);

it('keeps in pnpm typecheck every file the single tsconfig.json checked: the SPA, its tests and the root config', () => {
  const single = ts.parseJsonConfigFileContent(
    {
      compilerOptions: { allowJs: true, resolveJsonModule: true },
      include: ['frontend/**/*', 'apps/*/frontend/**/*', '*.ts', '*.js'],
      exclude: ['node_modules', 'frontend/dist'],
    },
    ts.sys,
    root,
    undefined,
    undefined,
    undefined,
    VUE,
  ).fileNames.map((file) => resolve(file));
  const files = new Set(typecheckProjects(VUE).flatMap((project) => [...checked(project)]));

  expect(single.filter((file) => file.endsWith('.vue')).length).toBeGreaterThan(0);
  expect(single.filter((file) => file.endsWith('.test.ts')).length).toBeGreaterThan(0);
  expect(single.filter((file) => !files.has(file)).map((file) => relative(root, file))).toEqual([]);
}, 60_000);
