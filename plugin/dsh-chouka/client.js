/**
 * dsh-chouka —— 浏览器半端：左侧栏「今日抽卡」面板
 * ============================================================================
 * 流程与视觉完整复刻仓库自带的 preview/index.html：
 *   选 pack（午饭 / 精选视频）→ 选主题（类型 / 区，够 5 张才能开）
 *   → 桌面上出现卡包（idle 浮动）→ 点击：摇晃 → 爆开 + 白闪
 *   → 五张牌背面朝上飞到五角星的五个尖 → hover 发光 → 点击翻面
 *   → 值得看=金色传说（带扫光），可以看=蓝稀有
 * 类名一律加 ck- 前缀、keyframes 加 ck 前缀，避免污染宿主全局样式。
 * 不改 UI 框架：宿主 slot + React；数据只来自本机 /api/chouka/*。
 * ============================================================================
 */
window.__ModuleLoader__.load({
  id: 'dsh-chouka',
  factory: (require) => {
    const React = require('react')
    const h = React.createElement

    const API = '/api/chouka'
    const asJson = async (res) => {
      if (res.ok) return res.json()
      throw new Error('HTTP ' + res.status)
    }
    const jget = async (p) => asJson(await fetch(API + p, { credentials: 'same-origin' }))
    const jpost = async (p, body) => asJson(await fetch(API + p, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify(body || {}),
    }))
    const wait = (ms) => new Promise((r) => setTimeout(r, ms))

    /* ── 样式：照 preview/index.html 搬运，类名/动画加 ck 前缀 ── */
    const CSS = `
.ck-root{--ck-ink:#1c1915;--ck-paper:#f4ecd9;--ck-night:#10140f;--ck-panel:#243028;--ck-gold:#f0c14a;--ck-line:#0c0d12;
  color:var(--ck-paper);font-family:"Microsoft YaHei UI","PingFang SC","Noto Sans SC",sans-serif;
  height:100%;min-height:0;overflow-y:auto;overscroll-behavior:contain;
  background:
    radial-gradient(ellipse at 50% 20%,rgba(240,193,74,.08),transparent 42%),
    linear-gradient(180deg,#1a221c,#10140f 40%);}
.ck-root *{box-sizing:border-box;}
.ck-root button{font:inherit;color:inherit;}
.ck-root button:focus-visible{outline:3px solid var(--ck-gold);outline-offset:3px;}
.ck-main{width:min(1120px,100%);margin:0 auto;padding:32px 0 48px;}
.ck-eyebrow{margin:0 0 8px;letter-spacing:.32em;font-size:12px;color:var(--ck-gold);}
.ck-root h1{margin:0 0 8px;font-size:36px;letter-spacing:.04em;}
.ck-lead{margin:0 0 22px;max-width:640px;line-height:1.6;color:#d9d0bb;}
.ck-note{margin:22px 0 0;color:#8f8878;font-size:13px;}
.ck-choices,.ck-actions{display:flex;flex-wrap:wrap;gap:14px;justify-content:center;}
/* ── 第一步的卡组选择：一叠卡，底层两张错开当卡背，顶层是金边卡面 ── */
.ck-decks{display:flex;flex-wrap:wrap;gap:34px;justify-content:center;padding:14px 0 8px;}
.ck-deck{position:relative;width:190px;height:264px;padding:0;cursor:pointer;border:none;background:none;
  transition:transform .18s ease;}
.ck-deck::before,.ck-deck::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;
  border:4px solid var(--ck-line);background:var(--ck-panel);box-shadow:6px 6px 0 var(--ck-line);
  transition:transform .18s ease;}
.ck-deck::before{transform:rotate(-2deg) translate(-3px,2px);}
.ck-deck::after{transform:rotate(3deg) translate(5px,4px);}
.ck-deck:hover{transform:translateY(-8px);}
.ck-deck:hover::before{transform:rotate(-8deg) translate(-12px,5px);}
.ck-deck:hover::after{transform:rotate(8deg) translate(12px,7px);}
.ck-deck-top{position:relative;z-index:1;width:100%;height:100%;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:10px;padding:16px;text-align:center;
  border:4px solid var(--ck-line);color:var(--ck-paper);
  background:linear-gradient(160deg,#a13b2c 0%,#6d221c 46%,#3c1214 100%);
  box-shadow:inset 0 0 0 4px var(--ck-gold),0 10px 0 #07110c;}
.ck-deck.is-video .ck-deck-top{background:linear-gradient(160deg,#2a6cb5 0%,#17345c 48%,#0d1c33 100%);
  box-shadow:inset 0 0 0 4px #8ec8ff,0 10px 0 #07110c;}
.ck-deck-top b{font-size:54px;line-height:1;}
.ck-deck-top strong{font-size:22px;}
.ck-deck-top small{color:var(--ck-gold);font-size:13px;line-height:1.5;}
.ck-deck.is-video .ck-deck-top small{color:#8ec8ff;}
.ck-deck .ck-ribbon{top:22px;}
.ck-deck.is-video .ck-ribbon{background:#8ec8ff;}
.ck-choice,.ck-chip,.ck-solid,.ck-texty{border:4px solid var(--ck-line);cursor:pointer;}
.ck-choice,.ck-chip{min-width:180px;padding:18px 16px;background:var(--ck-panel);
  box-shadow:6px 6px 0 var(--ck-line);text-align:left;}
.ck-choice strong,.ck-chip strong{display:block;font-size:22px;}
.ck-choice span,.ck-chip small{display:block;margin-top:6px;color:var(--ck-gold);font-size:13px;}
.ck-chip.is-ready{box-shadow:6px 6px 0 var(--ck-line),inset 0 0 0 2px var(--ck-gold);}
.ck-chip:disabled{opacity:.45;cursor:not-allowed;box-shadow:6px 6px 0 #2a2418;}
.ck-solid,.ck-texty{padding:10px 16px;background:transparent;}
.ck-solid{background:var(--ck-gold);color:var(--ck-ink);font-weight:700;box-shadow:4px 4px 0 var(--ck-line);}
.ck-solid:disabled{opacity:.45;cursor:not-allowed;}
.ck-texty{color:var(--ck-paper);margin-top:16px;}
.ck-actions{margin-top:16px;}
.ck-empty,.ck-loading{text-align:center;line-height:1.6;}
.ck-table{position:relative;min-height:800px;
  background:radial-gradient(ellipse at center,rgba(90,40,24,.35),transparent 58%),
    radial-gradient(ellipse at center,#1d4630 0%,#0e1a14 72%);
  border:4px solid var(--ck-line);box-shadow:inset 0 0 0 4px #c8a15a,8px 8px 0 var(--ck-line);overflow:hidden;}
.ck-pack{position:absolute;left:50%;top:50%;width:210px;height:300px;margin:-150px 0 0 -105px;padding:0;cursor:pointer;
  border:none;color:var(--ck-paper);animation:ck-idle 2.4s ease-in-out infinite;
  background:linear-gradient(160deg,#a13b2c 0%,#6d221c 46%,#3c1214 100%);
  box-shadow:0 16px 0 #07110c,inset 0 0 0 6px var(--ck-gold),inset 0 0 0 12px #6d221c;}
.ck-pack.is-video{background:linear-gradient(160deg,#2a6cb5 0%,#17345c 48%,#0d1c33 100%);
  box-shadow:0 16px 0 #07110c,inset 0 0 0 6px #8ec8ff,inset 0 0 0 12px #17345c;}
.ck-pack.is-shaking{animation:ck-shake .5s linear;}
.ck-pack.is-gone{animation:ck-burst .4s ease-in forwards;pointer-events:none;}
.ck-ribbon{position:absolute;top:36px;left:-8px;right:-8px;background:var(--ck-gold);color:var(--ck-ink);
  letter-spacing:.28em;font-size:12px;font-weight:700;padding:6px 0;}
.ck-pack b{display:block;margin-top:92px;font-size:76px;line-height:1;}
.ck-pack-name{display:block;margin-top:8px;font-size:18px;}
.ck-hint{position:absolute;left:0;right:0;bottom:22px;margin:0;text-align:center;letter-spacing:.24em;color:var(--ck-gold);}
.ck-burst{position:absolute;left:50%;top:50%;width:36px;height:36px;margin:-18px 0 0 -18px;
  border:6px solid var(--ck-gold);border-radius:50%;opacity:0;pointer-events:none;}
.ck-burst.is-on{animation:ck-ring .65s ease-out;}
.ck-flash{position:fixed;inset:0;background:#fff8e8;opacity:0;pointer-events:none;z-index:99;}
.ck-flash.is-on{animation:ck-flash .45s ease-out;}
.ck-fan{position:absolute;inset:0;--orbit:220px;}
.ck-card{--x:0;--y:0;--tilt:0deg;--glow:#ffd15c;position:absolute;left:50%;top:50%;width:150px;height:236px;
  margin:-118px 0 0 -75px;padding:0;border:none;background:none;cursor:pointer;perspective:900px;
  transform:translate(calc(var(--x) * var(--orbit)),calc(var(--y) * var(--orbit))) rotate(var(--tilt));
  animation:ck-deal .72s cubic-bezier(.16,.84,.32,1) both;animation-delay:calc(var(--i) * 80ms);}
.ck-inner{display:block;position:relative;width:100%;height:100%;transform-style:preserve-3d;
  transition:transform .55s cubic-bezier(.2,.8,.2,1);}
.ck-card:hover{z-index:4;}
.ck-card.is-open,.ck-card.is-open:hover{z-index:8;}
.ck-card:hover .ck-back,.ck-card:hover .ck-front{box-shadow:inset 0 0 18px var(--glow),0 0 12px var(--glow),0 0 28px var(--glow);}
.ck-card.rarity-legendary:hover .ck-back,.ck-card.rarity-legendary:hover .ck-front{
  box-shadow:inset 0 0 22px var(--glow),0 0 16px var(--glow),0 0 40px var(--glow);}
.ck-card.rarity-epic:hover .ck-back,.ck-card.rarity-epic:hover .ck-front{
  box-shadow:inset 0 0 20px var(--glow),0 0 14px var(--glow),0 0 34px var(--glow);}
.ck-card.is-open .ck-inner{transform:rotateY(180deg);}
.ck-side{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:8px;padding:14px;border:4px solid var(--ck-line);backface-visibility:hidden;overflow:hidden;}
.ck-back{background:#8d2f24;color:var(--ck-paper);}
.ck-fan.deck-video .ck-back{background:#1d4e89;}
.ck-back b{font-size:64px;line-height:1;}
.ck-front{background:var(--ck-paper);color:var(--ck-ink);transform:rotateY(180deg);
  align-items:stretch;justify-content:flex-start;padding:0;gap:0;}
.ck-face{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%;height:100%;min-height:0;
  padding:10px 10px 12px;overflow:hidden;text-align:left;overflow-wrap:break-word;}
.ck-kicker,.ck-front h2,.ck-line,.ck-reason,.ck-link{flex-shrink:0;}
.ck-kicker{color:#8a5a18;font-size:12px;letter-spacing:.08em;line-height:1.2;}
.ck-front h2{margin:0;font-size:16px;line-height:1.25;max-height:calc(1.25em * 2);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.ck-line,.ck-reason{margin:0;font-size:12px;line-height:1.35;}
.ck-reason{color:#3d3830;max-height:calc(1.35em * 2);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.ck-link{color:#1a4f8b;font-size:12px;line-height:1.3;text-decoration:underline;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;}
.ck-badge{align-self:flex-start;background:var(--ck-ink);color:var(--ck-gold);font-size:12px;padding:3px 6px;}
.ck-card.rarity-legendary.is-open .ck-front{box-shadow:inset 0 0 0 4px var(--ck-gold),0 0 26px rgba(240,193,74,.9);}
.ck-card.rarity-epic.is-open .ck-front{box-shadow:inset 0 0 0 4px #d9a6ff,0 0 22px rgba(217,166,255,.85);}
.ck-card.rarity-rare.is-open .ck-front{box-shadow:inset 0 0 0 4px #6cb6ff,0 0 18px rgba(108,182,255,.8);}
.ck-card.rarity-legendary.is-open .ck-front::after{content:"";position:absolute;inset:0;
  background:linear-gradient(115deg,transparent 30%,rgba(255,255,255,.55) 50%,transparent 70%);
  transform:translateX(-120%);animation:ck-shine .8s ease-out;}
@keyframes ck-idle{0%,100%{transform:translateY(0) rotate(-2deg);}50%{transform:translateY(-12px) rotate(2deg);}}
@keyframes ck-shake{0%{transform:rotate(0) scale(1);}20%{transform:rotate(-8deg) scale(1.04);}
  40%{transform:rotate(8deg) scale(1.08);}60%{transform:rotate(-6deg) scale(1.12);}
  80%{transform:rotate(5deg) scale(1.16);}100%{transform:rotate(0) scale(1.2);}}
@keyframes ck-burst{to{transform:translateY(-46px) scale(1.4);opacity:0;}}
@keyframes ck-ring{from{transform:scale(1);opacity:1;}to{transform:scale(16);opacity:0;}}
@keyframes ck-flash{0%{opacity:.85;}100%{opacity:0;}}
@keyframes ck-deal{from{transform:translate(0,0) scale(.18) rotate(0deg);opacity:0;}
  to{transform:translate(calc(var(--x) * var(--orbit)),calc(var(--y) * var(--orbit))) rotate(var(--tilt)) scale(1);opacity:1;}}
@keyframes ck-shine{to{transform:translateX(120%);}}
@media (max-width:980px){
  .ck-root h1{font-size:28px;}
  .ck-table{min-height:560px;}
  .ck-fan{--orbit:112px;}
  .ck-deck{width:150px;height:208px;}
  .ck-decks{gap:22px;}
  .ck-deck-top b{font-size:40px;}
  .ck-deck-top strong{font-size:18px;}
  .ck-deck-top small{font-size:12px;}
  .ck-card{width:88px;height:138px;margin:-69px 0 0 -44px;}
  .ck-back b{font-size:40px;}
  .ck-face{padding:6px 6px 7px;gap:2px;}
  .ck-kicker,.ck-link{font-size:10px;}
  .ck-front h2{font-size:12px;}
  .ck-line,.ck-reason{font-size:10px;}
  .ck-line:nth-of-type(n+2){display:none;}
}
@media (prefers-reduced-motion:reduce){
  .ck-pack,.ck-card,.ck-inner,.ck-flash,.ck-burst,.ck-front::after{animation:none !important;transition:none !important;}
}
/* ── 附近候选（可选开关） ── */
.ck-tabs{display:flex;gap:4px;padding:4px;border-radius:10px;background:rgba(127,127,127,.08);max-width:360px;margin:0 0 14px;}
.ck-tab{flex:1;cursor:pointer;font:inherit;font-size:13px;padding:7px 10px;border:0;border-radius:8px;background:transparent;color:#d9d0bb;}
.ck-tab[aria-selected=true]{background:#243028;color:var(--ck-paper);font-weight:600;}
.ck-draw{display:flex;flex-direction:column;}
.ck-nb{display:flex;flex-direction:column;gap:12px;max-width:640px;}
.ck-nb-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.ck-nb-label{font-size:12px;color:#8f8878;min-width:64px;}
.ck-nb-label:first-child{min-width:64px;}
.ck-input{flex:1;min-width:200px;padding:8px 10px;border-radius:8px;font-size:13px;font-family:inherit;
  border:1px solid rgba(127,127,127,.25);background:rgba(0,0,0,.25);color:inherit;}
.ck-input:focus{outline:none;border-color:var(--ck-gold);}
.ck-sw{flex:none;width:38px;height:22px;border-radius:11px;border:0;cursor:pointer;position:relative;
  background:rgba(128,128,128,.35);transition:background .15s;padding:0;}
.ck-sw[data-on]{background:#22c55e;}
.ck-sw i{position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;transition:left .15s;display:block;}
.ck-sw[data-on] i{left:19px;}
.ck-item{border:1px solid rgba(127,127,127,.22);border-radius:10px;padding:10px 12px;display:flex;
  flex-direction:column;gap:6px;background:rgba(127,127,127,.05);}
.ck-item-t{font-weight:600;font-size:14px;}
.ck-item-m{font-size:11px;color:#8f8878;line-height:1.5;}
.ck-added{color:#22c55e;font-weight:600;}
    `

    /* ── 与 preview/index.html 相同的几何 ── */
    const starPoint = (index) => {
      const angle = -Math.PI / 2 + index * (2 * Math.PI / 5)
      return { x: Math.cos(angle).toFixed(4), y: Math.sin(angle).toFixed(4) }
    }
    const TILTS = ['0deg', '16deg', '8deg', '-8deg', '-16deg']

    /* ── 稀有度：按播放量定档（贴合本精选池量级，可调） ──
     * 传说 gold ≥500 · 史诗 purple 200–500 · 稀有 sky 50–200 · 普通 white <50
     * 荧光绿 = 没记录播放量的视频牌 / 午饭牌（没有播放量概念） */
    const PLAY_TIERS = [
      { rarity: 'legendary', min: 500 },
      { rarity: 'epic', min: 200 },
      { rarity: 'rare', min: 50 },
      { rarity: 'common', min: 0 },
    ]
    const RARITY_GLOW = {
      legendary: '#ffd15c', epic: '#d9a6ff', rare: '#6cb6ff', common: '#ffffff', green: '#5dff9a',
    }
    const parsePlay = (raw) => {
      if (raw == null) return null
      const m = String(raw).trim().match(/^([\d.]+)\s*(亿|万)?$/)
      if (!m) return null
      const v = parseFloat(m[1])
      if (!Number.isFinite(v)) return null
      return Math.round(m[2] === '亿' ? v * 1e8 : m[2] === '万' ? v * 1e4 : v)
    }
    const rarityOf = (card, deck) => {
      if (deck !== 'bili_featured') return 'green' // 午饭：无播放量概念，统一荧光绿
      const play = parsePlay(card?.play)
      if (play == null) return 'green'             // 视频没记到播放量
      return (PLAY_TIERS.find((t) => play >= t.min) || { rarity: 'common' }).rarity
    }

    function CardFace({ card, index, deck, play, open, onOpen }) {
      const point = starPoint(index)
      const rarity = rarityOf({ play }, deck)
      const style = {
        '--i': String(index), '--x': point.x, '--y': point.y,
        '--tilt': TILTS[index] || '0deg', '--glow': RARITY_GLOW[rarity],
      }
      return h('div', {
        className: 'ck-card rarity-' + rarity + (open ? ' is-open' : ''),
        style, title: card.reason || '', onClick: onOpen, tabIndex: 0, key: card.id,
      },
        h('span', { className: 'ck-inner' },
          h('span', { className: 'ck-side ck-back' },
            h('span', null, card.kicker || ''), h('b', null, '抽')),
          h('span', { className: 'ck-side ck-front' },
            h('span', { className: 'ck-face' },
              h('span', { className: 'ck-kicker' }, card.kicker || ''),
              h('h2', null, card.title || ''),
              (card.lines || []).map((line, i) => h('p', { className: 'ck-line', key: i }, line)),
              h('p', { className: 'ck-reason' }, card.reason || ''),
              card.url ? h('a', {
                className: 'ck-link', href: card.url, target: '_blank', rel: 'noopener noreferrer',
                title: card.url,
                onClick: (e) => e.stopPropagation(),
              }, (String(card.url).match(/BV[0-9A-Za-z]+/) || ['打开视频'])[0]) : null,
            )),
        ))
    }

    function Panel() {
      // step: decks 选 pack → categories 选主题 → pack 卡包待开 → fan 五张牌
      const [step, setStep] = React.useState('decks')
      const [tab, setTab] = React.useState('draw')
      const [deck, setDeck] = React.useState(null)
      const [category, setCategory] = React.useState(null)
      const [cats, setCats] = React.useState(null)
      const [catsError, setCatsError] = React.useState(null)
      const [phase, setPhase] = React.useState('idle') // idle | shaking | gone
      const [pack, setPack] = React.useState(null)     // payload: {draw_id, cards, ...}
      const [playMap, setPlayMap] = React.useState({}) // card id → 播放量原始值（来自 record.face.play）
      const [opened, setOpened] = React.useState({})
      const [picked, setPicked] = React.useState(null)
      const [marked, setMarked] = React.useState(null)
      const [error, setError] = React.useState(null)
      const [busy, setBusy] = React.useState(false)
      const [flashOn, setFlashOn] = React.useState(false)
      const [showActions, setShowActions] = React.useState(false)
      const [importedNote, setImportedNote] = React.useState(null)

      const lunch = deck !== 'bili_featured'

      const pickDeck = (d) => {
        setDeck(d); setCategory(null); setCats(null); setCatsError(null)
        setStep('categories')
        // 选午饭卡组时触发每日自动导入。服务端有「一天一次」状态，这里每次都发；
        // 失败也显示出来（之前静默，开关没开/配置缺失根本看不见）
        if (d === 'lunch') {
          jpost('/nearby/import', {}).then((r) => {
            if (r.ok && !r.skipped && r.added && r.added.length) {
              setImportedNote('今日已自动导入附近 ' + r.added.length + ' 家餐厅（标签「附近」）')
            } else if (r.ok === false) {
              if (/没开/.test(String(r.error || ''))) {
                setImportedNote('💡 开「自动入池」可每天自动导入附近餐厅：去「附近候选」页打开那个开关并保存')
              } else {
                setImportedNote('⚠️ 附近自动导入失败：' + String(r.error || '未知错误'))
              }
            }
          }).catch((e) => { setImportedNote('⚠️ 附近自动导入请求失败：' + String(e?.message || e)) })
        }
      }
      React.useEffect(() => {
        if (step !== 'categories' || !deck) return
        let alive = true
        jget('/categories?deck=' + encodeURIComponent(deck))
          .then((r) => { if (alive) { setCats(r.ok ? r.data : null); setCatsError(r.ok ? null : r.error) } })
          .catch((e) => { if (alive) setCatsError(String(e.message || e)) })
        return () => { alive = false }
      }, [step, deck])

      const openPack = async (allowYesterday = false) => {
        if (busy) return
        setBusy(true); setError(null); setPhase('shaking')
        try {
          const [r] = await Promise.all([
            jget('/pack?deck=' + encodeURIComponent(deck) + '&category=' + encodeURIComponent(category.id)
              + (allowYesterday ? '&avoid_yesterday=false' : '')),
            wait(520),
          ])
          if (!r.ok) throw new Error(r.error || '开包失败')
          if (!r.data.payload.cards?.length) throw new Error('这一包是空的。')
          setPack(r.data.payload)
          const plays = {}
          for (const c of r.data.record?.cards || []) plays[c.id] = c?.face?.play ?? null
          setPlayMap(plays)
          setPhase('gone')
          setFlashOn(false); requestAnimationFrame(() => setFlashOn(true))
          await wait(220)
          setStep('fan'); setOpened({}); setPicked(null); setMarked(null); setShowActions(false)
          await wait(760)
          setShowActions(true)
        } catch (e) {
          setError(String(e.message || e)); setPhase('idle')
        }
        setBusy(false)
      }

      const doMark = async (result) => {
        if (!pack) return
        try {
          const r = await jpost('/mark', { draw_id: pack.draw_id, result })
          if (r.ok) setMarked(result)
          else setError(r.error || '标记失败')
        } catch (e) { setError(String(e.message || e)) }
      }
      const pickCard = (id) => { setPicked(id); doMark('picked:' + id) }

      const titles = {
        decks: '先选一副牌',
        categories: lunch ? '想吃哪种？' : '想看哪个区？',
        pack: (lunch ? '午饭' : '精选视频') + ' · ' + (category?.name || ''),
        fan: (lunch ? '午饭' : '精选视频') + ' · ' + (category?.name || ''),
      }
      const leads = {
        decks: '午饭选类型，视频选区。选完开一包，一共 5 张。',
        categories: lunch
          ? '只从你点的这一类里抽。不够 5 张的类型点不了，也不会拿别的类型来凑。'
          : '只从你点的这个区里抽。区是按标题和精选理由里的关键词归的，一条视频可以同时在多个区。',
        pack: '点击卡包。五张牌背面朝上，落到五角星的五个尖上。鼠标移上去会发光，点一下才翻开。',
        fan: pack?.draw_id ? ('这一包是 ' + pack.draw_id + '。鼠标移上去看光芒，点一下翻开。') : '',
      }

      return h('div', { className: 'ck-root' },
        h('div', { className: 'ck-flash' + (flashOn ? ' is-on' : '') }),
        h('div', { className: 'ck-main' },
          h('p', { className: 'ck-eyebrow' }, '每日一抽'),
          h('div', { className: 'ck-tabs' },
            h('button', { className: 'ck-tab', 'aria-selected': tab === 'draw', onClick: () => setTab('draw') }, '开包抽卡'),
            h('button', { className: 'ck-tab', 'aria-selected': tab === 'nearby', onClick: () => setTab('nearby') }, '附近候选（可选）')),
          tab === 'nearby' ? h(NearbyPanel) : h('div', { className: 'ck-draw' },
          h('h1', null, titles[step] || ''),
          h('p', { className: 'ck-lead' }, leads[step] || ''),
          importedNote && step === 'categories' && deck === 'lunch'
            ? h('p', { style: { margin: '-10px 0 12px', color: '#22c55e', fontSize: 12 } }, '🍱 ' + importedNote) : null,
          error ? h('p', { className: 'ck-empty', style: { color: '#f59e0b' } }, error) : null,

          /* 第一步：选 pack —— 卡组形式，一叠卡，hover 抬起散开 */
          step === 'decks' ? h('div', { className: 'ck-decks' },
            [['lunch', '午饭', '🍜', '先选类型，再从里面抽'], ['bili_featured', '精选视频', '📺', '先选区，再从里面抽']].map(([id, name, icon, sub]) =>
              h('button', {
                className: 'ck-deck' + (id === 'bili_featured' ? ' is-video' : ''),
                key: id, onClick: () => pickDeck(id),
              },
                h('span', { className: 'ck-deck-top' },
                  h('span', { className: 'ck-ribbon' }, 'DECK'),
                  h('b', null, icon),
                  h('strong', null, name),
                  h('small', null, sub)))),
          ) : null,

          /* 第二步：选主题（类型 / 区） */
          step === 'categories' ? (
            catsError ? h('p', { className: 'ck-empty' }, catsError)
              : !cats ? h('p', { className: 'ck-loading' }, '正在看卡池…')
                : !cats.categories.length ? h('p', { className: 'ck-empty' },
                  lunch ? '卡池里还没有标签。去改 data/lunch.json。' : '还没有分区。去改 data/bili_zones.json 里的关键词。')
                  : h('div', { className: 'ck-choices' },
                    cats.categories.map((item) => h('button', {
                      className: 'ck-chip' + (item.ready ? ' is-ready' : ''), key: item.id,
                      disabled: !item.ready,
                      onClick: () => { setCategory(item); setPhase('idle'); setPack(null); setError(null); setStep('pack') },
                    },
                      h('strong', null, item.name),
                      h('small', null, item.ready ? item.count + ' 张 · 可以开包' : item.count + ' 张 · 还差 ' + item.short + ' 张'))))
          ) : null,
          step === 'categories' ? h('button', { className: 'ck-texty', onClick: () => setStep('decks') }, '换一副牌') : null,

          /* 第三步：桌面 + 卡包 */
          (step === 'pack' || step === 'fan') ? h('div', { className: 'ck-table' },
            h('div', { className: 'ck-burst' + (step === 'fan' ? ' is-on' : '') }),
            step === 'pack' ? h('button', {
              className: 'ck-pack' + (lunch ? '' : ' is-video')
                + (phase === 'shaking' ? ' is-shaking' : phase === 'gone' ? ' is-gone' : ''),
              disabled: busy, onClick: openPack,
            },
              h('span', { className: 'ck-ribbon' }, 'PACK'),
              h('b', null, '抽'),
              h('span', { className: 'ck-pack-name' }, category?.name || '')) : null,
            step === 'pack' ? h('p', { className: 'ck-hint' }, busy ? '开包中…' : '点击卡包') : null,
          /* 开包失败：错误显示在桌面上，给一键「包含昨天」重试 */
          step === 'pack' && error ? h('div', { style: { position: 'absolute', left: 16, right: 16, bottom: 64, display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'center' } },
            h('p', { style: { margin: 0, color: '#ffb84d', fontSize: 13, lineHeight: 1.5, textAlign: 'center' } }, error),
            h('div', { className: 'ck-actions', style: { marginTop: 0 } },
              deck !== 'bili_featured' ? h('button', { className: 'ck-solid', disabled: busy, onClick: () => openPack(true) }, '包含昨天抽过的再试') : null,
              h('button', { className: 'ck-texty', style: { margin: 0 }, disabled: busy, onClick: () => { setError(null); setStep('categories') } }, '换一个类型'))) : null,
            step === 'fan' && pack ? h('div', { className: 'ck-fan' + (pack.deck === 'bili_featured' ? ' deck-video' : '') },
              pack.cards.map((card, index) => h(CardFace, {
                card, index, key: card.id, deck: pack.deck, play: playMap[card.id],
                open: !!opened[index],
                onOpen: () => setOpened((o) => ({ ...o, [index]: !o[index] })),
              })),
            ) : null,
          ) : null,

          /* 开包后的动作：换主题 / 再开一包 / 拣一张 / 记 did·skipped */
          step === 'pack' && phase === 'idle' ? h('button', {
            className: 'ck-texty', onClick: () => setStep('categories'),
          }, lunch ? '换一个类型' : '换一个区') : null,

          step === 'fan' && showActions ? h('div', { className: 'ck-actions' },
            h('button', { className: 'ck-solid', onClick: () => { setPhase('idle'); setPack(null); setStep('pack') } }, '再开一包'),
            h('button', { className: 'ck-texty', onClick: () => setStep('categories') }, lunch ? '换一个类型' : '换一个区'),
          ) : null,
          step === 'fan' && showActions && pack ? h('div', { className: 'ck-actions' },
            !picked ? h('span', { className: 'ck-note', style: { margin: 0, alignSelf: 'center' } }, '抽了 5 张：先点一张拣出来，再记照做。') : null,
            pack.cards.map((c) => h('button', {
              className: 'ck-solid', key: 'pick-' + c.id, disabled: !!picked || !!marked,
              style: picked === c.id ? { background: '#22c55e' } : {},
              onClick: () => pickCard(c.id),
            }, picked === c.id ? '✓ 已拣' : '拣「' + String(c.title).slice(0, 8) + '」')),
            h('button', {
              className: 'ck-texty', disabled: !picked || !!marked, onClick: () => doMark('did'),
              style: { margin: 0, alignSelf: 'center' },
            }, marked === 'did' ? '✓ 已记：照做了' : '照做了'),
            h('button', {
              className: 'ck-texty', disabled: !!marked, onClick: () => doMark('skipped'),
              style: { margin: 0, alignSelf: 'center' },
            }, marked === 'skipped' ? '✓ 已记：跳过' : '跳过'),
          ) : null,

          h('p', { className: 'ck-note' }, '不会打开视频，也不会下单。抽完如果照做了，点上面的「照做了」记一笔。'),
        )),
      )
    }

    /* 附近候选：默认关（零网络）；开启后高德周边搜索 → 人审 → 写进午饭卡池 */

    /* WGS-84（浏览器/_GPS 原始坐标）→ GCJ-02（高德/国测局坐标），纯数学无网络 */
    const _PI = 3.14159265358979324
    const _A = 6378245.0
    const _EE = 0.00669342162296594323
    const _inChina = (lng, lat) => lng > 73.66 && lng < 135.05 && lat > 3.86 && lat < 53.55
    const _tLat = (x, y) => {
      let r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
      r += (20 * Math.sin(6 * x * _PI) + 20 * Math.sin(2 * x * _PI)) * 2 / 3
      r += (20 * Math.sin(y * _PI) + 40 * Math.sin(y / 3 * _PI)) * 2 / 3
      r += (160 * Math.sin(y / 12 * _PI) + 320 * Math.sin(y * _PI / 30)) * 2 / 3
      return r
    }
    const _tLng = (x, y) => {
      let r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
      r += (20 * Math.sin(6 * x * _PI) + 20 * Math.sin(2 * x * _PI)) * 2 / 3
      r += (20 * Math.sin(x * _PI) + 40 * Math.sin(x / 3 * _PI)) * 2 / 3
      r += (150 * Math.sin(x / 12 * _PI) + 300 * Math.sin(x / 30 * _PI)) * 2 / 3
      return r
    }
    const wgs84ToGcj02 = (lng, lat) => {
      if (!_inChina(lng, lat)) return [lng, lat]
      let dLat = _tLat(lng - 105, lat - 35)
      let dLng = _tLng(lng - 105, lat - 35)
      const radLat = lat / 180 * _PI
      let magic = 1 - _EE * Math.sin(radLat) * Math.sin(radLat)
      const sqrtMagic = Math.sqrt(magic)
      dLat = (dLat * 180) / ((_A * (1 - _EE)) / (magic * sqrtMagic) * _PI)
      dLng = (dLng * 180) / (_A / sqrtMagic * Math.cos(radLat) * _PI)
      return [lng + dLng, lat + dLat]
    }

    function NearbyPanel() {
      const [cfg, setCfg] = React.useState(null)
      const [form, setForm] = React.useState({ enabled: false, amapKey: '', location: '', radius: 1000, autoAdd: false, autoAddTag: '附近', autoKeywords: '快餐,轻食,面馆,小吃' })
      const [keyword, setKeyword] = React.useState('快餐')
      const [pois, setPois] = React.useState(null)
      const [tag, setTag] = React.useState('清淡')
      const [busy, setBusy] = React.useState(false)
      const [locating, setLocating] = React.useState(false)
      const [msg, setMsg] = React.useState(null)
      const [added, setAdded] = React.useState({})
      React.useEffect(() => {
        jget('/nearby/config').then((r) => {
          if (r.ok) { setCfg(r.config); setForm({ autoAddTag: '附近', ...r.config }) }
        })
          .catch(() => setCfg({ enabled: false, amapKey: '', location: '', radius: 1000, autoAdd: false, autoAddTag: '附近' }))
      }, [])
      /* 本机定位：浏览器 Geolocation（127.0.0.1 是 secure context，可直接用）→ WGS-84 转 GCJ-02
       * 桌面 Mac 没有 GPS，全靠 Wi-Fi 定位：不开 enableHighAccuracy（开了会等 GPS 直到超时），
       * 超时后自动放宽再试一次 */
      const getPosition = (opts) => new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, opts)
      })
      const locate = async () => {
        if (!navigator.geolocation) {
          setMsg({ warn: true, text: '这个环境没有 Geolocation（需要 localhost/HTTPS，且浏览器支持）' })
          return
        }
        setLocating(true); setMsg({ good: true, text: '定位中…（Wi-Fi 定位，最长约 25 秒）' })
        const attempts = [
          { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 },
          { enableHighAccuracy: false, timeout: 25000, maximumAge: 0 },
        ]
        let lastErr = null
        for (const opts of attempts) {
          try {
            const pos = await getPosition(opts)
            const [lng, lat] = wgs84ToGcj02(pos.coords.longitude, pos.coords.latitude)
            setForm((f) => ({ ...f, location: lng.toFixed(6) + ',' + lat.toFixed(6) }))
            setMsg({
              good: true,
              text: '已定位并转成高德坐标（GCJ-02，精度约 ' + Math.round(pos.coords.accuracy || 0) + ' 米）。确认无误后点「保存设置」。',
            })
            setLocating(false)
            return
          } catch (e) { lastErr = e }
        }
        const code = lastErr?.code
        const hint = code === 1
          ? '权限被拒绝了。去 系统设置 → 隐私与安全性 → 定位服务，允许当前浏览器（浏览器自己也要允许本站点）。'
          : code === 2
            ? '拿不到位置。Mac 没有 GPS，靠 Wi-Fi 定位——确认 Wi-Fi 已连接；再检查 系统设置 → 隐私与安全性 → 定位服务 里是否允许了当前浏览器。'
            : '浏览器这条路不通（大陆网络下 Chrome 系常常拿不到）。换右边的「系统定位」试试。'
        setMsg({ warn: true, text: '定位失败：' + hint })
        setLocating(false)
      }
      /* 系统定位：宿主直接跑 CoreLocation（绕过浏览器），首次 macOS 会弹系统授权框 */
      const sysLocate = async () => {
        setLocating(true)
        setMsg({ good: true, text: '系统定位中…（首次会弹「想要访问你的位置」授权框，允许一次即可，最长约 25 秒）' })
        try {
          const r = await jget('/nearby/locate')
          if (!r.ok) {
            setMsg({ warn: true, text: r.error })
          } else {
            const [lng, lat] = wgs84ToGcj02(r.lng, r.lat)
            setForm((f) => ({ ...f, location: lng.toFixed(6) + ',' + lat.toFixed(6) }))
            setMsg({ good: true, text: '系统定位成功，已转高德坐标（精度约 ' + Math.round(r.accuracy || 0) + ' 米）。确认后点「保存设置」。' })
          }
        } catch (e) { setMsg({ warn: true, text: String(e.message || e) }) }
        setLocating(false)
      }
      const save = async () => {
        setBusy(true); setMsg(null)
        try {
          const r = await jpost('/nearby/config', form)
          if (r.ok) { setCfg(r.config); setMsg({ good: true, text: '已保存' + (r.config.enabled ? '，开关已开' : '') }) }
          else setMsg({ warn: true, text: r.error })
        } catch (e) { setMsg({ warn: true, text: String(e.message || e) }) }
        setBusy(false)
      }
      const search = async () => {
        setBusy(true); setMsg(null); setPois(null)
        try {
          const r = await jget('/nearby/search?keyword=' + encodeURIComponent(keyword))
          if (r.ok) {
            setPois(r.pois)
            if (r.auto) {
              setAdded((a) => ({ ...a, ...Object.fromEntries(r.auto.added.map((x) => [x.name, true])), ...Object.fromEntries(r.auto.existed.map((n) => [n, true])) }))
              setMsg({
                good: true,
                text: `自动入池：新加 ${r.auto.added.length} 家，已在池 ${r.auto.existed.length} 家（标签「${(cfg && cfg.autoAddTag) || '附近'}」，预算占位 25 可去卡池改）`,
              })
            } else if (!r.pois.length) setMsg({ warn: true, text: '附近没搜到，换个关键词试试' })
          } else setMsg({ warn: true, text: r.error })
        } catch (e) { setMsg({ warn: true, text: String(e.message || e) }) }
        setBusy(false)
      }
      const add = async (p) => {
        setBusy(true)
        try {
          const r = await jpost('/nearby/add', { name: p.name, address: p.address, walk_minutes: p.walk_minutes, tag })
          if (r.ok) {
            setAdded((a) => ({ ...a, [p.name]: true }))
            setMsg({ good: true, text: '已加入卡池：' + p.name + '（预算占位 25，可去 data/lunch.json 改）' })
          } else setMsg({ warn: true, text: r.error })
        } catch (e) { setMsg({ warn: true, text: String(e.message || e) }) }
        setBusy(false)
      }
      const ready = cfg && cfg.enabled && cfg.amapKey && cfg.location
      return h('div', { className: 'ck-nb' },
        h('h1', null, '附近候选（可选）'),
        h('p', { className: 'ck-lead' }, '默认关闭、零网络请求。开启后用高德周边搜索找店，人审后写进午饭卡池；不会自动下单。'),
        msg ? h('p', { className: 'ck-empty', style: { color: msg.warn ? '#f59e0b' : '#22c55e' } }, msg.text) : null,
        h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '开关'),
          h('button', { className: 'ck-sw', 'data-on': form.enabled ? '' : undefined, onClick: () => setForm({ ...form, enabled: !form.enabled }) }, h('i')),
          h('span', { className: 'ck-nb-label', style: { minWidth: 0 } }, form.enabled ? '开（会请求高德）' : '关')),
        h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '高德 Key'),
          h('input', { className: 'ck-input', value: form.amapKey, placeholder: 'lbs.amap.com 免费申请的 Web 服务 Key', onChange: (e) => setForm({ ...form, amapKey: e.target.value }) })),
        h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '位置'),
          h('input', { className: 'ck-input', value: form.location, placeholder: '经度,纬度（高德坐标拾取器可查，如 121.47,31.23）', onChange: (e) => setForm({ ...form, location: e.target.value }) }),
          h('button', { className: 'ck-solid', disabled: locating, onClick: sysLocate }, locating ? '定位中…' : '系统定位'),
          h('button', { className: 'ck-texty', style: { margin: 0 }, disabled: locating, onClick: locate }, '浏览器定位')),
        h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '半径'),
          h('input', { className: 'ck-input', style: { maxWidth: 120, flex: 'none' }, type: 'number', value: form.radius, onChange: (e) => setForm({ ...form, radius: Number(e.target.value) || 1000 }) }),
          h('span', { className: 'ck-nb-label', style: { minWidth: 0 } }, '米（100–5000）')),
        h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '自动入池'),
          h('button', { className: 'ck-sw', 'data-on': form.autoAdd ? '' : undefined, onClick: () => setForm({ ...form, autoAdd: !form.autoAdd }) }, h('i')),
          h('span', { className: 'ck-nb-label', style: { minWidth: 0 } }, form.autoAdd ? '开（选午饭卡组每天自动导入 + 搜索自动入池）' : '关（搜到后手动加）')),
        form.autoAdd ? h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '入池标签'),
          h('input', { className: 'ck-input', style: { maxWidth: 160, flex: 'none' }, value: form.autoAddTag, placeholder: '附近', onChange: (e) => setForm({ ...form, autoAddTag: e.target.value }) }),
          h('span', { className: 'ck-nb-label', style: { minWidth: 0 } }, '自动加入的店都打这个标（默认「附近」）')) : null,
        form.autoAdd ? h('div', { className: 'ck-nb-row' },
          h('span', { className: 'ck-nb-label' }, '自动搜什么'),
          h('input', { className: 'ck-input', value: form.autoKeywords, placeholder: '快餐,轻食,面馆,小吃', onChange: (e) => setForm({ ...form, autoKeywords: e.target.value }) }),
          h('span', { className: 'ck-nb-label', style: { minWidth: 0 } }, '选午饭卡组时按这些词每天自动导入一次')) : null,
        h('div', { className: 'ck-nb-row' },
          h('button', { className: 'ck-solid', disabled: busy, onClick: save }, '保存设置'),
          cfg ? h('span', { className: 'ck-nb-label', style: { minWidth: 0 } }, cfg.enabled ? '当前：开' : '当前：关') : null),
        ready ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 } },
          h('div', { className: 'ck-nb-row' },
            h('input', { className: 'ck-input', value: keyword, placeholder: '关键词：快餐 / 轻食 / 面馆…', onChange: (e) => setKeyword(e.target.value) }),
            h('button', { className: 'ck-solid', disabled: busy, onClick: search },
              cfg && cfg.autoAdd ? '搜附近（自动入池）' : '搜附近')),
          !(cfg && cfg.autoAdd) ? h('div', { className: 'ck-nb-row' },
            h('span', { className: 'ck-nb-label' }, '加入时打标'),
            ['清淡', '荤', '重口', '面', '蔬菜', '素'].map((t) => h('button', {
              className: 'ck-chip', key: t, 'aria-selected': tag === t,
              style: { minWidth: 0, padding: '6px 14px', boxShadow: 'none' },
              onClick: () => setTag(t),
            }, t))) : null,
          pois && pois.length ? pois.map((p, i) => h('div', { className: 'ck-item', key: i },
            h('span', { className: 'ck-item-t' }, p.name, ' ', added[p.name] ? h('span', { className: 'ck-added' }, '✓ 已在卡池') : null),
            h('span', { className: 'ck-item-m' }, (p.address || '') + (p.type ? ' · ' + p.type : '')),
            h('span', { className: 'ck-item-m' }, p.distance_m != null ? `直线约 ${p.distance_m} 米 · 步行约 ${p.walk_minutes} 分钟` : '距离未知'),
            !(cfg && cfg.autoAdd) ? h('div', { className: 'ck-nb-row' },
              h('button', { className: 'ck-solid', disabled: busy || added[p.name], onClick: () => add(p) }, '加入「' + tag + '」卡池')) : null)) : null,
        ) : h('p', { className: 'ck-note' }, '填好 Key 和位置、打开开关并保存后，这里能按关键词搜附近餐厅，直线距离估算步行分钟。'),
      )
    }

    /* 左侧栏图标（sidebar.panellist 全局面板行） */
    const PanelIcon = ({ size }) => h('span', {
      style: { fontSize: size, lineHeight: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' },
    }, '🎴')

    return {
      inject: ['slots'],
      apply(ctx) {
        const style = document.createElement('style')
        style.setAttribute('data-plugin-css', 'dsh-chouka')
        style.textContent = CSS
        document.head.appendChild(style)
        ctx.effect(() => () => style.remove(), 'dsh-chouka: 面板样式')

        const slots = (typeof ctx.get === 'function' ? ctx.get('slots') : undefined) || ctx.slots
        if (!slots) return
        try {
          slots.inject('sidebar.panellist', () => slots.register(
            { name: 'sidebar.panellist', id: 'chouka', order: 20, label: '今日抽卡' },
            PanelIcon,
          ))
        } catch (e) { /* 没有这个槽位就静默跳过 */ }
        try {
          slots.inject('main', () => slots.register(
            { name: 'main', key: 'chouka', label: '今日抽卡' },
            Panel,
          ))
        } catch (e) { /* 同上 */ }
      },
    }
  },
})
