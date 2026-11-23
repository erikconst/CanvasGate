import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const labels = ['Codex direct', 'Obsidian selection', 'CanvasGate + Obsidian'];
const subtitles = ['Full document packet', 'Three current notes', 'YAML gates + section slicing'];
const descriptions = { slow: 'relaxed serpentine motion', fast: 'rapid traveling wave', attack: 'strike & recovery', sleep: 'coiled rest, subtle breathing', sit: 'coiled upright rest', death: 'collapse & stillness' };
const stateList = ['slow','fast','attack','sleep','sit','death'];
const lab = window.snakeLab = { ready: false, models: [], errors: [], state: 'slow', time: 0, playing: true, speed: 1 };
const format = number => typeof number === 'number' ? number.toLocaleString('en-US') : 'Unavailable';
const initialCamera = new THREE.Vector3(5.1, 3.7, 6.2);

function makeStage(card) {
  const frame = card.querySelector('.frame');
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.6));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  frame.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xe9f2dc, 0x253024, 1.8));
  const key = new THREE.DirectionalLight(0xffefd7, 3.0);
  key.position.set(3, 7, 5); key.castShadow = true;
  key.shadow.mapSize.set(1024,1024); key.shadow.camera.left = -5; key.shadow.camera.right = 5;
  key.shadow.camera.top = 5; key.shadow.camera.bottom = -5; key.shadow.normalBias = 0.025;
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xb9e7be, 2); rim.position.set(-4,3,-3); scene.add(rim);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(200,200), new THREE.MeshStandardMaterial({color:0x162016, roughness:1}));
  floor.rotation.x = -Math.PI/2; floor.position.y = -0.035; floor.receiveShadow = true; scene.add(floor);
  const grid = new THREE.GridHelper(10,20,0x526248,0x3a4934); grid.position.y = -0.027;
  grid.material.transparent = true; grid.material.opacity = 0.18; scene.add(grid);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100); camera.position.copy(initialCamera);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0,0.38,0); controls.enableDamping = true; controls.minDistance = 4; controls.maxDistance = 18;
  controls.maxPolarAngle = Math.PI*0.48; controls.update();
  function resize() { const width=frame.clientWidth,height=frame.clientHeight; renderer.setSize(width,height,false); camera.aspect=width/height; camera.updateProjectionMatrix(); }
  new ResizeObserver(resize).observe(frame); resize();
  return { renderer, scene, camera, controls };
}

lab.setState = state => {
  if (!stateList.includes(state)) throw Error('Unknown state');
  lab.state=state; lab.time=0;
  document.querySelectorAll('[data-state]').forEach(button => button.classList.toggle('active',button.dataset.state===state));
  document.querySelector('#state-caption').textContent = `${state[0].toUpperCase()+state.slice(1)} · ${descriptions[state]}`;
};
lab.setTime = time => { lab.time=Math.max(0,Number(time)); renderAll(); };
lab.setPlaying = playing => { lab.playing=Boolean(playing); document.querySelector('#play').textContent=lab.playing?'Ⅱ Pause':'▶ Play'; };
lab.resetCameras = () => lab.models.forEach(model => { model.camera.position.copy(initialCamera); model.controls.target.set(0,0.38,0); model.controls.update(); });
document.querySelectorAll('[data-state]').forEach(button => button.addEventListener('click',()=>lab.setState(button.dataset.state)));
document.querySelector('#play').addEventListener('click',()=>lab.setPlaying(!lab.playing));
document.querySelector('#restart').addEventListener('click',()=>lab.setTime(0));
document.querySelector('#reset').addEventListener('click',lab.resetCameras);
document.querySelector('#time').addEventListener('input',event=>{lab.setPlaying(false);lab.setTime(event.target.value);});
document.querySelector('#speed').addEventListener('change',event=>{lab.speed=Number(event.target.value);});

function renderAll() {
  for (const model of lab.models) {
    if (!model.snake || model.failed) continue;
    try { model.snake.update(lab.time,lab.state); model.controls.update(); model.renderer.render(model.scene,model.camera); }
    catch(error) { model.failed=true; lab.errors.push({variant:model.number,error:String(error)}); model.card.querySelector('.model-status').textContent='Runtime error'; model.card.querySelector('.model-status').classList.add('error'); }
  }
  document.querySelector('#time').value=String(Math.min(lab.time,6));
  document.querySelector('#time-value').textContent=`${lab.time.toFixed(2)} s`;
}

function resources(root) {
  const meshes=[],geometries=new Set(),materials=new Set();
  root.traverse(object=>{ if(object.isMesh){ meshes.push(object); if(object.geometry)geometries.add(object.geometry); for(const material of Array.isArray(object.material)?object.material:[object.material])if(material)materials.add(material); } });
  return {meshes,geometries,materials};
}

