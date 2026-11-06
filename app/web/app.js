/* 千岁的窗口 —— 前端。
 *
 * 立绘的每一个坐标都是从 .hg3 文件头里读出来的（assets/layers.json），
 * 这个文件里不出现任何「猜」出来的位置。
 *
 * 她要动三样东西，别的都不动：
 *   呼吸 —— style.css 里的 #breathe
 *   眨眼 —— 换一张闭眼的五官层
 *   嘴   —— 跟着**真实音量**开合（Web Audio 分析当前播的那段声音）
 */

const $ = (s) => document.querySelector(s);

/* 自己的版本号（server.py 给 app.js 挂了 ?v=……）。
   ⚠ `layers.json` 住在 /assets/ 底下，那边的缓存是**故意放行**的
   （立绘 6M，每次重下太慢）。可它写着图层坐标和嘴的新裁剪框，改了必须跟着换。
   所以拿 app.js 自己的版本号去取它——**app.js 一变，坐标也跟着重下**，
   免得宝宝的界面里出现「旧坐标 + 新图片」这种半新不旧的东西。 */
const SELF_V = (() => {
  const s = document.currentScript;
  if (!s || !s.src) return '';
  const q = s.src.indexOf('?');
  return q < 0 ? '' : s.src.slice(q + 1);
})();

const PLATE = $('#plate');
const CN = $('#cn');
const JP = $('#jp');
const FACE = $('#L-face');
const HAIR = $('#L-hair');
const EYES = $('#L-eyes');
const MOUTH = $('#L-mouth');
const MOUTH_COVER = $('#L-mouth-cover');
const BLUSH = $('#L-blush');

/* 对话记录：全屏遮罩，背景完全不动 */
const LOG_PANEL = $('#logPanel');
const LOG_BTN = $('#logBtn');
const LOG_CLOSE = $('#logClose');
const LOG_SCROLL = $('#logScroll');
const LOG_LIST = $('#logList');
const LOG_LATEST = $('#logLatest');
const LOG_KEY = 'chitose.log.v1';
let LOG_ENTRIES = [];
let LOG_OPEN = false;
try {
  const raw = localStorage.getItem(LOG_KEY);
  if (raw) {
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) LOG_ENTRIES = arr.slice(-50);
  }
} catch (e) { /* 存档坏了就当没有 */ }

let LAYERS = null;
let tuning = { s: 0.47, axis: 695, top: 87 };

/* ── 起手：读坐标、摆图 ───────────────────────────── */

async function boot() {
  LAYERS = await (await fetch('/assets/layers.json?' + SELF_V)).json();

  for (const [tag, L] of Object.entries(LAYERS.layers)) {
    const img = ({ body: $('#L-body'), hair: $('#L-hair') })[tag];
    if (!img) continue;
    place(img, L);
  }
  // 脸红是差分层，平时不上，需要时用 setBlush() 盖上去
  BLUSH.removeAttribute('src');
  place(FACE, LAYERS.layers['face.idle']);
  // 说话用的那一小块嘴：位置放好就行。
  // **别在这儿写 `MOUTH.style.display = 'none'`** —— inline 样式会盖过 CSS，
  // 那样 `#L-mouth.on` 就永远显示不出来（姐姐 2026-10-11 踩过：
  // 截图里她的嘴一动不动，探针报 display:none 但 class 明明是 on）。
  // 藏起来这件事交给 style.css 的 `#L-mouth{display:none}`。
  place(MOUTH, LAYERS.layers['mouth.open']);
  place(MOUTH_COVER, LAYERS.layers['mouth.cover'] || LAYERS.layers['mouth.open']);
  // 眨眼用的那层「睁着的眼睛」（见 blinkOn）
  place(EYES, LAYERS.layers['eyes.idle']);

  // 五官层全部预热，眨眼/换表情时不闪（脸红也是——它是差分层，平时不上）
  for (const tag of Object.keys(LAYERS.layers)) {
    if (tag.startsWith('face.') || tag.startsWith('mouth.')
        || tag.startsWith('blush.') || tag.startsWith('eyes.')
        || tag.startsWith('hair.')) {
      new Image().src = url(LAYERS.layers[tag]);
    }
  }

  loadTuning();
  document.body.classList.add('ready');
  $('#figure').addEventListener('animationend', (e) => {
    e.target.style.animation = 'none';       // 让「大小」滑块还能改得动
  });

  // 眨眼动画跑完：底下换回该有的脸，那层眼睛也归位，然后排下一次
  EYES.addEventListener('animationend', () => {
    if (!blinkingNow) return;
    blinkingNow = false;
    setFace(baseFace);
    EYES.style.animation = 'none';
    scheduleBlink();
  });

  // 先看看这台机器有什么：脑子填了没、耳朵装没装。
  // 没脑子就先把「怎么填」说出来，比让她安安静静坐着更清楚。
  const st = await checkStatus();
  if (!st || st.brain !== false) greet();
  scheduleBlink();
}

/* ── 开窗先看这台机器有什么 ─────────────────────────
 * brain：有没有填模型钥匙（没填就在字幕板提醒，界面照样能看）
 * ears ：耳朵装没装（没装就把「按住说话」收起来，只留打字）
 */
async function checkStatus() {
  let st = null;
  try { st = await (await fetch('/api/status')).json(); } catch (e) { console.error(e); }
  if (!st) return null;

  if (!st.ears) {
    EARS_ON = false;
    const talk = $('#talk');
    if (talk) talk.remove();
  }

  if (!st.brain) {
    const cfg = st.config_path ? st.config_path.replace(/\\/g, '/') : 'config.json';
    CN.innerHTML = '<span class="err">姐姐的脑子还没接上。<br>' +
      '打开 ' + esc(cfg) + '，把 base_url 和 api_key 填好，再开一次窗。</span>';
    JP.textContent = '';
  }
  return st;
}

function url(L) {
  // 素材也要带版本号：/assets 是故意允许缓存的（立绘 6M），
  // 但羽化过的小嘴、眼睛如果被旧缓存顶掉，就会又冒出那个方框。
  // layers.json 里的 version 每次重建素材都会变，跟着它换 URL。
  return '/assets/' + L.file + (LAYERS && LAYERS.version ? '?v=' + LAYERS.version : '');
}

function place(img, L) {
  img.style.left = L.x + 'px';
  img.style.top = L.y + 'px';
  img.style.width = L.w + 'px';
  img.style.height = L.h + 'px';
  const u = url(L);
  if (img.getAttribute('src') !== u) img.src = u;
}

/* ── 她的脸 ───────────────────────────────────────── */

