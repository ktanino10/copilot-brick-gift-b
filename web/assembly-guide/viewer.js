import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { indexGuide, insertionPose, stepRange } from './model.js';

const $ = (s) => document.querySelector(s);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const fmt = (numbers) => numbers.map((n) => Number(n.toFixed(2))).join(' × ');
let data, index, plateView, assemblyView;
const geometries = new Map();
const state = { cursor: 0, empty: true, progress: 0, playing: false, playUntil: 0, slot: null, target: null, mode: 'build', ghost: true };

function fail(error) {
  state.playing = false;
  $('#loading').hidden = true;
  $('#guide-error').hidden = false;
  $('#guide-error').textContent = `3Dガイドを開始・継続できません: ${error.message || error}`;
  $('#guide-app').dataset.ready = 'error';
  console.error(error);
}

function button(text, action, className = '') {
  const node = document.createElement('button');
  node.type = 'button';
  node.textContent = text;
  node.className = className;
  node.addEventListener('click', () => {
    try { action(); } catch (error) { fail(error); }
  });
  return node;
}

function partMaterial(part, color) {
  return new THREE.MeshStandardMaterial({
    color: part.finish_color ? 0xffffff : data.colors[color].hex,
    vertexColors: Boolean(part.finish_color), roughness: .61, metalness: .02,
  });
}

function styleMesh(mesh, ghost, selected) {
  const style = `${ghost}:${selected}`;
  if (mesh.userData.materialStyle === style) return;
  mesh.userData.materialStyle = style;
  const part = data.parts[mesh.userData.part];
  const material = mesh.material;
  material.vertexColors = !ghost && Boolean(part.finish_color);
  material.color.set(ghost ? '#9eaeb3' : part.finish_color ? '#ffffff' : data.colors[mesh.userData.color].hex);
  material.transparent = ghost;
  material.opacity = ghost ? .18 : 1;
  material.depthWrite = !ghost;
  material.emissive.set(selected ? '#0a444b' : '#000000');
  material.emissiveIntensity = selected ? .38 : 0;
  material.needsUpdate = true;
}

