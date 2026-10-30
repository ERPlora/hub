// @vitest-environment node
// The SPA runs in the browser, so the type project that checks it must not see Node's types: with them, a
// `process.env` in a page passes `pnpm typecheck` and throws in the browser. Until 2026-10-17 the root
// tsconfig.json held the SPA, its Vitest tests and the root config together, and `vite` and `vitest` brought
// @types/node into all of them. These tests read the projects the `typecheck` script checks (one per chained
// `vue-tsc` run), plant a `process.env` in SPA files in memory and prove the SPA's project reports it, and prove
// the split left nothing the single project checked out of `pnpm typecheck`, nor out of the project an editor
// opens each file in (the root tsconfig.json only references the projects).
import { existsSync, globSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { beforeAll, expect, it, vi } from 'vitest';

import viteConfig from './vite.config';

const root = dirname(fileURLToPath(import.meta.url));
// vue-tsc's own extension: without it a project lists no .vue file.
const VUE: ts.FileExtensionInfo[] = [{ extension: '.vue', isMixedContent: true, scriptKind: ts.ScriptKind.Deferred }];

const scripts: Record<string, string> = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).scripts;

/** Each walk of the repo for a tsconfig's files, once per run: a `vue-tsc` run and an editor read the same tsconfigs. */
const walks = new Map<string, string[]>();

const configHost: ts.ParseConfigFileHost = {
  ...ts.sys,
  readDirectory: (...walk: Parameters<typeof ts.sys.readDirectory>) => {
    const key = JSON.stringify(walk);
    if (!walks.has(key)) walks.set(key, ts.sys.readDirectory(...walk));
    return walks.get(key)!;
  },
  onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
    throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'));
  },
};

/** Each tsconfig parsed, by the options it was read with (see the `beforeAll`). */
const parsedConfigs = new Map<string, ts.ParsedCommandLine>();

/** A tsconfig parsed as `vue-tsc` (or an editor, with the same `options`) reads it, its .vue files included, once per run. */
function parseConfig(config: string, options: ts.CompilerOptions): ts.ParsedCommandLine {
  const key = JSON.stringify([config, options]);
  const known = parsedConfigs.get(key);
  if (known) return known;
  const parsed = ts.getParsedCommandLineOfConfigFile(config, options, configHost, undefined, undefined, VUE);
  if (!parsed) throw new Error(`${config} could not be read`);
  parsedConfigs.set(key, parsed);
  return parsed;
}

/** A `vue-tsc` run of a package.json script, parsed as that run reads its tsconfig. */
function vueTscProject(command: string): ts.ParsedCommandLine {
  const [bin, ...args] = command.trim().split(/\s+/);
  const { options, fileNames, errors } = ts.parseCommandLine(args);
  if (bin !== 'vue-tsc' || errors.length || fileNames.length) {
    throw new Error(`"${command.trim()}" is not a plain vue-tsc run`);
  }
  const project = resolve(root, options.project ?? 'tsconfig.json');
  return parseConfig(project.endsWith('.json') ? project : join(project, 'tsconfig.json'), options);
}

/** Each `vue-tsc` run chained in the `typecheck` script. */
function typecheckProjects(): ts.ParsedCommandLine[] {
  return scripts.typecheck.split('&&').map(vueTscProject);
}

/** The files of each project, listed once (an editor's lookup asks for them for each file of the repo). */
const checkedFiles = new WeakMap<ts.ParsedCommandLine, Set<string>>();

function checked(project: ts.ParsedCommandLine): Set<string> {
  let files = checkedFiles.get(project);
  if (!files) checkedFiles.set(project, (files = new Set(project.fileNames.map((file) => resolve(file)))));
  return files;
}

/** A tsconfig as an editor reads it: without a command line. */
const editorConfig = (config: string) => parseConfig(config, {});

/**
 * The tsconfig an editor (tsserver) opens a file in: the nearest tsconfig.json above it if it holds the file,
 * else the first of its references that does; none means an inferred project, without this repo's settings
 * (no `bundler` resolution, so every `@erplora/ui/*` import shows as missing).
 */
function editorProject(file: string): string | undefined {
  for (let dir = dirname(file); ; dir = dirname(dir)) {
    const config = join(dir, 'tsconfig.json');
    if (ts.sys.fileExists(config)) {
      const parsed = editorConfig(config);
      if (checked(parsed).has(file)) return config;
      const references = (parsed.projectReferences ?? []).map(ts.resolveProjectReferencePath);
      return references.find((reference) => checked(editorConfig(reference)).has(file));
    }
    if (dir === root) return undefined;
  }
}