let showed = 'idle';        // 现在贴在脸上的那张（变了才换，不然会闪）
let baseFace = 'idle';      // 不算眨眼的话，这会儿该是哪张脸
let baseMood = '';          // 这一句的心情标签（同是 shut_smile，轻笑和亲密要分开）
let blinkingNow = false;
let speakingNow = false;    // 她正在说**一整句**（不是单个音节，也不是待机）
let speechSeq = 0;          // 第几句在说：旧的一句收尾时，别把新的一句关掉

let faceSeq = 0;            // 换脸序号：旧图解码慢了，不许它再动新脸的位置

function setFace(tag) {
  const L = LAYERS.layers['face.' + tag];
  if (!L || showed === tag) return;
  showed = tag;
  const my = ++faceSeq;
  const apply = () => {
    if (my !== faceSeq) return;   // 已经被下一张脸接替了，别回来捣乱
    place(FACE, L);
  };

  const u = url(L);
  if (FACE.getAttribute('src') === u) { apply(); return; }

  // ⚠ 先只换 src，**坐标和大小等新图解码完再换**。
  //   害羞那张（843×625）比平静脸（336×259）大一大圈；
  //   先改 width/height 的话，浏览器会有一帧把**旧的平静脸拉大**铺上去，
  //   宝宝 2026-10-27 看到的「两张脸同时出现」就是这一帧。
  FACE.src = u;
  if (FACE.decode) {
    FACE.decode().then(apply).catch(apply);
  } else if (FACE.complete && FACE.naturalWidth) {
    apply();
  } else {
    FACE.addEventListener('load', apply, { once: true });
  }
}

/* 换「常态脸」，顺便决定那层「睁着的眼睛」要不要让开。
   眨眼的时候先记着，眨完再换——不然刚换上的表情会被那一眨盖掉。 */
function setBaseFace(tag, moodTag) {
  baseFace = tag;
  baseMood = moodTag || '';
  syncEyes();
  // ⚠ 要是换脸的时候她**正好在眨**，那个眨眼就作废了：`syncEyes()` 一改
  //   display，动画立刻被掐掉，**animationend 永远不会来**，那新表情就永远
  //   挂不上去（姐姐 2026-10-11 卡在这上面：探针说 baseFace 是 question，
  //   屏幕上却还是上一张脸）。所以这里主动收尾，别等那个不会再来的事件。
  if (blinkingNow) {
    blinkingNow = false;
    EYES.style.animation = 'none';
    scheduleBlink();
  }
  setFace(tag);
  syncMouth();
}

/* 闭着眼的那两张表情（闭眼笑、打哈欠）。它们说完话要挂着的时候，
   得靠下面那层「平时的眼睛」把闭着的眼盖掉——不然她就一直闭着眼。 */
const CLOSED_FACES = ['shut_smile', 'shut_open'];

/* 这会儿脸上是不是由那层「平时的眼睛」做主（= 看起来是睁眼的）。 */
function eyesOn() {
  return baseFace === 'idle' || CLOSED_FACES.indexOf(baseFace) >= 0;
}

/* 那层「睁着的眼睛」什么时候露出来。
   · 平时（idle）——当然要露，不然她没眼睛
   · **闭着眼的表情也露**——这是宝宝 2026-10-11 逼出来的：
     「说完话了应该是继续保持变化后的表情 不要切回待机的表情了」。
     可闭眼笑那张如果就这么挂着，她就一直闭着眼。
     把平时那双眼睛盖上去，就成了「**平时那双眼睛 + 那张脸的笑嘴**」
     = 睁着眼笑，挂着也好看。
   · 其余表情（惊讶 / 难过 / 认真 / 无语）自带眼睛，这层必须让开 */
function syncEyes() {
  EYES.style.display = eyesOn() ? 'block' : 'none';
}

function setBlush(key) {
  if (!key) { BLUSH.removeAttribute('src'); return; }
  place(BLUSH, LAYERS.layers[key]);
}

/* 她说话时脸跟着情绪走（宝宝 2026-10-11 定的规矩：
   「表情要跟着情绪变 但必须是对应情景的」）。
   左边是她自己想话时标的心情（`[轻笑]`、`[害羞]` 这些，本来只给嗓子加音效），
   右边是要换的脸——**同一个标签两处使**。

   宝宝 2026-10-28 在 17 张总览上逐张正名：
     talk_a     = 惊讶 / 意外
     smile      = 生气 / 严肃（**不是浅笑**）
     tereb      = 被调戏了、和一般害羞不一样
     wow        = 尴尬
     blink_talk = 叹气 / 打哈欠犯困（心里有烦心事）
     question   = 疑惑 / 呆萌（也当无语用）
     serious    = 认真（**不含叹气**）
   说话时会开合的嘴：这些脸各自有一套 `mouth.open_<face>` / `cover`，
   没有的那几张用平时那张嘴（量过，盖得住）。 */
const MOOD_FACE = {
  '轻笑': 'shut_smile',
  // 害羞 / 撒娇 / 无奈 = 一般害羞那张（00000z：鼓脸 + 红晕）
  '害羞': 'shy',
  '撒娇': 'shy',
  '无奈': 'shy',
  // 轻笑 / 亲密 / 亲吻 = 闭眼含笑
  '亲密': 'shut_smile',
  '亲吻': 'shut_smile',
  // 宝宝正名后的几张
  '惊讶': 'talk_a',
  '难过': 'cry',
  '叹气': 'blink_talk',
  '犯困': 'blink_talk',
  '无语': 'question',
  '疑惑': 'question',
  '生气': 'smile',
  '说错话': 'wow', // 只在「意识到自己说错话/做错事」时用，不是普通害羞
  '尴尬': 'wow',   // 兼容旧标签
  '被调戏': 'tereb', // 只有她被宝宝逗的时候
  '调戏': 'tereb',   // 兼容旧称呼
  '懵': 'surprise',
  '认真': 'serious',
  '张嘴': 'ahaa',
  '卖萌': 'ahaa',   // 平时也可以用的卖萌脸
  '喊': 'shout',   // 只在她真的生气、呵斥宝宝时用（比如没吃饭）
  '担心': 'serious',
  '微笑': 'talk_b',
};
const MOOD_BLUSH = {
  // 现在**空着**：害羞那几张自己就带脸蛋的红（`face.shy` 就是 `00000z`）。
  // 想让她再红一点，往这儿加一行 `'害羞': 'blush.light'` 就行。
};