class SceneView {
  constructor(name, onPick) {
    this.name = name;
    this.canvas = $(`#${name}-canvas`);
    this.container = $(`#${name}-viewport`);
    this.labelContainer = $(`#${name}-labels`);
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    this.renderer.setClearColor('#eaf0f1');
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-150, 150, 150, -150, .1, 4000);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = false;
    this.controls.minZoom = .2;
    this.controls.maxZoom = 12;
    this.controls.addEventListener('change', () => { this.dirty = true; });
    this.scene.add(new THREE.HemisphereLight(0xf5fbff, 0x56656d, 2.5));
    for (const [position, strength] of [[[-220, -320, 480], 3.4], [[250, 180, 140], 1.8], [[0, -200, -100], 1.1]]) {
      const light = new THREE.DirectionalLight(0xffffff, strength);
      light.position.set(...position);
      this.scene.add(light);
    }
    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.meshes = [];
    this.labels = [];
    this.bounds = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(256, 256, 40));
    this.direction = 'iso';
    this.raycaster = new THREE.Raycaster();
    this.selection = new THREE.Box3Helper(new THREE.Box3(), 0xd4542e);
    this.selection.visible = false;
    this.scene.add(this.selection);
    this.canvas.addEventListener('pointerdown', (event) => { this.pointer = [event.clientX, event.clientY]; });
    this.canvas.addEventListener('pointerup', (event) => {
      if (!this.pointer || Math.hypot(event.clientX - this.pointer[0], event.clientY - this.pointer[1]) > 5) return;
      const rect = this.canvas.getBoundingClientRect();
      this.raycaster.setFromCamera(new THREE.Vector2(
        (event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.camera);
      const hit = this.raycaster.intersectObjects(this.meshes.filter((mesh) => mesh.visible), false)[0];
      if (hit) onPick(hit.object.userData.id);
    });
    this.canvas.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const offset = this.camera.position.clone().sub(this.controls.target);
      offset.applyAxisAngle(new THREE.Vector3(0, 0, 1), event.key === 'ArrowLeft' ? -.14 : .14);
      this.camera.position.copy(this.controls.target).add(offset);
      this.controls.update();
    });
    this.canvas.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      fail(new Error('WebGLが停止しました。ガイドを閉じて開き直してください。'));
    });
    new ResizeObserver(() => this.fit(false)).observe(this.container);
    this.dirty = true;
  }

  clear() {
    for (const mesh of this.meshes) mesh.material.dispose();
    this.meshes = [];
    this.root.clear();
    this.labels = [];
    this.labelContainer.replaceChildren();
    this.selection.visible = false;
  }

  add(part, color, id, position, rotation = [0, 0, 0]) {
    const mesh = new THREE.Mesh(geometries.get(part), partMaterial(data.parts[part], color));
    mesh.userData = { id, part, color };
    mesh.name = id;
    mesh.position.fromArray(position);
    mesh.rotation.set(...rotation.map(THREE.MathUtils.degToRad));
    this.root.add(mesh);
    this.meshes.push(mesh);
    return mesh;
  }

  addLabel(mesh, text, action) {
    const node = button(text, action, 'mesh-label');
    node.setAttribute('aria-label', `${this.name === 'plate' ? 'プレート内slot' : '組立位置'} ${text}`);
    this.labelContainer.append(node);
    this.labels.push({ mesh, node });
    return node;
  }

  setView(name) {
    const directions = {
      iso: [.85, -1.6, 1.4], front: [0, -1, .035], side: [1, 0, .035],
      top: [0, -.001, 1], back: [0, 1, .035], bottom: [0, -.001, -1],
    };
    if (!directions[name]) throw new Error('Unknown viewing direction');
    this.direction = name;
    const center = this.bounds.getCenter(new THREE.Vector3());
    this.camera.position.copy(center).add(new THREE.Vector3(...directions[name]).normalize().multiplyScalar(900));
    this.controls.target.copy(center);
    this.camera.lookAt(center);
    this.controls.update();
    this.fit(true);
    for (const btn of document.querySelectorAll(`.view-tools[data-scene="${this.name}"] button`)) {
      btn.setAttribute('aria-pressed', String(btn.dataset.view === name));
    }
  }

  fit(resetZoom) {
    const rect = this.container.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return;
    this.renderer.setSize(rect.width, rect.height, false);
    const center = this.bounds.getCenter(new THREE.Vector3());
    const offset = this.camera.position.clone().sub(this.controls.target);
    if (offset.length() < 1) offset.set(450, -850, 650);
    this.controls.target.copy(center);
    this.camera.position.copy(center).add(offset);
    this.camera.lookAt(center);
    this.camera.updateMatrixWorld();
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    const v = new THREE.Vector3();
    for (const x of [this.bounds.min.x, this.bounds.max.x]) for (const y of [this.bounds.min.y, this.bounds.max.y])
      for (const z of [this.bounds.min.z, this.bounds.max.z]) {
        v.set(x, y, z).applyMatrix4(this.camera.matrixWorldInverse);
        minX = Math.min(minX, v.x); maxX = Math.max(maxX, v.x);
        minY = Math.min(minY, v.y); maxY = Math.max(maxY, v.y);
      }
    const aspect = rect.width / rect.height;
    const height = Math.max(22, maxY - minY, (maxX - minX) / aspect) * 1.26;
    this.camera.left = -height * aspect / 2;
    this.camera.right = height * aspect / 2;
    this.camera.top = height / 2;
    this.camera.bottom = -height / 2;
    if (resetZoom) this.camera.zoom = 1;
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.dirty = true;
  }

  draw() {
    if (!this.dirty) return;
    this.scene.updateMatrixWorld(true);
    this.renderer.render(this.scene, this.camera);
    const width = this.container.clientWidth, height = this.container.clientHeight;
    for (const { mesh, node } of this.labels) {
      node.hidden = !mesh.visible;
      if (!mesh.visible) continue;
      const local = geometries.get(mesh.userData.part).boundingBox;
      const point = local.getCenter(new THREE.Vector3());
      point.z = local.max.z + 3;
      point.applyMatrix4(mesh.matrixWorld).project(this.camera);
      node.hidden = point.z < -1 || point.z > 1 || Math.abs(point.x) > 1 || Math.abs(point.y) > 1;
      node.style.left = `${(point.x * .5 + .5) * width}px`;
      node.style.top = `${(-point.y * .5 + .5) * height}px`;
      node.classList.toggle('selected', mesh.userData.id === (this.name === 'plate' ? state.slot : state.target));
    }
    this.dirty = false;
  }
}

