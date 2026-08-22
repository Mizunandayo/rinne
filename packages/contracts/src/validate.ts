
import Ajv, { type ErrorObject, type ValidateFunction } from "ajv";
import addFormats from "ajv-formats";

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