/* 嘴只有两态：抿着 / 张开。
 *
 * ⚠ **姐姐不再换整张脸了**，这条是宝宝 2026-10-11 看出来的：
 * 「眼睛突然变大又恢复」。原来说话时把 face 层在 idle 和 talk_a 之间来回切，
 * 可 talk_a 那张的**眼睛是睁圆的，比 idle 大一圈**——每开一次口眼睛就放大一次。
 * 实测两张脸差 25726 个像素，**其中 20862 全在眼睛上**，嘴只占 4864。
 * 换成 talk_b 也没用（眼睛还差 3522，看得出来）。
 *
 * 现在：脸永远是最上面那张 idle，一动不动；说话时只往嘴上盖一小块
 * 裁剪出来的嘴（layers.json 的 mouth.open）。量过：抿嘴那 307 个像素
 * **一个不漏**地全被盖住，所以两只眼睛从头到尾纹丝不动。
 *
 * 另外两条老坑也还记着：
 * · **原来每帧都 setFace** → 一秒换几十次，嘴在跳。现在状态没变就一个像素都不碰
 * · **阈值不能写死** → 她这几句的 RMS 峰值是 0.47，按 0.085 算的话嘴全程大张。
 *   所以每句话都按**它自己的音量**归一（取 92 分位当峰值，不用最大值，
 *   免得一个爆音把整句压平） */
const HOP_MS = 30;

/* 一段声音 → 每 30ms 一个 RMS。回复走这条，问候用的是服务端算好的同一份 */
function envelopeOf(ab) {
  const hop = Math.max(1, Math.round(ab.sampleRate * HOP_MS / 1000));
  const ch = ab.getChannelData(0);
  const out = [];
  for (let i = 0; i + hop <= ch.length; i += hop) {
    let s = 0;
    for (let j = 0; j < hop; j++) { const v = ch[i + j]; s += v * v; }
    out.push(Math.sqrt(s / hop));
  }
  return out;
}

function peakOf(env) {
  if (!env.length) return 0.05;
  const s = env.slice().sort((a, b) => a - b);
  return Math.max(0.02, s[Math.floor(s.length * 0.92)] || s[s.length - 1]);
}

let mouthLevel = 0;         // 平滑后的音量
let mouthAmt = 0;           // 0~1 的张口程度（也平滑过）
let mouthOpen = false;      // 那块张开的嘴现在露不露（控制 .on）
let mouthLoudAt = 0;        // 最后一次「够响」的时刻
let mouthCloseRAF = 0;

/* 阈值都是**相对这一段自己的音量**，不是绝对音量。 */
const MOUTH_ON = 0.12;      // 过了就说明她在出声
const MOUTH_MIN = 0.16;     // 抿住时嘴的高度（scaleY），不是 0——0 会缩成一条线
const MOUTH_MIN_X = 0.55;   // 抿住时嘴的宽度（scaleX）：第 10 张的嘴比待机嘴宽，
                            // 收窄一点才像从那张嘴张开，不是横着拉一条缝

/* 把张口程度交给 CSS（style.css 的 --mopen / --mopenx）。 */
function setMouthOpen(v) {
  const k = v < MOUTH_MIN ? MOUTH_MIN : (v > 1 ? 1 : v);
  const a = (k - MOUTH_MIN) / (1 - MOUTH_MIN);          // 0 = 抿住，1 = 全张
  MOUTH.style.setProperty('--mopen', k.toFixed(3));
  MOUTH.style.setProperty('--mopenx',
    (MOUTH_MIN_X + (1 - MOUTH_MIN_X) * a).toFixed(3));
}

/* 嘴那一块什么时候露：她这会儿在出声。
   遮片和张开嘴一起 `.on`，CSS 里做 90ms 的交叉淡入淡出——
   待机嘴被皮肤慢慢盖住，张开的嘴慢慢浮上来。

   眨眼不用管嘴：眨眼那张的嘴和说话的嘴是同一个位置
   （`check_all_faces.py` 量过，盖不住 0 个），说到一半眨眼照样开合。 */
function syncMouth() {
  // ⚠ **害羞那张不叠说话的嘴**。宝宝 2026-10-11 看合成图时说的：
  //   「第二张…嘴巴是张开的」——`face.shy`（`00000z`）自己那个小抿嘴
  //   就是害羞的味道，叠上「啊」型的大张嘴就串味了。
  //   她抿着嘴说话也挺好，反正声音和字幕都在。
  // 害羞那张不叠说话嘴。
  // **轻笑**（shut_smile + 心情「轻笑」）用**待机那张嘴**——
  // 宝宝 2026-10-26：「轻笑时的张嘴应该也和待机的张嘴一样」。
  // 亲密 / 亲吻还是用它自己的小圆笑嘴，不要一起换掉。
  // 惊讶（surprise / 00000e）用 talk_a 的**正圆嘴**——
  // 宝宝 2026-10-26 要的「圆嘴」；它自己的小嘴太小，开合看不出来。
  // 素材在 build_web_assets.py 的 _mouth_on_face 里对准它的嘴中心。
  // 害羞那张不叠说话嘴（理由见上面那段）。
  // ⚠ **微笑（talk_b）要叠**——宝宝 2026-10-29：「千岁微笑时说话嘴巴不动了」。
  //   那张脸自己的嘴是一条薄薄的微笑线（94×43，开合几乎看不出来），
  //   所以它**不进**下面 ownMouth，借平时那张圆嘴来讲。戴的是 `mouth.cover`，
  //   量过：talk_b 的嘴 146 个深色像素一个不漏全盖住。
  const show = mouthOpen && baseFace !== 'shy';
  if (show) {
    // 每张脸优先用它自己的那套嘴（build_web_assets.py 里的 mouth.open_<face>）；
    // 没有的（cry / serious / question …）用平时那张，量过盖得住。
    // 轻笑虽然也是 shut_smile，但宝宝要它和待机用同一张嘴，所以不加 _smile。
    let suffix = '';
    // 注意：`mouth.open_smile` 是「闭眼含笑」专用的，不是 face.smile（生气）的。
    // 所以这里只认这几张**自己带嘴型素材**的脸，别让名字撞上。
    // talk_b 故意不列：它自己的嘴是条薄笑线，开合看不出来（见上面那段）。
    const ownMouth = ['talk_a', 'tereb', 'wow', 'blink_talk', 'shout'];
    if (baseFace === 'shut_smile' && baseMood !== '轻笑') suffix = '_smile';
    else if (baseFace === 'surprise') suffix = '_surprise';
    else if (ownMouth.indexOf(baseFace) >= 0
             && LAYERS.layers['mouth.open_' + baseFace]) suffix = '_' + baseFace;
    place(MOUTH, LAYERS.layers['mouth.open' + suffix] || LAYERS.layers['mouth.open']);
    // 嘴唇缩小时会露出底下的待机嘴，所以遮片要跟着一起上
    place(MOUTH_COVER, LAYERS.layers['mouth.cover' + suffix] || LAYERS.layers['mouth.cover']);
  }
  MOUTH.classList.toggle('on', show);
  MOUTH_COVER.classList.toggle('on', show);
}

