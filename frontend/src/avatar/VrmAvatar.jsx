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
      // Re-frame whenever the container changes size (focus mode, window
      // resize, mobile rotation). Checked per frame: cheap and never misses.
      if (`${mount.clientWidth}x${mount.clientHeight}` !== framedSize) frameCamera();
      const delta = Math.min(clock.getDelta(), 0.1);
      if (vrm && motion) {
        const state = live.current;
        state.loudness = state.speaking ? readLoudness(state) : null;
        motion.update(delta, state, pointer, lookTarget);
        vrm.update(delta);
      }
      renderer.render(scene, camera);
    }
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onPointerMove);
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
