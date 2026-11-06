/* 视线跟随 + 头部转动 + 图层视差 —— 让千岁会「看着你」。
 *
 * 为什么单独一个文件：app.js 管的是她的嘴、眨眼、换衣服，那些都不能碰。
 * 这个文件只做一件事——把鼠标的位置，翻译成「头转过去一点」。
 * 不想要了，删掉 index.html 里那行 <script src="gaze.js"> 就干净复原。
 *
 * 三层动作，缺一层就假（2026-10-25 第一版只做了前两层，宝宝说「头没有动」）：
 *
 *   1. 头转  —— 脸、眼、嘴、脸红**一起绕脖子转**（±1.8°）。
 *               同一圈五官给同一个角度、同一个轴心，才不会各转各的散架。
 *               轴心不写死：拿「脸」那层自己的框算下巴位置（left+w/2, top+h），
 *               换衣服换了立绘也跟得上。
 *   2. 走位  —— 每层按深度平移，近的（眼睛）多走一点，远的（身体）少走。
 *   3. 头发  —— 比头慢半拍，用弹簧不用插值：弹簧会先冲过头再回来，
 *               那点过冲就是头发甩起来的味道。转的角度也比头小一半，
 *               不然长发下摆会从身体上撕开。
 *
 * 2026-10-25 加。参数都在下面，界面上「摆一摆」里也有个「跟随」滑块，
 * 拖到 0 就是彻底关掉。
 */