/* 声音 → 嘴。宝宝 2026-10-26：
   「要有动画，不要硬切，动画要丝滑」。
   所以不再按固定节拍一张一合，也不靠 CSS 循环：
   每一帧拿真实音量算一个 0~1 的张口量，开得快、合得慢，
   再交给 CSS 去缩那一小块嘴（--mopen）。
   短促的音节之间留 160ms 的余温，嘴不会一闪一闪。 */
function driveMouth(rms, peak) {
  const p = peak || 0.05;
  const rel = rms / p;
  // 先平滑音量：出声跟得快，收得慢一点
  mouthLevel += (rms - mouthLevel) * (rms > mouthLevel ? 0.55 : 0.10);

  const now = performance.now();
  if (rel > MOUTH_ON) {
    mouthLoudAt = now;
    if (mouthCloseRAF) { cancelAnimationFrame(mouthCloseRAF); mouthCloseRAF = 0; }
  }

  // 0 = 闭着，1 = 全张；留一点底噪不动
  let want = (mouthLevel / p - MOUTH_ON * 0.5) / 0.55;
  if (!(want > 0)) want = 0;
  else if (want > 1) want = 1;

  // 嘴唇的惯性：张开快、合上慢。每帧只走一小步，就不会「啪」地跳。
  mouthAmt += (want - mouthAmt) * (want > mouthAmt ? 0.45 : 0.18);
  if (mouthAmt < 0.001) mouthAmt = 0;
  else if (mouthAmt > 0.999) mouthAmt = 1;

  const show = (now - mouthLoudAt) < 160;   // 短停顿里嘴不急着消失
  if (show !== mouthOpen) {
    mouthOpen = show;
    syncMouth();
    if (!show) closeMouth();                // 淡出的同时把嘴慢慢合上
  }
  if (mouthOpen) setMouthOpen(MOUTH_MIN + (1 - MOUTH_MIN) * mouthAmt);
}

/* 把嘴从现在的张开度收回到抿住，90ms。
   和 opacity 的淡出同时走，所以是「边说边合上」，
   不是定住一张张大的嘴、直接消失。 */
function closeMouth() {
  cancelAnimationFrame(mouthCloseRAF);
  const from = mouthAmt;
  mouthAmt = 0;
  const t0 = performance.now();
  (function close() {
    const k = Math.min(1, (performance.now() - t0) / 90);
    setMouthOpen(MOUTH_MIN + (1 - MOUTH_MIN) * from * (1 - k));
    if (k < 1) mouthCloseRAF = requestAnimationFrame(close);
  })();
}

function mouthRest() {
  mouthLevel = 0;
  mouthOpen = false;
  syncMouth();               // opacity 开始淡出
  closeMouth();              // 同时把这口气慢慢收回去
}

/* 眨眼：**待机的时候才眨**。
   用的那张是「闭眼 + 平时的嘴」（`build_web_assets.py` 的 `_blink_face`
   拼出来的）——不哭也不笑，就是平时的她闭上了眼。

   ⚠ **她说话的时候不许眨。** 宝宝 2026-10-11：
   「说到一半又突然变成待机的那个眯眼了 这不应该出现的」。
   有道理的：她说话说到一半忽然闭一下眼，看着像**表情掉了、退回待机**。

   ⚠ 条件得**两个一起看**：
   · `speakingNow`（整句在说）——**不能只盯 `baseFace !== 'idle'`**：
     她有时候回的话不带心情标签，那时 baseFace 也是 idle，一眨眼又露馅了
   · `baseFace !== 'idle'`（说完还挂着表情的那几秒）——那会儿脸上
     没有那层「睁着的眼睛」（`syncEyes` 收起来了），硬眨只会让嘴闪一下
   跳过这一次就再排下一轮，反正她回话也就几秒。

   **一次眨多久**：95~145ms（照真人写的）→ 200~340ms（宝宝要看清）→
   现在是**一整段 600~800ms 的动画**，闭上占 35%、闭着停 20%、睁开占 45%。
   真人没这么慢，可是看得清、也好看——宝宝原话：「把眨眼的时长变久一点
   直接当一个表情 但要有动画一样的转变过程 不要两张图切」。
   间隔仍是 2.6~6.2 秒。 */
let blinkTimer = null;
function scheduleBlink() {
  clearTimeout(blinkTimer);
  blinkTimer = setTimeout(() => {
    // 她正在说话、或者脸上这层眼睛不在（表情自带眼睛的那种）——这一轮不眨
    if (speakingNow || !eyesOn()) {
      scheduleBlink();
      return;
    }
    blinkOn();
  }, 2600 + Math.random() * 3600);
}

/* 眨一次眼 —— **不是两张图切**，是眼睑慢慢落下来、再慢慢抬起来。
   做法：底下先换成闭着眼的那张（`face.blink`，反正被上面盖着看不见），
   然后让那层「睁着的眼睛」跑 eyeBlink 动画：慢慢淡掉（=闭上）、
   停一下、再慢慢淡回来（=睁开）。收尾在下面那个 animationend 里。
   宝宝 2026-10-11：「把眨眼的时长变久一点 直接当一个表情
   但要有动画一样的转变过程 不要两张图切」。 */
function blinkOn() {
  blinkingNow = true;
  /* 2026-10-26 修：这里原来是 `if (!eyesOn())`，条件反了。
     ~~~~~~~~~~~~ 症状：眼睛一动不动，看着"不眨眼"了。
     量出来的原因：上层 `eyes_idle.png` 和底下 `idle_face.png` 里的眼睛
     是同一幅画（实心区域 IoU 99.5%），所以淡掉上层 = 露出底下那双**睁着的**
     眼睛，动画在跑、画面上什么都没变。
     正确的做法就是注释里写的：**被上层盖着的时候**把底下换成闭眼那张
     （`face.blink` = 闭眼 + 平时的嘴，跟 idle 的嘴一样，所以看不见嘴变），
     上层淡下去的过程中，闭着的眼睛就一点点透出来。
     闭眼的表情（shut_smile / shut_open）本来就没睁眼，不用换也不会闪嘴。 */
  if (baseFace === 'idle') setFace('blink');
  EYES.style.animation = 'none';
  void EYES.offsetWidth;                  // 逼它重排，动画才能从头再来一遍
  /* 一次眨多久：600~800ms → **400~540ms**（2026-10-26 宝宝说「眨一次眼的动作
     感觉有点慢了」）。真人眨眼 100~400ms，之前那档本来就是为了"看得清"故意
     拖长的；现在闭眼那张脸已经真的会换了（见上面那个修），不用再拖那么久
     才看得见，收到 400~540 既清楚也不拖沓。
     比例没动：0→35% 闭上、35→55% 停、55→100% 睁开，
     所以是"整体走得快一点"，不是硬切。 */
  EYES.style.animation = 'eyeBlink ' + (220 + Math.random() * 80) + 'ms ease-in-out';
}

