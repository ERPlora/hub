// Contract test for the pnpm workspace of the hub — "no dead packages".
//
// Regression test for ERPlora/hub#1244.
//
// WHY THIS EXISTS. `packages/module-cli` shipped `src/validate.test.mjs` and NOTHING ran it:
// the root `verify` script only filters `@erplora/web` and `@erplora/module-sdk`, and
// `test-web.yml` triggers on `packages/**` — so the package LOOKED covered by CI while its
// suite had not been executed since the modules left the workspace (2026-06). A guard that
// never runs gives confidence without checking anything, which is worse than no guard.
//
// The two rules below are the boring, mechanical version of that lesson:
//
//   1. A package under `packages/*` that carries test files must have them executed by the
//      root `verify` script (the single command `test-web.yml` runs). Tests that live
//      nowhere in the pipeline are dead weight pretending to be coverage.
//
//   2. Every workspace filter used by a root script must resolve to a package that exists and
//      to a script that package actually declares. This is what makes deleting a package a
//      complete operation: leave `pnpm -F @erplora/module-cli build:inventory` behind and the
//      guard fails naming the filter, instead of a contributor finding out on `pnpm run`.
//
// Kernel contract: ADR «El Hub se CIERRA como KERNEL» (architecture/hub/kernel-contract.md).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
// Overridable so the guard can be pointed at a fixture workspace and proven to catch the
// positive (see the PR body of hub#1244); defaults to this repo.
const repoRoot = process.env.NO_DEAD_PACKAGES_ROOT
    ? path.resolve(process.env.NO_DEAD_PACKAGES_ROOT)
    : path.resolve(scriptDir, "..", "..");

const IGNORED_DIRS = new Set(["node_modules", "dist", "coverage", ".turbo", "target"]);
const TEST_FILE = /\.test\.[cm]?[jt]sx?$/;

function readJson(file) {
    return JSON.parse(readFileSync(file, "utf8"));
}

/** Directory globs declared in pnpm-workspace.yaml, e.g. `apps/*`, `packages/*`. */
function workspaceGlobs() {
    const yaml = readFileSync(path.join(repoRoot, "pnpm-workspace.yaml"), "utf8");
    return yaml
        .split("\n")
        .map((line) => line.match(/^\s*-\s*['"]?([^'"#]+?)['"]?\s*$/))
        .filter(Boolean)
        .map((m) => m[1]);
}

/** Every workspace package: name -> { dir, manifest }. Only `<dir>/*` globs are used here. */
function workspacePackages() {
    const found = new Map();
    for (const glob of workspaceGlobs()) {
        if (!glob.endsWith("/*")) continue;
        const parent = path.join(repoRoot, glob.slice(0, -2));
        if (!existsSync(parent)) continue;
        for (const entry of readdirSync(parent, { withFileTypes: true })) {
            if (!entry.isDirectory() || IGNORED_DIRS.has(entry.name)) continue;
            const manifestPath = path.join(parent, entry.name, "package.json");
            if (!existsSync(manifestPath)) continue;
            const manifest = readJson(manifestPath);
            found.set(manifest.name, { dir: path.join(parent, entry.name), manifest });
        }
    }
    return found;
}

function testFilesUnder(dir) {
    const out = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (IGNORED_DIRS.has(entry.name)) continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) out.push(...testFilesUnder(full));
        else if (TEST_FILE.test(entry.name)) out.push(path.relative(repoRoot, full));
    }
    return out;
}

/**
 * Workspace filters used by a pnpm command line: `pnpm -F <pkg> <script>` /
 * `pnpm --filter <pkg> <script>`. Returns { pkg, script, segment } per occurrence.
 */
function filtersIn(command) {
    const out = [];
    for (const segment of command.split(/&&|\|\||;/)) {
        const tokens = segment.trim().split(/\s+/).filter(Boolean);
        for (let i = 0; i < tokens.length; i += 1) {
            if (tokens[i] !== "-F" && tokens[i] !== "--filter") continue;
            const pkg = tokens[i + 1];
            if (!pkg) continue;
            const script = tokens[i + 2];
            out.push({ pkg, script, segment: segment.trim() });
        }
    }
    return out;
}

const rootManifest = readJson(path.join(repoRoot, "package.json"));
const rootScripts = rootManifest.scripts ?? {};
const packages = workspacePackages();

test("every packages/* suite is executed by the root `verify` script (hub#1244)", () => {
    const verify = rootScripts.verify;
    assert.ok(verify, "the root package.json must declare a `verify` script — it is what CI runs");

    const verified = new Set(filtersIn(verify).map((f) => f.pkg));

    const dead = [];
    for (const [name, { dir, manifest }] of packages) {
        if (path.dirname(dir) !== path.join(repoRoot, "packages")) continue;
        const tests = testFilesUnder(dir);
        if (tests.length === 0) continue;
        if (!verified.has(name)) {
            dead.push(`${name} (${tests.length} test file(s), e.g. ${tests[0]})`);
        }
    }

    assert.deepEqual(
        dead,
        [],
        `these packages ship tests that \`pnpm verify\` never runs, so CI reports green without ` +
            `executing them — wire them into the root \`verify\` script or delete the package: ` +
            dead.join(", "),
    );
});

test("every workspace filter in the root scripts resolves to a real package + script (hub#1244)", () => {
    const dangling = [];
    for (const [scriptName, command] of Object.entries(rootScripts)) {
        for (const { pkg, script } of filtersIn(command)) {
            const target = packages.get(pkg);
            if (!target) {
                dangling.push(`${scriptName}: filter \`${pkg}\` matches no workspace package`);
                continue;
            }
            if (script && !(target.manifest.scripts ?? {})[script]) {
                dangling.push(`${scriptName}: \`${pkg}\` declares no \`${script}\` script`);
            }
        }
    }

    assert.deepEqual(
        dangling,
        [],
        `root scripts point at packages or scripts that do not exist: ${dangling.join(" | ")}`,
    );
});
