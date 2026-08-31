"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { Pose } from "@rinne/scene";

// Section 11: the viewer surface is #111111 so light line work reads on it.
const VIEWER_SURFACE = 0x111111;

// Section 11 proposed confidence-as-motion. It was built, and it read as a broken
// viewer rather than as a signal, so it is gone: the mesh is still and the number
// beside it carries the uncertainty. ConfidenceReadout already states it plainly.

interface MeshViewerProps {
  readonly requestId: string;
  readonly heightMeters: number;
  /** Live pose from a browser simulation. null leaves the mesh where it settled. */
  readonly pose?: Pose | null;
}

export function MeshViewer({ requestId, heightMeters, pose = null }: MeshViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const posed = useRef<Pose | null>(pose);
  posed.current = pose;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    // A reconstruction lit by one lamp reads as clay. Image-based lighting plus a
    // filmic curve is what makes the SAME geometry look like an object: the
    // difference people call "quality" is mostly shading, not vertices.
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(VIEWER_SURFACE);

    const pmrem = new THREE.PMREMGenerator(renderer);
    const environment = pmrem.fromScene(new RoomEnvironment(), 0.04);
    scene.environment = environment.texture;

    const camera = new THREE.PerspectiveCamera(
      45,
      mount.clientWidth / mount.clientHeight,
      0.01,
      50,
    );
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;

    // Three-point rig over the IBL: a key that casts, a cool fill to keep the
    // shadow side readable, and a rim to separate the object from the ground.
    const key = new THREE.DirectionalLight(0xffffff, 2.6);
    key.position.set(0.8, 1.6, 1.2);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.bias = -0.0006;
    key.shadow.normalBias = 0.012;
    scene.add(key);

    const fill = new THREE.DirectionalLight(0xbfd4ff, 0.7);
    fill.position.set(-1.4, 0.6, 0.8);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0xffffff, 1.1);
    rim.position.set(-0.4, 0.9, -1.6);
    scene.add(rim);

    // Catches the key light's shadow without painting a surface of its own.
    const shadowCatcher = new THREE.Mesh(
      new THREE.PlaneGeometry(6, 6),
      new THREE.ShadowMaterial({ opacity: 0.42 }),
    );
    shadowCatcher.rotation.x = -Math.PI / 2;
    shadowCatcher.receiveShadow = true;
    scene.add(shadowCatcher);

    // A ground grid gives the scale an anchor. Without it a normalised mesh
    // floats with no sense of how big it is claimed to be.
    const grid = new THREE.GridHelper(1, 10, 0x666666, 0x333333);
    scene.add(grid);

    // Held so the animation loop can drive it without re-creating the context.
    let loaded: THREE.Group | null = null;
    let settledY = 0;

    let disposed = false;
    let frame = 0;
    const loader = new GLTFLoader();
    loader.load(
      `/api/mesh/${requestId}`,
      (gltf) => {
        if (disposed) return;
        loaded = gltf.scene;
        // Where normalisation left it, so stopping a replay returns it there.
        settledY = gltf.scene.position.y;
        gltf.scene.traverse((node) => {
          if (!(node instanceof THREE.Mesh)) return;
          node.castShadow = true;
          node.receiveShadow = true;
          // glTF declares COLOR_0 LINEAR, but a reconstruction writes the sRGB
          // bytes it sampled. Read as linear they come out dark and desaturated,
          // which is why the red car looked washed out. Convert them once.
          const attribute = node.geometry?.getAttribute("color");
          if (attribute !== undefined && attribute.userData.rinneLinear !== true) {
            const values = attribute.array as Float32Array | Uint8Array;
            const scale = values instanceof Float32Array ? 1 : 255;
            const linear = new Float32Array(values.length);
            for (let i = 0; i < values.length; i += 1) {
              linear[i] = THREE.SRGBToLinear((values[i] ?? 0) / scale);
            }
            node.geometry?.setAttribute(
              "color",
              new THREE.BufferAttribute(linear, attribute.itemSize),
            );
            node.geometry!.getAttribute("color").userData.rinneLinear = true;
          }

          const material = node.material;
          if (material instanceof THREE.MeshStandardMaterial) {
            // Reconstructed vertex colour is albedo, not a finished material. A
            // low roughness over the IBL is what reads as a surface rather than
            // as clay; the small metalness sharpens the highlight without
            // turning a plastic object into chrome.
            material.roughness = 0.28;
            material.metalness = 0.15;
            material.envMapIntensity = 1.9;
            material.flatShading = false;
            material.vertexColors = attribute !== undefined;
            material.needsUpdate = true;
          }
          node.geometry?.computeVertexNormals();
        });
        scene.add(gltf.scene);

        const box = new THREE.Box3().setFromObject(gltf.scene);
        const size = box.getSize(new THREE.Vector3());
        const centre = box.getCenter(new THREE.Vector3());
        const radius = Math.max(size.x, size.y, size.z) || heightMeters || 0.3;

        controls.target.set(centre.x, centre.y, centre.z);
        camera.position.set(
          centre.x + radius * 1.6,
          centre.y + radius * 1.1,
          centre.z + radius * 2,
        );
        camera.near = radius / 100;
        camera.far = radius * 100;
        camera.updateProjectionMatrix();
        controls.update();

        grid.scale.setScalar(Math.max(radius * 4, 0.1));
      },
      undefined,
      () => {
        if (!disposed) setFailed(true);
      },
    );

    const render = () => {
      frame = requestAnimationFrame(render);

      // A pose from the browser simulation moves the loaded mesh. The solver works
      // in the same metres and the same Y-up frame the mesh was normalised into,
      // so the values apply directly - no fitting, no scaling, no guesswork.
      const live = posed.current;
      if (loaded !== null) {
        if (live !== null) {
          loaded.position.set(live.translation.x, live.translation.y, live.translation.z);
          loaded.quaternion.set(live.rotation.x, live.rotation.y, live.rotation.z, live.rotation.w);
        } else {
          loaded.position.set(0, settledY, 0);
          loaded.quaternion.identity();
        }
      }

      controls.update();
      renderer.render(scene, camera);
    };
    render();

    const resize = new ResizeObserver(() => {
      if (mount.clientWidth === 0 || mount.clientHeight === 0) return;
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
    });
    resize.observe(mount);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resize.disconnect();
      controls.dispose();
      // WebGL contexts are a finite browser resource; a viewer that leaks them
      // stops rendering after a handful of scans.
      scene.traverse((node) => {
        if (node instanceof THREE.Mesh) {
          node.geometry.dispose();
          const materials = Array.isArray(node.material) ? node.material : [node.material];
          materials.forEach((material) => {
            material.dispose();
          });
        }
      });
      environment.texture.dispose();
      pmrem.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [requestId, heightMeters]);

  return (
    <div className="rinne-viewer">
      <div ref={mountRef} className="rinne-viewer-stage" />
      {failed ? <p className="rinne-viewer-note">The mesh could not be loaded.</p> : null}
      <p className="rinne-caption rinne-viewer-hint">Drag to orbit, scroll to zoom</p>
    </div>
  );
}
