'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[character]));
const pretty = value => value.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const shortTitle = value => value.replace(/^Large Print /i, '').replace(/ Word Search$/i, '');
const state = {catalog:null, theme:null, kind:'wordsearch', palette:'nature', preview:null, mode:'puzzle', index:0, selectedWord:-1, books:[], jobs:[], editing:null, editIndex:0, page:'create'};
let token = new URLSearchParams(location.hash.slice(1)).get('token');
try {
  if (token) sessionStorage.setItem('studio-token', token);
  else token = sessionStorage.getItem('studio-token');
} catch (_) { /* Cookies keep this session usable when storage is unavailable. */ }
if (location.hash.includes('token=')) history.replaceState(null, '', location.pathname);
let toastTimer, previewTimer, previewController, jobSignature = '';

function createRNG(seed) {
  let s = Number(seed) || 7;
  return function() {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function clientWordSearch(words, size = 15, seed = 7) {
  const rnd = createRNG(seed);
  const DIRS = [[0,1],[1,0],[1,1],[1,-1],[-1,1],[-1,-1],[-1,0],[0,-1]];
  const clean = (words || []).map(w => String(w).toUpperCase().replace(/[^A-Z]/g, '')).filter(w => w && w.length <= size);
  const sorted = [...new Set(clean)].sort((a,b) => b.length - a.length);
  let grid = Array.from({length: size}, () => Array(size).fill(''));
  let paths = [];
  let placed = [];
  for (const word of sorted) {
    for (let attempt = 0; attempt < 500; attempt++) {
      const [dr, dc] = DIRS[Math.floor(rnd() * DIRS.length)];
      const r = Math.floor(rnd() * size);
      const c = Math.floor(rnd() * size);
      let cells = [];
      let ok = true;
      for (let k = 0; k < word.length; k++) {
        const rr = r + dr * k, cc = c + dc * k;
        if (rr < 0 || rr >= size || cc < 0 || cc >= size) { ok = false; break; }
        const cur = grid[rr][cc];
        if (cur && cur !== word[k]) { ok = false; break; }
        cells.push([rr, cc]);
      }
      if (ok) {
        for (let k = 0; k < word.length; k++) grid[cells[k][0]][cells[k][1]] = word[k];
        paths.push(cells); placed.push(word); break;
      }
    }
  }
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (!grid[r][c]) grid[r][c] = letters[Math.floor(rnd() * letters.length)];
    }
  }
  return { grid, paths, words: placed };
}

function clientSudoku(seed = 7, profile = 'mixed') {
  const rnd = createRNG(seed);
  const BASE = [
    [1, 2, 3, 4, 5, 6, 7, 8, 9],
    [4, 5, 6, 7, 8, 9, 1, 2, 3],
    [7, 8, 9, 1, 2, 3, 4, 5, 6],
    [2, 3, 4, 5, 6, 7, 8, 9, 1],
    [5, 6, 7, 8, 9, 1, 2, 3, 4],
    [8, 9, 1, 2, 3, 4, 5, 6, 7],
    [3, 4, 5, 6, 7, 8, 9, 1, 2],
    [6, 7, 8, 9, 1, 2, 3, 4, 5],
    [9, 1, 2, 3, 4, 5, 6, 7, 8],
  ];
  const digits = [1,2,3,4,5,6,7,8,9];
  for (let i = digits.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [digits[i], digits[j]] = [digits[j], digits[i]];
  }
  let solution = BASE.map(row => row.map(v => digits[v - 1]));
  for (let band = 0; band < 3; band++) {
    const rIndices = [0, 1, 2].sort(() => rnd() - 0.5);
    const bandRows = [solution[band*3], solution[band*3+1], solution[band*3+2]];
    for (let i = 0; i < 3; i++) solution[band*3 + i] = bandRows[rIndices[i]];
  }
  for (let stack = 0; stack < 3; stack++) {
    const cIndices = [0, 1, 2].sort(() => rnd() - 0.5);
    for (let r = 0; r < 9; r++) {
      const orig = [solution[r][stack*3], solution[r][stack*3+1], solution[r][stack*3+2]];
      for (let i = 0; i < 3; i++) solution[r][stack*3 + i] = orig[cIndices[i]];
    }
  }
  const blanksTarget = {easy: 36, hard: 52}[profile] || 44;
  let puzzle = solution.map(row => [...row]);
  const coords = [];
  for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) coords.push([r, c]);
  coords.sort(() => rnd() - 0.5);
  for (let i = 0; i < blanksTarget && i < coords.length; i++) {
    const [r, c] = coords[i];
    puzzle[r][c] = 0;
  }
  return { grid: puzzle, solution };
}