/* ── 字幕 ─────────────────────────────────────────── */

function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

/* ── 对话记录 ───────────────────────────────────────
   全屏盖上来，但房间和她完全不动。只改文字层，不碰背景。 */
function saveLog() {
  try { localStorage.setItem(LOG_KEY, JSON.stringify(LOG_ENTRIES.slice(-50))); } catch (e) {}
}

function logStamp(t) {
  const d = new Date(t), now = new Date();
  const p = (n) => String(n).padStart(2, '0');
  const same = d.toDateString() === now.toDateString();
  return (same ? '' : p(d.getMonth() + 1) + '/' + p(d.getDate()) + ' ') +
    p(d.getHours()) + ':' + p(d.getMinutes());
}

function renderLog() {
  const stick = LOG_OPEN && (LOG_SCROLL.scrollHeight - LOG_SCROLL.scrollTop - LOG_SCROLL.clientHeight < 80);
  const prev = LOG_SCROLL.scrollTop;
  if (!LOG_ENTRIES.length) {
    LOG_LIST.innerHTML = '<div class="log-empty">还没有记录呀</div>';
    LOG_LATEST.classList.remove('show');
    return;
  }
  LOG_LIST.innerHTML = LOG_ENTRIES.map((e) => {
    const me = e.who === 'user';
    const jp = e.jp ? '<div class="log-jp">' + esc(e.jp) + '</div>' : '';
    const mood = e.mood ? '<span class="log-mood">' + esc(e.mood) + '</span>' : '';
    return '<div class="log-entry' + (me ? ' me' : '') + '">' +
      '<div class="log-who">' + (me ? '宝宝' : '千岁') + '</div>' +
      '<div class="log-cn">' + esc(e.cn) + '</div>' + jp +
      '<div class="log-meta">' + mood + '<span>' + logStamp(e.t) + '</span></div>' +
      '</div>';
  }).join('');
  if (stick) requestAnimationFrame(() => { LOG_SCROLL.scrollTop = LOG_SCROLL.scrollHeight; updateLogLatest(); });
  else LOG_SCROLL.scrollTop = prev;
}

function addLog(cn, jp, mood, who) {
  if (!cn) return;
  LOG_ENTRIES.push({
    cn: String(cn), jp: jp ? String(jp) : '', mood: mood ? String(mood) : '',
    who: who === 'user' ? 'user' : '',
    t: Date.now(),
  });
  LOG_ENTRIES = LOG_ENTRIES.slice(-50);
  saveLog();
  renderLog();
}

function openLog() {
  if (LOG_OPEN) return;
  LOG_OPEN = true;
  LOG_PANEL.classList.add('open');
  LOG_PANEL.setAttribute('aria-hidden', 'false');
  document.body.classList.add('log-open');
  renderLog();
  requestAnimationFrame(() => {
    LOG_SCROLL.scrollTop = LOG_SCROLL.scrollHeight;
    updateLogLatest();
  });
}

function closeLog() {
  if (!LOG_OPEN) return;
  LOG_OPEN = false;
  LOG_PANEL.classList.remove('open');
  LOG_PANEL.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('log-open');
}

function updateLogLatest() {
  const near = LOG_SCROLL.scrollHeight - LOG_SCROLL.scrollTop - LOG_SCROLL.clientHeight < 28;
  LOG_LATEST.classList.toggle('show', !near && LOG_ENTRIES.length > 0);
}

LOG_BTN.addEventListener('click', openLog);
LOG_CLOSE.addEventListener('click', closeLog);
LOG_LATEST.addEventListener('click', () => {
  LOG_SCROLL.scrollTop = LOG_SCROLL.scrollHeight;
  updateLogLatest();
});
LOG_SCROLL.addEventListener('scroll', updateLogLatest, { passive: true });
LOG_PANEL.addEventListener('click', (e) => { if (e.target === LOG_PANEL) closeLog(); });
window.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const a = document.activeElement;
  const typing = a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA');
  if (e.code === 'KeyL' && !typing) {
    e.preventDefault();
    LOG_OPEN ? closeLog() : openLog();
  } else if (e.code === 'Escape' && LOG_OPEN) {
    e.preventDefault();
    closeLog();
  }
});
renderLog();

/* 她自己发出的声音（开头的 `[轻笑]`、`[叹气]`）和「……」这类，
   压暗一点、标出来，读起来才像在听她说话，而不是在看一行说明。
   注意：`[轻笑]` 这个标注**同时也是换脸用的那个**（见 MOOD_FACE）。 */
/* 服务器偶尔只把标签留在正文里、`mood` 没带过来（旧进程或格式差异）。
   这里再兜一层：从她这句话开头的标签认出心情，脸照样换。 */
const TAG_MOOD = {
  '轻笑': '轻笑', '笑': '轻笑', '微笑': '轻笑', '笑意': '轻笑',
  '害羞': '害羞', '羞': '害羞', '脸红': '害羞',
  '撒娇': '撒娇', '无奈': '无奈', '亲密': '亲密', '亲吻': '亲吻',
  '惊讶': '惊讶', '吃惊': '惊讶', '难过': '难过', '伤心': '难过',
  '叹气': '叹气', '叹息': '叹气', '犯困': '犯困', '困': '犯困', '无语': '无语',
  '说错话': '说错话', '尴尬': '说错话', '做错事': '说错话', '说漏嘴': '说错话',
  '搞砸': '说错话', '糟了': '说错话', '糟糕': '说错话', '失误': '说错话',
  '疑惑': '疑惑', '困惑': '疑惑', '不解': '疑惑',
  '生气': '生气', '不高兴': '生气', '吃醋': '生气',
  '被调戏': '被调戏', '调戏': '被调戏', '逗你': '被调戏', '捉弄': '被调戏',
  '懵': '懵', '呆住': '懵', '愣住': '懵',
  '认真': '认真', '正经': '认真',
  '张嘴': '张嘴', '喂': '张嘴',
  '卖萌': '卖萌', '装可爱': '卖萌', '卖乖': '卖萌',
  '喊': '喊', '呵斥': '喊', '吼': '喊', '凶': '喊',
  '担心': '担心', '担忧': '担心', '挂心': '担心',
  '微笑': '微笑', '浅笑': '微笑',
};

