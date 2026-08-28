import { describe, expect, it } from "vitest";
import { MeshDecodeError, readPositions } from "../src/glb.js";
import { BOX_SIZE, boxGlb, boxPositions, glbFromPositions } from "./fixture.js";

describe("GLB reader", () => {
  it("reads every POSITION back out of a file it just wrote", () => {
    const positions = boxPositions(BOX_SIZE, 2);
    const read = readPositions(glbFromPositions(positions));

    expect(read.length).toBe(positions.length);
    expect([...read.slice(0, 9)]).toEqual([...positions.slice(0, 9)]);
  });

  it("reads a mesh seated on the ground plane, which is what normalise() produces", () => {
    const read = readPositions(boxGlb());
    let minY = Infinity;
    for (let i = 1; i < read.length; i += 3) minY = Math.min(minY, read[i] ?? 0);
    expect(minY).toBeCloseTo(0, 6);
  });

  it("rejects bytes that are not a GLB", () => {
    expect(() => readPositions(new Uint8Array([1, 2, 3, 4]))).toThrow(MeshDecodeError);
    expect(() => readPositions(new Uint8Array(40))).toThrow(/not a GLB/);
  });

  it("rejects a file whose header length disagrees with the file", () => {
    const glb = boxGlb();
    new DataView(glb.buffer).setUint32(8, glb.byteLength + 4, true);
    expect(() => readPositions(glb)).toThrow(/does not match its header/);
  });

  it("REFUSES a node transform rather than silently scaling the collider", () => {
    // Positions are handed straight to the hull in mesh-local space, so an
    // unapplied transform would be a body of the wrong size in the wrong place.
    const positions = boxPositions(BOX_SIZE, 2);
    const glb = glbFromPositions(positions);
    const text = new TextDecoder().decode(
      glb.subarray(20, 20 + new DataView(glb.buffer).getUint32(12, true)),
    );
    const document = JSON.parse(text) as { nodes: { scale?: number[] }[] };
    document.nodes[0]!.scale = [2, 2, 2];
    const rebuilt = rewriteJsonChunk(glb, document);

    expect(() => readPositions(rebuilt)).toThrow(/carries a transform/);
  });

  it("names the rule and nothing else", () => {
    // Long enough to reach the magic-number check. A four-byte buffer trips
    // the size guard first, which is a different rule.
    try {
      readPositions(new Uint8Array(40));
      expect.unreachable("should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(MeshDecodeError);
      expect((error as MeshDecodeError).rule).toBe("mesh is not a GLB");
    }
  });

  it("distinguishes too-small from wrong-magic", () => {
    expect(() => readPositions(new Uint8Array([1, 2, 3, 4]))).toThrow(/too small/);
    expect(() => readPositions(new Uint8Array(40))).toThrow(/not a GLB/);
  });
});

/** Re-emit a GLB with a modified JSON chunk, preserving 4-byte padding. */
function rewriteJsonChunk(original: Uint8Array, document: unknown): Uint8Array {
  const view = new DataView(original.buffer, original.byteOffset, original.byteLength);
  const oldJsonLength = view.getUint32(12, true);
  const binaryStart = 20 + oldJsonLength;
  const binaryChunk = original.subarray(binaryStart);

  let json = new TextEncoder().encode(JSON.stringify(document));
  const remainder = json.byteLength % 4;
  if (remainder !== 0) {
    const padded = new Uint8Array(json.byteLength + (4 - remainder));
    padded.set(json, 0);
    padded.fill(0x20, json.byteLength);
    json = padded;
  }

  const total = 12 + 8 + json.byteLength + binaryChunk.byteLength;
  const out = new Uint8Array(total);
  const target = new DataView(out.buffer);
  target.setUint32(0, 0x46546c67, true);
  target.setUint32(4, 2, true);
  target.setUint32(8, total, true);
  target.setUint32(12, json.byteLength, true);
  target.setUint32(16, 0x4e4f534a, true);
  out.set(json, 20);
  out.set(binaryChunk, 20 + json.byteLength);
  return out;
}