function selectedSlot() { return index.slots.get(state.slot); }
function activePlacement() { return state.empty ? null : data.placements[state.cursor] || null; }
function activeStep() { return state.empty ? 0 : activePlacement()?.step || data.steps.length; }
function activeSeated() { return Boolean(activePlacement()) && state.progress === 1; }
function seatedCount() { return state.cursor + (activeSeated() ? 1 : 0); }

function changePlate(filename) {
  const plate = index.plates.get(filename);
  if (!plate) throw new Error('印刷ファイルが見つかりません。');
  plateView.clear();
  for (const slot of plate.slots) {
    const mesh = plateView.add(slot.part, plate.color, slot.id, slot.print_position, slot.print_rotation);
    plateView.addLabel(mesh, String(slot.number), () => selectSlot(slot.id));
  }
  $('#plate-select').value = filename;
  const finish = plate.finish_color ? `黒→白: 支持体${plate.manual_change_after_z_mm} mmの後。Pauseは未設定。` : '単色。';
  $('#plate-note').textContent = `${plate.slots.length}個 / ${finish} 元の3MF配置の実STLです。番号は案内専用。`;
  updatePlate(true);
}

function updatePlate(fit = false) {
  const isolate = $('#plate-isolate').checked;
  const bounds = new THREE.Box3();
  const current = selectedSlot();
  plateView.selection.visible = false;
  for (const mesh of plateView.meshes) {
    const selected = mesh.userData.id === state.slot;
    mesh.visible = !isolate || selected;
    styleMesh(mesh, false, selected);
    if (mesh.visible) bounds.expandByObject(mesh);
    if (selected) {
      plateView.selection.box.setFromObject(mesh);
      plateView.selection.visible = true;
    }
  }
  if (!isolate) bounds.expandByPoint(new THREE.Vector3(0, 0, 0)).expandByPoint(new THREE.Vector3(...data.bed_mm, 0));
  if (!bounds.isEmpty()) plateView.bounds.copy(bounds);
  if (fit) plateView.fit(true);
  plateView.dirty = true;
  if (current) for (const node of $('#slot-list').children) node.setAttribute('aria-pressed', String(node.dataset.slot === current.id));
}

function buildSlotList() {
  const plate = index.plates.get($('#plate-select').value);
  $('#slot-list').replaceChildren(...plate.slots.map((s) => {
    const node = button('', () => selectSlot(s.id), 'slot-button');
    const number = document.createElement('span');
    number.className = 'slot-number';
    number.textContent = String(s.number).padStart(2, '0');
    node.append(number, document.createTextNode(s.part));
    node.dataset.slot = s.id;
    node.setAttribute('aria-pressed', String(state.slot === s.id));
    return node;
  }));
}

function selectSlot(id, lookup = true) {
  const slot = index.slots.get(id);
  if (!slot) throw new Error('プレート内の番号が見つかりません。');
  pause();
  state.slot = id;
  state.target = slot.suggested_placement;
  if (lookup) state.mode = 'lookup';
  if ($('#plate-select').value !== slot.plate || !plateView.meshes.length) changePlate(slot.plate);
  buildSlotList();
  updatePlate($('#plate-isolate').checked);
  updateDetails();
  updateAssembly(true);
  updateText();
  draw();
}

function selectPlacement(id) {
  const placement = index.placements.get(id);
  if (!placement) throw new Error('組立場所が見つかりません。');
  selectSlot(placement.suggested_source.slot_id);
  state.target = id;
  updateAssembly(false);
  updateDetails();
  updateText();
  draw();
}