function moodFromText(text) {
  const m = String(text || '').match(/^[\[【［（(]\s*([^\[\]【】［］（）()\s]{1,6})\s*[\]】］）)]/);
  if (!m) return '';
  const name = m[1].replace(/[！!。.，,、～~…・]+$/, '').trim();
  return TAG_MOOD[name] || '';
}

function markVoices(text) {
  let head = '';
  let rest = text;
  const t = rest.match(/^[\[【［（(]\s*[^\[\]【】［］（）()\s]{1,6}\s*[\]】］）)]\s*/);
  if (t) { head = t[0]; rest = rest.slice(t[0].length); }
  const m = rest.match(/^[（(]?[…‥・\s、。，！？!?~ー]+/);
  if (m && m[0].trim().length >= 2) {
    head += m[0];
    rest = rest.slice(m[0].length);
  }
  if (!head) return esc(text);
  return '<span class="me">' + esc(head) + '</span>' + esc(rest);
}

let typer = null;
let typerCancel = null;

/* 把正在打的字停下来。下一句要用字幕板时先叫它——
   不然上一句的定时器会一直往上写，把新的一句盖掉。 */
function stopTypeOut() {
  if (typer) { clearInterval(typer); typer = null; }
  const cancel = typerCancel;
  typerCancel = null;
  if (cancel) cancel();
  CN.classList.remove('typing');
}

function typeOut(text, ms) {
  stopTypeOut();
  CN.classList.add('typing');
  const raw = text == null ? '' : String(text);
  const html = markVoices(raw);
  // 按字符数均分时间：字跟声音一起走完，不抢在声音前面
  const chars = [...raw];
  const step = Math.max(30, Math.min(260, (ms || chars.length * 62) / Math.max(1, chars.length)));
  let i = 0;
  return new Promise((done) => {
    let finished = false;
    const finish = (withFinal) => {
      if (finished) return;
      finished = true;
      if (typer) { clearInterval(typer); typer = null; }
      if (typerCancel === cancel) typerCancel = null;
      CN.classList.remove('typing');
      if (withFinal) CN.innerHTML = html;
      done();                 // 被下一句打断也收尾，别让 await 永远卡着
    };
    const cancel = () => finish(false);
    typerCancel = cancel;
    if (!chars.length) { finish(true); return; }
    // 第一个字立刻上板：不然短句子要等一个节拍（最长 260ms）才看见字，
    // 听起来像「她说了但对话框没显示」。
    CN.textContent = chars[0];
    i = 1;
    if (i >= chars.length) { finish(true); return; }
    typer = setInterval(() => {
      i += 1;
      CN.textContent = chars.slice(0, i).join('');
      if (i >= chars.length) finish(true);
    }, step);
  });
}

function sayNow(cn, jp) {
  JP.textContent = jp || '';
  JP.style.visibility = jp ? 'visible' : 'hidden';
}

/* ── 声音：放出来，同时让她的嘴跟着动 ─────────────── */

let AC = null;
function audioCtx() {
  if (!AC) AC = new (window.AudioContext || window.webkitAudioContext)();
  if (AC.state === 'suspended') AC.resume();
  return AC;
}

function b64bytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/* 出声，嘴跟着走。嘴用的是**预先算好的音量曲线**，跟音频时钟对齐——
   比每帧现读分析器稳，也不会把抖动传进脸里。 */
function playBuffer(ab) {
  const ac = audioCtx();
  const env = envelopeOf(ab);
  const peak = peakOf(env);
  document.body.classList.add('speaking');
  return new Promise((done) => {
    const src = ac.createBufferSource();
    src.buffer = ab;
    src.connect(ac.destination);
    const t0 = ac.currentTime + 0.05;      // 起步留一点余量
    src.start(t0);
    let live = true;
    src.onended = () => {
      live = false;
      document.body.classList.remove('speaking');
      mouthRest();
      done(ab.duration);
    };
    (function loop() {
      if (!live) return;
      const t = (ac.currentTime - t0) * 1000;
      if (t >= 0) driveMouth(env[Math.floor(t / HOP_MS)] || 0, peak);
      requestAnimationFrame(loop);
    })();
  });
}

/* 开场问候：声音是**服务端**放的（网页还没被点过，浏览器不让出声），
   这边只跑嘴。曲线就是那段话的真实音量，30ms 一格。 */
function playEnvelope(env, durMs) {
  const peak = peakOf(env);
  document.body.classList.add('speaking');
  return new Promise((done) => {
    const t0 = performance.now();
    (function loop() {
      const t = performance.now() - t0;
      if (t > durMs + 150) {
        document.body.classList.remove('speaking');
        mouthRest();
        done();
        return;
      }
      driveMouth(env[Math.floor(t / HOP_MS)] || 0, peak);
      requestAnimationFrame(loop);
    })();
  });
}

/* ── 一次完整的来回 ───────────────────────────────── */

function reset() {
  // 上一句还在打字的话，先停下来——不然它会盖掉这一轮的「……」
  stopTypeOut();
  PLATE.classList.remove('is-listening', 'is-thinking');
  document.body.classList.remove('speaking');
}

async function reply(body) {
  const { cn, jp, audio, mood } = body;
  // 有声版：先把声音解出来（要它的长度），再**同时**起字幕——原来是等声音放完才打字，慢了一整句
  // 静音版：audio 是 null，按字数估一个时长，只打字。
  let ab = null;
  if (audio) {
    try {
      ab = await audioCtx().decodeAudioData(b64bytes(audio).buffer);
    } catch (e) { console.error(e); }
  }
  sayNow(cn, jp);

  // 这一整句都算「她在说话」——期间不眨眼（见 scheduleBlink）
  const moodTag = Array.isArray(mood) ? mood[0]
    : (typeof mood === 'string' ? mood : '');
  // 服务器给了认识的心情就用；没给（或给了不认识的）就从正文开头的标签补
  const tag = (moodTag && MOOD_FACE[moodTag]) ? moodTag
    : (moodFromText(cn) || moodTag);
  addLog(cn, jp, tag);
  const my = ++speechSeq;
  speakingNow = true;
  try {
    // 开口之前先对上表情：她说话的时候脸跟着这句话的情绪走（见 MOOD_FACE）
    setBaseFace(MOOD_FACE[tag] || 'idle', tag);
    setBlush(MOOD_BLUSH[tag] || null);

    const typed = typeOut(cn, ab ? Math.max(800, ab.duration * 1000)
                                 : Math.max(1200, cn.length * 90));
    if (ab) await playBuffer(ab);
    await typed;
  } finally {
    // 只有「最新这一句」才归它关灯：上一句被新的一句接替时，
    // 不能把新的一句的 speakingNow 也抹掉（那会让眨眼误开）。
    if (my === speechSeq) speakingNow = false;
    // **不切回平时的脸**——表情留着等下一句（见下面那段）
    syncEyes();          // 说完这层眼睛要不要露（闭眼的表情得盖上）
  }
}

/* 说完之后**不切回平时的脸**。宝宝 2026-10-11 说了两回：
   先是「说完了不应该立马切回待机表情 应该继续保持 a 表情等着下一段对话再变表情」，
   姐姐给闭眼的表情加了个 2.2 秒的限时，他又说
   「不是说 说完话了应该是继续保持变化后的表情 不要切回待机的表情了」。
   —— **那就一直挂着**。下一句进来时 reply() 自然会换掉；
   想让她回平时的样子，说一句不带心情的话就行。
   闭眼的表情怎么挂着不别扭，见 syncEyes() 上面那段。 */

async function turn(fetchCall) {
  reset();
  PLATE.classList.add('is-thinking');
  CN.innerHTML = '<span class="me">……</span>';
  CN.classList.remove('typing');
  try {
    const r = await fetchCall();
    const body = await r.json();
    if (!r.ok || body.error) throw new Error(body.error || ('HTTP ' + r.status));
    reset();
    if (body.heard === '') {                        // 没听清
      CN.innerHTML = '<span class="me">……</span>';
      JP.textContent = '';
      return;
    }
    // 按住说话：把她听到的那句话也记进对话记录（打字那条在提交时记）
    if (typeof body.heard === 'string' && body.heard) {
      addLog(body.heard, '', '', 'user');
    }
    await reply(body);
  } catch (e) {
    reset();
    console.error(e);
    JP.textContent = '';
    CN.innerHTML = '<span class="err">没接上话：' + esc(e.message) +
      '<br>看看 config.json 里的模型地址和钥匙填对了没。</span>';
  }
}

/* ── 按住说话 ─────────────────────────────────────── */

let recording = false;
let EARS_ON = true;          // checkStatus() 会按 /api/status 改它
const TALK = $('#talk');

async function recStart() {
  if (!EARS_ON || recording) return;
  recording = true;
  TALK.classList.add('on');
  TALK.textContent = '松开发送';
  PLATE.classList.add('is-listening');
  try { await fetch('/api/rec/start', { method: 'POST' }); } catch (e) { console.error(e); }
}

async function recStop() {
  if (!recording) return;
  recording = false;
  TALK.classList.remove('on');
  TALK.textContent = '按住说话';
  PLATE.classList.remove('is-listening');
  await turn(() => fetch('/api/rec/stop', { method: 'POST' }));
}

TALK.addEventListener('pointerdown', (e) => { e.preventDefault(); recStart(); });
window.addEventListener('pointerup', () => recStop());
window.addEventListener('pointercancel', () => recStop());
TALK.addEventListener('contextmenu', (e) => e.preventDefault());

/* 空格也能按住说话（在输入框里打字时不管） */
window.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' || e.repeat) return;
  const a = document.activeElement;
  if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA')) return;
  e.preventDefault();
  recStart();
});
window.addEventListener('keyup', (e) => {
  if (e.code !== 'Space') return;
  const a = document.activeElement;
  if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA')) return;
  e.preventDefault();
  recStop();
});