function pose(snake,time,state) {
  snake.update(time,state); snake.root.updateMatrixWorld(true);
  const values=[]; let finite=true,vertices=0;
  const bounds={min:[Infinity,Infinity,Infinity],max:[-Infinity,-Infinity,-Infinity]};
  const point=new THREE.Vector3();
  snake.root.traverse(object=>{
    if(!object.isMesh)return;
    values.push(object.visible?1:0,...object.matrixWorld.elements);
    for(const material of Array.isArray(object.material)?object.material:[object.material]) {
      if(material?.color)values.push(material.color.r,material.color.g,material.color.b,material.opacity);
    }
    const attribute=object.geometry?.getAttribute('position');
    if(attribute){
      vertices+=attribute.count;
      for(let i=0;i<attribute.array.length;i++)if(!Number.isFinite(attribute.array[i]))finite=false;
      const step=Math.max(1,Math.floor(attribute.count/32));
      for(let i=0;i<attribute.count;i+=step){point.fromBufferAttribute(attribute,i).applyMatrix4(object.matrixWorld);values.push(point.x,point.y,point.z);const coordinates=[point.x,point.y,point.z];for(let axis=0;axis<3;axis++){bounds.min[axis]=Math.min(bounds.min[axis],coordinates[axis]);bounds.max[axis]=Math.max(bounds.max[axis],coordinates[axis]);}}
    }
  });
  return {values,finite:finite&&values.every(Number.isFinite),vertices,bounds};
}
function distance(a,b) { if(a.length!==b.length)return Infinity; return Math.sqrt(a.reduce((sum,value,i)=>sum+(value-b[i])**2,0)/Math.max(1,a.length)); }
function activity(snake,state) { let total=0; for(let i=0;i<24;i++){const t=i/12;total+=distance(pose(snake,t,state).values,pose(snake,t+0.025,state).values);} return total/24; }
function headPosition(snake,t,state) {snake.update(t,state);snake.root.updateMatrixWorld(true);return snake.root.getObjectByName('snake-head')?.getWorldPosition(new THREE.Vector3())??null;}

lab.testModels = () => lab.models.map(model=>{
  const checks=[], measurements={}; let snake;
  const check=(name,passed,detail='')=>checks.push({name,passed:Boolean(passed),detail});
  try {
    check('Six declared states',JSON.stringify(model.module.states)===JSON.stringify(stateList));
    snake=model.module.createSnake(THREE);
    check('Required factory contract',snake.root?.isGroup&&typeof snake.update==='function'&&typeof snake.dispose==='function');
    if(!snake.root||!snake.update||!snake.dispose)throw Error('Missing factory contract');
    const initial=resources(snake.root),geometryIds=[...initial.geometries].map(g=>g.uuid).sort().join(),materialIds=[...initial.materials].map(m=>m.uuid).sort().join();
    check('Named head and body',snake.root.getObjectByName('snake-head')&&snake.root.getObjectByName('snake-body'));
    check('Renderable model',initial.meshes.length>=1&&initial.geometries.size>=1);
    const poses=stateList.map(state=>pose(snake,0.73,state));
    check('Finite geometry in all six states',poses.every(p=>p.finite));
    check('Model fits common stage scale',poses.every(p=>p.bounds.min[0]>-4.5&&p.bounds.max[0]<4.5&&p.bounds.min[2]>-4.5&&p.bounds.max[2]<4.5&&p.bounds.min[1]>-0.4&&p.bounds.max[1]<3.2));
    check('Vertex budget',poses.every(p=>p.vertices<100000));
    let deterministic=true;
    for(let i=0;i<stateList.length;i++){snake.update(1.7,'death');snake.update(0.35,'attack');const replay=pose(snake,0.73,stateList[i]);if(distance(poses[i].values,replay.values)>0.00001)deterministic=false;}
    check('Deterministic state transitions',deterministic,'Same time/state after shuffled calls');
    const trajectories=stateList.map(state=>[0.17,0.35,0.73,1.7].flatMap(t=>pose(snake,t,state).values));
    check('Six distinct animation trajectories',trajectories.every((a,i)=>trajectories.every((b,j)=>i===j||distance(a,b)>0.0001)),'Includes strike peak and recovery; a recovered attack may share a slow pose at one instant');
    const slow=activity(snake,'slow'),fast=activity(snake,'fast'),sleep=activity(snake,'sleep');
    measurements.slow_motion=slow;measurements.fast_motion=fast;measurements.sleep_motion=sleep;measurements.fast_slow_ratio=slow?fast/slow:null;
    check('Slow and fast animate',slow>0.00001&&fast>0.00001);
    check('Fast motion exceeds slow',fast>slow*1.25,`Observed motion ratio ${slow?(fast/slow).toFixed(2):'n/a'}×; geometric proxy, not direct frequency measurement`);
    check('Sleep is quieter than slow',sleep<slow*0.65);
    check('Death becomes static',distance(pose(snake,2,'death').values,pose(snake,3,'death').values)<0.000001);
    const attackStart=headPosition(snake,0,'attack');
    const attackPeak=headPosition(snake,0.35,'attack');
    measurements.attack_extension=attackStart&&attackPeak?attackPeak.z-attackStart.z:null;
    check('Forward attack lunge',attackStart&&attackPeak&&attackPeak.z-attackStart.z>0.35);
    const sleeping=headPosition(snake,0.73,'sleep'),sitting=headPosition(snake,0.73,'sit');
    measurements.sit_elevation=sleeping&&sitting?sitting.y-sleeping.y:null;
    check('Sit raises the head',sleeping&&sitting&&sitting.y-sleeping.y>0.35);
    const after=resources(snake.root);
    check('Stable mesh and resource counts',initial.meshes.length===after.meshes.length&&geometryIds===[...after.geometries].map(g=>g.uuid).sort().join()&&materialIds===[...after.materials].map(m=>m.uuid).sort().join());
    const disposedGeometry=new Set(),disposedMaterial=new Set();
    for(const geometry of after.geometries)geometry.addEventListener('dispose',()=>disposedGeometry.add(geometry));
    for(const material of after.materials)material.addEventListener('dispose',()=>disposedMaterial.add(material));
    snake.dispose();snake=null;
    check('Owned resources disposed',disposedGeometry.size===after.geometries.size&&disposedMaterial.size===after.materials.size);
  } catch(error) {check('No test-time exception',false,String(error));try{snake?.dispose();}catch{}}
  return {variant:model.number,passed:checks.every(c=>c.passed),passed_count:checks.filter(c=>c.passed).length,check_count:checks.length,checks,measurements};
});

