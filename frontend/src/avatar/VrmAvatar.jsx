import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";

import { AvatarMotion, EMOTION_FACES } from "./avatarMotion";
import { DEFAULT_MODEL } from "./outfits";

// Models are served by Vite from frontend/public/models. The default is
// AvatarSample_A (c) pixiv / VRoid Project — free for any use, no credit required:
// https://vroid.pixiv.help/hc/en-us/articles/4402394424089
// Other VRMs (whole outfits) are picked in the Wardrobe; see outfits.js.


const VrmAvatar = forwardRef(function VrmAvatar(
  { fallback = null, className = "", closeUp = false, modelUrl = DEFAULT_MODEL, clothTint = null },
  ref,
) {
  const mountRef = useRef(null);
  const [status, setStatus] = useState("loading");   // loading | ready | failed
  // Focus mode: a head-and-chest close-up instead of the upper body.
  const closeUpRef = useRef(closeUp);
  closeUpRef.current = closeUp;
  // Wardrobe: which model file to show, and the colour her clothes are tinted.
  const outfitRef = useRef({ modelUrl, clothTint });
  outfitRef.current = { modelUrl, clothTint };
  const wardrobe = useRef(null);       // { showModel, applyTint, shownUrl } once the scene exists

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
    const baseTurn = new THREE.Quaternion();   // model's own facing after load (VRM 0.x is turned 180°)
    let shownUrl = null;
    let loads = 0;            // the newest outfit choice wins if several are loading

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
    let framedCloseUp = closeUpRef.current;
    let span = 0;             // visible height in metres, eased toward targetSpan
    let targetSpan = 0.75;
    let backoff = 0;          // extra distance while her feet swing toward the lens
    const pivot = new THREE.Vector3();    // where the camera aims; she turns about it

    function viewDistance() {
      return span / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
    }

    function placeCamera() {
      // headY is the head bone (base of the skull); the hair top is ~22 cm above it.
      const centerY = headY + 0.24 - span / 2;
      pivot.set(0, centerY, 0);
      camera.position.set(0, centerY + 0.05, viewDistance() + backoff);
      camera.lookAt(pivot);
    }

    function frameCamera() {
      const width = mount.clientWidth || 1;
      const height = mount.clientHeight || 1;
      framedSize = `${width}x${height}`;
      framedCloseUp = closeUpRef.current;
      renderer.setSize(width, height, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      // Frame by visible HEIGHT. Normally it scales with the container: the
      // small sidebar card shows head and shoulders, a big stage the upper
      // body. Focus mode is a close-up from the hair to the chest. On a narrow
      // portrait screen keep at least her shoulders (~0.45 m) in the width.
      targetSpan = framedCloseUp
        ? Math.max(0.5, 0.45 / camera.aspect)
        : THREE.MathUtils.clamp(height / 850, 0.6, 0.9);
      if (!span) {
        span = targetSpan;
        placeCamera();
      }
    }

    // Eyes follow the pointer a little; otherwise look at the viewer.
    const pointer = { x: 0, y: 0 };
    function onPointerMove(event) {
      pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
      pointer.y = (event.clientY / window.innerHeight) * 2 - 1;
    }
    window.addEventListener("pointermove", onPointerMove);

    // ── Grab to turn her any way (trackball with inertia; double-click resets) ──
    // Like turning a figure in your hand: the axis is perpendicular to the drag on
    // screen, so dragging right spins her right, down tips her toward you, and
    // diagonals or circles roll her any way at all.
    const spin = {
      turn: new THREE.Quaternion(),     // the user's rotation, about `pivot`
      velocity: new THREE.Vector3(),    // world axis * rad/s, for the glide after a flick
      dragging: false, resetting: false, lastX: 0, lastY: 0, lastT: 0, moved: 0,
    };
    const turnAxis = new THREE.Vector3();
    const turnStep = new THREE.Quaternion();
    const upright = new THREE.Quaternion();
    const offset = new THREE.Vector3();
    function turnBy(axis, angle) {
      spin.turn.premultiply(turnStep.setFromAxisAngle(axis, angle)).normalize();
    }
    mount.style.touchAction = "none";           // every drag direction turns her
    mount.style.cursor = "grab";
    function onDown(event) {
      if (event.button !== undefined && event.button !== 0) return;
      spin.dragging = true;
      spin.resetting = false;
      spin.moved = 0;
      spin.velocity.set(0, 0, 0);
      spin.lastX = event.clientX;
      spin.lastY = event.clientY;
      spin.lastT = performance.now();
      mount.setPointerCapture?.(event.pointerId);
      mount.style.cursor = "grabbing";
    }
    function onDrag(event) {
      if (!spin.dragging) return;
      const now = performance.now();
      const dx = event.clientX - spin.lastX;
      const dy = event.clientY - spin.lastY;
      const length = Math.hypot(dx, dy);
      if (!length) return;
      const dt = Math.max(1, now - spin.lastT) / 1000;
      // A drag across the whole stage is one full turn, in any direction.
      const angle = (length / Math.max(200, mount.clientWidth)) * Math.PI * 2;
      turnAxis.set(dy / length, dx / length, 0).applyQuaternion(camera.quaternion);
      turnBy(turnAxis, angle);
      spin.velocity.copy(turnAxis).multiplyScalar(angle / dt);
      spin.moved += length;
      spin.lastX = event.clientX;
      spin.lastY = event.clientY;
      spin.lastT = now;
    }
    function onUp() {
      if (!spin.dragging) return;
      spin.dragging = false;
      mount.style.cursor = "grab";
      if (performance.now() - spin.lastT > 80) spin.velocity.set(0, 0, 0);   // held still before letting go
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
      // Ease back upright and facing the viewer, the short way round.
      spin.resetting = true;
      spin.velocity.set(0, 0, 0);
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

    // Loads a model and swaps it in once it's ready, so changing outfits never
    // shows an empty stage. A file that fails falls back to the default model.
    function showModel(url) {
      shownUrl = url;
      const load = ++loads;
      loadModel(url === DEFAULT_MODEL ? [url] : [url, DEFAULT_MODEL])
        .then((gltf) => {
          if (disposed || load !== loads) {           // a newer choice replaced this one
            VRMUtils.deepDispose(gltf.scene);
            return;
          }
          const next = gltf.userData.vrm;
          VRMUtils.removeUnnecessaryVertices(gltf.scene);
          VRMUtils.combineSkeletons(gltf.scene);
          VRMUtils.rotateVRM0(next);             // VRM 0.x models face the other way
          baseTurn.copy(next.scene.quaternion);
          next.scene.traverse((object) => { object.frustumCulled = false; });
          if (vrm) {
            scene.remove(vrm.scene);
            VRMUtils.deepDispose(vrm.scene);
          }
          vrm = next;
          // VRM 0.x rigs are turned around on load, which inverts X/Z rotations.
          motion = new AvatarMotion(vrm, vrm.meta?.metaVersion === "0" ? -1 : 1);
          scene.add(vrm.scene);
          if (vrm.lookAt) vrm.lookAt.target = lookTarget;

          // Raw bones carry the model's real rest pose (normalized ones may not
          // have world matrices yet at this point).
          const head = vrm.humanoid.getRawBoneNode("head");
          if (head) {
            vrm.scene.updateMatrixWorld(true);
            headY = new THREE.Vector3().setFromMatrixPosition(head.matrixWorld).y;
          }
          applyTint();
          frameCamera();
          placeCamera();                       // headY changed: re-aim right away
          setStatus("ready");
        })
        .catch((error) => {
          console.warn("[Yashi avatar] could not load a VRM model", error);
          if (!disposed && !vrm) setStatus("failed");
        });
    }

    // Built-in outfits recolour her clothes. VRoid exports keep all clothing in
    // materials named "..._CLOTH"; skin, hair and eyes are left alone.
    function applyTint() {
      if (!vrm) return;
      const tint = new THREE.Color(outfitRef.current.clothTint || 0xffffff);
      vrm.scene.traverse((object) => {
        for (const material of [].concat(object.material || [])) {
          if (!/CLOTH/i.test(material?.name || "")) continue;
          const saved = material.userData;
          if (!saved.yashiColor && material.color) saved.yashiColor = material.color.clone();
          if (!saved.yashiShade && material.shadeColorFactor) saved.yashiShade = material.shadeColorFactor.clone();
          if (saved.yashiColor) material.color.copy(saved.yashiColor).multiply(tint);
          if (saved.yashiShade) material.shadeColorFactor.copy(saved.yashiShade).multiply(tint);
        }
      });
    }

    wardrobe.current = { showModel, applyTint, shownUrl: () => shownUrl };
    showModel(outfitRef.current.modelUrl);

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
      if (`${mount.clientWidth}x${mount.clientHeight}` !== framedSize
          || closeUpRef.current !== framedCloseUp) frameCamera();
      const delta = Math.min(clock.getDelta(), 0.1);
      // Glide into / out of the close-up instead of cutting.
      if (Math.abs(targetSpan - span) > 0.0005) {
        span += (targetSpan - span) * (1 - Math.exp(-delta * 5));
        placeCamera();
      }
      if (vrm && motion) {
        const state = live.current;
        state.loudness = state.speaking ? readLoudness(state) : null;
        motion.update(delta, state, pointer, lookTarget);
        if (!spin.dragging) {
          if (spin.resetting) {
            spin.turn.slerp(upright, 1 - Math.exp(-delta * 8));
            if (spin.turn.angleTo(upright) < 0.002) {
              spin.turn.identity();
              spin.resetting = false;
            }
          } else if (spin.velocity.lengthSq() > 0.0001) {
            const speed = spin.velocity.length();
            turnBy(turnAxis.copy(spin.velocity).divideScalar(speed), speed * delta);
            spin.velocity.multiplyScalar(Math.exp(-delta * 3.2));        // friction
          }
        }
        // Turn about the point the camera aims at, so what's framed stays framed.
        vrm.scene.quaternion.multiplyQuaternions(spin.turn, baseTurn);
        vrm.scene.position.copy(pivot).sub(offset.copy(pivot).applyQuaternion(spin.turn));
        // Her feet are the model's origin. Tipped toward the viewer (mostly in the
        // close-up) they'd reach the lens, so the camera steps back while they're near.
        const clearance = Math.max(0, vrm.scene.position.z + 0.4 - viewDistance());
        if (Math.abs(clearance - backoff) > 0.001) {
          backoff += (clearance - backoff) * (1 - Math.exp(-delta * 6));
          placeCamera();
        }
        vrm.update(delta);
      }
      renderer.render(scene, camera);
    }
    animate();

    return () => {
      disposed = true;
      wardrobe.current = null;
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

  // Outfit changes: swap the model file, or just recolour the one on stage.
  useEffect(() => {
    const current = wardrobe.current;
    if (!current) return;
    if (current.shownUrl() !== modelUrl) current.showModel(modelUrl);
    else current.applyTint();
  }, [modelUrl, clothTint]);

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