/* ── 打字 ─────────────────────────────────────────── */

$('#type').addEventListener('click', () => {
  PLATE.classList.toggle('typing');
  if (PLATE.classList.contains('typing')) $('#typing').focus();
});

const TYPING = $('#typing');
let composing = false;
let justComposedAt = 0;
TYPING.addEventListener('compositionstart', () => { composing = true; });
TYPING.addEventListener('compositionend', () => {
  composing = false;
  justComposedAt = performance.now();
});
// 输入法用 Enter 选字时，别让表单把它当成「发送」——那会把输入框清空，
// 输入法也跟着被重置。捕获阶段先拦住。
// ⚠ 有些输入法会**先**发 compositionend、**再**发同一个 Enter 的 keydown，
//   只查 composing 会漏掉；所以结束后的 180ms 里也把 Enter 让给输入法。
TYPING.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (e.isComposing || composing || e.keyCode === 229 ||
      performance.now() - justComposedAt < 180) {
    e.preventDefault();
    e.stopPropagation();
  }
}, true);

$('#typebar').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (composing) return;
  const t = TYPING.value.trim();
  if (!t) return;
  TYPING.value = '';
  // 先把宝宝这句话记下来——不用等她回完，记录里马上就能看到
  addLog(t, '', '', 'user');
  // 发出去以后把焦点留在输入框，输入法别被按钮抢走
  if (PLATE.classList.contains('typing')) TYPING.focus();
  await turn(() => fetch('/api/say', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: t }),
  }));
});

/* ── 开场那一句：按现在的钟点，用她提前录好的声音 ────
   声音是**服务端放的**——网页刚打开、还没被点过，浏览器不让出声。
   服务端把那段话的真实音量曲线一起给过来，嘴照样跟着动。 */

async function greet() {
  let hello = null;
  try {
    hello = await (await fetch('/api/hello')).json();
  } catch (e) { console.error(e); }
  if (!hello || !hello.cn) return;

  sayNow(hello.cn, hello.jp);
  addLog(hello.cn, hello.jp, '');
  const durMs = Math.max(900, (hello.dur || 2) * 1000);

  const my = ++speechSeq;
  speakingNow = true;                 // 问候也是一整句，这期间不眨眼
  // ⚠ 字要**先起头**，再放声音。原来等 playEnvelope 跑完才 typeOut，
  //   整段问候期间字幕板都是空的；而且这期间宝宝一说话，
  //   新回复会被迟到的问候字盖掉（2026-10-26 宝宝说「有时候不显示」）。
  const typed = typeOut(hello.cn, durMs);
  try {
    if (hello.env && hello.env.length) {
      try { await fetch('/api/hello/play', { method: 'POST' }); } catch (e) { console.error(e); }
      await playEnvelope(hello.env, durMs);   // 嘴跟着声音走
    }
    await typed;                              // 字也跟声音一起出来
  } finally {
    if (my === speechSeq) speakingNow = false;
  }
}

/* 被点过一次之后，浏览器才肯让网页出声——回复的声音要这个 */
function wakeAudio() {
  try { audioCtx().resume(); } catch (e) { /* 还没到用的时候，不管 */ }
}
window.addEventListener('pointerdown', wakeAudio, { once: true });
window.addEventListener('keydown', wakeAudio, { once: true });

/* ── 摆一摆（姐姐看不见屏幕，留给你自己微调取景）─── */