/** A file of this repo (the submodules are their own, as are the dependencies). */
const ownFile = (file: string) => !/^(packages|node_modules)\//.test(relative(root, file));

/**
 * Every project these tests read: each `vue-tsc` run of the `typecheck` and `build` scripts, and each tsconfig an
 * editor opens their files in (tsconfig.json, whose references are those runs', or the run's own, as tests/e2e's).
 */
function projectsRead(): ts.ParsedCommandLine[] {
  const runs = [...typecheckProjects(), vueTscProject(scripts.build.split('&&')[0])];
  const configs = [join(root, 'tsconfig.json'), ...runs.map((run) => run.options.configFilePath as string)];
  return [...runs, ...configs.map(editorConfig)];
}

// Parsing a project walks the repo for its files, and the tests read the same projects again and again (each run of
// the typecheck and build scripts, and an editor's); listing a project's files resolves each of them, and the editor's
// lookup asked for them once per file of the repo. At rest that is 1.3 s and 160 garbage collections; under load what
// counts is the opening of files and folders, whose time is the machine's (1,687 files read in 38–50 s with 15 busy
// cores, 0.1–0.3 s at rest): a run opened 2,588 folders, 930 of them in one test, and a test of this file took 118 s
// beside `pnpm test` at load ~30 (2026-10-29). Here, once per run (465 folders), with the limit of the guardrails that
// read the whole tree; each test keeps its own work (the planted program, the build's reads) and its 60 s (2026-10-30).
beforeAll(() => {
  for (const project of projectsRead()) checked(project);
}, 60_000);

it('reads the projects the warm-up parsed: no test walks the repo for a project, nor lists its files, again', () => {
  const walk = vi.spyOn(ts.sys, 'readDirectory');
  try {
    const projects = projectsRead();
    for (const project of projects) {
      const file = [...checked(project)].find(ownFile);
      if (file) editorProject(file);
    }
    // Another command line over a tsconfig already read lists the same files: the walk is not repeated.
    vueTscProject('vue-tsc --noEmit --strict -p tsconfig.app.json');
    const again = projectsRead();

    expect(walk).not.toHaveBeenCalled();
    // Read again, each is the project parsed before, with the list of its files made before.
    expect(projects.filter((project, index) => again[index] !== project || checked(again[index]) !== checked(project)).length).toBe(0);
  } finally {
    walk.mockRestore();
  }
});

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
  // TypeScript reads no .vue file (vue-tsc's own): the program takes the rest of the project.
  const rootNames = spa.fileNames.filter((file) => !file.endsWith('.vue'));
  const program = ts.createProgram({ rootNames, options: spa.options, host });

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
      include: ['frontend/**/*', 'base/frontend/**/*', 'apps/*/frontend/**/*', '*.ts', '*.js'],
      exclude: ['node_modules', 'frontend/dist'],
    },
    ts.sys,
    root,
    undefined,
    undefined,
    undefined,
    VUE,
  ).fileNames.map((file) => resolve(file));
  const files = new Set(typecheckProjects().flatMap((project) => [...checked(project)]));

  expect(single.filter((file) => file.endsWith('.vue')).length).toBeGreaterThan(0);
  expect(single.filter((file) => file.endsWith('.test.ts')).length).toBeGreaterThan(0);
  expect(single.filter((file) => !files.has(file)).map((file) => relative(root, file))).toEqual([]);
}, 60_000);

it('opens every file pnpm typecheck checks, in an editor, in a project that checks it', () => {
  // Each file of this repo (the submodules are their own) with the tsconfigs of the runs that check it.
  const runs = new Map<string, Set<string>>();
  for (const project of typecheckProjects()) {
    for (const file of [...checked(project)].filter(ownFile)) {
      runs.set(file, (runs.get(file) ?? new Set()).add(resolve(project.options.configFilePath as string)));
    }
  }

  const lost = [...runs].filter(([file, configs]) => !configs.has(editorProject(file) ?? ''));
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
  const spa = vueTscProject(scripts.build.split('&&')[0]);
  const files = ['frontend/main.ts', 'apps/demo/frontend/routes.ts'].map((name) => join(root, name));

  expect(files.filter((file) => !checked(spa).has(file)).map((file) => relative(root, file))).toEqual([]);
  expect(spa.options.types).not.toContain('node');
});

