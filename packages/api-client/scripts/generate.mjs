#!/usr/bin/env node
/**
 * Regenerates src/openapi.d.ts from the live FastAPI schema in src/api.py.
 *
 * The backend endpoints are typed `-> dict`, not Pydantic `response_model`s,
 * so FastAPI's OpenAPI output only has real type information for *request*
 * bodies/params. Response shapes are still hand-maintained in src/types.ts
 * (ported from frontend/src/types.ts, which is verified against real
 * payloads) — this generated file exists so request typing and any future
 * response_model additions on the backend flow through automatically.
 */
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const pythonBin = resolve(repoRoot, ".venv/bin/python");

const tmpDir = mkdtempSync(join(tmpdir(), "fpl-openapi-"));
const schemaPath = join(tmpDir, "openapi.json");

execFileSync(pythonBin, [
  "-c",
  "import sys, json; sys.path.insert(0, 'src'); from api import app; " +
    "json.dump(app.openapi(), open(sys.argv[1], 'w'))",
  schemaPath,
], { cwd: repoRoot, stdio: "inherit" });

const ast = await openapiTS(new URL(`file://${schemaPath}`));
const output = astToString(ast);

writeFileSync(join(here, "..", "src", "openapi.d.ts"), output);
rmSync(tmpDir, { recursive: true, force: true });

console.log("Wrote packages/api-client/src/openapi.d.ts");