function clientMaze(size = 15, seed = 7) {
  const rnd = createRNG(seed);
  const wallsMap = {};
  for (let x = 0; x < size; x++) for (let y = 0; y < size; y++) wallsMap[x + ',' + y] = new Set(['N','E','S','W']);
  const visited = new Set();
  const stack = [[0, 0]];
  visited.add('0,0');
  const dirs = [{d:'N',opp:'S',dx:0,dy:-1},{d:'S',opp:'N',dx:0,dy:1},{d:'E',opp:'W',dx:1,dy:0},{d:'W',opp:'E',dx:-1,dy:0}];
  while (stack.length > 0) {
    const [cx, cy] = stack[stack.length - 1];
    const neighbors = [];
    for (const {d, opp, dx, dy} of dirs) {
      const nx = cx + dx, ny = cy + dy;
      if (nx >= 0 && nx < size && ny >= 0 && ny < size && !visited.has(nx + ',' + ny)) neighbors.push({nx, ny, d, opp});
    }
    if (neighbors.length > 0) {
      const {nx, ny, d, opp} = neighbors[Math.floor(rnd() * neighbors.length)];
      wallsMap[cx + ',' + cy].delete(d); wallsMap[nx + ',' + ny].delete(opp);
      visited.add(nx + ',' + ny); stack.push([nx, ny]);
    } else {
      stack.pop();
    }
  }
  const walls = [];
  for (let x = 0; x < size; x++) for (let y = 0; y < size; y++) walls.push([x, y, Array.from(wallsMap[x + ',' + y]).sort()]);
  const parent = {}, queue = [[0, 0]], seenPath = new Set(['0,0']);
  while (queue.length > 0) {
    const [cx, cy] = queue.shift();
    if (cx === size - 1 && cy === size - 1) break;
    for (const {d, dx, dy} of dirs) {
      if (!wallsMap[cx + ',' + cy].has(d)) {
        const nx = cx + dx, ny = cy + dy;
        if (nx >= 0 && nx < size && ny >= 0 && ny < size && !seenPath.has(nx + ',' + ny)) {
          seenPath.add(nx + ',' + ny); parent[nx + ',' + ny] = [cx, cy]; queue.push([nx, ny]);
        }
      }
    }
  }
  const path = [];
  let curr = [size - 1, size - 1];
  while (curr) { path.unshift(curr); if (curr[0] === 0 && curr[1] === 0) break; curr = parent[curr[0] + ',' + curr[1]]; }
  return { size, walls, path };
}

async function staticApi(path, data) {
  const cleanPath = path.split('?')[0];
  if (cleanPath === 'bootstrap') {
    const res = await fetch('./data/bootstrap.json');
    return await res.json();
  }
  if (cleanPath === 'topics') {
    const res = await fetch('./data/topics.json');
    return await res.json();
  }
  if (cleanPath === 'theme') {
    const id = new URLSearchParams(path.split('?')[1] || '').get('id') || 'nature.json';
    const res = await fetch('./themes/' + id);
    return await res.json();
  }
  if (cleanPath === 'preview') {
    const kind = data?.kind || 'wordsearch';
    const seed = Number(data?.seed || 7);
    if (kind === 'wordsearch') {
      let theme = data?.theme_data;
      if (!theme && data?.theme) {
        try {
          const res = await fetch('./themes/' + data.theme);
          theme = await res.json();
        } catch (_) {}
      }
      const idx = data?.index || 0;
      const puzzle = theme?.puzzles?.[idx] || {name: 'Word Search', words: ['EVERGREEN','PUZZLE','FOREST','NATURE','HARMONY']};
      const ws = clientWordSearch(puzzle.words, data?.design?.grid_size || 15, seed + idx);
      return { kind, name: puzzle.name, grid: ws.grid, paths: ws.paths, words: ws.words };
    }
    if (kind === 'sudoku') {
      const sud = clientSudoku(seed, data?.profile || 'mixed');
      return { kind, name: 'Sudoku', grid: sud.grid, solution: sud.solution };
    }
    if (kind === 'maze') {
      const difficulty = data?.profile || 'mixed';
      const n = {easy: 11, mixed: 15, hard: 19}[difficulty] || 15;
      const mz = clientMaze(n, seed);
      return { kind, name: 'Maze', size: mz.size, walls: mz.walls, path: mz.path };
    }
  }
  if (cleanPath === 'jobs') {
    if (data) {
      return {
        id: 'preview-' + Date.now(),
        title: data.title || 'Online Preview Book',
        status: 'completed',
        stage: 'Client-side preview ready',
        progress: 100,
        result: { message: 'Running on GitHub Pages. To generate full 300 DPI Amazon KDP interior & wrap cover PDFs, run "python studio.py" locally.' }
      };
    }
    return [];
  }
  if (cleanPath === 'connections') return { ollama: { connected: false }, chrome: { connected: false } };
  if (cleanPath === 'ai-status') return {};
  if (cleanPath === 'books') return [];
  if (cleanPath === 'assets') return [];
  if (cleanPath === 'design-validate') return data?.design || {};
  if (cleanPath === 'compose') {
    const ids = new Set(data?.ids || []);
    try {
      const res = await fetch('./data/topics.json');
      const allTopics = await res.json();
      const selected = allTopics.filter(t => ids.has(t.id));
      return {
        title: 'Curated Topic Collection',
        subtitle: 'Hand-picked puzzles for curious minds',
        author: 'E. P. Greenwood',
        puzzles: selected.map(t => ({name: t.name, words: t.words || ['WORD','SEARCH']}))
      };
    } catch (_) {}
  }
  return {};
}