/** Relative paths a source names: `import … from`, `export … from`, a bare `import '…'` and `import('…')`. */
const SPECIFIERS = [
  /\bimport\s+(?:type\s+)?[^'"`;]*?\bfrom\s*['"](\.[^'"]+)['"]/g,
  /\bimport\s*['"](\.[^'"]+)['"]/g,
  /\bexport\s+(?:type\s+)?(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})\s*from\s*['"](\.[^'"]+)['"]/g,
  /\bimport\s*\(\s*['"](\.[^'"]+)['"]\s*\)/g,
];
/** `import.meta.glob(<pattern or [patterns]>)`, with or without its type argument. */
const GLOBS = /\bimport\.meta\.glob(?:<[^>]*>)?\s*\(\s*(\[[^\]]*\]|['"][^'"]+['"])/g;
const QUOTED = /['"]([^'"]+)['"]/g;

/** The file an extensionless or folder import lands on (`.ts`, `.vue`, `index.ts`; a type-only one, `.d.ts`). */
function landing(path: string): string {
  for (const candidate of [path, `${path}.ts`, `${path}.vue`, `${path}.d.ts`, join(path, 'index.ts')]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return path;
}

/**
 * Every file of this repo `pnpm build` reads for the SPA: its type project's files (vue-tsc), what they import
 * (also lazily), what their `import.meta.glob`s match, and Vite's entries. Paths relative to the repo; a glob
 * that matches nothing here is reported, as it would match nothing in the image either, without an error.
 */
function spaBuildReads(): { files: Set<string>; emptyGlobs: string[] } {
  const spa = vueTscProject(scripts.build.split('&&')[0]);
  const input = viteConfig.build?.rollupOptions?.input;
  const entries = typeof input === 'string' ? [input] : Array.isArray(input) ? input : Object.values(input ?? {});
  const files = new Set([...checked(spa)].map((file) => relative(root, file)).filter((file) => !file.startsWith('node_modules/')));
  for (const entry of entries) files.add(relative(root, resolve(root, entry)));
  const emptyGlobs: string[] = [];
  for (const file of [...files].filter((name) => /\.(ts|vue)$/.test(name) && !name.endsWith('.d.ts'))) {
    const source = readFileSync(join(root, file), 'utf8');
    const folder = dirname(join(root, file));
    for (const pattern of SPECIFIERS) {
      for (const [, specifier] of source.matchAll(pattern)) files.add(relative(root, landing(resolve(folder, specifier))));
    }
    for (const [, argument] of source.matchAll(GLOBS)) {
      for (const [, glob] of argument.matchAll(QUOTED)) {
        const matched = globSync(glob, { cwd: folder }).map((match) => relative(root, resolve(folder, match)));
        if (matched.length === 0) emptyGlobs.push(`${file}: ${glob}`);
        for (const match of matched) files.add(match);
      }
    }
  }
  return { files, emptyGlobs };
}

/** `.dockerignore`'s patterns as matchers of repo paths (`**` any depth, `*` within one folder; a folder covers what is under it). */
function dockerIgnored(): (file: string) => boolean {
  const patterns = readFileSync(join(root, '.dockerignore'), 'utf8')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'));
  if (patterns.some((pattern) => pattern.startsWith('!'))) throw new Error('.dockerignore has an exception (!): not read here');
  const matchers = patterns.map((pattern) => {
    const body = pattern
      .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
      .replace(/\*\*\//g, '\u0000')
      .replace(/\*/g, '[^/]*')
      .replace(/\u0000/g, '(?:.*/)?');
    return new RegExp(`^${body}(?:/.*)?$`);
  });
  return (file) => matchers.some((matcher) => matcher.test(file));
}

it('copies into the image every file pnpm build reads for the SPA, and keeps none of them out by .dockerignore', () => {
  // 2026-10-22: hub#168 gave base its own frontend/ (the Home, the bell, «Upgrade plan»), which main.ts imports and
  // globs; the `web` stage copied frontend/ and apps/ only, so the image's `pnpm build` failed on the import (and a
  // glob alone would have built a hub without its Home, silently). The CI's `pnpm build` runs on the whole checkout.
  const sources = webStageCopies();
  const ignored = dockerIgnored();
  const { files, emptyGlobs } = spaBuildReads();

  expect([...files]).toEqual(expect.arrayContaining(['frontend/main.ts', 'base/frontend/lib/home.ts', 'base/frontend/routes.ts']));
  expect(emptyGlobs).toEqual([]);
  expect([...files].filter((file) => !copiedBy(sources, file)).sort()).toEqual([]);
  expect([...files].filter((file) => ignored(file)).sort()).toEqual([]);
}, 60_000);

