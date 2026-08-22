export type JsonSchemaObject = Record<string, unknown>;


export function toRouteSchema(schema: JsonSchemaObject): JsonSchemaObject {
  const clone: JsonSchemaObject = { ...schema };
  delete clone["$schema"];
  delete clone["$id"];
  return clone;
}