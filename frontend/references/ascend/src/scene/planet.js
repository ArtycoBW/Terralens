/* ============================================================
   PLANET — ported verbatim from getlayers-scenes/planet.html into a
   mountable module. A GLTF earth with a day/night-lights/rim/water shader,
   a soft atmosphere halo, three drifting cloud shells, ambient motes, a
   starfield and radar-ping land markers, composited through a bloom +
   corner-flame final pass. The interactive control panel and localStorage
   overrides were dropped; CONFIG defaults are baked in. OrbitControls is
   kept for the auto-rotate plumbing but user input is disabled so the canvas
   never swallows page scroll.

   initPlanet(canvas) builds the scene and returns a cleanup function that
   stops the render loop and releases GL resources.
============================================================ */
import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { GammaCorrectionShader } from 'three/examples/jsm/shaders/GammaCorrectionShader.js'
import { CopyShader } from 'three/examples/jsm/shaders/CopyShader.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export function initPlanet(canvas) {
  const CONFIG = {
    rimColor: '#c1faff',
    rimPower: 2.4,
    nightLights: 10,
    terrainDepth: 0.33,
    terrainShade: 1.3,
    oceanGlint: 0.45,
    oceanDeep: 0.12,
    oceanFlow: 3,
    oceanFlowSpeed: 0.8,
    oceanFlowScale: 2.1,
    glowColor: '#3a6cff',
    glowIntensity: 3.35,
    planetRadius: 1.95,
    spin: 0.03,
    initRotation: 2.07,
    tilt: 0.37,
    autoRotate: 0,
    cloud1Height: 1.005,
    cloud1Opacity: 0.6,
    cloud1Spin: 0.06,
    cloud2Height: 1.03,
    cloud2Opacity: 0.5,
    cloud2Spin: 0.14,
    cloud3Height: 1.075,
    cloud3Opacity: 0.5,
    cloud3Spin: 0.1,
    bgColor: '#040a1e',
    flameColor: '#3a6cff',
    flameColor2: '#c1faff',
    flameAmt: 0.15,
    atmoColor: '#9fc4ff',
    atmoCount: 320,
    atmoSize: 22,
    atmoSpeed: 0.8,
    starColor: '#cfe0ff',
    starCount: 1400,
    starSize: 1.6,
    starFlicker: 1,
    markerColor: '#ffd27a',
    markerCount: 60,
    markerSize: 16,
    markerSpeed: 0.5,
  }

  const LAYERS = { NONE: 0, TORUS_SCENE: 1, BLOOM_SCENE: 2, ENTIRE_SCENE: 3 }
  const Lerp = (a, b, t) => a + (b - a) * t
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

  // Piecewise smoothstep interpolation over keyframe stops [{p, v}] (p ascending).
  function sample(stops, p) {
    if (p <= stops[0].p) return stops[0].v
    for (let i = 1; i < stops.length; i++) {
      if (p <= stops[i].p) {
        const a = stops[i - 1], b = stops[i]
        const t = (p - a.p) / (b.p - a.p)
        const e = t * t * (3 - 2 * t)
        return a.v + (b.v - a.v) * e
      }
    }
    return stops[stops.length - 1].v
  }

  function hexToVec3(hex) {
    const n = parseInt(hex.slice(1), 16)
    return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255)
  }

  const SNOISE = `
    vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
    float snoise(vec3 v){
      const vec2 C = vec2(1.0/6.0, 1.0/3.0); const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
      vec3 i = floor(v + dot(v, C.yyy)); vec3 x0 = v - i + dot(i, C.xxx);
      vec3 g = step(x0.yzx, x0.xyz); vec3 l = 1.0 - g;
      vec3 i1 = min(g.xyz, l.zxy); vec3 i2 = max(g.xyz, l.zxy);
      vec3 x1 = x0 - i1 + 1.0 * C.xxx; vec3 x2 = x0 - i2 + 2.0 * C.xxx; vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;
      i = mod(i, 289.0);
      vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
      float n_ = 1.0/7.0; vec3 ns = n_ * D.wyz - D.xzx;
      vec4 j = p - 49.0 * floor(p * ns.z *ns.z);
      vec4 x_ = floor(j * ns.z); vec4 y_ = floor(j - 7.0 * x_);
      vec4 x = x_ *ns.x + ns.yyyy; vec4 y = y_ *ns.x + ns.yyyy; vec4 h = 1.0 - abs(x) - abs(y);
      vec4 b0 = vec4(x.xy, y.xy); vec4 b1 = vec4(x.zw, y.zw);
      vec4 s0 = floor(b0)*2.0 + 1.0; vec4 s1 = floor(b1)*2.0 + 1.0; vec4 sh = -step(h, vec4(0.0));
      vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy; vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
      vec3 p0 = vec3(a0.xy,h.x); vec3 p1 = vec3(a0.zw,h.y); vec3 p2 = vec3(a1.xy,h.z); vec3 p3 = vec3(a1.zw,h.w);
      vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
      p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
      vec4 m = max(0.5 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0); m = m * m;
      return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
    }`

  const FinalPass = {
    uniforms: {
      iTime: { value: 0 },
      tDiffuse: { value: null }, torusTexture: { value: null }, bloomTexture: { value: null }, haloTexture: { value: null },
      uBg: { value: hexToVec3(CONFIG.bgColor) },
      uFlameA: { value: hexToVec3(CONFIG.flameColor) },
      uFlameB: { value: hexToVec3(CONFIG.flameColor2) },
      uFlameAmt: { value: CONFIG.flameAmt },
    },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }`,
    fragmentShader: `
      uniform float iTime; uniform sampler2D tDiffuse; uniform sampler2D bloomTexture; uniform sampler2D torusTexture; uniform sampler2D haloTexture;
      uniform vec3 uBg; uniform vec3 uFlameA; uniform vec3 uFlameB; uniform float uFlameAmt;
      varying vec2 vUv;
      vec3 warp3d(vec3 pos, float t){ float curv=.8,a=1.9,b=0.7; pos*=2.;
        pos.x+=curv*sin(t+a*pos.y)+t*b; pos.y+=curv*cos(t+a*pos.x);
        pos.y+=curv*sin(t+a*pos.z)+t*b; pos.z+=curv*cos(t+a*pos.y);
        pos.z+=curv*sin(t+a*pos.x)+t*b; pos.x+=curv*cos(t+a*pos.z);
        return 0.5+0.5*cos(pos.xyz+vec3(1,2,4)); }
      void main(){
        vec2 uv = 2.*vUv - 1.;
        vec3 w = pow(warp3d(vec3(uv.x, sin(uv.y), uv.y), iTime*1.5), vec3(1.5));
        vec3 flame = 1.5*uFlameA*w.x; flame*=w.y; flame += uFlameB*w.z;
        flame *= smoothstep(0.25, 1., abs(uv.y));
        float md = smoothstep(-0.7, 1., -uv.y*uv.x); flame *= md*md;
        vec3 bg = uBg * (1.0 - 0.4 * length(uv));
        vec3 halo = texture2D(haloTexture, vUv).xyz;
        gl_FragColor = vec4(bg + flame*uFlameAmt + texture2D(bloomTexture, vUv).xyz + texture2D(torusTexture, vUv).xyz + texture2D(tDiffuse, vUv).xyz + halo, 1.);
      }`,
  }

  /* ---------- RENDERER / SCENE / CAMERA ---------- */
  const renderer = new THREE.WebGL1Renderer({ canvas, antialias: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.outputEncoding = THREE.sRGBEncoding
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.VSMShadowMap
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0x000000)
  const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.1, 200)
  camera.position.set(0, 0, 8)
  camera.layers.enable(LAYERS.TORUS_SCENE); camera.layers.enable(LAYERS.BLOOM_SCENE); camera.layers.enable(LAYERS.ENTIRE_SCENE)
  scene.add(camera)

  const ambient = new THREE.AmbientLight(0xffffff, 1.8); ambient.layers.enable(LAYERS.ENTIRE_SCENE); scene.add(ambient)
  const sun = new THREE.DirectionalLight(0xffffff, 0.8); sun.position.set(0, 10, 2); sun.layers.enable(LAYERS.ENTIRE_SCENE); scene.add(sun)

  /* ---------- COMPOSER ---------- */
  const renderScene = new RenderPass(scene, camera)
  const torusComposer = new EffectComposer(renderer); torusComposer.renderToScreen = false
  torusComposer.addPass(renderScene)
  torusComposer.addPass(new ShaderPass(GammaCorrectionShader))
  torusComposer.addPass(new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 0.22, 0.2, 0))
  torusComposer.addPass(new ShaderPass(CopyShader))
  const bloomComposer = new EffectComposer(renderer); bloomComposer.renderToScreen = false
  bloomComposer.addPass(renderScene)
  bloomComposer.addPass(new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 0.5, 0.6, 0))
  bloomComposer.addPass(new ShaderPass(GammaCorrectionShader))
  const finalPass = new ShaderPass(FinalPass)
  finalPass.uniforms.bloomTexture.value = bloomComposer.renderTarget1.texture
  finalPass.uniforms.torusTexture.value = torusComposer.renderTarget1.texture
  const finalComposer = new EffectComposer(renderer)
  finalComposer.addPass(renderScene); finalComposer.addPass(finalPass)

  /* ---------- ORBIT CONTROLS (input disabled — auto-spin only) ---------- */
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true; controls.dampingFactor = 0.06
  controls.enablePan = false
  controls.enabled = false               // landing hero: never capture pointer / scroll
  controls.autoRotate = true; controls.autoRotateSpeed = CONFIG.autoRotate
  controls.minDistance = 3.5; controls.maxDistance = 16
  controls.target.set(0, 0, 0)

  /* ---------- PLANET ASSEMBLY ----------
     worldGroup is the scroll-driven parent: it carries the globe, the clouds
     and the atmosphere halo together so scroll can translate + scale the whole
     planet as one. It only ever gets position + uniform scale (never rotation),
     so the halo's camera-billboard stays valid. */
  const worldGroup = new THREE.Group()
  scene.add(worldGroup)
  const planetGroup = new THREE.Group()
  planetGroup.rotation.z = CONFIG.tilt
  worldGroup.add(planetGroup)
  const cloudGroup = new THREE.Group()
  cloudGroup.rotation.z = CONFIG.tilt
  cloudGroup.visible = false
  worldGroup.add(cloudGroup)
  const planetTime = { value: 0 }
  const cloudTime = { value: 0 }
  let planetMat = null
  let cloudMat = null
  let glowMat = null
  let glowMesh = null
  let spinPhase = 0
  let entryActive = false
  let entryT = 0
  const ENTRY_DUR = 1.9
  const ENTRY_START_Y = -6.5

  /* ---------- SCROLL STORYTELLING ----------
     Scroll progress (0..1 down the page) drives the planet's position + scale
     through keyframe stops. Beat 0 = hero: a huge globe, low, half below the
     fold. Then it zooms out and swings side to side (left → right) before
     settling near the final CTA. Targets are damped per-frame for smoothness. */
  const STOPS_X = [{ p: 0, v: 0 }, { p: 0.32, v: -3.1 }, { p: 0.64, v: 3.2 }, { p: 1, v: 0 }]
  // hero globe sits low (more sky above it); nudged a further ~5% of the viewport down
  const STOPS_Y = [{ p: 0, v: -4.5 }, { p: 0.32, v: 0.55 }, { p: 0.64, v: 0.45 }, { p: 1, v: 0.15 }]
  const STOPS_S = [{ p: 0, v: 2.15 }, { p: 0.32, v: 1.0 }, { p: 0.64, v: 0.92 }, { p: 1, v: 1.12 }]
  let curX = STOPS_X[0].v, curY = STOPS_Y[0].v, curS = STOPS_S[0].v, curP = 0
  worldGroup.position.set(curX, curY, 0)
  worldGroup.scale.setScalar(curS)

  function firstMesh(obj) {
    let found = null
    obj.traverse(o => { if (!found && o.isMesh) found = o })
    return found
  }

  function applyPlanetShader(material, nightTex) {
    material.onBeforeCompile = (shader) => {
      shader.uniforms.time = planetTime
      shader.uniforms.noiseScale = { value: 30.0 }
      shader.uniforms.speedX = { value: 1.5 }
      shader.uniforms.speedY = { value: 2.0 }
      shader.uniforms.speedZ = { value: 2.5 }
      shader.uniforms.rimColor = { value: hexToVec3(CONFIG.rimColor) }
      shader.uniforms.rimPower = { value: CONFIG.rimPower }
      shader.uniforms.nightBlendTexture = { value: nightTex }
      shader.uniforms.nightLights = { value: CONFIG.nightLights }
      shader.uniforms.terrainDepth = { value: CONFIG.terrainDepth }
      shader.uniforms.terrainShade = { value: CONFIG.terrainShade }
      shader.uniforms.oceanGlint = { value: CONFIG.oceanGlint }
      shader.uniforms.oceanDeep = { value: CONFIG.oceanDeep }
      shader.uniforms.oceanFlow = { value: CONFIG.oceanFlow }
      shader.uniforms.oceanFlowSpeed = { value: CONFIG.oceanFlowSpeed }
      shader.uniforms.oceanFlowScale = { value: CONFIG.oceanFlowScale }
      planetMat.userData.shader = shader
      shader.vertexShader = `varying vec2 vCustomUv;\n` + shader.vertexShader
      shader.vertexShader = shader.vertexShader.replace('void main() {', 'void main() {\n  vCustomUv = uv;')
      shader.fragmentShader = `
        uniform float time; uniform float noiseScale; uniform float speedX; uniform float speedY; uniform float speedZ;
        uniform vec3 rimColor; uniform float rimPower; uniform sampler2D nightBlendTexture; uniform float nightLights;
        uniform float terrainDepth; uniform float terrainShade;
        uniform float oceanGlint; uniform float oceanDeep; uniform float oceanFlow;
        uniform float oceanFlowSpeed; uniform float oceanFlowScale;
        varying vec2 vCustomUv;
        ${SNOISE}
      ` + shader.fragmentShader
      shader.fragmentShader = shader.fragmentShader.replace('#include <dithering_fragment>', `#include <dithering_fragment>
        vec3 normalizedNormal = normalize(vNormal);
        vec3 viewDir = normalize(vViewPosition);
        float rim = 1.0 - max(dot(viewDir, normalizedNormal), 0.0);
        rim = pow(rim, rimPower); rim = pow(rim, 1.5); rim *= 0.7;
        vec3 currentColor = gl_FragColor.rgb;
        float blueDom = currentColor.b - max(currentColor.r, currentColor.g);
        float waterMask = clamp(smoothstep(-0.005, 0.03, blueDom), 0.0, 1.0);
        float shimmer = snoise(vec3(vCustomUv.x * noiseScale + time * speedX, vCustomUv.y * noiseScale - time * speedY, time * speedZ));
        gl_FragColor.rgb += waterMask * shimmer * 0.025;
        float fT = time * oceanFlowSpeed * 4.0;
        float fS = 4.0 * oceanFlowScale;
        float warp = snoise(vec3(vCustomUv.x * fS - fT * 0.5, vCustomUv.y * fS + fT * 0.4, fT * 0.5));
        float flow = snoise(vec3(vCustomUv.x * fS * 2.0 + fT * 0.6 + warp, vCustomUv.y * fS * 2.0 - fT * 0.5, fT * 0.7));
        flow = warp * 0.6 + flow * 0.4;
        gl_FragColor.rgb += waterMask * flow * 0.12 * oceanFlow;
        gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.01, 0.06, 0.16), waterMask * oceanDeep);
        vec3 finalColor = mix(gl_FragColor.rgb, rimColor, rim);
        gl_FragColor = vec4(finalColor, 1.0);
        vec3 surfPos = -vViewPosition;
        float terrH = dot(texture2D(map, vCustomUv).rgb, vec3(0.299, 0.587, 0.114));
        vec3 sigX = dFdx(surfPos), sigY = dFdy(surfPos);
        vec3 vR1 = cross(sigY, normalizedNormal), vR2 = cross(normalizedNormal, sigX);
        float fDet = dot(sigX, vR1);
        vec3 vGrad = sign(fDet) * (dFdx(terrH) * vR1 + dFdy(terrH) * vR2);
        vec3 bumpedNormal = normalize(abs(fDet) * normalizedNormal - terrainDepth * vGrad);
        vec3 shadeNormal = mix(bumpedNormal, normalizedNormal, waterMask);
        vec3 cityLights = texture2D(nightBlendTexture, vCustomUv).rgb * gl_FragColor.rgb * nightLights;
        vec3 viewSunDir = normalize(vec3(-0.9, 0.18, 0.4));
        float ndl = dot(normalizedNormal, viewSunDir);
        float dayAmt = smoothstep(-0.05, 0.35, ndl);
        float relief = dot(shadeNormal, viewSunDir) - ndl;
        gl_FragColor.rgb *= clamp(1.0 + relief * terrainShade * dayAmt, 0.55, 1.6);
        float nightFactor  = smoothstep(0.18, -0.30, ndl);
        float lightsFactor = smoothstep(0.30, -0.35, ndl);
        gl_FragColor.rgb = mix(gl_FragColor.rgb, gl_FragColor.rgb * 0.08, nightFactor);
        gl_FragColor.rgb += cityLights * lightsFactor;
        vec3 halfDir = normalize(viewSunDir + viewDir);
        float ripple = snoise(vec3(vCustomUv * 240.0, time * 4.0));
        float ndh = max(dot(normalizedNormal, halfDir) + ripple * 0.02, 0.0);
        float glint = pow(ndh, 140.0);
        gl_FragColor.rgb += glint * waterMask * dayAmt * oceanGlint * vec3(1.0, 0.97, 0.88);
      `)
    }
    material.needsUpdate = true
  }

  function addAtmosphereGlow(radius) {
    const g = new THREE.PlaneGeometry(2, 2)
    glowMat = new THREE.ShaderMaterial({
      transparent: true, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uGlow: { value: hexToVec3(CONFIG.glowColor) }, uIntensity: { value: CONFIG.glowIntensity } },
      vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `uniform vec3 uGlow; uniform float uIntensity; varying vec2 vUv;
        void main(){
          float d = length(vUv - 0.5) * 2.0;
          float a = pow(clamp(1.0 - d, 0.0, 1.0), 2.2);
          gl_FragColor = vec4(uGlow * a * uIntensity, a);
        }`,
    })
    glowMesh = new THREE.Mesh(g, glowMat)
    glowMesh.scale.setScalar(radius * 2.3)
    glowMesh.layers.enable(LAYERS.ENTIRE_SCENE)
    worldGroup.add(glowMesh)
  }

  const CLOUD_LAYERS = [
    { hKey: 'cloud1Height', oKey: 'cloud1Opacity', sKey: 'cloud1Spin', ry: 0.0, phase: 0.0 },
    { hKey: 'cloud2Height', oKey: 'cloud2Opacity', sKey: 'cloud2Spin', ry: 2.2, phase: 13.0 },
    { hKey: 'cloud3Height', oKey: 'cloud3Opacity', sKey: 'cloud3Spin', ry: 4.3, phase: 27.0 },
  ]
  const cloudMeshes = []
  function addClouds() {
    const tex = new THREE.TextureLoader().load('/assets/planet-clouds.png')
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping
    tex.repeat.set(5, 5)
    for (const layer of CLOUD_LAYERS) {
      const g = new THREE.SphereGeometry(CONFIG.planetRadius * CONFIG[layer.hKey], 64, 64)
      const mat = new THREE.MeshStandardMaterial({ map: tex, transparent: true, depthWrite: false })
      mat.onBeforeCompile = (shader) => {
        shader.uniforms.uTime = cloudTime
        shader.uniforms.noiseScale = { value: 20.0 }
        shader.uniforms.uSpeedX = { value: 1.0 }
        shader.uniforms.uSpeedY = { value: 2.0 }
        shader.uniforms.uSpeedZ = { value: 2.0 }
        shader.uniforms.uOpacity = { value: CONFIG[layer.oKey] }
        shader.uniforms.uPhase = { value: layer.phase }
        mat.userData.shader = shader
        shader.vertexShader = `varying vec2 vCloudUv;\n` + shader.vertexShader
        shader.vertexShader = shader.vertexShader.replace('void main() {', 'void main() {\n  vCloudUv = uv;')
        shader.fragmentShader = `
          uniform float uTime; uniform float noiseScale; uniform float uSpeedX; uniform float uSpeedY; uniform float uSpeedZ; uniform float uOpacity; uniform float uPhase;
          varying vec2 vCloudUv;
          ${SNOISE}
        ` + shader.fragmentShader
        shader.fragmentShader = shader.fragmentShader.replace('#include <dithering_fragment>', `#include <dithering_fragment>
          gl_FragColor.rgb = vec3(1.0);
          float cloudNoise = snoise(vec3(vCloudUv.x * noiseScale + uTime * uSpeedX + uPhase, vCloudUv.y * noiseScale - uTime * uSpeedY + uPhase, uTime * uSpeedZ + uPhase));
          float cloudNdv = max(dot(normalize(vNormal), normalize(vViewPosition)), 0.0);
          float cloudEdge = pow(1.0 - cloudNdv, 3.0);
          float cloudMod = mix(cloudNoise, 1.0, cloudEdge);
          float cloudNdl = dot(normalize(vNormal), normalize(vec3(-0.9, 0.18, 0.4)));
          float cloudDay = 1.0 - smoothstep(0.30, -0.30, cloudNdl) * 0.9;
          gl_FragColor.a *= cloudMod * uOpacity * cloudDay;
        `)
      }
      mat.needsUpdate = true
      if (!cloudMat) cloudMat = mat
      const clouds = new THREE.Mesh(g, mat)
      clouds.rotation.y = layer.ry
      clouds.renderOrder = 2
      clouds.layers.enable(LAYERS.ENTIRE_SCENE)
      cloudGroup.add(clouds)
      cloudMeshes.push({ mesh: clouds, layer, phase: layer.ry })
    }
  }
  addClouds()

  const draco = new DRACOLoader()
  draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.5/')
  const gltfLoader = new GLTFLoader(); gltfLoader.setDRACOLoader(draco)

  function loadPlanet() {
    gltfLoader.load('/assets/planet-lights.glb', (lights) => {
      const lmesh = firstMesh(lights.scene)
      const nightTex = lmesh && lmesh.material && lmesh.material.map ? lmesh.material.map : null
      gltfLoader.load('/assets/planet.glb', (gltf) => {
        const mesh = firstMesh(gltf.scene)
        if (!mesh) return
        mesh.geometry.computeBoundingSphere()
        const r = mesh.geometry.boundingSphere ? mesh.geometry.boundingSphere.radius : 1
        const s = CONFIG.planetRadius / r
        planetMat = mesh.material.clone()
        planetMat.metalness = 0.0
        planetMat.roughness = 1.0
        planetMat.envMapIntensity = 0.0
        applyPlanetShader(planetMat, nightTex)
        const planet = new THREE.Mesh(mesh.geometry, planetMat)
        planet.scale.setScalar(s)
        planet.layers.enable(LAYERS.ENTIRE_SCENE)
        planetGroup.add(planet)
        addMarkers(planet)
        addAtmosphereGlow(CONFIG.planetRadius)
        cloudGroup.visible = true
        entryActive = true; entryT = 0
      })
    })
  }
  loadPlanet()

  /* ---------- ambient atmosphere particles ---------- */
  let atmoMat = null
  const atmoPts = (function () {
    const N = Math.round(CONFIG.atmoCount)
    const positions = new Float32Array(N * 3), sizes = new Float32Array(N), seeds = new Float32Array(N)
    for (let i = 0; i < N; i++) {
      positions[i * 3] = 2 * Math.random() - 1; positions[i * 3 + 1] = 2 * Math.random() - 1; positions[i * 3 + 2] = 2 * Math.random() - 1
      sizes[i] = CONFIG.atmoSize * (0.4 + Math.random()); seeds[i] = Math.random()
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    g.setAttribute('size', new THREE.Float32BufferAttribute(sizes, 1))
    g.setAttribute('seed', new THREE.Float32BufferAttribute(seeds, 1))
    atmoMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 }, uColor: { value: hexToVec3(CONFIG.atmoColor) },
        uRes: { value: new THREE.Vector2(window.innerWidth * window.devicePixelRatio, window.innerHeight * window.devicePixelRatio) },
      },
      vertexShader: `
        attribute float size; attribute float seed; uniform float uTime; uniform vec2 uRes;
        varying float vA;
        vec3 warp(vec3 p, float t){ float c=0.9,a=1.9,b=0.02,s=0.05; p*=2.;
          p.x+=c*sin(s*t+a*p.y)+t*b; p.y+=c*cos(s*t+a*p.x); p.y+=c*sin(s*t+a*p.z)+t*b;
          p.z+=c*cos(s*t+a*p.y); p.z+=c*sin(s*t+a*p.x)+t*b; p.x+=c*cos(s*t+a*p.z);
          return cos(p+vec3(1,2,4)); }
        void main(){
          vec3 v = position*4.0 + warp(position, uTime)*1.2;
          vec4 mv = modelViewMatrix * vec4(v, 1.0);
          float r = length(v); float farF = 1.0 - smoothstep(5.0, 6.5, r); float nearF = smoothstep(0.0, 0.5, -mv.z);
          vA = farF * nearF;
          gl_PointSize = size * uRes.y / 900.0 / -mv.z; gl_PointSize = max(gl_PointSize, 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform vec3 uColor; varying float vA;
        void main(){ vec2 p = gl_PointCoord - 0.5; float l = length(p); if (l > 0.5) discard;
          float tex = smoothstep(0.5, 0.0, l); gl_FragColor = vec4(uColor * tex, tex * vA * 0.55); }`,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false,
    })
    const pts = new THREE.Points(g, atmoMat)
    pts.frustumCulled = false
    pts.layers.enable(LAYERS.ENTIRE_SCENE)
    scene.add(pts)
    pts.onBeforeRender = () => {
      const t = performance.now() / 1000
      atmoMat.uniforms.uTime.value = t * CONFIG.atmoSpeed * 8.0
      pts.position.copy(camera.position)
      finalPass.uniforms.iTime.value = t
    }
    return pts
  })()

  /* ---------- STARFIELD ---------- */
  const starTime = { value: 0 }
  let starMat = null
  function addStars() {
    const COUNT = Math.max(0, Math.floor(CONFIG.starCount))
    const R = 90
    const pos = new Float32Array(COUNT * 3)
    const seed = new Float32Array(COUNT)
    const bright = new Float32Array(COUNT)
    for (let i = 0; i < COUNT; i++) {
      const u = Math.random() * 2 - 1
      const th = Math.random() * Math.PI * 2
      const r = Math.sqrt(1 - u * u)
      pos[i * 3] = R * r * Math.cos(th)
      pos[i * 3 + 1] = R * u
      pos[i * 3 + 2] = R * r * Math.sin(th)
      seed[i] = Math.random() * 6.2831853
      bright[i] = 0.35 + Math.random() * 0.65
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    geo.setAttribute('seed', new THREE.Float32BufferAttribute(seed, 1))
    geo.setAttribute('bright', new THREE.Float32BufferAttribute(bright, 1))
    starMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: starTime, uSize: { value: CONFIG.starSize }, uFlicker: { value: CONFIG.starFlicker },
        uColor: { value: hexToVec3(CONFIG.starColor) },
        uRes: { value: new THREE.Vector2(window.innerWidth * window.devicePixelRatio, window.innerHeight * window.devicePixelRatio) },
      },
      vertexShader: `
        attribute float seed; attribute float bright;
        uniform float uTime; uniform float uSize; uniform float uFlicker; uniform vec2 uRes;
        varying float vTw;
        void main(){
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          float tw = 0.6 + 0.4 * sin(uTime * uFlicker + seed);
          vTw = bright * tw;
          gl_PointSize = max(uSize * uRes.y / 900.0 * (90.0 / max(-mv.z, 1.0)), 1.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform vec3 uColor; varying float vTw;
        void main(){
          vec2 p = gl_PointCoord - 0.5; float l = length(p); if (l > 0.5) discard;
          float core = smoothstep(0.5, 0.0, l);
          gl_FragColor = vec4(uColor, core * vTw);
        }`,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: true,
    })
    const stars = new THREE.Points(geo, starMat)
    stars.frustumCulled = false
    stars.layers.enable(LAYERS.ENTIRE_SCENE)
    scene.add(stars)
  }
  addStars()

  /* ---------- LOCATION MARKERS ---------- */
  let markerMat = null
  const markerTime = { value: 0 }
  function addMarkers(planetMesh) {
    const tex = planetMat && planetMat.map
    if (!tex || !tex.image) return
    const img = tex.image
    const W = Math.min(img.width || 1024, 1024), H = Math.min(img.height || 512, 512)
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H
    const cctx = cv.getContext('2d'); cctx.drawImage(img, 0, 0, W, H)
    let px
    try { px = cctx.getImageData(0, 0, W, H).data } catch (e) { return }
    const geom = planetMesh.geometry
    const pos = geom.attributes.position, uv = geom.attributes.uv
    if (!uv) return
    const index = geom.index
    const triCount = index ? (index.count / 3) : (pos.count / 3)
    const triIdx = (t, k) => index ? index.getX(t * 3 + k) : (t * 3 + k)
    const cum = new Float32Array(triCount)
    const A = new THREE.Vector3(), B = new THREE.Vector3(), C = new THREE.Vector3(), e1 = new THREE.Vector3(), e2 = new THREE.Vector3()
    let total = 0
    for (let t = 0; t < triCount; t++) {
      A.fromBufferAttribute(pos, triIdx(t, 0)); B.fromBufferAttribute(pos, triIdx(t, 1)); C.fromBufferAttribute(pos, triIdx(t, 2))
      e1.subVectors(B, A); e2.subVectors(C, A)
      total += e1.cross(e2).length() * 0.5
      cum[t] = total
    }
    const pickTri = () => {
      const rnd = Math.random() * total
      let lo = 0, hi = triCount - 1
      while (lo < hi) { const m = (lo + hi) >> 1; if (cum[m] < rnd) lo = m + 1; else hi = m }
      return lo
    }
    const want = Math.max(0, Math.floor(CONFIG.markerCount))
    const positions = [], seeds = []
    const lift = 1.012
    const uvA = new THREE.Vector2(), uvB = new THREE.Vector2(), uvC = new THREE.Vector2()
    let attempts = 0, maxAtt = want * 400 + 2000
    while (positions.length / 3 < want && attempts < maxAtt) {
      attempts++
      const t = pickTri()
      const i0 = triIdx(t, 0), i1 = triIdx(t, 1), i2 = triIdx(t, 2)
      let r1 = Math.random(), r2 = Math.random()
      if (r1 + r2 > 1) { r1 = 1 - r1; r2 = 1 - r2 }
      const w0 = 1 - r1 - r2, w1 = r1, w2 = r2
      uvA.fromBufferAttribute(uv, i0); uvB.fromBufferAttribute(uv, i1); uvC.fromBufferAttribute(uv, i2)
      const u = uvA.x * w0 + uvB.x * w1 + uvC.x * w2
      const vv = uvA.y * w0 + uvB.y * w1 + uvC.y * w2
      const sx = Math.min(W - 1, Math.max(0, (u * W) | 0))
      const sy = Math.min(H - 1, Math.max(0, ((1 - vv) * H) | 0))
      const o = (sy * W + sx) * 4
      const cr = px[o], cg = px[o + 1], cb = px[o + 2]
      if (cb > cr + 6 && cb > cg + 6) continue
      A.fromBufferAttribute(pos, i0); B.fromBufferAttribute(pos, i1); C.fromBufferAttribute(pos, i2)
      positions.push((A.x * w0 + B.x * w1 + C.x * w2) * lift, (A.y * w0 + B.y * w1 + C.y * w2) * lift, (A.z * w0 + B.z * w1 + C.z * w2) * lift)
      seeds.push(Math.random())
    }
    if (!positions.length) return
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    g.setAttribute('seed', new THREE.Float32BufferAttribute(seeds, 1))
    markerMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: markerTime, uColor: { value: hexToVec3(CONFIG.markerColor) },
        uSize: { value: CONFIG.markerSize }, uSpeed: { value: CONFIG.markerSpeed },
        uRes: { value: new THREE.Vector2(window.innerWidth * window.devicePixelRatio, window.innerHeight * window.devicePixelRatio) },
      },
      vertexShader: `
        attribute float seed; uniform float uSize; uniform vec2 uRes;
        varying float vSeed; varying float vFade;
        void main(){
          vSeed = seed;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vec3 vn = normalize(normalMatrix * normalize(position));
          vec3 vd = normalize(-mv.xyz);
          vFade = smoothstep(0.15, 0.5, dot(vn, vd));
          gl_PointSize = max(uSize * uRes.y / 900.0 * (7.0 / max(-mv.z, 1.0)), 2.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform vec3 uColor; uniform float uTime; uniform float uSpeed;
        varying float vSeed; varying float vFade;
        void main(){
          if (vFade <= 0.001) discard;
          vec2 p = gl_PointCoord - 0.5;
          float d = length(p) * 2.0;
          if (d > 1.0) discard;
          float core = smoothstep(0.30, 0.0, d) * 1.2;
          float ph = fract(uTime * uSpeed + vSeed);
          float ring = smoothstep(0.07, 0.0, abs(d - ph)) * (1.0 - ph);
          gl_FragColor = vec4(uColor, clamp(core + ring, 0.0, 1.0) * vFade);
        }`,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: true,
    })
    const marks = new THREE.Points(g, markerMat)
    marks.frustumCulled = false
    marks.layers.enable(LAYERS.ENTIRE_SCENE)
    planetMesh.add(marks)
  }

  /* ---------- RESIZE ---------- */
  function resize() {
    const w = window.innerWidth, h = window.innerHeight, dpr = window.devicePixelRatio
    renderer.setPixelRatio(dpr); renderer.setSize(w, h, false)
    camera.aspect = w / h; camera.updateProjectionMatrix()
    for (const c of [torusComposer, bloomComposer, finalComposer]) { c.setPixelRatio(dpr); c.setSize(w, h) }
    if (atmoMat) atmoMat.uniforms.uRes.value.set(w * dpr, h * dpr)
    if (starMat) starMat.uniforms.uRes.value.set(w * dpr, h * dpr)
    if (markerMat) markerMat.uniforms.uRes.value.set(w * dpr, h * dpr)
  }
  window.addEventListener('resize', resize); resize()

  /* ---------- RENDER LOOP ---------- */
  let raf = 0
  let disposed = false
  let t0 = performance.now() / 1000
  function render() {
    if (disposed) return
    raf = requestAnimationFrame(render)
    const t = performance.now() / 1000
    const dt = Math.min(0.05, t - t0); t0 = t
    planetTime.value += dt / 12
    cloudTime.value += dt / 20
    starTime.value += dt
    markerTime.value += dt
    spinPhase += dt * CONFIG.spin
    for (const cl of cloudMeshes) { cl.phase += dt * CONFIG[cl.layer.sKey]; cl.mesh.rotation.y = cl.phase }

    // --- scroll-driven framing ---
    const maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
    const pTarget = clamp(window.scrollY / maxScroll, 0, 1)
    curP += (pTarget - curP) * Math.min(1, dt * 4.5)
    // less lateral travel on narrow screens so the planet never leaves frame entirely
    const sideScale = clamp(window.innerWidth / 1200, 0.5, 1)
    const tx = sample(STOPS_X, curP) * sideScale
    const ty = sample(STOPS_Y, curP)
    const ts = sample(STOPS_S, curP)
    const k = Math.min(1, dt * 3.2)
    curX += (tx - curX) * k; curY += (ty - curY) * k; curS += (ts - curS) * k

    // one-time float-up entrance, applied on top of the scroll target
    let entryY = 0
    if (entryActive) {
      entryT = Math.min(1, entryT + dt / ENTRY_DUR)
      const e = 1 - Math.pow(1 - entryT, 3)
      entryY = Lerp(ENTRY_START_Y, 0, e)
      if (entryT >= 1) entryActive = false
    }
    worldGroup.position.set(curX, curY + entryY, 0)
    worldGroup.scale.setScalar(curS)
    // base auto-spin + extra rotation coupled to scroll progress (the "turn")
    planetGroup.rotation.y = CONFIG.initRotation + spinPhase + curP * Math.PI * 1.6

    controls.update()
    if (glowMesh) glowMesh.quaternion.copy(camera.quaternion)

    camera.layers.set(LAYERS.TORUS_SCENE); torusComposer.render()
    camera.layers.set(LAYERS.BLOOM_SCENE); bloomComposer.render()
    camera.layers.set(LAYERS.ENTIRE_SCENE); finalComposer.render()
  }
  render()

  /* ---------- CLEANUP ---------- */
  return function cleanup() {
    disposed = true
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
    controls.dispose()
    torusComposer.dispose?.()
    bloomComposer.dispose?.()
    finalComposer.dispose?.()
    renderer.dispose()
    scene.traverse(o => {
      if (o.geometry) o.geometry.dispose()
      if (o.material) {
        const mats = Array.isArray(o.material) ? o.material : [o.material]
        mats.forEach(m => { m.map?.dispose?.(); m.dispose?.() })
      }
    })
  }
}
