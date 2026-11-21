// Whether a script the Hub's e2e runs inside the SaaS (`manage.py shell -c`, as SEED_PY of assistant-seed.ts) still
// fits the SaaS checked out beside the Hub. Run in that SaaS, so a SaaS that moves or renames what the script uses
// fails the Hub's Vitest instead of a run's preparation.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { REPO_DIR } from './helpers';

type Env = Record<string, string | undefined>;

/** The SaaS beside the Hub (`E2E_SAAS_DIR`, by default `../saas`), or null: CI always has it, because the check must
 *  run there, and a lone checkout of the Hub skips it. */
export function saasCheckout(env: Env): string | null {
  const dir = env.E2E_SAAS_DIR || join(REPO_DIR, 'saas');
  if (existsSync(join(dir, 'manage.py'))) return dir;
  if (env.CI) throw new Error(`no SaaS at ${dir} (E2E_SAAS_DIR): CI clones it beside the Hub before Vitest`);
  return null;
}

/** Run inside the SaaS with the script on stdin. It never runs the script: it runs each of its imports alone, then
 *  resolves every attribute read on an imported name and binds every call of one to its signature. */
const NAMES_PY = `
import ast, inspect, json, sys

MISSING = object()
tree = ast.parse(sys.stdin.read())
imported, problems = {}, set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        try:
            exec(compile(ast.Module([node], []), "<script>", "exec"), imported)
        except ImportError as error:
            problems.add((node.lineno, str(error)))


def resolve(node):
    """What an attribute chain rooted at an imported name stands for in the SaaS; MISSING for any other expression."""
    if isinstance(node, ast.Name):
        return imported.get(node.id, MISSING)
    owner = resolve(node.value) if isinstance(node, ast.Attribute) else MISSING
    if owner is MISSING:
        return MISSING
    try:
        return getattr(owner, node.attr)
    except AttributeError as error:
        problems.add((node.lineno, str(error)))
        return MISSING


def bind(call):
    """A call of a name of the SaaS, its arguments bound to the signature (spread arguments are not checked)."""
    function = resolve(call.func)
    spread = any(isinstance(arg, ast.Starred) for arg in call.args) or any(kw.arg is None for kw in call.keywords)
    if function is MISSING or spread:
        return
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return
    try:
        signature.bind(*call.args, **{kw.arg: kw.value for kw in call.keywords})
    except TypeError as error:
        problems.add((call.lineno, f"{ast.unparse(call.func)}: {error}"))


for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        bind(node)
    elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        resolve(node)
if problems:
    sys.exit("\\n".join(f"line {line}: {message}" for line, message in sorted(problems)))
print(json.dumps(sorted(name for name in imported if name != "__builtins__")))
`;

export interface SaasCheck {
  status: number | null;
  names: string[];
  problems: string;
}

/** The script's names resolved in the SaaS at `saasDir`: `names`, what it imports, when everything resolves; otherwise
 *  `problems` names, line by line, what the SaaS lacks. The process runs off the Vitest worker's thread: a test waits
 *  for it with NO_CLOCK (vitest.load.ts), as long as starting Django cold takes. */
export function checkInSaas(script: string, saasDir: string): Promise<SaasCheck> {
  return new Promise((settle) => {
    const child = spawn('uv', ['run', 'python', 'manage.py', 'shell', '--no-imports', '-c', NAMES_PY], { cwd: saasDir });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8').on('data', (chunk: string) => (stdout += chunk));
    child.stderr.setEncoding('utf8').on('data', (chunk: string) => (stderr += chunk));
    child.stdin.on('error', (error) => (stderr += `${error.message}\n`));
    child.once('error', (error) => settle({ status: null, names: [], problems: `${stderr}${error.message}` }));
    child.once('close', (status) => {
      const names = status === 0 ? (JSON.parse(stdout.trim().split('\n').at(-1) ?? '[]') as string[]) : [];
      settle({ status, names, problems: `${stderr}${stdout}` });
    });
    child.stdin.end(script);
  });
}
