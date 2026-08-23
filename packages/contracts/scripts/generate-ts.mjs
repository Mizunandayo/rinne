#!/usr/bin/env node
/**
 * packages/contracts/scripts/generate-ts.mjs
 *
 * Generates TypeScript types and inlined schema constants from schemas/*.schema.json.
 *
 *   node scripts/generate-ts.mjs            write src/generated/
 *   node scripts/generate-ts.mjs --check    exit 1 if the committed output is stale
 *
 * The --check mode is what turns "schema-first" from a claim into a build gate.
 */
import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const SCHEMA_DIR = join(ROOT, "schemas");
const OUT_DIR = join(ROOT, "src", "generated");
const CHECK_ONLY = process.argv.includes("--check");

const BANNER = `/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Source of truth : packages/contracts/schemas
 * Regenerate      : pnpm --filter @rinne/contracts run generate:ts
 *
 * CI runs the same generator with --check and fails the build if this file
 * differs. A schema edit without a regeneration is a build failure, which is
 * the entire point of defining the contract once.
 */
`;

/** json-schema-to-typescript passes `style` straight to Prettier. */
const COMPILE_OPTIONS = {
  bannerComment: "",
  additionalProperties: false,
  declareExternallyReferenced: true,
  unreachableDefinitions: false,
  enableConstEnums: false,
  strictIndexSignatures: true,
  style: {
    printWidth: 100,
    semi: true,
    singleQuote: false,
    trailingComma: "all",
  },
};

const moduleNameOf = (file) => basename(file, ".schema.json");

const constNameOf = (file) =>
  `${moduleNameOf(file).replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase())}Schema`;

async function buildArtifacts() {
  const files = (await readdir(SCHEMA_DIR)).filter((f) => f.endsWith(".schema.json")).sort();

  if (files.length === 0) {
    throw new Error(`No *.schema.json files found in ${SCHEMA_DIR}`);
  }

  /** @type {Map<string, string>} */
  const artifacts = new Map();

  // 1. One TypeScript module per schema.
  for (const file of files) {
    const raw = await readFile(join(SCHEMA_DIR, file), "utf8");
    const schema = JSON.parse(raw);

    if (typeof schema.title !== "string" || schema.title.length === 0) {
      throw new Error(`${file} has no "title". The generated type name is derived from it.`);
    }

    const ts = await compile(schema, schema.title, COMPILE_OPTIONS);
    artifacts.set(`${moduleNameOf(file)}.ts`, `${BANNER}\n${ts}`);
  }

  // 2. schemas.ts — raw documents inlined as `as const`.
  //    Inlining avoids JSON import attributes entirely, which keeps every
  //    consumer (Next.js server, Fastify, Vitest) on one boring code path.
  const constants = [];
  for (const file of files) {
    const raw = await readFile(join(SCHEMA_DIR, file), "utf8");
    const pretty = JSON.stringify(JSON.parse(raw), null, 2);
    constants.push(`export const ${constNameOf(file)} = ${pretty} as const;`);
  }
  artifacts.set("schemas.ts", `${BANNER}\n${constants.join("\n\n")}\n`);

  // 3. Barrel.
  const lines = files.map((f) => `export type * from "./${moduleNameOf(f)}.js";`);
  lines.push(`export * from "./schemas.js";`);
  artifacts.set("index.ts", `${BANNER}\n${lines.join("\n")}\n`);

  return artifacts;
}

async function main() {
  const artifacts = await buildArtifacts();

  if (CHECK_ONLY) {
    const drifted = [];
    for (const [name, expected] of artifacts) {
      const path = join(OUT_DIR, name);
      const actual = existsSync(path) ? await readFile(path, "utf8") : null;
      if (actual !== expected) drifted.push(name);
    }
    if (drifted.length > 0) {
      console.error("Contract drift detected in packages/contracts/src/generated:");
      for (const name of drifted) console.error(`  - ${name}`);
      console.error("\nA schema changed without regenerating. Run:");
      console.error("  pnpm contracts:generate\n");
      process.exitCode = 1;
      return;
    }
    console.error("contracts: generated TypeScript is up to date");
    return;
  }

  await mkdir(OUT_DIR, { recursive: true });
  for (const [name, content] of artifacts) {
    await writeFile(join(OUT_DIR, name), content, "utf8");
  }
  console.error(`contracts: wrote ${artifacts.size} file(s) to src/generated`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
