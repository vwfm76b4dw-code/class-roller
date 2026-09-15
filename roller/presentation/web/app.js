/* ============================================================
   课堂抽奖器 — 前端逻辑
   ------------------------------------------------------------
   抽奖、名单、配置全部由 Python 侧负责；这里只做呈现与交互。

   抽奖动画设计（界面的核心体验，不是装饰）：
   把"抽"拆成三段，让等待可感知、结果有分量：

     1. 起跑（约 480ms）  姓名快速跳动，快到看不清具体字
     2. 减速（约 760ms）  跳动间隔递增，开始能看清字
     3. 落定（约 420ms）  定格 + 放大过冲回弹 + 转为强调色

   减速段是关键：人能感觉到"快出来了"，注意力自然集中到结果上。
   相比"固定频率闪 600ms 再突然停"，这样才有物理感。
   总时长约 1.2s——够被看见，又不用等。

   动画用 requestAnimationFrame 自控节奏（setInterval 做不出平滑减速），
   并尊重系统"减少动态效果"。
   ============================================================ */

const $ = (id) => document.getElementById(id);

const el = {
  body: document.body,
  liveDot: $('liveDot'),
  statusTag: $('statusTag'),
  nameText: $('nameText'),
  metaLine: $('metaLine'),
  btnDraw: $('btnDraw'),
  btnSettings: $('btnSettings'),
  btnMin: $('btnMin'),
  btnClose: $('btnClose'),
  btnPin: $('btnPin'),
  sheet: $('sheet'),
  btnSheetClose: $('btnSheetClose'),
  btnSheetDone: $('btnSheetDone'),
  tabs: $('tabs'),
  rosterList: $('rosterList'),
  rosterHint: $('rosterHint'),
  historyList: $('historyList'),
  historyHint: $('historyHint'),
  cfgPath: $('cfgPath'),
  toast: $('toast'),
  swTop: $('swTop'),
  swFair: $('swFair'),
  swAnim: $('swAnim'),
};

/* 动画节奏（毫秒） */
const TIMING = {
  runup: 480,
  slow: 760,
  settle: 420,
};

let state = { animations: true, drawing: false, rollRaf: null, rollTimer: null };

/* ---------- 与 Python 通信 ---------- */
async function call(fn, ...args) {
  try {
    return await window.pywebview.api[fn](...args);
  } catch (err) {
    console.error('调用失败', fn, err);
    return null;
  }
}

/* ---------- 轻提示 ---------- */
let toastTimer = null;
function toast(text, isError = false) {
  el.toast.textContent = text;
  el.toast.classList.toggle('err', isError);
  el.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.remove('show'), 2400);
}

