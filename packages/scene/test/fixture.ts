/* A valid GLB, built in code */

const JSON_CHUNK = 0x4e4f534a;
const BIN_CHUNK = 0x004e4942;

/** A box centred in XZ and seated at y = 0, matching mesh.normalise(). */
export function boxPositions(
  size: { x: number; y: number; z: number },
  subdivisions = 8,
): Float32Array {
  const points: number[] = [];
  const n = Math.max(1, subdivisions);
  for (let i = 0; i <= n; i += 1) {
    for (let j = 0; j <= n; j += 1) {
      const u = i / n;
      const v = j / n;
      const x = (u - 0.5) * size.x;
      const y = v * size.y;
      const w = (u - 0.5) * size.z;
      const h = v * size.y;

      points.push(x, y, -size.z / 2, x, y, size.z / 2);
      points.push(-size.x / 2, h, w, size.x / 2, h, w);
      points.push(x, 0, w, x, size.y, w);
    }
  }
  return new Float32Array(points);
}

export function glbFromPositions(positions: Float32Array): Uint8Array {
  const binary = new Uint8Array(positions.buffer.slice(0));
  const count = positions.length / 3;

  let minX = Infinity,
    minY = Infinity,
    minZ = Infinity;
  let maxX = -Infinity,
    maxY = -Infinity,
    maxZ = -Infinity;
  for (let i = 0; i + 2 < positions.length; i += 3) {
    const x = positions[i] ?? 0,
      y = positions[i + 1] ?? 0,
      z = positions[i + 2] ?? 0;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }

  const document = {
    asset: { version: "2.0", generator: "rinne-test-fixture" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ name: "geometry_0", mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, mode: 4 }] }],
    accessors: [
      {
        bufferView: 0,
        byteOffset: 0,
        componentType: 5126,
        count,
        type: "VEC3",
        min: [minX, minY, minZ],
        max: [maxX, maxY, maxZ],
      },
    ],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: binary.byteLength }],
    buffers: [{ byteLength: binary.byteLength }],
  };

  const jsonBytes = pad(new TextEncoder().encode(JSON.stringify(document)), 0x20);
  const binBytes = pad(binary, 0x00);
  const total = 12 + 8 + jsonBytes.byteLength + 8 + binBytes.byteLength;

  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonBytes.byteLength, true);
  view.setUint32(16, JSON_CHUNK, true);
  out.set(jsonBytes, 20);
  const binHeader = 20 + jsonBytes.byteLength;
  view.setUint32(binHeader, binBytes.byteLength, true);
  view.setUint32(binHeader + 4, BIN_CHUNK, true);
  out.set(binBytes, binHeader + 8);
  return out;
}

function pad(bytes: Uint8Array, filler: number): Uint8Array {
  const remainder = bytes.byteLength % 4;
  if (remainder === 0) return bytes;
  const padded = new Uint8Array(bytes.byteLength + (4 - remainder));
  padded.set(bytes, 0);
  padded.fill(filler, bytes.byteLength);
  return padded;
}

/** The scene every test starts from: a 0.30m box, 2.4kg, on level ground. */
export const BOX_SIZE = { x: 0.2, y: 0.2, z: 0.3 };

export function boxGlb(): Uint8Array {
  return glbFromPositions(boxPositions(BOX_SIZE));
}
