const GLB_MAGIC = 0x46546c67; // "glTF", little-endian
const JSON_CHUNK = 0x4e4f534a;
const BIN_CHUNK = 0x004e4942;
const COMPONENT_FLOAT = 5126;
const MODE_TRIANGLES = 4;
const VEC3_BYTES = 12;

export class MeshDecodeError extends Error {
  public readonly rule: string;

  constructor(rule: string) {
    super(rule);
    this.name = "MeshDecodeError";
    this.rule = rule;
  }
}

interface GltfAccessor {
  readonly componentType?: number;
  readonly type?: string;
  readonly bufferView?: number;
  readonly byteOffset?: number;
  readonly count?: number;
}

interface GltfBufferView {
  readonly byteOffset?: number;
  readonly byteStride?: number;
}

interface GltfNode {
  readonly matrix?: readonly number[];
  readonly translation?: readonly number[];
  readonly rotation?: readonly number[];
  readonly scale?: readonly number[];
}

interface GltfPrimitive {
  readonly mode?: number;
  readonly attributes?: Readonly<Record<string, number>>;
}

interface GltfDocument {
  readonly nodes?: readonly GltfNode[];
  readonly meshes?: readonly { readonly primitives?: readonly GltfPrimitive[] }[];
  readonly accessors?: readonly GltfAccessor[];
  readonly bufferViews?: readonly GltfBufferView[];
}

/** Every POSITION in the file, concatenated, as a flat xyz Float32Array. */
export function readPositions(bytes: Uint8Array): Float32Array {
  if (bytes.byteLength < 12) throw new MeshDecodeError("mesh is too small to be a GLB");
  const header = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  if (header.getUint32(0, true) !== GLB_MAGIC) throw new MeshDecodeError("mesh is not a GLB");
  if (header.getUint32(4, true) !== 2) throw new MeshDecodeError("mesh is not glTF 2.0");
  if (header.getUint32(8, true) !== bytes.byteLength) {
    throw new MeshDecodeError("mesh length does not match its header");
  }

  let offset = 12;
  let document: GltfDocument | null = null;
  let binary: Uint8Array | null = null;

  while (offset + 8 <= bytes.byteLength) {
    const length = header.getUint32(offset, true);
    const kind = header.getUint32(offset + 4, true);
    const start = offset + 8;
    if (start + length > bytes.byteLength)
      throw new MeshDecodeError("mesh chunk overruns the file");

    if (kind === JSON_CHUNK && document === null) {
      const text = new TextDecoder().decode(bytes.subarray(start, start + length));
      document = JSON.parse(text) as GltfDocument;
    } else if (kind === BIN_CHUNK && binary === null) {
      binary = bytes.subarray(start, start + length);
    }
    offset = start + length;
  }

  if (document === null) throw new MeshDecodeError("mesh has no glTF JSON chunk");
  if (binary === null) throw new MeshDecodeError("mesh has no binary chunk");

  // Positions are read in mesh-local space
  for (const node of document.nodes ?? []) {
    if (node.matrix ?? node.translation ?? node.rotation ?? node.scale) {
      throw new MeshDecodeError("mesh node carries a transform");
    }
  }

  const chunks: Float32Array[] = [];
  for (const mesh of document.meshes ?? []) {
    for (const primitive of mesh.primitives ?? []) {
      if ((primitive.mode ?? MODE_TRIANGLES) !== MODE_TRIANGLES) {
        throw new MeshDecodeError("mesh primitive is not triangles");
      }
      const index = primitive.attributes?.POSITION;
      if (index === undefined) continue;
      chunks.push(readVec3Accessor(document, binary, index));
    }
  }
  if (chunks.length === 0) throw new MeshDecodeError("mesh has no POSITION attribute");

  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const points = new Float32Array(total);
  let cursor = 0;
  for (const chunk of chunks) {
    points.set(chunk, cursor);
    cursor += chunk.length;
  }
  return points;
}

function readVec3Accessor(document: GltfDocument, binary: Uint8Array, index: number): Float32Array {
  const accessor = document.accessors?.[index];
  if (accessor === undefined) throw new MeshDecodeError("mesh references a missing accessor");
  if (accessor.componentType !== COMPONENT_FLOAT || accessor.type !== "VEC3") {
    throw new MeshDecodeError("mesh positions are not float vec3");
  }

  const viewIndex = accessor.bufferView;
  const view = viewIndex === undefined ? undefined : document.bufferViews?.[viewIndex];
  if (view === undefined) throw new MeshDecodeError("mesh references a missing bufferView");

  const base = (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
  const stride = view.byteStride ?? VEC3_BYTES;
  const count = accessor.count ?? 0;
  if (count <= 0) throw new MeshDecodeError("mesh accessor is empty");
  if (base + (count - 1) * stride + VEC3_BYTES > binary.byteLength) {
    throw new MeshDecodeError("mesh accessor overruns its buffer");
  }

  const data = new DataView(binary.buffer, binary.byteOffset, binary.byteLength);
  const out = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const at = base + i * stride;
    out[i * 3] = data.getFloat32(at, true);
    out[i * 3 + 1] = data.getFloat32(at + 4, true);
    out[i * 3 + 2] = data.getFloat32(at + 8, true);
  }
  return out;
}