function presentQa(results){
  document.querySelector('#qa-status').textContent=results.map(r=>`${r.variant}: ${r.passed_count}/${r.check_count}`).join(' · ');
  const area=document.querySelector('#qa-results');area.replaceChildren();
  for(const result of results){const column=document.createElement('div');column.className='qa-result';for(const check of result.checks){const row=document.createElement('p');row.className=check.passed?'passed':'failed';row.textContent=`${check.passed?'✓':'×'} ${check.name}`;row.title=check.detail;column.append(row);}area.append(column);const model=lab.models.find(m=>m.number===result.variant);if(model)model.card.querySelector('.model-status').textContent=`${result.passed_count}/${result.check_count} engineering checks`;}
}

try {
  const manifest=await fetch('./latest.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Run python -m canvasgate.snake_benchmark first.');return r.json();});
  lab.manifest=manifest;
  document.querySelector('#report').href=`./runs/${manifest.run}/COMPARISON.md`;
  const max=Math.max(...manifest.models.map(m=>m.usage?.total_tokens??0),1);
  for(const metric of manifest.models){
    const number=metric.variant,card=document.createElement('article');card.className='model';card.dataset.variant=number;
    card.innerHTML=`<div class="model-top"><div class="model-title"><span class="model-num">0${number}</span><div><h3>${labels[number-1]}</h3><small>${subtitles[number-1]}</small></div></div><span class="tag">PROCEDURAL</span></div><div class="frame"><span class="frame-label">PERSPECTIVE / +Z FORWARD</span><span class="axes-label">Y ↑ &nbsp; Z ↗</span><span class="loading">Loading model…</span></div><div class="model-bottom"><span class="model-status">Generated · awaiting checks</span><a href="./runs/${manifest.run}/0${number}/snake.mjs" target="_blank" rel="noopener">View source ↗</a></div>`;
    document.querySelector('#models').append(card);
    const metricBox=document.createElement('div');metricBox.innerHTML=`<div class="metric-label">0${number} / ${labels[number-1]}</div><div><span class="metric-value">${format(metric.usage?.total_tokens)}</span><span class="metric-unit">TOKENS</span></div><div class="metric-bar"><i style="width:${100*(metric.usage?.total_tokens??0)/max}%"></i></div><div class="metric-note">${format(metric.usage?.input_tokens)} input · ${format(metric.usage?.output_tokens)} output<br>${metric.elapsed_seconds.toFixed(1)}s generation · fresh session</div>`;document.querySelector('#comparison').append(metricBox);
    try {
      if(metric.generation_error)throw Error(metric.generation_error);
      const module=await import(`./runs/${manifest.run}/0${number}/snake.mjs`);
      if(typeof module.createSnake!=='function')throw Error('createSnake export missing');
      const stage=makeStage(card),snake=module.createSnake(THREE);stage.scene.add(snake.root);
      lab.models.push({...stage,number,card,module,snake});card.querySelector('.loading').remove();
    }catch(error){lab.errors.push({variant:number,error:String(error)});card.querySelector('.loading').textContent=String(error);card.querySelector('.loading').classList.add('error-message');card.querySelector('.model-status').textContent='Load failed';}
  }
  if(manifest.qa)presentQa(manifest.qa);
  lab.ready=true;
  const params=new URLSearchParams(location.search);if(params.has('state'))lab.setState(params.get('state'));if(params.has('t'))lab.time=Number(params.get('t'));if(params.get('paused')==='1')lab.setPlaying(false);
  let last=performance.now();
  function animate(now){const delta=Math.min((now-last)/1000,0.1);last=now;if(lab.playing)lab.time+=delta*lab.speed;renderAll();requestAnimationFrame(animate);}requestAnimationFrame(animate);
}catch(error){lab.errors.push({error:String(error)});document.querySelector('#models').textContent=String(error);lab.ready=true;}
