import RAPIER from "@dimforge/rapier3d-compat";


export interface SelfTestResult {
  readonly steps: number;
  readonly restingY: number;
  readonly durationMs: number;
}


const EXPECTED_RESTING_Y = 0.5; 
const TOLERANCE = 0.05;


let initialized = false;
let lastSelfTest: SelfTestResult | null = null;
let initError: string | null = null;



export function isReady(): boolean {
  return initialized && lastSelfTest !== null;
}

export function lastResult(): SelfTestResult | null {
  return lastSelfTest;
}

export function initFailureReason(): string | null {
  return initError;
}




/** Idempotent. Safe to call from both server startup and a test's beforeAll. */
export async function initPhysics(): Promise<void> {
  if (initialized) return;
  try {
    await RAPIER.init();
    initialized = true;
    initError = null;
  } catch (error) {
    initError = error instanceof Error ? error.name : "unknown";
    throw new Error("Rapier WASM failed to initialise");
  }
}


export function selfTest(): SelfTestResult {
  if (!initialized) throw new Error("initPhysics() must be awaited before selfTest()");

  const started = performance.now();
  const world = new RAPIER.World({ x: 0, y: -9.81, z: 0 });
  world.timestep = 1 / 60;

  try {
    // Static ground: a wide, thin slab whose top face sits exactly at y = 0.
    world.createCollider(
      RAPIER.ColliderDesc.cuboid(20, 0.1, 20).setTranslation(0, -0.1, 0).setFriction(0.6),
    );

    // Dynamic 1m cube released 1m above the ground.
    const body = world.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(0, 1.5, 0));
    world.createCollider(
      RAPIER.ColliderDesc.cuboid(0.5, 0.5, 0.5).setFriction(0.6).setRestitution(0.05),
      body,
    );

    // 240 steps at 1/60 = 4 simulated seconds. Bounded, per §12.
    const steps = 240;
    for (let i = 0; i < steps; i += 1) world.step();

    const restingY = body.translation().y;
    const durationMs = Math.round(performance.now() - started);

    if (!Number.isFinite(restingY) || Math.abs(restingY - EXPECTED_RESTING_Y) > TOLERANCE) {
      throw new Error(
        `Rapier self-test failed: cube rested at y=${restingY.toFixed(4)}, expected ` +
          `${EXPECTED_RESTING_Y} +/- ${TOLERANCE}`,
      );
    }

    lastSelfTest = { steps, restingY, durationMs };
    return lastSelfTest;
  } finally {
     world.free();
  }
}

export function rapierVersion(): string {
  return RAPIER.version();
}