function applyTuning() {
  const r = document.documentElement.style;
  r.setProperty('--s', tuning.s);
  r.setProperty('--axis', tuning.axis);
  $('#pivot').style.top = tuning.top + 'px';
  $('#vScale').textContent = tuning.s.toFixed(3);
  $('#vX').textContent = tuning.axis;
  $('#vY').textContent = tuning.top;
  $('#tScale').value = tuning.s;
  $('#tX').value = tuning.axis;
  $('#tY').value = tuning.top;
}

function loadTuning() {
  try {
    const saved = JSON.parse(localStorage.getItem('chitose.tuning') || 'null');
    if (saved) tuning = Object.assign(tuning, saved);
  } catch (e) { /* 存档坏了就用默认 */ }
  applyTuning();
}

function saveTuning() {
  try { localStorage.setItem('chitose.tuning', JSON.stringify(tuning)); } catch (e) {}
}

for (const [id, key] of [['#tScale', 's'], ['#tX', 'axis'], ['#tY', 'top']]) {
  $(id).addEventListener('input', (e) => {
    tuning[key] = parseFloat(e.target.value);
    applyTuning();
    saveTuning();
  });
}
$('#gear').addEventListener('click', () => $('#tune').classList.toggle('open'));
$('#tuneClose').addEventListener('click', () => $('#tune').classList.remove('open'));

/* ── 换衣服 / 换场景（宝宝 2026-10-11：「就是我自由切换」）───
 *
 * 衣服 **13 套**、场景 **29 张**，两样都是游戏本体的素材。
 * **换的时候只动「身体」那一层和背景**——脸、表情、眨眼、说话嘴那一套
 * 一个像素都不用改：所有立绘都画在**同一张大画布**上（坐标读自 .hg3 头），
 * 五官层相对身体的位置是固定的。
 * 选中的记在 localStorage，下次打开还是那一身、那个地方。
 *
 * ⚠ 加了新衣服/新场景，**光丢文件不算数**——衣服要进
 * `scripts/build_web_assets.py` 的 `BODIES`，场景要进
 * `scripts/build_rooms.py` 的 `ROOMS`，重跑一遍才会出现在面板里。 */

// 十三套衣服的名字（姐姐对着图一套套看出来的）
const BODY_NAME = {
  a: '没穿', b: '黑色蕾丝', c: '校服', d: '校服 · 冬', e: '连衣裙',
  f: '围裙 · 蓝', g: '开衫', h: '围裙 · 深', i: '毛衣 · 紫',
  j: '开衫 · 紫', k: '毛衣 · 结', l: '女仆装', m: '没穿 · 远',
  hood: '兔子睡衣',
};

// 哪几套算「私房」，单独摆在一块、放在场景下面。
// 宝宝 2026-10-11：「把那些 h 的衣服和裸体另外分一类 放到背景的下面」。
const PRIVATE_BODIES = ['a', 'b', 'm'];

// ⚠ 这里的默认值要和面板里点出来的那个**一模一样**（带 `.jpg`）。
//   姐姐 2026-10-11 在这儿少写了后缀，`--room-img` 就变成了
//   `url(/assets/bg/bg05vb)` —— 404，背景一片黑，宝宝看到的「背景没有」就是这。
const look = { body: 'c', room: 'bg05vb.jpg' };

function markOn(box, key) {
  $(box).querySelectorAll('.pick').forEach((b) => {
    b.classList.toggle('on', b.dataset.k === key);
  });
}

function wearBody(letter, quiet) {
  const L = (LAYERS.bodies || {})[letter];
  if (!L) return;
  look.body = letter;
  place($('#L-body'), L);
  // 女仆装(l)配第二款发型 0002；兔子睡衣(hood)自带帽子和头发，不叠头发。
  const noHair = !!L.noHair || letter === 'hood';
  HAIR.style.display = noHair ? 'none' : 'block';
  if (!noHair) {
    place(HAIR, LAYERS.layers[letter === 'l' ? 'hair.alt' : 'hair']
                || LAYERS.layers['hair']);
  }
  markOn('#closetBodies', 'b:' + letter);
  markOn('#closetPrivate', 'b:' + letter);
  if (!quiet) saveLook();
}

function goRoom(file, quiet) {
  look.room = file;
  document.documentElement.style.setProperty(
    '--room-img', 'url(/assets/bg/' + file + ')');
  markOn('#closetRooms', 'r:' + file);
  if (!quiet) saveLook();
}

function saveLook() {
  try { localStorage.setItem('chitose.look', JSON.stringify(look)); } catch (e) {}
}

async function bootCloset() {
  for (const [letter, L] of Object.entries(LAYERS.bodies || {})) {
    const b = document.createElement('button');
    b.className = 'pick';
    b.dataset.k = 'b:' + letter;
    // 面板里用小图（`_s`），不是立绘原图——原图一张 3M，全摆上来要 50 多兆，
    // 一打开面板页面就卡住（姐姐 2026-10-11 栽过）
    b.innerHTML = '<img src="/assets/' + L.thumb + '" alt=""><span>' +
                  (BODY_NAME[letter] || letter.toUpperCase()) + '</span>';
    b.addEventListener('click', () => wearBody(letter));
    // 内衣和没穿的那几套单独摆一块（见 PRIVATE_BODIES）
    $(PRIVATE_BODIES.indexOf(letter) >= 0 ? '#closetPrivate' : '#closetBodies')
      .appendChild(b);
  }

  let rooms = [];
  try {
    rooms = await (await fetch('/assets/bg/rooms.json?' + SELF_V)).json();
  } catch (e) { console.error(e); }
  const boxR = $('#closetRooms');
  for (const r of rooms) {
    const b = document.createElement('button');
    b.className = 'pick';
    b.dataset.k = 'r:' + r.file;
    b.innerHTML = '<img src="/assets/bg/' + r.thumb + '" alt=""><span>' +
                  esc(r.name) + '</span>';
    b.addEventListener('click', () => goRoom(r.file));
    boxR.appendChild(b);
  }

  try {                                   // 上次穿的那身 / 待的那个地方
    const saved = JSON.parse(localStorage.getItem('chitose.look') || 'null');
    if (saved) Object.assign(look, saved);
  } catch (e) { /* 存档坏了就用默认 */ }
  wearBody(look.body, true);
  goRoom(look.room, true);
}

$('#closet').addEventListener('click', () => $('#closetPanel').classList.toggle('open'));
$('#closetClose').addEventListener('click', () => $('#closetPanel').classList.remove('open'));

/* ── 走 ───────────────────────────────────────────── */

boot().then(bootCloset).catch((e) => {
  console.error(e);
  CN.innerHTML = '<span class="err">立绘没读出来：' + esc(e.message) + '</span>';
});