function updateDetails() {
  const slot = selectedSlot(), group = data.groups[slot.group], part = data.parts[slot.part];
  $('#selected-part').textContent = `${slot.part} / ${data.colors[group.color].name}`;
  $('#selected-size').textContent = `印刷姿勢の外形 ${fmt(part.dimensions)} mm / 同じ形・色は全${group.quantity}個。選択: ${slot.plate} のslot ${slot.number}。便宜割当: ${slot.suggested_placement}`;
  $('#target-count').textContent = `(${group.placements.length})`;
  $('#target-list').replaceChildren(...group.placements.map((id) => {
    const p = index.placements.get(id), row = document.createElement('div');
    row.className = 'target-row';
    const choose = button(`${id} · 工程${p.step}`, () => selectPlacement(id));
    choose.setAttribute('aria-pressed', String(state.target === id));
    row.append(choose, button('ここから組む', () => setCursor(p.index)));
    const text = document.createElement('span');
    text.textContent = `位置 ${fmt(p.position)} mm / 回転 ${fmt(p.rotation)}°`;
    row.append(text);
    return row;
  }));
  $('#source-list').replaceChildren(...group.sources.map((s) =>
    button(`${s.plate} · slot ${s.slot} → 便宜例 ${s.suggested_placement}`, () => selectSlot(s.slot_id))));
}

function updateAssembly(refit = false) {
  const active = activePlacement();
  const selected = selectedSlot();
  const bounds = new THREE.Box3();
  assemblyView.selection.visible = false;
  for (const mesh of assemblyView.meshes) {
    const p = index.placements.get(mesh.userData.id);
    mesh.visible = state.mode === 'lookup' || (!state.empty && p.index <= state.cursor);
    if (!active && !state.empty && state.mode === 'build') mesh.visible = true;
    const pose = state.mode === 'build' && active?.id === p.id
      ? insertionPose(p, state.progress, data.motion) : p;
    mesh.position.fromArray(pose.position);
    mesh.rotation.set(...pose.rotation.map(THREE.MathUtils.degToRad));
    const emphasized = state.mode === 'lookup' ? p.group === selected.group : p.id === active?.id;
    styleMesh(mesh, state.mode === 'lookup' ? !emphasized : state.ghost && p.index < state.cursor, emphasized);
    if (mesh.visible) bounds.expandByObject(mesh);
    if (mesh.visible && p.id === state.target) {
      assemblyView.selection.box.setFromObject(mesh);
      assemblyView.selection.visible = true;
    }
  }
  const target = assemblyView.target;
  target.visible = state.mode === 'build' && Boolean(active) && state.progress < .99;
  if (target.visible) {
    target.geometry = geometries.get(active.part);
    target.position.fromArray(active.position);
    target.rotation.set(...active.rotation.map(THREE.MathUtils.degToRad));
    bounds.expandByObject(target);
  }
  if (state.mode === 'build' && active) {
    // Keep the entire insertion path framed, not a zoom that shrinks as the part descends.
    for (const progress of [0, .14, .28, .55, 1]) {
      const box = geometries.get(active.part).boundingBox.clone();
      const pose = insertionPose(active, progress, data.motion);
      const matrix = new THREE.Matrix4().compose(new THREE.Vector3(...pose.position),
        new THREE.Quaternion().setFromEuler(new THREE.Euler(...pose.rotation.map(THREE.MathUtils.degToRad))),
        new THREE.Vector3(1, 1, 1));
      bounds.union(box.applyMatrix4(matrix));
    }
  }
  bounds.expandByPoint(new THREE.Vector3(...data.bounds[0]));
  if (state.empty && state.mode === 'build') {
    bounds.expandByPoint(new THREE.Vector3(data.bounds[1][0], data.bounds[1][1], 12));
  }
  if (!bounds.isEmpty()) assemblyView.bounds.copy(bounds);
  for (const label of assemblyView.labels) {
    const p = index.placements.get(label.mesh.userData.id);
    label.node.style.display = (state.mode === 'lookup' ? p.group === selected.group : p.id === active?.id) ? '' : 'none';
  }
  if (refit) assemblyView.fit(true);
  assemblyView.dirty = true;
}

function updateMotion() {
  const active = activePlacement();
  if (!active) return;
  const mesh = assemblyView.meshes[active.index];
  const pose = insertionPose(active, state.progress, data.motion);
  mesh.position.fromArray(pose.position);
  mesh.rotation.set(...pose.rotation.map(THREE.MathUtils.degToRad));
  assemblyView.target.visible = state.progress < .99;
  assemblyView.selection.box.setFromObject(mesh);
  assemblyView.dirty = true;
}

