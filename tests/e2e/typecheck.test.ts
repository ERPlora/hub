// @vitest-environment node
// `pnpm typecheck` (package.json; CI runs it) type-checks the e2e suite too. Until 2026-10-17 the root
// tsconfig.json left tests/e2e/ out, so a type error in a spec or a helper passed CI unseen. These tests read
// the projects the script checks (one per chained `vue-tsc` run) and prove they hold every .ts of this
// folder and report an error planted in a helper and in a spec.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { expect, it } from 'vitest';

import { NO_CLOCK } from '../../vitest.load';
import { readProgram, readText, walkAhead, walkingHost } from '../../vitest.offload';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const e2eDir = join(root, 'tests', 'e2e');

/**
 * Each `vue-tsc` run chained in the `typecheck` script: its tsconfig (`-p`, by default tsconfig.json) with the
 * run's own flags on top, so a `--noCheck` in the script counts, and anything that is not a flag (`|| true`, a
 * pipe), which would lose the run's exit code, fails.
 */
function typecheckProjects(): ts.ParsedCommandLine[] {
  const script: string = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).scripts.typecheck;
  return script.split('&&').map((command) => {
    const [bin, ...args] = command.trim().split(/\s+/);
    if (bin !== 'vue-tsc') throw new Error(`"${command.trim()}" in the typecheck script is not a vue-tsc run`);
    const { options, fileNames, errors } = ts.parseCommandLine(args);
    const stray = [...errors.map((error) => ts.flattenDiagnosticMessageText(error.messageText, ' ')), ...fileNames];
    if (stray.length) {
      throw new Error(`"${command.trim()}" in the typecheck script is not a plain vue-tsc run: ${stray.join('; ')}`);
    }
    const project = resolve(root, options.project ?? 'tsconfig.json');
    return parse(project.endsWith('.json') ? project : join(project, 'tsconfig.json'), options);
  });
}

function parse(project: string, options: ts.CompilerOptions): ts.ParsedCommandLine {
  const parsed = ts.getParsedCommandLineOfConfigFile(project, options, {
    ...walkingHost,
    onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
      throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'));
    },
  });
  if (!parsed) throw new Error(`${project} could not be read`);
  return parsed;
}

const checked = (project: ts.ParsedCommandLine) => new Set(project.fileNames.map((file) => resolve(file)));

/** Every .ts under tests/e2e/, outside dot folders (the screenshots of `.artifacts/`) and node_modules. */
const e2eFiles = readdirSync(e2eDir, { recursive: true, encoding: 'utf8' })
  .filter((name) => name.endsWith('.ts'))
  .filter((name) => !name.split(/[\\/]/).some((part) => part.startsWith('.') || part === 'node_modules'))
  .map((name) => join(e2eDir, name));

it('checks every .ts of tests/e2e', () => {
  const files = new Set(typecheckProjects().flatMap((project) => [...checked(project)]));
  expect(e2eFiles.length).toBeGreaterThan(0);
  expect(e2eFiles.filter((file) => !files.has(file)).map((file) => relative(root, file))).toEqual([]);
});

// The projects walked ahead and the program read ahead, without holding the worker (hub#1315): some 1,500 files, each
// first open of which waits on its own on a loaded machine. What is left here is TypeScript's own work, the check.
it('reports a type error planted in a helper and in a spec', async () => {
  const planted = ['helpers.ts', 'csp.spec.ts'].map((name) => join(e2eDir, name));
  const projects = await walkAhead(typecheckProjects);
  const project = projects.find((candidate) => planted.every((file) => checked(candidate).has(file)));
  if (!project) throw new Error('no project of the typecheck script holds tests/e2e/');

  await readProgram(project.fileNames, project.options);
  const host = ts.createCompilerHost(project.options);
  host.readFile = (file) => {
    const text = readText(file);
    return planted.includes(resolve(file)) ? `${text}\nexport const planted: number = 'not a number';\n` : text;
  };
  const program = ts.createProgram({ rootNames: project.fileNames, options: project.options, host });

  const errors = planted.flatMap((file) => {
    const source = program.getSourceFile(file);
    if (!source) throw new Error(`${relative(root, file)} is not in the program`);
    return program.getSemanticDiagnostics(source).map((diagnostic) => [relative(root, file), diagnostic.code]);
  });
  // TS2322: Type 'string' is not assignable to type 'number'.
  expect(errors).toEqual([
    ['tests/e2e/helpers.ts', 2322],
    ['tests/e2e/csp.spec.ts', 2322],
  ]);
}, NO_CLOCK);