(() => {
  'use strict';

  // 系统开了「减少动态效果」就不折腾她
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return;
  }

  const figure = document.getElementById('figure');
  if (!figure) return;   // 不是在千岁的窗口里，什么都不做

  /* 每一层的「深度」：数字越大，离镜头越近，走位越夸张。
     身体最沉、眼睛最灵——照着真人的头写的，不是随手排的。

     2026-10-26 改过一次，原因很重要：
     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     原来身体给 0.30、眼睛给 0.95，眼睛跑 17px 而脸皮只跑 5px——
     宝宝的原话是「眼睛后面那一层脸部都不动，看着很奇怪」。
     对：脸皮是长在 body 那张图上的（不是单独一层），
     所以**头是一整块**，body / 脸红 / 五官必须几乎同一个深度一起走，
     只有眼睛稍微领先一点点（+0.06，约 1px，是眼珠子转的味道，不是打滑）。
     唯一允许落后的是头发——它靠弹簧的惯性慢半拍，那是重量感，不是脱节。 */
  const DEPTH = {
    'L-body': 0.92,
    'L-hair': 0.84,
    'L-blush': 0.94,
    'L-face': 0.94,
    'L-mouth': 0.97,
    'L-mouth-cover': 0.97,
    'L-eyes': 0.98,
  };

  const MAX_X = 18;        // 最深那层最多平移多少像素（原画尺度，外面还会被 --s 缩一次）
  const MAX_Y = 10;
  /* 2026-10-25 退回：头和五官**先不转了**。
     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     原因：脸不是单独一层——body 那张图在脸那块 97.8% 不透明，
     脸皮长在身体上；能转的只有 7.3% 的那几笔五官。
     硬转的结果就是「眼睛嘴在脸皮上滑」，比不转更假。
     所以先回到只平移的版本（宝宝说的「眼睛头发动了」那版），
     等真把头从 body 里切出来，再把 HEAD_ROT 打开。 */
  const HEAD_ROT = 0;      // 头绕脖子最多转多少度（0 = 不转，等切头）
  const HAIR_ROT = 0;      // 头发跟着转多少（同上）
  const FIG_ROT = 0.55;    // 整身再让一点点，像重心跟着偏（这版原本就是 0.55）
  const IDLE_MS = 2600;    // 鼠标不动这么久，她慢慢看回正前方
  /* 跟随速度：每层一个，眼睛最快，身体最沉。
     2026-10-26 提速：原来六个图层共用一个 0.14，宝宝说「眼睛有点慢」。
     但**不能只加快眼睛**——眼睛一快就会在快速晃鼠标时甩到脸皮前面去，
     又变成上一条反馈说的「打滑」。所以整块头一起提速（0.26~0.28），
     眼睛只比脸快一点点（0.32），领先的是**时间**不是距离。 */
  const LERP = {
    'L-body': 0.26,
    'L-face': 0.28,
    'L-blush': 0.28,
    'L-mouth': 0.28,
    'L-mouth-cover': 0.28,
    'L-eyes': 0.32,
  };
  const LERP_DEFAULT = 0.14;
  const HEAD_LERP = 0.10;  // 头转的跟随速度（比平移再软一点）
  const SPRING_K = 0.055;  // 头发：弹簧刚度
  const SPRING_DAMP = 0.86;// 头发：阻尼，越小甩得越软
  const HAIR_ROT_K = 0.045;// 头发的**转角**用另一根更软的弹簧
  const HAIR_ROT_DAMP = 0.88;

  const NUM = (v) => {
    const n = parseFloat(v);
    return isFinite(n) ? n : 0;
  };

  const els = {};
  const cur = {};
  for (const id of Object.keys(DEPTH)) {
    const el = document.getElementById(id);
    if (!el) continue;
    els[id] = el;
    cur[id] = { x: 0, y: 0, vx: 0, vy: 0, ox: null, oy: null };
  }

  // 跟随强度（0 = 关）。存在这台机器上，下次打开还记得。
  let strength = 1;
  try {
    const v = parseFloat(localStorage.getItem('chitose.gaze'));
    if (isFinite(v) && v >= 0 && v <= 1.6) strength = v;
  } catch (e) { /* 存档坏了就用默认 */ }

  const now = () => (window.performance && performance.now ? performance.now() : Date.now());
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

  let tx = 0;
  let ty = 0;
  let lastMove = -1e9;

  /* 鼠标在哪 = 她该看哪。以窗口中间偏上（大概是她的脸）当原点。 */
  function aim(clientX, clientY) {
    const ax = window.innerWidth / 2;
    const ay = window.innerHeight * 0.38;
    tx = clamp((clientX - ax) / (window.innerWidth * 0.5), -1, 1);
    ty = clamp((clientY - ay) / (window.innerHeight * 0.5), -1, 1);
    lastMove = now();
  }

  window.addEventListener('pointermove', (e) => aim(e.clientX, e.clientY), { passive: true });
  window.addEventListener('pointerdown', (e) => aim(e.clientX, e.clientY), { passive: true });
  window.addEventListener('blur', () => { lastMove = -1e9; });

  /* 脖子在哪：拿「脸」那层的框当下巴。
     脸那层的 left/top/w/h 是 app.js 从 layers.json 摆的，这里只读不改。
     读不到就退回 0，顶多这一帧不转——绝不写死一个猜的数。 */
  function neckPoint() {
    const f = els['L-face'];
    if (!f) return null;
    const l = NUM(f.style.left);
    const t = NUM(f.style.top);
    const w = NUM(f.style.width);
    const h = NUM(f.style.height);
    if (!w || !h) return null;
    return { x: l + w / 2, y: t + h };   // 下巴正中：脸框底边中点
  }

  let headRot = 0;
  let hairRot = 0;
  let hairRotV = 0;
  let figRot = 0;
  let figApplied = null;

  function frame() {
    const idle = (now() - lastMove) > IDLE_MS;
    const gx = idle ? 0 : tx;
    const gy = idle ? 0 : ty;

    // 头：脸/眼/嘴/脸红共用一个角度
    const wantHead = gx * HEAD_ROT * strength;
    headRot += (wantHead - headRot) * HEAD_LERP;
    if (Math.abs(wantHead - headRot) < 0.003) headRot = wantHead;

    // 头发：转角的软弹簧（慢半拍 + 过冲）
    const wantHairRot = gx * HAIR_ROT * strength;
    hairRotV += (wantHairRot - hairRot) * HAIR_ROT_K;
    hairRotV *= HAIR_ROT_DAMP;
    hairRot += hairRotV;

    // 整身：再让一点点，像重心跟着偏
    const wantFig = gx * FIG_ROT * strength;
    figRot += (wantFig - figRot) * 0.08;
    if (Math.abs(wantFig - figRot) < 0.004) figRot = wantFig;

    const neck = neckPoint();

    for (const id in els) {
      const c = cur[id];
      const el = els[id];
      const d = DEPTH[id] * strength;

      // ── 走位 ──
      const wantX = gx * MAX_X * d;
      const wantY = gy * MAX_Y * d;

      if (id === 'L-hair') {
        c.vx += (wantX - c.x) * SPRING_K;
        c.vy += (wantY - c.y) * SPRING_K;
        c.vx *= SPRING_DAMP;
        c.vy *= SPRING_DAMP;
        c.x += c.vx;
        c.y += c.vy;
      } else {
        const k = LERP[id] || LERP_DEFAULT;
        c.x += (wantX - c.x) * k;
        c.y += (wantY - c.y) * k;
        if (Math.abs(wantX - c.x) < 0.02) c.x = wantX;
        if (Math.abs(wantY - c.y) < 0.02) c.y = wantY;
      }

      // ── 转角 ──
      // 头发转一半；其余头部件跟头；身体不转。
      let rot = 0;
      if (id === 'L-hair') rot = hairRot;
      else if (id !== 'L-body') rot = headRot;

      // 嘴：不直接写 transform，交给 CSS 动画（translate 变量 + scaleY）。
      // 否则动画会把 translate 覆盖掉；遮片仍然按普通图层跟随。
      if (id === 'L-mouth') {
        el.style.setProperty('--mx', c.x.toFixed(2) + 'px');
        el.style.setProperty('--my', c.y.toFixed(2) + 'px');
        el.style.setProperty('--mrot', rot.toFixed(3) + 'deg');
        el.style.transformOrigin = '50% 50%';
      } else {
        // 轴心：同一个世界点(脖子) → 每层自己的坐标里该是哪里
        if (neck) {
          const l = NUM(el.style.left);
          const t = NUM(el.style.top);
          const ox = (neck.x - l).toFixed(2) + 'px';
          const oy = (neck.y - t).toFixed(2) + 'px';
          if (c.ox !== ox || c.oy !== oy) {
            el.style.transformOrigin = ox + ' ' + oy;
            c.ox = ox;
            c.oy = oy;
          }
        }
        el.style.transform =
          'translate3d(' + c.x.toFixed(2) + 'px,' + c.y.toFixed(2) + 'px,0)' +
          (rot ? ' rotate(' + rot.toFixed(3) + 'deg)' : '');
      }
    }

    // style.css 的 #figure 里有个 rotate(calc(var(--gazeRot) * 1deg))
    if (figApplied === null || Math.abs(figRot - figApplied) > 0.002) {
      document.documentElement.style.setProperty('--gazeRot', figRot.toFixed(3));
      figApplied = figRot;
    }

    requestAnimationFrame(frame);
  }

  /* 「摆一摆」里加一行滑块。不想手动调就无视它。 */
  try {
    const tune = document.getElementById('tune');
    if (tune) {
      const row = document.createElement('div');
      row.className = 'row';

      const label = document.createElement('label');
      label.textContent = '跟随';

      const input = document.createElement('input');
      input.type = 'range';
      input.id = 'tGaze';
      input.min = '0';
      input.max = '1.6';
      input.step = '0.05';
      input.value = String(strength);

      const val = document.createElement('span');
      val.className = 'val';
      val.id = 'vGaze';
      val.textContent = strength.toFixed(2);

      input.addEventListener('input', () => {
        strength = parseFloat(input.value) || 0;
        val.textContent = strength.toFixed(2);
        try { localStorage.setItem('chitose.gaze', String(strength)); } catch (e) {}
      });

      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(val);
      const anchor = tune.querySelector('p');
      if (anchor) tune.insertBefore(row, anchor); else tune.appendChild(row);
    }
  } catch (e) { /* 面板结构变了也不影响她跟进鼠标 */ }

  requestAnimationFrame(frame);
})();
