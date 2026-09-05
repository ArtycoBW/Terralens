import { TERRAIN_MARKERS, type TerrainController } from "./terrain-data";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

// Сцена TerraLens из GetLayers Scene Lab. Поле высот, сглаженные изолинии
// и инерционная камера адаптируют приёмы Argent Massif.
// Оформление задаётся в CONFIG; рельеф иллюстративный, без измеренной DEM.
export const CONFIG = {
  ground: "#13140e",
  earth: "#303d23",
  crest: "#818b53",
  line: "#c6cf9d",
  scan: "#ebfc72",
  base: "#22291b",
  width: 10,
  depth: 8,
  height: 2.5,
  segments: 150,
  contourSpacing: 0.13,
  lineOpacity: 0.58,
  scanOpacity: 0.2,
  scanSpeed: 0.17,
  cameraDamp: 3.2,
  cameraX: 10.5,
  cameraY: 10.5,
  cameraZ: 12.5,
  entranceDistance: 4,
  parallax: 0.65,
  maxDpr: 1.5,
  fov: 37,
};

export function terrainHeight(x: number, z: number) {
  const edge = Math.max(
    0,
    Math.min(
      1,
      (CONFIG.width / 2 - Math.abs(x)) * 1.2,
      (CONFIG.depth / 2 - Math.abs(z)) * 1.2,
    ),
  );
  const mountain = Math.exp(-((x + 1.7) ** 2 / 4.5 + (z + 0.5) ** 2 / 6.5));
  const ridge = Math.exp(-((x - 2) ** 2 / 5 + (z - 1.3) ** 2 / 2.8)) * 0.6;
  const detail =
    (Math.sin(x * 2.4 + Math.sin(z * 1.6)) * Math.cos(z * 2.2) +
      Math.sin(x * 5.1 + z * 3.4) * 0.2) *
    0.09;
  const valley =
    Math.exp(-((z - Math.sin(x * 0.75) * 0.8 - 0.8) ** 2) / 0.28) * 0.35;
  return Math.max(
    0.03,
    (mountain + ridge + detail - valley) * CONFIG.height * edge,
  );
}

