// @vitest-environment node
// The SPA runs in the browser, so the type project that checks it must not see Node's types: with them, a
// `process.env` in a page passes `pnpm typecheck` and throws in the browser. Until 2026-10-17 the root
// tsconfig.json held the SPA, its Vitest tests and the root config together, and `vite` and `vitest` brought
// @types/node into all of them. These tests read the projects the `typecheck` script checks (one per chained
// `vue-tsc` run), plant a `process.env` in SPA files in memory and prove the SPA's project reports it, and prove
// the split left nothing the single project checked out of `pnpm typecheck`, nor out of the project an editor
// opens each file in (the root tsconfig.json only references the projects).
import { readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));
// vue-tsc's own extension: without it a project lists no .vue file.
const VUE: ts.FileExtensionInfo[] = [{ extension: '.vue', isMixedContent: true, scriptKind: ts.ScriptKind.Deferred }];

const scripts: Record<string, string> = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).scripts;

/** A tsconfig parsed as `vue-tsc` (or an editor, with the same `options`) reads it. */
function parseConfig(config: string, options: ts.CompilerOptions, extensions: ts.FileExtensionInfo[]) {
  const parsed = ts.getParsedCommandLineOfConfigFile(
    config,
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
  if (!parsed) throw new Error(`${config} could not be read`);
  return parsed;
}

/** A `vue-tsc` run of a package.json script, parsed as that run reads its tsconfig. */
function vueTscProject(command: string, extensions: ts.FileExtensionInfo[]): ts.ParsedCommandLine {
  const [bin, ...args] = command.trim().split(/\s+/);
  const { options, fileNames, errors } = ts.parseCommandLine(args);
  if (bin !== 'vue-tsc' || errors.length || fileNames.length) {
    throw new Error(`"${command.trim()}" is not a plain vue-tsc run`);
  }
  const project = resolve(root, options.project ?? 'tsconfig.json');
  return parseConfig(project.endsWith('.json') ? project : join(project, 'tsconfig.json'), options, extensions);
}

/** Each `vue-tsc` run chained in the `typecheck` script. */
function typecheckProjects(extensions: ts.FileExtensionInfo[] = []): ts.ParsedCommandLine[] {
  return scripts.typecheck.split('&&').map((command) => vueTscProject(command, extensions));
}

const checked = (project: ts.ParsedCommandLine) => new Set(project.fileNames.map((file) => resolve(file)));

/**
 * The tsconfig an editor (tsserver) opens a file in: the nearest tsconfig.json above it if it holds the file,
 * else the first of its references that does; none means an inferred project, without this repo's settings
 * (no `bundler` resolution, so every `@erplora/ui/*` import shows as missing).
 */
function editorProject(file: string, parse: (config: string) => ts.ParsedCommandLine): string | undefined {
  for (let dir = dirname(file); ; dir = dirname(dir)) {
    const config = join(dir, 'tsconfig.json');
    if (ts.sys.fileExists(config)) {
      const parsed = parse(config);
      if (checked(parsed).has(file)) return config;
      const references = (parsed.projectReferences ?? []).map(ts.resolveProjectReferencePath);
      return references.find((reference) => checked(parse(reference)).has(file));
    }
    if (dir === root) return undefined;
  }
}

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

it('opens every file pnpm typecheck checks, in an editor, in a project that checks it', () => {
  const parsed = new Map<string, ts.ParsedCommandLine>();
  const parse = (config: string) => {
    if (!parsed.has(config)) parsed.set(config, parseConfig(config, {}, VUE));
    return parsed.get(config)!;
  };
  // Each file of this repo (the submodules are their own) with the tsconfigs of the runs that check it.
  const runs = new Map<string, Set<string>>();
  for (const project of typecheckProjects(VUE)) {
    for (const file of checked(project)) {
      if (/^(packages|node_modules)\//.test(relative(root, file))) continue;
      runs.set(file, (runs.get(file) ?? new Set()).add(resolve(project.options.configFilePath as string)));
    }
  }

  const lost = [...runs].filter(([file, configs]) => !configs.has(editorProject(file, parse) ?? ''));
  expect(runs.size).toBeGreaterThan(0);
  expect(lost.map(([file]) => relative(root, file))).toEqual([]);
}, 60_000);

/** What the image's `web` stage (Dockerfile) copies from the build context, as repo paths or globs. */
function webStageCopies(): string[] {
  const lines = readFileSync(join(root, 'Dockerfile'), 'utf8').split('\n');
  const start = lines.findIndex((line) => /^FROM\s.+\sAS\s+web\s*$/i.test(line));
  if (start < 0) throw new Error('the Dockerfile has no `web` stage');
  const end = lines.findIndex((line, index) => index > start && /^FROM\s/i.test(line));
  return lines
    .slice(start + 1, end < 0 ? undefined : end)
    .filter((line) => /^COPY\s/i.test(line) && !/\s--from=/.test(line))
    .flatMap((line) => {
      const args = line.trim().split(/\s+/).slice(1).filter((arg) => !arg.startsWith('--'));
      const target = args.pop();
      // Into the same place as in the repo: root files into `./`, a path into itself.
      const sameLayout = target === './' ? args.every((source) => !source.includes('/')) : args.length === 1 && args[0] === target;
      if (!sameLayout) throw new Error(`"${line.trim()}" does not keep the repo's layout`);
      return args;
    });
}

function copiedBy(sources: string[], file: string): boolean {
  return sources.some((source) =>
    source.includes('*')
      ? new RegExp(`^${source.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*')}$`).test(file)
      : file === source || file.startsWith(`${source}/`),
  );
}

/** A tsconfig and every tsconfig it extends or references, recursively. */
function configClosure(config: string, seen = new Set<string>()): Set<string> {
  if (seen.has(config)) return seen;
  seen.add(config);
  const { config: raw, error } = ts.readConfigFile(config, ts.sys.readFile);
  if (error) throw new Error(ts.flattenDiagnosticMessageText(error.messageText, '\n'));
  const extended: string[] = raw.extends === undefined ? [] : [raw.extends].flat();
  for (const parent of extended) {
    if (!parent.startsWith('.')) throw new Error(`${relative(root, config)} extends a package (${parent}): not followed`);
    configClosure(resolve(dirname(config), parent), seen);
  }
  for (const reference of raw.references ?? []) {
    configClosure(ts.resolveProjectReferencePath({ path: resolve(dirname(config), reference.path) }), seen);
  }
  return seen;
}

it('copies into the image every tsconfig Vite reads to compile the SPA: tsconfig.json and what it references or extends', () => {
  // Vite's esbuild takes each file's compiler options from the nearest tsconfig.json, through its references.
  // Without them it compiles class fields as constructor assignments (`useDefineForClassFields` false; the
  // base's target ES2022 makes it true): the image would ship a bundle `pnpm build` never built.
  const sources = webStageCopies();
  const configs = [...configClosure(join(root, 'tsconfig.json'))].map((config) => relative(root, config));

  expect(configs).toEqual(expect.arrayContaining(['tsconfig.json', 'tsconfig.app.json']));
  expect(configs.filter((config) => !copiedBy(sources, config))).toEqual([]);
});

it('type-checks the SPA in pnpm build too: the image runs it, and a run without its project checks nothing', () => {
  const spa = vueTscProject(scripts.build.split('&&')[0], VUE);
  const files = ['frontend/main.ts', 'apps/demo/frontend/routes.ts'].map((name) => join(root, name));

  expect(files.filter((file) => !checked(spa).has(file)).map((file) => relative(root, file))).toEqual([]);
  expect(spa.options.types).not.toContain('node');
});