function updateText() {
  const active = activePlacement(), slot = selectedSlot();
  $('#mode-label').textContent = state.mode === 'lookup' ? '仕分ける / 同じ形・色の行き先を全部表示' : '1個ずつ組む / 着地点は淡い青';
  $('#cursor-value').textContent = `${seatedCount()} / ${data.part_count} 個配置済み`;
  $('#action-title').textContent = state.mode === 'lookup'
    ? `${slot.plate} · slot ${slot.number}` : state.empty ? '工程0 · 空の机から始める'
      : active ? `工程${active.step} · ${activeSeated() ? `${active.id} の配置完了` : `次は ${active.id}`}`
        : '全パーツの配置が完了 — 実物の保持を確認';
  $('#capture-caption').textContent = state.mode === 'lookup'
    ? `${slot.plate} / slot ${slot.number} / ${slot.part} → ${slot.candidate_placements.join(', ')}（同形同色の適用先全て）`
    : state.empty ? `${data.first_source.plate} / slot ${data.first_source.slot} → ${data.first_source.suggested_placement}。まだ載せていません。「最初の1個」または再生で開始。`
      : active
      ? `${active.suggested_source.plate} / slot ${active.suggested_source.slot} / ${active.part} → ${active.id} / 工程${active.step}`
      : `${data.model} / ${data.part_count}個 / 形状・位置の案内のみ。実物の保持・転倒は未試験。`;
  $('#insertion-note').textContent = state.mode === 'lookup'
    ? '色の濃い実形状がこのpart ID＋色の全適用先。場所を選び「ここから組む」で順番の案内へ戻ります。'
    : state.empty ? '空の机です。左の見本から最初の台座を取り出し、スタッドと溝の向きを確認してから開始します。'
      : !active ? '銘板・右ロゴ・3個のkeeper、5段の着座と転倒を確認。違和感があれば止めてください。'
      : active.role === 'front_module'
        ? '印刷時の表面を正面へ90°起こす → keeperがない状態で溝の上へ → 45 mm以上上から下ろす。前から押し込まない。'
        : active.role === 'keeper'
          ? '銘板と右ロゴを先に着座。対応する上面スタッドへkeeperを上から載せる。外すときは上6 mm → 前32 mm以上 → 脇へ。'
          : active.step === 1 ? '最初の台座です。スタッドを上、前面の取付け溝を手前へ。まだ他の部品に押し込む工程ではありません。'
            : `${data.steps[active.step - 1].title}。色・溝・向きを見比べて上から載せる。無理に押さない。`;
  $('#assembly-cursor').value = String(state.cursor);
  $('#motion-progress').value = String(Math.round(state.progress * 100));
  $('#motion-progress').disabled = state.empty || !active;
  $('#motion-value').textContent = `${Math.round(state.progress * 100)}%`;
  $('#progress-note').textContent = activeSeated()
    ? '今の1個は図内で配置完了です。「次の1個」で確認して先へ進みます。実物も同じ位置・向きか確認してください。'
    : state.empty ? 'まだ部品を載せていません。「最初の1個」か再生で始めます。'
      : state.cursor === data.part_count ? '図内の全ての位置が揃いました。実物の保持・転倒が確認済みという意味ではありません。'
        : `手順の区切りは${state.cursor}個。上の数は今の1個が着座した時点も含む、図内の配置済み数です。`;
  $('#step-select').value = String(activeStep());
  $('#previous').disabled = state.cursor === 0;
  $('#next').disabled = state.cursor === data.part_count;
  $('#play').disabled = state.cursor === data.part_count;
  $('#play').textContent = state.playing ? '一時停止' : reducedMotion ? '再生（動きを開始）' : '再生';
  $('#play').setAttribute('aria-pressed', String(state.playing));
}

function pause() { state.playing = false; if (data) updatePlayButton(); }
function updatePlayButton() {
  $('#play').textContent = state.playing ? '一時停止' : '再生';
  $('#play').setAttribute('aria-pressed', String(state.playing));
}