/* ---------- 动画能力 ---------- */
function animEnabled() {
  if (!state.animations) return false;
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/* ---------- 抽奖动画 ---------- */

/**
 * 起跑 + 减速：姓名跳动的间隔由小到大递增。
 *
 * 用 requestAnimationFrame 自己控节奏——每次跳动后把间隔加大一点，
 * 就能得到平滑的减速；setInterval 只能固定频率，做不出"快出来了"的感觉。
 */
function startRolling(names) {
  stopRolling();
  if (!names.length) return;

  el.statusTag.textContent = '抽取中';
  el.statusTag.classList.add('show');
  el.liveDot.className = 'dot busy';
  el.nameText.classList.remove('idle', 'winner');

  if (!animEnabled()) {
    el.nameText.textContent = names[0];
    return;
  }
  el.nameText.classList.add('rolling');

  const start = performance.now();
  const total = TIMING.runup + TIMING.slow;
  let last = 0;
  let interval = 42;      // 起始约 24 次/秒：快到看不清

  const step = (now) => {
    const t = now - start;
    if (t >= total) return;
    if (t - last >= interval) {
      last = t;
      const p = t / total;
      interval = 42 + 155 * p * p;      // 间隔递增 → 减速
      el.nameText.textContent = names[Math.floor(Math.random() * names.length)];
    }
    state.rollRaf = requestAnimationFrame(step);
  };
  state.rollRaf = requestAnimationFrame(step);
}

function stopRolling() {
  if (state.rollTimer) { clearInterval(state.rollTimer); state.rollTimer = null; }
  if (state.rollRaf) { cancelAnimationFrame(state.rollRaf); state.rollRaf = null; }
  el.liveDot.className = 'dot';
  el.nameText.classList.remove('rolling');
}

/**
 * 落定：定格 + 放大过冲回弹 + 颜色转强调色。
 *
 * 关键是"先过冲再收回"——这一下让结果有落地的重量感；
 * 直接放大到目标值会显得轻飘。
 */
function settleWinner(name) {
  const node = el.nameText;
  node.textContent = name;
  node.classList.remove('idle', 'rolling');
  node.classList.add('winner');

  if (!animEnabled()) {
    node.style.transform = '';
    node.style.filter = '';
    node.style.opacity = '';
    return;
  }

  node.animate(
    [
      { transform: 'scale(0.7)', filter: 'blur(7px)', opacity: 0.3 },
      { transform: 'scale(1.12)', filter: 'blur(0px)', opacity: 1, offset: 0.66 },
      { transform: 'scale(0.97)', offset: 0.85 },
      { transform: 'scale(1)', filter: 'blur(0px)', opacity: 1 },
    ],
    { duration: TIMING.settle, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'none' }
  );
}

/** 按钮涟漪：从按下处扩散，确认"收到了"。 */
function ripple(button, event) {
  if (!animEnabled()) return;
  const rect = button.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const span = document.createElement('span');
  span.className = 'ripple';
  span.style.width = span.style.height = `${size}px`;
  const px = (event && event.clientX != null) ? event.clientX : rect.left + rect.width / 2;
  const py = (event && event.clientY != null) ? event.clientY : rect.top + rect.height / 2;
  span.style.left = `${px - rect.left - size / 2}px`;
  span.style.top = `${py - rect.top - size / 2}px`;
  button.appendChild(span);
  setTimeout(() => span.remove(), 560);
}

/* ---------- 抽奖 ---------- */
async function draw(event) {
  if (state.drawing) return;

  const overview = await call('overview');
  if (!overview || overview.count === 0) {
    toast('还没有名单，先到「设置 → 名单」导入', true);
    openSheet('roster');
    return;
  }

  state.drawing = true;
  el.btnDraw.disabled = true;
  ripple(el.btnDraw, event);

  startRolling(overview.names);
  const rollTotal = animEnabled() ? TIMING.runup + TIMING.slow : 0;

  // Python 侧完成抽取；这里等动画走完再落定
  const winner = await call('draw');

  setTimeout(async () => {
    stopRolling();
    if (!winner) {
      toast('抽取失败', true);
      state.drawing = false;
      el.btnDraw.disabled = false;
      return;
    }
    settleWinner(winner);
    el.statusTag.textContent = '抽中';
    el.statusTag.classList.add('show');
    el.liveDot.className = 'dot ok';
    setTimeout(() => { el.liveDot.className = 'dot'; }, 1400);

    await refreshMeta();
    await refreshHistory();
    state.drawing = false;
    el.btnDraw.disabled = false;
  }, rollTotal);
}

/* ---------- 状态刷新 ---------- */
async function refreshMeta() {
  const s = await call('status');
  if (s) el.metaLine.textContent = s;
}

function renderRoster(names) {
  el.rosterList.innerHTML = '';
  if (!names || !names.length) {
    const li = document.createElement('li');
    li.textContent = '（名单为空，点「导入文件」添加）';
    li.style.color = 'var(--label-tertiary)';
    el.rosterList.appendChild(li);
    el.rosterHint.textContent = '共 0 名学生';
    return;
  }
  const frag = document.createDocumentFragment();
  names.forEach((n) => {
    const li = document.createElement('li');
    li.textContent = n;
    frag.appendChild(li);
  });
  el.rosterList.appendChild(frag);
  el.rosterHint.textContent = `共 ${names.length} 名学生`;
}

function renderHistory(records) {
  el.historyList.innerHTML = '';
  if (!records || !records.length) {
    const li = document.createElement('li');
    li.textContent = '（暂无抽奖记录）';
    li.style.color = 'var(--label-tertiary)';
    el.historyList.appendChild(li);
    el.historyHint.textContent = '共 0 条记录';
    return;
  }
  const frag = document.createDocumentFragment();
  records.forEach((r, i) => {
    const li = document.createElement('li');
    if (i === 0) li.classList.add('win');
    const name = document.createElement('span');
    name.textContent = r.name;
    const t = document.createElement('time');
    t.textContent = r.time;
    li.append(name, t);
    frag.appendChild(li);
  });
  el.historyList.appendChild(frag);
  el.historyHint.textContent = `共 ${records.length} 条记录（最近在上）`;
}

async function refreshRoster() {
  renderRoster((await call('roster_names')) || []);
}

async function refreshHistory() {
  renderHistory((await call('history')) || []);
}

async function loadSettings() {
  const cfg = await call('settings');
  if (!cfg) return;
  el.swTop.checked = !!cfg.always_on_top;
  el.swFair.checked = !!cfg.fair_mode;
  el.swAnim.checked = !!cfg.animations;
  state.animations = !!cfg.animations;
  el.body.classList.toggle('no-anim', !state.animations);
  el.cfgPath.textContent = cfg.config_path || '';
  el.btnPin.classList.toggle('is-on', !!cfg.always_on_top);
}

/* ---------- 设置抽屉 ---------- */
function openSheet(tab) {
  if (tab) switchTab(tab);
  el.sheet.classList.add('open');
  el.sheet.setAttribute('aria-hidden', 'false');
}
function closeSheet() {
  el.sheet.classList.remove('open');
  el.sheet.setAttribute('aria-hidden', 'true');
}
function switchTab(name) {
  el.tabs.querySelectorAll('.tab').forEach((b) =>
    b.classList.toggle('is-active', b.dataset.tab === name));
  document.querySelectorAll('.pane').forEach((p) =>
    p.classList.toggle('is-active', p.dataset.pane === name));
}

/* ---------- 事件绑定 ---------- */
function bind() {
  el.btnDraw.addEventListener('click', draw);

  el.btnSettings.addEventListener('click', async () => {
    await refreshRoster();
    await refreshHistory();
    await loadSettings();
    openSheet();
  });
  el.btnSheetClose.addEventListener('click', closeSheet);
  el.btnSheetDone.addEventListener('click', closeSheet);
  el.sheet.addEventListener('click', (e) => {
    if (e.target === el.sheet) closeSheet();
  });

  el.tabs.addEventListener('click', (e) => {
    const b = e.target.closest('.tab');
    if (b) switchTab(b.dataset.tab);
  });

  el.btnMin.addEventListener('click', () => call('minimize'));
  el.btnClose.addEventListener('click', () => call('close'));
  el.btnPin.addEventListener('click', async () => {
    const on = await call('toggle_topmost');
    el.btnPin.classList.toggle('is-on', !!on);
    el.swTop.checked = !!on;
  });

  $('btnImport').addEventListener('click', async () => {
    const res = await call('import_roster');
    if (res && res.count) {
      toast(`已导入 ${res.count} 条，共 ${res.total} 人`);
      await refreshRoster();
      await refreshMeta();
    } else if (res && res.error) {
      toast(res.error, true);
    }
  });

  $('btnAdd').addEventListener('click', async () => {
    const text = prompt('输入姓名（多个用逗号分隔）');
    if (!text) return;
    const res = await call('add_students', text);
    toast(res && res.added ? `新增 ${res.added} 人` : '没有新增（姓名为空）');
    await refreshRoster();
    await refreshMeta();
  });

  $('btnExport').addEventListener('click', async () => {
    const res = await call('export_roster');
    if (res && res.ok) toast(`已导出 ${res.path}`);
    else if (res && res.error) toast(res.error, true);
  });

  $('btnClear').addEventListener('click', async () => {
    if (!confirm('确认清空全部学生？')) return;
    await call('clear_roster');
    toast('名单已清空');
    await refreshRoster();
    await refreshMeta();
  });

  $('btnClearHistory').addEventListener('click', async () => {
    if (!confirm('确认清空全部抽奖历史？')) return;
    await call('clear_history');
    toast('历史已清空');
    await refreshHistory();
  });

  $('btnOpenCfg').addEventListener('click', () => call('open_config_dir'));

  el.swTop.addEventListener('change', () => call('set_topmost', el.swTop.checked));
  el.swFair.addEventListener('change', async () => {
    await call('set_fair_mode', el.swFair.checked);
    await refreshMeta();
    toast(el.swFair.checked ? '已开启：一轮内不重复' : '已关闭：纯均匀随机');
  });
  el.swAnim.addEventListener('change', async () => {
    state.animations = el.swAnim.checked;
    el.body.classList.toggle('no-anim', !state.animations);
    await call('set_animations', state.animations);
  });

  // 空格也能抽（讲课时手不用离开键盘）
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !el.sheet.classList.contains('open')) {
      e.preventDefault();
      draw(null);
    }
    if (e.key === 'Escape') closeSheet();
  });
}

/* ---------- 启动 ---------- */
async function boot() {
  bind();
  await loadSettings();
  await refreshMeta();
  await refreshHistory();

  const overview = await call('overview');
  el.nameText.textContent = (overview && overview.count === 0)
    ? '还没有名单，点右上角设置导入'
    : '准备好了';
  el.nameText.classList.add('idle');
}

if (window.pywebview && window.pywebview.api) boot();
else window.addEventListener('pywebviewready', boot);
