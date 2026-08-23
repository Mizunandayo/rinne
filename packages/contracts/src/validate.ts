
import _Ajv, { type ErrorObject, type ValidateFunction } from "ajv";
import _addFormats from "ajv-formats";

/**
 * Ajv 8 and ajv-formats are CommonJS packages whose type declarations use
 * `export default`. Under `module: NodeNext`, TypeScript models the default
 * import of such a module as the module NAMESPACE rather than the value, so
 * `new Ajv()` fails to typecheck with "has no construct signatures" even though
 * it is correct at runtime: both packages do `module.exports = <the value>`,
 * which is exactly what a default import from ESM receives.
 *
 * These casts are type-only. They change no emitted JavaScript.
 */
const Ajv = _Ajv as unknown as typeof _Ajv.default;
const addFormats = _addFormats as unknown as typeof _addFormats.default;

export class ContractViolationError extends Error {
  public readonly issues: readonly string[];

  constructor(schemaTitle: string, issues: readonly string[]) {
    super(`Contract violation (${schemaTitle}): ${issues.join("; ")}`);
    this.name = "ContractViolationError";
    this.issues = issues;
  }
}

const ajv = new Ajv({
  allErrors: true,
  strict: false,
  // Never mutate what crossed the boundary. Coercion and default-filling hide
  // the fact that the other side sent something wrong.
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false,
});
addFormats(ajv);

function describe(errors: ErrorObject[] | null | undefined): string[] {
  if (!errors || errors.length === 0) return ["unknown validation failure"];
  return errors.slice(0, 8).map((e) => `${e.instancePath === "" ? "/" : e.instancePath} ${e.message ?? ""}`.trim());
}

/**
 * Compile once at module scope, call per request. Compiling per call is both
 * slow and a source of Ajv "$id already exists" errors.
 */
export function compileValidator<T>(schema: object): (data: unknown) => T {
  const title = (schema as { title?: string }).title ?? "anonymous schema";
  const validate = ajv.compile(schema) as ValidateFunction<T>;

  return (data: unknown): T => {
    if (!validate(data)) {
      throw new ContractViolationError(title, describe(validate.errors));
    }
    return data;
  };
}

/** Non-throwing variant, for paths that must degrade rather than fail. */
export function compileChecker<T>(schema: object): (data: unknown) => data is T {
  const validate = ajv.compile(schema) as ValidateFunction<T>;
  return (data: unknown): data is T => validate(data);
}
