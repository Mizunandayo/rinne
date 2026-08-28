/* SceneDescription -> a Rapier world. One module, both hosts. */

import RAPIER from "@dimforge/rapier3d-compat";
import type { SceneDescription, Vec3 } from "@rinne/contracts";

export const GROUND_HALF_EXTENT = 20;
export const GROUND_THICKNESS = 0.1;

/** Voxels per axis when thinning hull points. Six. See the note above. */
export const HULL_GRID = 6;

let started: Promise<void> | null = null;

export async function initScene(): Promise<void> {
  started ??= RAPIER.init();
  await started;
}

export function engineVersion(): string {
  return RAPIER.version();
}

export interface Extent {
  readonly min: Vec3;
  readonly max: Vec3;
  readonly size: Vec3;
}

export function extentOf(points: Float32Array): Extent {
  let minX = Infinity,
    minY = Infinity,
    minZ = Infinity;
  let maxX = -Infinity,
    maxY = -Infinity,
    maxZ = -Infinity;

  for (let i = 0; i + 2 < points.length; i += 3) {
    const x = points[i] ?? 0;
    const y = points[i + 1] ?? 0;
    const z = points[i + 2] ?? 0;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }

  if (!Number.isFinite(minX)) {
    const zero = { x: 0, y: 0, z: 0 };
    return { min: zero, max: zero, size: zero };
  }
  return {
    min: { x: minX, y: minY, z: minZ },
    max: { x: maxX, y: maxY, z: maxZ },
    size: { x: maxX - minX, y: maxY - minY, z: maxZ - minZ },
  };
}

export function decimate(points: Float32Array, grid: number = HULL_GRID): Float32Array {
  if (points.length < 3) return new Float32Array(0);

  const { min, size } = extentOf(points);
  const spanX = size.x || 1;
  const spanY = size.y || 1;
  const spanZ = size.z || 1;
  const cell = (value: number, low: number, span: number): number =>
    Math.min(grid - 1, Math.max(0, Math.floor(((value - low) / span) * grid)));

  const kept = new Map<string, readonly [number, number, number]>();
  for (let i = 0; i + 2 < points.length; i += 3) {
    const x = points[i] ?? 0;
    const y = points[i + 1] ?? 0;
    const z = points[i + 2] ?? 0;
    const key = `${cell(x, min.x, spanX)},${cell(y, min.y, spanY)},${cell(z, min.z, spanZ)}`;
    if (!kept.has(key)) kept.set(key, [x, y, z]);
  }

  const keys = [...kept.keys()].sort();
  const out = new Float32Array(keys.length * 3);
  let cursor = 0;
  for (const key of keys) {
    const point = kept.get(key);
    if (point === undefined) continue;
    out[cursor] = point[0];
    out[cursor + 1] = point[1];
    out[cursor + 2] = point[2];
    cursor += 3;
  }
  return out;
}

const RADIANS = Math.PI / 180;

export interface Quaternion {
  readonly x: number;
  readonly y: number;
  readonly z: number;
  readonly w: number;
}

export function quaternionFromEulerDegrees(euler: Vec3): Quaternion {
  const cx = Math.cos(euler.x * RADIANS * 0.5),
    sx = Math.sin(euler.x * RADIANS * 0.5);
  const cy = Math.cos(euler.y * RADIANS * 0.5),
    sy = Math.sin(euler.y * RADIANS * 0.5);
  const cz = Math.cos(euler.z * RADIANS * 0.5),
    sz = Math.sin(euler.z * RADIANS * 0.5);
  return {
    x: sx * cy * cz - cx * sy * sz,
    y: cx * sy * cz + sx * cy * sz,
    z: cx * cy * sz - sx * sy * cz,
    w: cx * cy * cz + sx * sy * sz,
  };
}

/* Angle between the body's local +Y and world +Y. */
export function tiltDegrees(rotation: Quaternion): number {
  const upX = 2 * (rotation.x * rotation.y + rotation.w * rotation.z);
  const upY = 1 - 2 * (rotation.x * rotation.x + rotation.z * rotation.z);
  const upZ = 2 * (rotation.y * rotation.z - rotation.w * rotation.x);
  const length = Math.hypot(upX, upY, upZ) || 1;
  return (Math.acos(Math.min(1, Math.max(-1, upY / length))) * 180) / Math.PI;
}

export class SceneBuildError extends Error {
  public readonly rule: string;

  constructor(rule: string) {
    super(rule);
    this.name = "SceneBuildError";
    this.rule = rule;
  }
}

export interface BuiltScene {
  readonly world: RAPIER.World;
  readonly body: RAPIER.RigidBody;
  readonly extent: Extent;
  readonly sourceVertices: number;
  readonly hullVertices: number;
}

export function buildScene(scene: SceneDescription, points: Float32Array): BuiltScene {
  const world = new RAPIER.World(scene.gravity);

  world.createCollider(
    RAPIER.ColliderDesc.cuboid(GROUND_HALF_EXTENT, GROUND_THICKNESS, GROUND_HALF_EXTENT)
      .setTranslation(0, -GROUND_THICKNESS, 0)
      .setFriction(scene.ground.friction)
      .setRestitution(scene.ground.restitution),
  );

  const start = scene.body.initialTranslation;
  let desc = RAPIER.RigidBodyDesc.dynamic().setTranslation(start.x, start.y, start.z);
  if (scene.body.initialRotationDegrees !== undefined) {
    desc = desc.setRotation(quaternionFromEulerDegrees(scene.body.initialRotationDegrees));
  }
  if (scene.body.linearDamping !== undefined) {
    desc = desc.setLinearDamping(scene.body.linearDamping);
  }
  if (scene.body.angularDamping !== undefined) {
    desc = desc.setAngularDamping(scene.body.angularDamping);
  }
  const body = world.createRigidBody(desc);

  const hullPoints = decimate(points);
  const hull = RAPIER.ColliderDesc.convexHull(hullPoints);
  if (hull === null) {
    world.free();
    throw new SceneBuildError("mesh produced no convex hull");
  }

  world.createCollider(
    hull
      .setMass(scene.body.massKilograms)
      .setFriction(scene.body.friction)
      .setRestitution(scene.body.restitution),
    body,
  );

  return {
    world,
    body,
    extent: extentOf(points),
    sourceVertices: points.length / 3,
    hullVertices: hullPoints.length / 3,
  };
}