export function mountTerrain(
  canvas: HTMLCanvasElement,
  markers: (HTMLButtonElement | null)[] = [],
  animated = true,
): TerrainController {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    powerPreference: "low-power",
    preserveDrawingBuffer: true,
  });
  renderer.setClearColor(CONFIG.ground, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(CONFIG.fov, 1, 0.1, 100);
  camera.position.set(CONFIG.cameraX, CONFIG.cameraY, CONFIG.cameraZ);
  const target = new THREE.Vector3(0, 0.2, 0);
  const controls = new OrbitControls(camera, canvas);
  controls.target.copy(target);
  controls.enableDamping = animated;
  controls.dampingFactor = 0.08;
  controls.minDistance = 7;
  controls.maxDistance = 30;
  controls.minPolarAngle = 0.15;
  controls.maxPolarAngle = Math.PI / 2.1;
  controls.enablePan = false;
  controls.rotateSpeed = 0.65;
  controls.zoomSpeed = 0.7;
  controls.update();
  controls.saveState();
  const rig = new THREE.Group();
  scene.add(rig);
  const geometry = new THREE.PlaneGeometry(
    CONFIG.width,
    CONFIG.depth,
    CONFIG.segments,
    CONFIG.segments,
  );
  geometry.rotateX(-Math.PI / 2);
  const positions = geometry.attributes.position;
  for (let i = 0; i < positions.count; i++)
    positions.setY(i, terrainHeight(positions.getX(i), positions.getZ(i)));
  geometry.computeVertexNormals();
  const uniforms = {
    uEarth: { value: new THREE.Color() },
    uCrest: { value: new THREE.Color() },
    uLine: { value: new THREE.Color() },
    uScanColor: { value: new THREE.Color() },
    uHeight: { value: CONFIG.height },
    uSpacing: { value: CONFIG.contourSpacing },
    uOpacity: { value: CONFIG.lineOpacity },
    uScanOpacity: { value: CONFIG.scanOpacity },
    uScan: { value: -7 },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    extensions: { derivatives: true },
    vertexShader: `varying vec3 vWorld; varying vec3 vNormal;
      void main() { vWorld=position; vNormal=normal; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `precision highp float;
      varying vec3 vWorld; varying vec3 vNormal;
      uniform vec3 uEarth,uCrest,uLine,uScanColor;
      uniform float uHeight,uSpacing,uOpacity,uScan,uScanOpacity;
      void main() {
        float altitude=clamp(vWorld.y/uHeight,0.,1.);
        float light=.56+.44*max(0.,dot(normalize(vNormal),normalize(vec3(-.4,1.,.5))));
        vec3 color=mix(uEarth,uCrest,altitude)*light;
        float band=vWorld.y/uSpacing;
        float distanceToLine=abs(fract(band+.5)-.5);
        float antialias=max(fwidth(band),.025);
        float contour=1.-smoothstep(.012,.012+antialias*.85,distanceToLine);
        color=mix(color,uLine,contour*uOpacity);
        float scan=1.-smoothstep(0.,.32,abs(vWorld.x-uScan));
        color=mix(color,uScanColor,scan*uScanOpacity);
        gl_FragColor=vec4(color,1.);
      }`,
  });
  const baseGeometry = new THREE.BoxGeometry(CONFIG.width, 0.45, CONFIG.depth);
  const baseMaterial = new THREE.MeshStandardMaterial({
    color: CONFIG.base,
    roughness: 0.9,
  });
  const base = new THREE.Mesh(baseGeometry, baseMaterial);
  base.position.y = -0.225;
  rig.add(base, new THREE.Mesh(geometry, material));
  const ambient = new THREE.AmbientLight(CONFIG.crest, 0.7);
  scene.add(ambient);
  const light = new THREE.DirectionalLight(CONFIG.line, 1.2);
  light.position.set(-4, 9, 5);
  scene.add(light);
  function applyConfig() {
    uniforms.uEarth.value.set(CONFIG.earth);
    uniforms.uCrest.value.set(CONFIG.crest);
    uniforms.uLine.value.set(CONFIG.line);
    uniforms.uScanColor.value.set(CONFIG.scan);
    uniforms.uHeight.value = CONFIG.height;
    uniforms.uSpacing.value = CONFIG.contourSpacing;
    uniforms.uOpacity.value = CONFIG.lineOpacity;
    uniforms.uScanOpacity.value = CONFIG.scanOpacity;
    baseMaterial.color.set(CONFIG.base);
  }
  applyConfig();
  const markerPoints = TERRAIN_MARKERS.map(
    (marker) =>
      new THREE.Vector3(
        marker.x,
        terrainHeight(marker.x, marker.z) + 0.16,
        marker.z,
      ),
  );
  const projection = new THREE.Vector3();
  let frame = 0,
    visible = false,
    disposed = false,
    last = performance.now(),
    elapsed = 0;
  function resize() {
    const width = canvas.clientWidth,
      height = canvas.clientHeight;
    if (!width || !height) return;
    renderer.setPixelRatio(Math.min(devicePixelRatio, CONFIG.maxDpr));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  function render(now: number) {
    if (disposed || !visible || document.hidden) {
      frame = 0;
      return;
    }
    const delta = Math.min((now - last) / 1000, 0.05);
    last = now;
    elapsed += delta;
    controls.update();
    if (animated)
      uniforms.uScan.value = ((elapsed * CONFIG.scanSpeed) % 14) - 7;
    markerPoints.forEach((point, index) => {
      const element = markers[index];
      if (!element) return;
      projection.copy(point).project(camera);
      element.dataset.visible = String(
        projection.z > -1 &&
          projection.z < 1 &&
          Math.abs(projection.x) < 0.94 &&
          Math.abs(projection.y) < 0.94,
      );
      element.style.transform = `translate3d(${((projection.x + 1) * canvas.clientWidth) / 2}px, ${((1 - projection.y) * canvas.clientHeight) / 2}px, 0) translate(-50%, -50%)`;
    });
    renderer.render(scene, camera);
    canvas.dataset.ready = "true";
    frame = requestAnimationFrame(render);
  }
  function resume() {
    if (!frame && visible && !document.hidden && !disposed) {
      last = performance.now();
      frame = requestAnimationFrame(render);
    }
  }
  const observer = new IntersectionObserver(
    ([entry]) => {
      visible = entry.isIntersecting;
      resume();
    },
    { threshold: 0.05 },
  );
  observer.observe(canvas);
  const sizing = new ResizeObserver(resize);
  sizing.observe(canvas);
  const lost = (event: Event) => {
    event.preventDefault();
    canvas.dataset.ready = "false";
    visible = false;
  };
  canvas.addEventListener("webglcontextlost", lost);
  document.addEventListener("visibilitychange", resume);
  resize();
  const dispose = () => {
    disposed = true;
    controls.dispose();
    cancelAnimationFrame(frame);
    observer.disconnect();
    sizing.disconnect();
    canvas.removeEventListener("webglcontextlost", lost);
    document.removeEventListener("visibilitychange", resume);
    geometry.dispose();
    material.dispose();
    baseGeometry.dispose();
    baseMaterial.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    markers.forEach((element) => {
      if (element) element.dataset.visible = "false";
    });
  };
  return {
    dispose,
    reset: () => controls.reset(),
    zoom: (factor) => {
      const offset = camera.position.clone().sub(controls.target);
      offset.setLength(
        THREE.MathUtils.clamp(
          offset.length() * factor,
          controls.minDistance,
          controls.maxDistance,
        ),
      );
      camera.position.copy(controls.target).add(offset);
      controls.update();
    },
    rotate: (horizontal, vertical = 0) => {
      const spherical = new THREE.Spherical().setFromVector3(
        camera.position.clone().sub(controls.target),
      );
      spherical.theta += horizontal;
      spherical.phi = THREE.MathUtils.clamp(
        spherical.phi + vertical,
        controls.minPolarAngle,
        controls.maxPolarAngle,
      );
      camera.position
        .copy(controls.target)
        .add(new THREE.Vector3().setFromSpherical(spherical));
      controls.update();
    },
  };
}
