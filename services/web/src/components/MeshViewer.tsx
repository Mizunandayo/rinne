"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

// Section 11: the viewer surface is #111111 so light line work reads on it.
const VIEWER_SURFACE = 0x111111;

interface MeshViewerProps {
  readonly requestId: string;
  readonly heightMeters: number;
}

export function MeshViewer({ requestId, heightMeters }: MeshViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(VIEWER_SURFACE);

    const camera = new THREE.PerspectiveCamera(
      45,
      mount.clientWidth / mount.clientHeight,
      0.01,
      50,
    );
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(1, 2, 1.5);
    scene.add(key);

    // A ground grid gives the scale an anchor. Without it a normalised mesh
    // floats with no sense of how big it is claimed to be.
    const grid = new THREE.GridHelper(1, 10, 0x666666, 0x333333);
    scene.add(grid);

    let disposed = false;
    let frame = 0;

    const loader = new GLTFLoader();
    loader.load(
      `/api/mesh/${requestId}`,
      (gltf) => {
        if (disposed) return;
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