function setCursor(number, empty = false) {
  if (!Number.isInteger(number) || number < 0 || number > data.part_count) throw new RangeError('Invalid assembly cursor');
  pause();
  state.cursor = number;
  state.empty = empty;
  state.progress = 0;
  state.mode = 'build';
  const active = data.placements[number];
  if (active) selectSlot(active.suggested_source.slot_id, false);
  else { updateAssembly(true); updateText(); draw(); }
}

function setStep(number) { setCursor(stepRange(data, number)[0], number === 0); }
function setProgress(progress) {
  if (!Number.isFinite(progress) || progress < 0 || progress > 1) throw new RangeError('Invalid motion progress');
  pause();
  if (state.mode !== 'build') setCursor(index.placements.get(state.target).index);
  else if (state.empty) setCursor(0);
  state.progress = progress;
  updateAssembly();
  updateText();
  draw();
}
function play(until = data.part_count) {
  if (state.mode !== 'build') setCursor(index.placements.get(state.target).index);
  else if (state.empty) setCursor(0);
  state.playUntil = until;
  state.playing = state.cursor < until;
  updateText();
}
function replayStep() {
  const range = stepRange(data, Number($('#step-select').value));
  setCursor(range[0]);
  play(range[1]);
}
function draw() { plateView?.draw(); assemblyView?.draw(); }

async function decodeMesh(part, encoded) {
  if (encoded.encoding !== 'gzip-base64-stl' || typeof DecompressionStream === 'undefined') {
    throw new Error('圧縮形状を読める現行版のChrome・Edge・Firefox・Safariで開いてください。');
  }
  const bytes = Uint8Array.from(atob(encoded.payload), (c) => c.charCodeAt(0));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const buffer = await new Response(stream).arrayBuffer();
  if (buffer.byteLength !== encoded.bytes) throw new Error(`形状データが不完全です: ${part.id}`);
  const geometry = new STLLoader().parse(buffer);
  geometry.computeBoundingBox();
  if (geometry.boundingBox.isEmpty()) throw new Error(`空の形状: ${part.id}`);
  if (part.finish_color) {
    const position = geometry.getAttribute('position'), colors = new Float32Array(position.count * 3);
    const light = new THREE.Color(data.colors[part.finish_color].hex), dark = new THREE.Color(data.colors.black.hex);
    for (let i = 0; i < position.count; i += 3) {
      const middle = (position.getZ(i) + position.getZ(i + 1) + position.getZ(i + 2)) / 3;
      const color = middle > part.color_change_z_mm + .001 ? light : dark;
      for (let j = i; j < i + 3; j++) color.toArray(colors, j * 3);
    }
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  }
  return geometry;
}

