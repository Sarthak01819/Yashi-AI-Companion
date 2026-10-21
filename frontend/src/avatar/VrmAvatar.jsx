import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";

import { AvatarMotion, EMOTION_FACES } from "./avatarMotion";

// Served by Vite from frontend/public/models.
// AvatarSample_A (c) pixiv / VRoid Project — free for any use, no credit required:
// https://vroid.pixiv.help/hc/en-us/articles/4402394424089
// To use another VRM, put it next to it and add its URL first in this list.
const MODEL_URLS = ["/models/AvatarSample_A.vrm"];


const VrmAvatar = forwardRef(function VrmAvatar({ fallback = null, className = "" }, ref) {
  const mountRef = useRef(null);
  const [status, setStatus] = useState("loading");   // loading | ready | failed

  // Mutable animation state, read every frame (no React re-renders).
  const live = useRef({
    emotion: "neutral",
    thinking: false,
    listening: false,
    speaking: false,
    analyser: null,
    analyserData: null,
    bounce: false,
    reaction: null,
    loudness: null,
  });
  const audioCtxRef = useRef(null);

  const api = useRef(null);
  useImperativeHandle(ref, () => api.current, []);
  api.current = api.current || ({
    setEmotion(emotion) {
      live.current.emotion = EMOTION_FACES[emotion] ? emotion : "neutral";
    },
    setThinking(value) {
      live.current.thinking = !!value;
    },
    setListening(value) {
      live.current.listening = !!value;
    },
    triggerBounce() {
      live.current.bounce = true;
    },
    // Interactive reaction: "headpat" | "tease" | "cheer".
    react(kind) {
      live.current.reaction = kind;
    },
    // With an <audio> element we lip-sync to its real loudness (ElevenLabs);
    // without one (browser speech) the mouth moves procedurally.
    startLip(audio) {
      live.current.speaking = true;
      live.current.analyser = null;
      if (!audio) return;
      try {
        const Ctor = window.AudioContext || window.webkitAudioContext;
        const ctx = audioCtxRef.current || (audioCtxRef.current = new Ctor());
        if (ctx.state === "suspended") ctx.resume();
        if (!audio.__yashiSource) {
          audio.__yashiSource = ctx.createMediaElementSource(audio);
          audio.__yashiAnalyser = ctx.createAnalyser();
          audio.__yashiAnalyser.fftSize = 512;
          audio.__yashiSource.connect(audio.__yashiAnalyser);
          audio.__yashiAnalyser.connect(ctx.destination);
        }
        live.current.analyser = audio.__yashiAnalyser;
        live.current.analyserData = new Uint8Array(audio.__yashiAnalyser.fftSize);
      } catch (error) {
        live.current.analyser = null;          // fall back to procedural mouth
      }
    },
    stopLip() {
      live.current.speaking = false;
      live.current.analyser = null;
    },
  });

  // Dev-only handle for poking expressions from the console.
  useEffect(() => {
    if (!import.meta.env.DEV) return undefined;
    window.__yashiAvatar = api.current;
    return () => { delete window.__yashiAvatar; };
  }, []);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    let disposed = false;
    let frame = 0;
    let vrm = null;
    let motion = null;
    let baseYaw = 0;          // model's own facing after load (VRM 0.x is turned 180°)

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch (error) {
      setStatus("failed");                      // no WebGL -> show the fallback
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.display = "block";
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(22, 1, 0.1, 20);
    const lookTarget = new THREE.Object3D();
    camera.add(lookTarget);
    scene.add(camera);

    const key = new THREE.DirectionalLight(0xffffff, Math.PI * 0.9);
    key.position.set(0.6, 1.4, 2.2);
    scene.add(key);
    scene.add(new THREE.AmbientLight(0xffffff, Math.PI * 0.35));

    // Upper-body framing, recomputed on resize.
    let headY = 1.35;
    let framedSize = "";
    function frameCamera() {
      const width = mount.clientWidth || 1;
      const height = mount.clientHeight || 1;
      framedSize = `${width}x${height}`;
      renderer.setSize(width, height, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = width / height;
      // Frame by visible HEIGHT, scaled with the container: the small sidebar
      // card shows head and shoulders, the big focus view shows the upper body.
      // headY is the head bone (base of the skull); the hair top is ~22 cm above it.
      const span = THREE.MathUtils.clamp(height / 850, 0.6, 0.9);
      const distance = span / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
      const centerY = headY + 0.24 - span / 2;
      camera.position.set(0, centerY + 0.05, distance);
      camera.lookAt(0, centerY, 0);
      camera.updateProjectionMatrix();
    }

    // Eyes follow the pointer a little; otherwise look at the viewer.
    const pointer = { x: 0, y: 0 };
    function onPointerMove(event) {
      pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
      pointer.y = (event.clientY / window.innerHeight) * 2 - 1;
    }
    window.addEventListener("pointermove", onPointerMove);

    // ── Grab to spin 360° (turntable with inertia; double-click resets) ─────
    const spin = { yaw: 0, velocity: 0, dragging: false, lastX: 0, lastT: 0, moved: 0, target: null };
    mount.style.touchAction = "pan-y";          // horizontal drags rotate, vertical still scrolls
    mount.style.cursor = "grab";
    function onDown(event) {
      if (event.button !== undefined && event.button !== 0) return;
      spin.dragging = true;
      spin.moved = 0;
      spin.velocity = 0;
      spin.target = null;
      spin.lastX = event.clientX;
      spin.lastT = performance.now();
      mount.setPointerCapture?.(event.pointerId);
      mount.style.cursor = "grabbing";
    }
    function onDrag(event) {
      if (!spin.dragging) return;
      const now = performance.now();
      const dx = event.clientX - spin.lastX;
      const dt = Math.max(1, now - spin.lastT) / 1000;
      const delta = (dx / Math.max(200, mount.clientWidth)) * Math.PI * 2;
      spin.yaw += delta;
      spin.velocity = delta / dt;
      spin.moved += Math.abs(dx);
      spin.lastX = event.clientX;
      spin.lastT = now;
    }
    function onUp() {
      if (!spin.dragging) return;
      spin.dragging = false;
      mount.style.cursor = "grab";
      if (performance.now() - spin.lastT > 80) spin.velocity = 0;   // held still before letting go
    }
    // A drag shouldn't also count as a click (headpat) on the stage underneath.
    function onClickCapture(event) {
      if (spin.moved > 6) {
        event.stopPropagation();
        event.preventDefault();
      }
      spin.moved = 0;
    }
    function onDoubleClick() {
      // Ease back to facing the viewer the short way round.
      const turns = Math.round(spin.yaw / (Math.PI * 2));
      spin.target = turns * Math.PI * 2;
      spin.velocity = 0;
    }
    mount.addEventListener("pointerdown", onDown);
    mount.addEventListener("pointermove", onDrag);
    mount.addEventListener("pointerup", onUp);
    mount.addEventListener("pointercancel", onUp);
    mount.addEventListener("click", onClickCapture, true);
    mount.addEventListener("dblclick", onDoubleClick);

    function loadModel(urls) {
      const loader = new GLTFLoader();
      loader.register((parser) => new VRMLoaderPlugin(parser));
      const [url, ...rest] = urls;
      return loader.loadAsync(url).catch((error) => {
        if (rest.length) return loadModel(rest);
        throw error;
      });
    }

    loadModel(MODEL_URLS)
      .then((gltf) => {
        if (disposed) return;
        vrm = gltf.userData.vrm;
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.combineSkeletons(gltf.scene);
        VRMUtils.rotateVRM0(vrm);              // VRM 0.x models face the other way
        baseYaw = vrm.scene.rotation.y;
        // VRM 0.x rigs are turned around on load, which inverts X/Z rotations.
        motion = new AvatarMotion(vrm, vrm.meta?.metaVersion === "0" ? -1 : 1);
        vrm.scene.traverse((object) => { object.frustumCulled = false; });
        scene.add(vrm.scene);
        if (vrm.lookAt) vrm.lookAt.target = lookTarget;

        // Raw bones carry the model's real rest pose (normalized ones may not
        // have world matrices yet at this point).
        const head = vrm.humanoid.getRawBoneNode("head");
        if (head) {
          vrm.scene.updateMatrixWorld(true);
          headY = new THREE.Vector3().setFromMatrixPosition(head.matrixWorld).y;
        }
        frameCamera();
        setStatus("ready");
      })
      .catch((error) => {
        console.warn("[Yashi avatar] could not load a VRM model", error);
        if (!disposed) setStatus("failed");
      });

    const clock = new THREE.Clock();

    function readLoudness(state) {
      if (!state.analyser) return null;            // procedural mouth (browser speech)
      state.analyser.getByteTimeDomainData(state.analyserData);
      let sum = 0;
      for (let i = 0; i < state.analyserData.length; i += 1) {
        const v = (state.analyserData[i] - 128) / 128;
        sum += v * v;
      }
      return Math.min(1, Math.sqrt(sum / state.analyserData.length) * 6);
    }

    function animate() {
      frame = requestAnimationFrame(animate);
      // Hidden (e.g. chat kept alive behind the dashboard): skip all work.
      if (!mount.clientWidth || !mount.clientHeight) {
        clock.getDelta();
        return;
      }
      // Re-frame whenever the container changes size (focus mode, window
      // resize, mobile rotation). Checked per frame: cheap and never misses.
      if (`${mount.clientWidth}x${mount.clientHeight}` !== framedSize) frameCamera();
      const delta = Math.min(clock.getDelta(), 0.1);
      if (vrm && motion) {
        const state = live.current;
        state.loudness = state.speaking ? readLoudness(state) : null;
        motion.update(delta, state, pointer, lookTarget);
        if (!spin.dragging) {
          if (spin.target !== null) {
            spin.yaw += (spin.target - spin.yaw) * (1 - Math.exp(-delta * 8));
            if (Math.abs(spin.target - spin.yaw) < 0.002) spin.target = null;
          } else if (Math.abs(spin.velocity) > 0.01) {
            spin.yaw += spin.velocity * delta;
            spin.velocity *= Math.exp(-delta * 3.2);        // friction
          }
        }
        vrm.scene.rotation.y = baseYaw + spin.yaw;
        vrm.update(delta);
      }
      renderer.render(scene, camera);
    }
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onPointerMove);
      mount.removeEventListener("pointerdown", onDown);
      mount.removeEventListener("pointermove", onDrag);
      mount.removeEventListener("pointerup", onUp);
      mount.removeEventListener("pointercancel", onUp);
      mount.removeEventListener("click", onClickCapture, true);
      mount.removeEventListener("dblclick", onDoubleClick);
      if (vrm) {
        scene.remove(vrm.scene);
        VRMUtils.deepDispose(vrm.scene);
      }
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  if (status === "failed") return fallback;

  return (
    <div className={`relative h-full w-full ${className}`}>
      <div className="h-full w-full" ref={mountRef} />
      {status === "loading" ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs tracking-[0.08em] text-[#f3d6db] uppercase">
          Waking Yashi up...
        </div>
      ) : null}
    </div>
  );
});

export default VrmAvatar;