async function api(path, data, signal) {
  try {
    const response = await fetch('/api/' + path, {method:data === undefined ? 'GET':'POST', headers:{'Content-Type':'application/json', ...(token ? {Authorization:'Bearer ' + token} : {})}, ...(data === undefined ? {} : {body:JSON.stringify(data)}), signal});
    if (response.ok) return await response.json();
    if (response.status !== 404 && response.status !== 405) {
      const result = await response.json();
      throw new Error(result.error || 'The operation could not be completed.');
    }
  } catch (error) {
    if (error.name === 'AbortError') throw error;
  }
  return await staticApi(path, data);
}
function toast(message, error = false) {
  const element = $('#toast');
  element.textContent = message; element.classList.toggle('error', error); element.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => element.hidden = true, error ? 9000 : 5000);
}
function on(selector, event, handler) {
  $(selector).addEventListener(event, async e => {
    try { await handler(e); } catch (error) { if (error.name !== 'AbortError') toast(error.message, true); }
  });
}
function go(page) {
  if (!$('#page-' + page)) return;
  state.page = page;
  $$('.page').forEach(element => element.hidden = element.id !== 'page-' + page);
  $$('.nav-item').forEach(element => element.classList.toggle('active', element.dataset.page === page));
  const name = {create:'Create a book', themes:'Theme collection', library:'Your library', factory:'Auto factory', publish:'Publishing tools', design:'Design & artwork', ai:'AI workshop', trends:'Trend notebook', topics:'Topic packs'}[page];
  $('#breadcrumb').innerHTML = 'Workspace <span>/</span> ' + name;
  if (location.hash !== '#' + page) history.replaceState(null, '', '#' + page);
  if (page === 'library') refreshBooks().catch(error => toast(error.message, true));
  if (page === 'publish') checkConnections();
  if (page === 'design') DesignStudio.render();
}
$$('[data-page]').forEach(element => element.addEventListener('click', () => go(element.dataset.page)));
window.addEventListener('hashchange', () => go(location.hash.slice(1)));
$$('.close-dialog').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$$('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog && event.clientX && (event.clientX < dialog.getBoundingClientRect().left || event.clientX > dialog.getBoundingClientRect().right || event.clientY < dialog.getBoundingClientRect().top || event.clientY > dialog.getBoundingClientRect().bottom)) dialog.close(); }));
on('#help-button', 'click', () => $('#help-dialog').showModal());
on('#jobs-button', 'click', () => { renderJobs(); $('#jobs-dialog').showModal(); });

async function refreshCatalog() {
  state.catalog = await api('bootstrap');
  const selected = $('#theme').value;
  $('#theme').innerHTML = state.catalog.themes.map(theme => `<option value="${escapeHTML(theme.id)}">${escapeHTML(shortTitle(theme.title))} · ${theme.count} puzzles</option>`).join('');
  if (state.catalog.themes.some(theme => theme.id === selected)) $('#theme').value = selected;
  $('#theme-count').textContent = state.catalog.themes.length;
  $('#ollama-model').value = state.catalog.model;
  renderThemes(); renderFactory(); renderPalettes();
  DesignStudio.init(state.catalog);
}
async function chooseTheme(id) {
  state.theme = await api('theme?id=' + encodeURIComponent(id));
  if(state.theme.design)DesignStudio.set(state.theme.design);
  $('#theme').value = id;
  $('#title').value = state.theme.title;
  $('#subtitle').value = state.theme.subtitle || '';
  $('#author').value = state.theme.author || 'E. P. Greenwood';
  $('#count').value = state.theme.puzzles.length;
  $('#count').max = state.theme.puzzles.length;
  $('#also-from').value = state.theme.also_from?.length ? JSON.stringify(state.theme.also_from, null, 2) : '';
  state.palette = state.catalog.palettes[state.theme.palette] ? state.theme.palette : 'nature';
  if(!state.theme.design)DesignStudio.palette(state.catalog.palettes[state.palette]);
  state.index = 0; renderPalettes(); schedulePreview(); saveDraft();
}
function setKind(kind, keepValues = false) {
  state.kind = kind;
  $(`input[name="kind"][value="${kind}"]`).checked = true;
  $('#theme-field').hidden = kind !== 'wordsearch';
  $('#palette-field').hidden = kind !== 'wordsearch';
  $('#profile-field').hidden = kind === 'wordsearch';
  $('#puzzle-pager').hidden = kind !== 'wordsearch';
  $('#count').max = kind === 'wordsearch' ? state.theme?.puzzles.length || 300 : 300;
  if (!keepValues) {
    if (kind === 'wordsearch' && state.theme) {
      $('#title').value = state.theme.title; $('#subtitle').value = state.theme.subtitle || ''; $('#count').value = state.theme.puzzles.length;
    } else {
      $('#title').value = kind === 'sudoku' ? 'Large Print Sudoku' : 'Large Print Mazes';
      $('#count').value = kind === 'sudoku' ? 100 : 80;
      $('#subtitle').value = 'Relaxing puzzles for curious minds, with complete solutions';
    }
  }
  state.index = 0; schedulePreview(); saveDraft();
}
function config() {
  const result = Object.fromEntries(new FormData($('#build-form')));
  result.design = DesignStudio.value();
  result.palette = state.palette; result.kind = state.kind;
  result.badge = $('#badge').value; result.back = $('#back').value;
  result.also_from = $('#also-from').value.trim() ? JSON.parse($('#also-from').value) : [];
  if (state.kind === 'wordsearch' && state.theme) result.theme_data = {...state.theme, also_from:result.also_from};
  return result;
}
function saveDraft() {
  try { localStorage.setItem('puzzle-studio-draft', JSON.stringify(config())); } catch (_) { /* Draft storage is optional. */ }
}
function renderPalettes() {
  if (!state.catalog) return;
  $('#palette-name').textContent = pretty(state.palette);
  $('#palettes').innerHTML = Object.entries(state.catalog.palettes).map(([name, palette]) => `<button type="button" class="swatch ${name === state.palette ? 'selected' : ''}" style="--swatch:rgb(${palette.accent})" data-palette="${escapeHTML(name)}" title="${escapeHTML(pretty(name))}" aria-label="${escapeHTML(pretty(name))}" aria-pressed="${name === state.palette}"></button>`).join('');
}
on('#palettes', 'click', event => {
  const button = event.target.closest('[data-palette]'); if (!button) return;
  state.palette = button.dataset.palette; DesignStudio.palette(state.catalog.palettes[state.palette]); renderPalettes(); renderPreview(); saveDraft();
});
on('#theme', 'change', () => chooseTheme($('#theme').value));
$$('input[name="kind"]').forEach(input => input.addEventListener('change', () => setKind(input.value)));
on('#random-seed', 'click', () => { $('#seed').value = crypto.getRandomValues(new Uint32Array(1))[0] % 2147483647; schedulePreview(); saveDraft(); });
on('#build-form', 'input', event => {
  if (['seed','profile','count'].includes(event.target.id)) schedulePreview();
  else renderPreview();
  saveDraft();
});
on('#build-form', 'change', event => { if (event.target.id === 'profile') schedulePreview(); });
on('#build-form', 'submit', async event => {
  event.preventDefault();
  const button = $('#build-button'); button.disabled = true;
  try { await queue({action:'build', ...config()}); } finally { button.disabled = false; }
});
async function queue(data) {
  const isOnlinePreview = location.hostname.endsWith('github.io') || !location.port;
  const job = await api('jobs', data);
  state.jobs.unshift(job); renderJobs(); $('#jobs-dialog').showModal();
  toast(isOnlinePreview ? 'Preview build logged. Run "python studio.py" locally for real 300 DPI PDFs.' : 'Added to your workshop. You can keep creating.');
}

function schedulePreview() {
  clearTimeout(previewTimer); previewTimer = setTimeout(loadPreview, 250);
}
async function loadPreview() {
  if (!state.theme) return;
  previewController?.abort(); previewController = new AbortController();
  $('#preview-loading').textContent = 'Preparing your preview…';
  $('#preview-loading').hidden = false;
  try {
    const maximum = Math.min(state.theme.puzzles.length, Number($('#count').value) || 1);
    state.index = Math.max(0, Math.min(state.index, maximum - 1));
    const result = await api('preview', {kind:state.kind, theme:$('#theme').value, theme_data:state.kind === 'wordsearch' ? state.theme:undefined, seed:$('#seed').value, profile:$('#profile').value, index:state.index, design:DesignStudio.value()}, previewController.signal);
    state.preview = result; state.selectedWord = -1; renderPreview();
    $('#preview-loading').hidden = true;
  } catch (error) {
    if (error.name !== 'AbortError') { $('#preview-loading').textContent = error.message; toast(error.message, true); }
  }
}
$$('[data-preview]').forEach(button => button.addEventListener('click', () => {
  state.mode = button.dataset.preview; state.selectedWord = -1;
  $$('[data-preview]').forEach(b => b.classList.toggle('selected', b === button)); renderPreview();
}));
on('#previous-puzzle', 'click', () => { state.index--; schedulePreview(); });
on('#next-puzzle', 'click', () => { state.index++; schedulePreview(); });
on('#word-list', 'click', event => {
  const word = event.target.closest('[data-word]'); if (!word) return;
  state.selectedWord = state.selectedWord === Number(word.dataset.word) ? -1 : Number(word.dataset.word); renderPreview();
});
function renderPreview() {
  const puzzle = state.preview;
  if (!puzzle) return;
  const isCover = state.mode === 'cover', solutions = state.mode === 'solution';
  const paper = $('#paper');
  paper.classList.toggle('cover-concept', isCover);
  const palette = puzzle.kind === 'sudoku' ? {bg:[237,242,249],accent:[72,104,156],deep:[22,41,78]} : puzzle.kind === 'maze' ? {bg:[238,244,236],accent:[74,122,86],deep:[26,58,40]} : state.catalog.palettes[state.palette] || state.catalog.palettes.nature;
  const design = DesignStudio.value();
  paper.style.background = isCover ? design.bg : '#fffefa';
  paper.style.color = isCover || design.color_interior ? design.ink : '#34452f';
  $('.paper-title h2').style.fontFamily = {sans:'Segoe UI, sans-serif',serif:'Georgia, serif',mono:'monospace'}[design.font];
  $('#paper-running').textContent = $('#title').value.toUpperCase();
  $('#paper-title').textContent = isCover ? $('#title').value.replace(/^Large Print /i, '') : puzzle.name;
  $('#paper-subtitle').textContent = isCover ? $('#subtitle').value : puzzle.kind === 'wordsearch' ? 'Find a little wonder in every word.' : puzzle.kind === 'maze' ? 'A little patience. A path to discover.' : 'One number at a time.';
  $('#paper-eyebrow').textContent = isCover ? 'LARGE PRINT' : solutions ? 'THE WAY THROUGH' : 'A MOMENT FOR YOURSELF';
  $('#paper-number').textContent = String(state.index + 1).padStart(2, '0');
  $('#paper-author').textContent = $('#author').value;
  $('#paper-footer').textContent = isCover ? `${$('#count').value} PUZZLES · FULL SOLUTIONS` : `${solutions ? 'SOLUTION' : 'PUZZLE'} ${String(state.index + 1).padStart(2, '0')}`;
  $('#preview-caption').textContent = isCover ? 'Cover concept · final artwork in your library' : puzzle.kind === 'wordsearch' ? 'Select a word to reveal its position' : 'Sample puzzle · book uses a difficulty mix';
  const count = Math.min(state.theme?.puzzles.length || 1, Number($('#count').value) || 1);
  $('#puzzle-position').textContent = `${state.index + 1} / ${count}`;
  $('#previous-puzzle').disabled = state.index === 0; $('#next-puzzle').disabled = state.index >= count - 1;
  const canvas = $('#puzzle-canvas'), ctx = canvas.getContext('2d');
  const width = canvas.width;
  ctx.clearRect(0, 0, width, width); ctx.lineCap = 'round';
  const ink = isCover || design.color_interior ? design.ink : '#34452f';
  if (puzzle.kind === 'wordsearch') {
    const n = puzzle.grid.length, cell = width / n;
    const paths = solutions || isCover ? puzzle.paths : state.selectedWord >= 0 ? [puzzle.paths[state.selectedWord]] : [];
    ctx.strokeStyle = design.highlight; ctx.lineWidth = cell * .72;
    paths.forEach(path => { ctx.beginPath(); ctx.moveTo((path[0][1]+.5)*cell,(path[0][0]+.5)*cell); const end=path.at(-1); ctx.lineTo((end[1]+.5)*cell,(end[0]+.5)*cell); ctx.stroke(); });
    ctx.fillStyle = ink; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = `500 ${cell * Math.min(.60, design.font_size / 40)}px ${design.font === 'serif' ? 'Georgia' : design.font === 'mono' ? 'monospace' : 'sans-serif'}`;
    puzzle.grid.forEach((row,r) => row.forEach((letter,c) => ctx.fillText(letter,(c+.5)*cell,(r+.53)*cell)));
    $('#word-list').innerHTML = isCover ? '' : puzzle.words.map((word,index) => `<span data-word="${index}" role="button" tabindex="0" class="${state.selectedWord === index ? 'active' : ''}" aria-label="Reveal ${escapeHTML(word)}">${escapeHTML(word)}</span>`).join('');
  } else if (puzzle.kind === 'sudoku') {
    const pad=7, cell=(width-pad*2)/9;
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.font=`${cell*.46}px 'Segoe UI', sans-serif`;
    for (let i=0;i<=9;i++) { ctx.strokeStyle=i%3===0 ? ink:'#c7cdbf'; ctx.lineWidth=i%3===0?4:1.3; ctx.beginPath(); ctx.moveTo(pad+i*cell,pad); ctx.lineTo(pad+i*cell,width-pad); ctx.moveTo(pad,pad+i*cell); ctx.lineTo(width-pad,pad+i*cell); ctx.stroke(); }
    const grid=solutions ? puzzle.solution:puzzle.grid;
    grid.forEach((row,r)=>row.forEach((number,c)=>{ if(number){ctx.fillStyle=puzzle.grid[r][c]?ink:'#71904d';ctx.fillText(number,pad+(c+.5)*cell,pad+(r+.54)*cell);}}));
    $('#word-list').innerHTML='';
  } else {
    const pad=8,cell=(width-pad*2)/puzzle.size;
    if (solutions) {ctx.strokeStyle='#bdd195';ctx.lineWidth=cell*.32;ctx.beginPath();puzzle.path.forEach(([x,y],i)=>{const px=pad+(x+.5)*cell,py=pad+(y+.5)*cell;i?ctx.lineTo(px,py):ctx.moveTo(px,py);});ctx.stroke();}
    ctx.strokeStyle=ink;ctx.lineWidth=2.5;
    puzzle.walls.forEach(([x,y,walls])=>{
      const x0=pad+x*cell,y0=pad+y*cell;
      for(const wall of walls){if((x===0&&y===0&&wall==='W')||(x===puzzle.size-1&&y===puzzle.size-1&&wall==='E'))continue;ctx.beginPath();const points={N:[x0,y0,x0+cell,y0],E:[x0+cell,y0,x0+cell,y0+cell],S:[x0,y0+cell,x0+cell,y0+cell],W:[x0,y0,x0,y0+cell]}[wall];ctx.moveTo(points[0],points[1]);ctx.lineTo(points[2],points[3]);ctx.stroke();}
    });
    $('#word-list').innerHTML='<span>START ↗</span><span></span><span>↘ FINISH</span>';
  }
}
on('#word-list', 'keydown', event => {if(event.key==='Enter'||event.key===' '){event.preventDefault();event.target.click();}});

function renderThemes() {
  if (!state.catalog) return;
  const query=$('#theme-search').value.toLowerCase();
  const themes=state.catalog.themes.filter(theme=>theme.title.toLowerCase().includes(query));
  $('#theme-grid').innerHTML=themes.map((theme,index)=>{
    const palette=state.catalog.palettes[theme.palette]||state.catalog.palettes.nature;
    const title=shortTitle(theme.title);
    const letters=title.split(/[ &-]+/).filter(Boolean).slice(0,2).map(word=>word[0]).join('');
    return `<button class="theme-card" data-theme="${escapeHTML(theme.id)}" style="--delay:${Math.min(index,8)*25}ms;--theme-bg:rgb(${palette.bg});--theme-color:rgb(${palette.deep})"><div class="theme-art"><span class="letter-art">${escapeHTML(letters)}</span></div><div class="theme-card-content"><h3>${escapeHTML(title)}</h3><small><span>${theme.count} puzzles · Word search</span><span>↗</span></small></div></button>`;
  }).join('') || '<div class="empty"><h2>No themes found.</h2><p>Try another search, or create your own collection.</p></div>';
}
on('#theme-search','input',renderThemes);
on('#theme-grid','click',async event=>{const button=event.target.closest('[data-theme]');if(button){await chooseTheme(button.dataset.theme);setKind('wordsearch',true);go('create');}});
function commitPuzzle() {
  if(!state.editing)return;
  const theme=state.editing;
  theme.title=$('#edit-title').value;theme.author=$('#edit-author').value;theme.subtitle=$('#edit-subtitle').value;
  theme.puzzles[state.editIndex]={name:$('#edit-puzzle-name').value,words:$('#edit-words').value.split(/[,\n]+/).map(word=>word.trim().toUpperCase()).filter(Boolean)};
  $('#theme-json').value=JSON.stringify(theme,null,2);
}
function renderThemeEditor() {
  const theme=state.editing;
  $('#edit-title').value=theme.title||'';$('#edit-author').value=theme.author||'';$('#edit-subtitle').value=theme.subtitle||'';
  $('#edit-puzzle-select').innerHTML=theme.puzzles.map((puzzle,index)=>`<option value="${index}">${index+1}. ${escapeHTML(puzzle.name)}</option>`).join('');
  $('#edit-puzzle-select').value=state.editIndex;
  const puzzle=theme.puzzles[state.editIndex];
  $('#edit-puzzle-name').value=puzzle.name;$('#edit-words').value=puzzle.words.join(', ');
  $('#theme-json').value=JSON.stringify(theme,null,2);
  $('#remove-puzzle').disabled=theme.puzzles.length<=1;
}
function openThemeEditor(theme) {
  if(!theme||!Array.isArray(theme.puzzles)||!theme.puzzles.length||theme.puzzles.some(p=>!p||!Array.isArray(p.words)))throw new Error('Theme JSON needs a puzzles array, with names and word lists.');
  state.editing=structuredClone(theme);state.editIndex=0;renderThemeEditor();$('#theme-dialog').showModal();
}
on('#edit-current','click',()=>openThemeEditor(state.theme));
on('#new-theme','click',()=>openThemeEditor({title:'My Word Search Collection',author:'E. P. Greenwood',subtitle:'',palette:'nature',puzzles:[{name:'A walk in the woods',words:['FOREST','FERN','MOSS','OAK','PINE','TRAIL','LEAF','BIRD']}]}));
on('#theme-editor-form','input',event=>{if(event.target.id!=='theme-json')commitPuzzle();});
on('#edit-puzzle-select','change',()=>{commitPuzzle();state.editIndex=Number($('#edit-puzzle-select').value);renderThemeEditor();});
on('#add-puzzle','click',()=>{commitPuzzle();state.editing.puzzles.push({name:'New puzzle',words:[]});state.editIndex=state.editing.puzzles.length-1;renderThemeEditor();$('#edit-puzzle-name').focus();});
on('#remove-puzzle','click',()=>{if(state.editing.puzzles.length<=1)return;commitPuzzle();state.editing.puzzles.splice(state.editIndex,1);state.editIndex=Math.max(0,state.editIndex-1);renderThemeEditor();});
on('#apply-theme-json','click',()=>{const data=JSON.parse($('#theme-json').value);if(!Array.isArray(data.puzzles)||!data.puzzles.length||data.puzzles.some(p=>!p||!Array.isArray(p.words)))throw new Error('Provide a puzzles array with names and words.');state.editing=data;state.editIndex=0;renderThemeEditor();toast('JSON applied to the editor.');});
on('#theme-editor-form','submit',async event=>{event.preventDefault();commitPuzzle();const result=await api('themes',{theme:state.editing});await refreshCatalog();await chooseTheme(result.id);setKind('wordsearch',true);$('#theme-dialog').close();go('create');toast('Your new theme is saved.');});
function downloadJSON(value,filename){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
on('#export-theme','click',()=>{commitPuzzle();downloadJSON(state.editing,'puzzle-theme.json');});
on('#import-theme','click',()=>$('#theme-file').click());
on('#theme-file','change',async event=>{const file=event.target.files[0];if(!file)return;if(file.size>2000000)throw new Error('Theme files must be smaller than 2 MB.');openThemeEditor(JSON.parse(await file.text()));event.target.value='';});
on('#draft-form','submit',async event=>{event.preventDefault();const form=Object.fromEntries(new FormData(event.target));await queue({action:'draft',title:form.title,model:form.model,topics:form.topics.split('\n').map(topic=>topic.trim()).filter(Boolean)});});

async function refreshBooks(){state.books=await api('books');$('#book-count').textContent=state.books.length;renderBooks();}
function renderBooks(){
  const query=$('#book-search').value.toLowerCase();
  const books=state.books.filter(book=>book.title.toLowerCase().includes(query));
  $('#book-grid').innerHTML=books.map(book=>{
    const cover=book.files.find(file=>file.name==='thumbnail.png')||book.files.find(file=>file.name==='cover.png');
    const active=state.jobs.some(job=>job.book===book.id&&['queued','running'].includes(job.status));
    const status=active?'Building':book.report?book.report.ok?'Preflight passed':'Review needed':'Not checked';
    return `<article class="book-card"><button class="book-cover" data-book="${escapeHTML(book.id)}" aria-label="Open ${escapeHTML(book.title)}">${cover?`<img src="${escapeHTML(cover.url)}" alt="${escapeHTML(book.title)} cover" loading="lazy">`:'<span class="letter-art">Ab</span>'}</button><div class="book-info"><h3>${escapeHTML(book.title)}</h3><span class="tag ${book.report&&!book.report.ok?'warn':''}">${status}</span><div class="book-actions"><button class="secondary" data-book="${escapeHTML(book.id)}">Open book</button><a class="primary" href="/api/download?book=${encodeURIComponent(book.id)}">ZIP ↓</a></div></div></article>`;
  }).join('')||`<div class="empty"><span>▤</span><h2>${query?'No matching books.':'Your first chapter is waiting.'}</h2><p>${query?'Try another search.':'Create a book and its finished files will find a home here.'}</p><button class="primary" id="empty-create">Create a book ↗</button></div>`;
  $('#empty-create')?.addEventListener('click',()=>go('create'));
}
on('#book-search','input',renderBooks);on('#refresh-library','click',refreshBooks);
on('#book-grid','click',event=>{const button=event.target.closest('[data-book]');if(button)openBook(button.dataset.book);});
function reportHTML(report){return report?report.checks.map(line=>`<div class="check-line ${line.startsWith('FAIL')?'fail':line.startsWith('WARN')?'warn':''}">${escapeHTML(line)}</div>`).join(''):'<p class="fine-print">Run preflight to check the generated print files.</p>';}
function openBook(id){
  const book=state.books.find(book=>book.id===id);if(!book)return;
  $('#book-dialog-title').textContent=book.title;
  $('#book-detail').innerHTML=`<div class="download-list">${book.files.filter(file=>file.name!=='thumbnail.png').map(file=>`<a href="${escapeHTML(file.url)}" target="_blank" rel="noopener">${escapeHTML(file.name)} <small>${Math.max(1,Math.round(file.size/1024))} KB ↗</small></a>`).join('')}</div><div class="toolbar"><a class="primary" href="/api/download?book=${encodeURIComponent(id)}">Download everything ↓</a><div><button class="secondary" id="preflight-book">Run preflight</button>${book.editable?'<button class="quiet-button" id="reuse-book">Use settings</button><button class="quiet-button" id="rebuild-cover">Rebuild covers</button>':''}</div></div><div id="book-report">${reportHTML(book.report)}</div><p class="fine-print">Review the complete files before publishing. Preflight checks the engine’s existing rules.</p><iframe class="book-preview" src="${escapeHTML(book.files.find(file=>file.name==='interior.pdf')?.url||'')}" title="Interior PDF preview"></iframe>`;
  $('#preflight-book').addEventListener('click',async()=>{try{$('#book-dialog').close();await queue({action:'preflight',book:id});}catch(error){toast(error.message,true);}});
  $('#rebuild-cover')?.addEventListener('click',async()=>{try{$('#book-dialog').close();await queue({action:'covers',book:id});}catch(error){toast(error.message,true);}});
  $('#reuse-book')?.addEventListener('click',async()=>{try{
    const file=book.files.find(file=>file.name==='project.json');const response=await fetch(file.url);if(!response.ok)throw new Error('Could not load book settings.');const data=await response.json();
    applyConfig(data);$('#book-dialog').close();go('create');toast('Settings restored. Your next build creates a new book.');
  }catch(error){toast(error.message,true);}});
  if(!$('#book-dialog').open)$('#book-dialog').showModal();
}
function applyConfig(data){
  if(data.theme_data)state.theme=data.theme_data;
  if(data.design)DesignStudio.set(data.design);
  for(const name of ['theme','title','subtitle','author','count','seed','profile','badge','back'])if(data[name]!==undefined&&$('#'+name))$('#'+name).value=data[name];
  $('#also-from').value=data.also_from?.length?JSON.stringify(data.also_from,null,2):'';
  state.palette=state.catalog.palettes[data.palette]?data.palette:'nature';renderPalettes();setKind(data.kind||'wordsearch',true);saveDraft();
}
function renderFactory(){
  const {recipes,factory_index:index}=state.catalog;const current=index%recipes.length,recipe=recipes[current];
  $('#next-recipe').textContent=recipe.title;$('#factory-description').textContent=`${recipe.count} puzzles · ${pretty(recipe.profile)} difficulty · Volume ${Math.floor(index/recipes.length)+1}`;
  $('#recipe-list').innerHTML=recipes.map((recipe,i)=>`<article class="recipe ${i===current?'active':''}"><span class="recipe-index">${String(i+1).padStart(2,'0')}</span><div><h3>${escapeHTML(recipe.title)}</h3><p>${escapeHTML(recipe.subtitle)}</p></div><span class="tag">${i===current?'Up next':recipe.count+' puzzles'}</span></article>`).join('');
}
on('#run-factory','click',()=>queue({action:'factory'}));
async function checkConnections(){
  const button=$('#check-connections');button.disabled=true;
  try{const result=await api('connections');for(const key of ['ollama','chrome']){const element=$('#'+key+'-status');element.textContent=result[key].connected?'Connected':'Not connected';element.classList.toggle('warn',!result[key].connected);}}
  catch(error){toast(error.message,true);}finally{button.disabled=false;}
}
on('#check-connections','click',checkConnections);
on('#publish-operation','change',()=>{const series=$('#publish-operation').value==='series';$('#keywords-field').hidden=series;$('#series-note').hidden=!series;});
on('#publish-form','submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.target));await queue({action:'publish',operation:values.operation,book_id:values.book_id,keywords:values.keywords.split('\n').map(keyword=>keyword.trim()).filter(Boolean),confirmed:values.confirmed==='on'});});

function renderJobs(){
  const jobs=state.jobs;
  $('#job-count').textContent=jobs.filter(job=>['queued','running'].includes(job.status)).length;
  $('#job-list').innerHTML=jobs.map(job=>{
    const active=['queued','running'].includes(job.status);
    return `<article class="job"><div class="job-head"><h3>${escapeHTML(job.title)}</h3><span class="tag ${job.status==='failed'?'fail':job.status==='running'?'running':''}">${pretty(job.status)}</span></div><p>${escapeHTML(job.stage)}</p>${active?`<progress max="100" value="${job.progress}" aria-label="${escapeHTML(job.stage)}"></progress>`:''}${job.result?.report?reportHTML(job.result.report):job.result?.checks?reportHTML(job.result):''}${job.result?.message?`<p>${escapeHTML(job.result.message)}</p>`:''}<div class="job-actions">${active?`<button class="quiet-button" data-cancel="${job.id}">Cancel</button>`:''}${job.result?.book?`<button class="secondary" data-result="${escapeHTML(job.result.book)}">View book ↗</button>`:''}${job.result?.asset?`<button class="secondary" data-art="${escapeHTML(job.result.asset.id)}">Use artwork ↗</button>`:''}${job.result?.theme?`<button class="secondary" data-draft="${escapeHTML(job.result.theme)}">Review draft ↗</button>`:''}<button class="quiet-button" data-log="${job.id}">Show log</button></div><pre id="log-${job.id}" hidden></pre></article>`;
  }).join('')||'<div class="empty"><h2>A quiet moment in the workshop.</h2><p>Your builds, drafts, and checks will appear here.</p></div>';
}
on('#job-list','click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.art){DesignStudio.set({...DesignStudio.value(),image:button.dataset.art});$('#jobs-dialog').close();go('design');}
  if(button.dataset.cancel){await api('cancel',{id:button.dataset.cancel});toast('Cancellation requested.');}
  if(button.dataset.log){const block=$('#log-'+button.dataset.log);if(!block.hidden){block.hidden=true;return;}const result=await api('log?id='+button.dataset.log);block.textContent=result.log||'No log output yet.';block.hidden=false;}
  if(button.dataset.result){await refreshBooks();$('#jobs-dialog').close();go('library');openBook(button.dataset.result);}
  if(button.dataset.draft){await refreshCatalog();const theme=await api('theme?id='+encodeURIComponent(button.dataset.draft));$('#jobs-dialog').close();openThemeEditor(theme);}
});
async function pollJobs(){
  try{
    const previous=new Map(state.jobs.map(job=>[job.id,job.status]));const jobs=await api('jobs');
    state.jobs=jobs;
    const signature=JSON.stringify(jobs.map(job=>[job.id,job.status,job.progress,job.stage]));
    if(signature!==jobSignature){jobSignature=signature;renderJobs();}
    let completed=false;
    for(const job of jobs){if(previous.has(job.id)&&['queued','running'].includes(previous.get(job.id))&&!['queued','running'].includes(job.status)){completed=true;toast(job.status==='completed'?`${job.title}: complete.`:job.status==='cancelled'?'Job cancelled.':`${job.title}: needs attention.`,job.status==='failed');}}
    if(completed){await Promise.all([refreshBooks(),refreshCatalog()]);window.dispatchEvent(new Event('studio-artwork'));}
    if (location.hostname.endsWith('github.io') || !location.port) {
      $('#connection-label').textContent='GitHub Pages Preview';$('#connection-dot').style.background='#74995c';
    } else {
      $('#connection-label').textContent='Your engine is connected';$('#connection-dot').style.background='#74995c';
    }
  }catch(error){
    if (location.hostname.endsWith('github.io') || !location.port) {
      $('#connection-label').textContent='GitHub Pages Preview';$('#connection-dot').style.background='#74995c';
    } else {
      $('#connection-label').textContent='Engine disconnected';$('#connection-dot').style.background='#b67c55';
    }
  }
  setTimeout(pollJobs,state.jobs.some(job=>['queued','running'].includes(job.status))?1400:6000);
}
async function start(){
  try{
    await refreshCatalog();
    let draft;try{draft=JSON.parse(localStorage.getItem('puzzle-studio-draft'));}catch(_){}
    await chooseTheme(state.catalog.themes.some(theme=>theme.id==='nature.json')?'nature.json':state.catalog.themes[0].id);
    if(draft)applyConfig(draft);
    await refreshBooks();go(location.hash.slice(1)||'create');pollJobs();
  }catch(error){$('#connection-label').textContent='Access link required';$('#connection-dot').style.background='#b67c55';$('#build-button').disabled=true;$('#preview-loading').hidden=false;$('#preview-loading').textContent=error.message;toast(error.message,true);}
}
start();