async function main() {
  const payload = JSON.parse($('#assembly-guide-data').textContent);
  data = payload.mapping;
  index = indexGuide(data);
  $('#guide-title').textContent = data.title;
  $('#revision').textContent = `${data.model} / ${data.guide_revision} / ${data.geometry_revision}`;
  for (const [id, part] of Object.entries(data.parts)) geometries.set(id, await decodeMesh(part, payload.meshes[id]));
  $('#loading').hidden = true;
  $('#interactive').hidden = false;
  plateView = new SceneView('plate', (id) => selectSlot(id));
  assemblyView = new SceneView('assembly', (id) => selectPlacement(id));
  for (const p of data.placements) {
    const mesh = assemblyView.add(p.part, p.color, p.id, p.position, p.rotation);
    assemblyView.addLabel(mesh, p.id, () => selectPlacement(p.id));
  }
  assemblyView.target = new THREE.Mesh(geometries.get(data.placements[0].part),
    new THREE.MeshBasicMaterial({ color: 0x007c83, transparent: true, opacity: .18, depthWrite: false }));
  assemblyView.scene.add(assemblyView.target);
  $('#plate-select').replaceChildren(...data.plates.map((plate) => new Option(`${plate.file} (${plate.slots.length}個)`, plate.file)));
  $('#step-select').replaceChildren(new Option('0 · 空から始める', '0'),
    ...data.steps.map((s) => new Option(`${s.number} · ${s.title}`, String(s.number))));
  $('#assembly-cursor').max = String(data.part_count);
  const first = data.first_source;
  $('#first-file').textContent = `最初は ${first.plate} のslot ${first.slot} → ${first.suggested_placement}（工程1）。ファイル名の「01」から順に組むわけではありません。`;
  $('#base-files').replaceChildren(...data.base_source_files.map((file) => {
    const item = document.createElement('li');
    item.append(button(file, () => selectSlot(index.plates.get(file).slots[0].id)));
    return item;
  }));
  $('#plate-select').addEventListener('change', (event) => selectSlot(index.plates.get(event.target.value).slots[0].id));
  $('#plate-isolate').addEventListener('change', () => updatePlate(true));
  $('#ghost').addEventListener('change', (event) => { state.ghost = event.target.checked; updateAssembly(); });
  $('#step-select').addEventListener('change', (event) => setStep(Number(event.target.value)));
  $('#assembly-cursor').addEventListener('input', (event) => setCursor(Number(event.target.value)));
  $('#motion-progress').addEventListener('input', (event) => setProgress(Number(event.target.value) / 100));
  $('#start-first').disabled = false;
  $('#start-first').addEventListener('click', () => {
    $('#plate-isolate').checked = false;
    setCursor(0);
    plateView.setView('iso'); assemblyView.setView('iso');
    $('#capture-card').scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  });
  $('#restart').addEventListener('click', () => setStep(0));
  $('#previous').addEventListener('click', () => setCursor(Math.max(0, state.cursor - 1)));
  $('#next').addEventListener('click', () => setCursor(state.empty ? 0 : Math.min(data.part_count, state.cursor + 1)));
  $('#play').addEventListener('click', () => { if (state.playing) { pause(); updateText(); } else play(); });
  $('#replay-step').addEventListener('click', replayStep);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { pause(); updateText(); }
  });
  for (const toolbar of document.querySelectorAll('.view-tools')) for (const btn of toolbar.querySelectorAll('button')) {
    btn.addEventListener('click', () => (toolbar.dataset.scene === 'plate' ? plateView : assemblyView).setView(btn.dataset.view));
  }
  setStep(0);
  plateView.setView('iso');
  assemblyView.setView('iso');
  draw();
  window.BrickAssemblyGuide = Object.freeze({
    ready: true, mapping: () => data,
    state: () => ({
      model: data.model, cursor: state.cursor, empty: state.empty, progress: state.progress, playing: state.playing, mode: state.mode,
      step: activeStep(), activeId: activePlacement()?.id || null, selectedSlot: state.slot,
      selectedPlate: selectedSlot().plate, selectedSlotNumber: selectedSlot().number,
      renderError: $('#guide-error').hidden ? null : $('#guide-error').textContent,
      selectedPlacement: state.target, completedIds: data.placements.slice(0, state.cursor).map((p) => p.id),
      seatedCount: seatedCount(), seatedIds: data.placements.slice(0, seatedCount()).map((p) => p.id),
      activeSeated: activeSeated(),
      candidateIds: [...selectedSlot().candidate_placements],
      sourceSlots: data.groups[selectedSlot().group].sources.map((s) => s.slot_id),
      assemblyPoses: assemblyView.meshes.filter((m) => m.visible).map((m) => ({
        id: m.name, position: m.position.toArray(), rotation: m.rotation.toArray().slice(0, 3).map(THREE.MathUtils.radToDeg),
      })),
    }),
    setCursor, setStep, setProgress, selectSlot, selectPlacement,
    setView: (scene, view) => {
      if (!['plate', 'assembly'].includes(scene)) throw new Error('Invalid scene');
      (scene === 'plate' ? plateView : assemblyView).setView(view); draw();
    },
    play, pause, restart: () => setStep(0),
  });
  $('#guide-app').dataset.ready = 'true';
  let last = performance.now();
  function frame(time) {
    const elapsed = Math.max(0, time - last);
    last = time;
    if (state.playing) {
      state.progress = Math.min(1, state.progress + elapsed / Number($('#speed').value));
      if (state.progress >= 1) {
        const until = state.playUntil;
        setCursor(state.cursor + 1);
        state.playUntil = until;
        state.playing = state.cursor < until;
        updateText();
      } else {
        updateMotion();
        updateText();
      }
    }
    draw();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

main().catch(fail);
