/**
 * dsh-chouka —— 宿主半端（cordis 插件）
 * ============================================================================
 * 职责只有三件，抽卡规则一行不碰（都在引擎仓库 chouka/ 里）：
 *   1. 把 draw_card / mark_result 注册成 Agent 可调用的 tool（子进程调 runner.py）；
 *   2. 挂一条 /api/chouka/* HTTP 路由给侧栏面板用（同一个引擎，不另开数据通道）；
 *   3. 数据只读引擎自己声明的位置：仓库 config/paths.json → data/lunch.json、
 *      data/draws.jsonl、data/bili_zones.json，精选视频只读 ~/.dsh/bili-duty 已有结果。
 * 不发网络请求、不自动播放、不下单、不发帖。
 * ============================================================================
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export const name = 'chouka'
export const inject = ['webServer', 'tools']

const pluginDir = dirname(fileURLToPath(import.meta.url))

/** 从宿主树里取 defineTool（跟 bili-scroll 同一套办法：按可能性翻候选根，逐个试 entry） */
async function loadHostDefineTool() {
  const { homedir } = await import('node:os')
  const { readdirSync } = await import('node:fs')
  const roots = []
  if (process.env.DSH_HOST_MODULES) roots.push(process.env.DSH_HOST_MODULES)
  roots.push(join(homedir(), '.npm-global', 'lib', 'node_modules', '@deepseek-ai', 'dsh', 'node_modules', '@deepseek-ai'))
  roots.push('/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai')
  try {
    const dshHome = process.env.DSH_HOME || join(homedir(), '.dsh')
    for (const p of readdirSync(join(dshHome, 'profiles'))) {
      roots.push(join(dshHome, 'profiles', p, 'node_modules', '@deepseek-ai'))
    }
  } catch { /* 没有 profiles 就算了 */ }
  for (const root of roots) {
    try {
      const pkgFile = join(root, 'dsh-tools', 'package.json')
      if (!existsSync(pkgFile)) continue
      const pkg = JSON.parse(readFileSync(pkgFile, 'utf8'))
      const rel = typeof pkg.exports?.['.'] === 'string' ? pkg.exports['.'] : pkg.exports?.['.']?.default || pkg.main
      const url = pathToFileURL(join(root, 'dsh-tools', String(rel).replace(/^\.\//, ''))).href
      const mod = await import(url)
      if (typeof mod.defineTool === 'function') return mod.defineTool
    } catch { /* 换下一个根 */ }
  }
  return null
}

const defineTool = await loadHostDefineTool()

const safe = (v) => {
  if (v === undefined || v === null || typeof v !== 'object') return v
  try { return JSON.parse(JSON.stringify(v)) } catch { return String(v) }
}

export function apply(ctx, config) {
  const cfg = config || {}

  // 播种 skill 到用户全局目录（~/.dsh/skills，rank 400）：装了插件的所有会话开箱即用。
  // 内容有变化就覆盖（skill 正文每次加载都重读，无需失效缓存）。
  try {
    const skillSrc = join(pluginDir, 'skill', 'SKILL.md')
    const skillDir = join(process.env.DSH_HOME || join(homedir(), '.dsh'), 'skills', 'chouka-lunch-collect')
    if (existsSync(skillSrc)) {
      const want = readFileSync(skillSrc, 'utf8')
      const dst = join(skillDir, 'SKILL.md')
      let current = ''
      try { current = readFileSync(dst, 'utf8') } catch { /* 还没播种 */ }
      if (current !== want) {
        mkdirSync(skillDir, { recursive: true })
        writeFileSync(dst, want, 'utf8')
        try { ctx.logger?.info?.('[chouka] skill 已播种：~/.dsh/skills/chouka-lunch-collect') } catch { /* 忽略 */ }
      }
    }
  } catch { /* skill 播种失败不影响插件本体 */ }
  const repo = String(cfg.repoPath || '').trim()
  const repoValid = repo && existsSync(join(repo, 'chouka', 'engine.py'))
  const bundled = join(pluginDir, 'engine', 'chouka', 'engine.py')
  const bundledValid = existsSync(bundled)
  const stateDir = join(process.env.DSH_HOME || join(homedir(), '.dsh'), 'chouka')
  // 开发模式：配置了有效 repoPath 就用仓库（引擎+数据都在仓库）；
  // 发布模式：引擎用包里带的 engine/，数据落在插件家目录 ~/.dsh/chouka（首次自动播种）
  const engineDir = repoValid ? repo : join(pluginDir, 'engine')
  const engineRoot = repoValid ? repo : stateDir
  const runner = join(pluginDir, 'runner.py')
  const log = (m) => { try { ctx.logger?.info?.(`[chouka] ${m}`) } catch { /* 没有 logger 就算了 */ } }
  if (!repoValid && !bundledValid) {
    log(`引擎不可用：既没有有效 repoPath（${repo || '未配置'}），包里也没有 ${bundled} —— 工具会返回 ok:false`)
  }

  /** Python 解释器：配置优先，否则探测 python3 / python / py -3（要求 >= 3.10） */
  let pyCache = null
  const findPython = () => {
    if (pyCache) return pyCache
    const candidates = []
    const configured = String(cfg.pythonPath || '').trim()
    if (configured) candidates.push([configured, []])
    if (process.platform === 'win32') candidates.push(['py', ['-3']], ['python', []])
    else candidates.push(['python3', []], ['python3.13', []], ['python3.12', []], ['python3.11', []], ['python3.10', []], ['python', []])
    for (const [cmd, pre] of candidates) {
      try {
        const v = spawnSync(cmd, [...pre, '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'], { encoding: 'utf8', timeout: 10_000 })
        if (v.status === 0) { pyCache = { cmd, pre }; return pyCache }
      } catch { /* 换下一个 */ }
    }
    return null
  }

  /** 调引擎。规则、卡池、记录全在引擎那侧，这里只传参收结果。 */
  const callEngine = (payload) => {
    const py = findPython()
    if (!py) {
      return { ok: false, error: '找不到 Python >= 3.10：装一个（python.org / Microsoft Store），或在插件设置里把 pythonPath 指到解释器' }
    }
    if (!repoValid && !bundledValid) {
      return { ok: false, error: `引擎不可用（包里缺 engine/，repoPath=${repo || '未配置'} 也无效）` }
    }
    const r = spawnSync(py.cmd, [...py.pre, runner, JSON.stringify(payload)], {
      cwd: engineDir,
      env: { ...process.env, CHOUKA_ROOT: engineRoot, CHOUKA_ENGINE_DIR: engineDir },
      encoding: 'utf8',
      timeout: 30_000,
    })
    if (r.error) return { ok: false, error: `起不来引擎（${r.error.message}）` }
    const line = (r.stdout || '').trim().split('\n').filter(Boolean).pop() || ''
    try {
      const parsed = JSON.parse(line)
      if (!parsed.ok) log(`引擎拒绝：${parsed.error}`)
      return parsed
    } catch {
      return { ok: false, error: `引擎输出不可解析：${(r.stderr || r.stdout || '').slice(0, 300)}` }
    }
  }

  // ── 1. Agent tools ──────────────────────────────────────────────────────
  /* 宿主只吃无损 JSON；输出必须有 render（bili-scroll 同款 textOutput） */
  const safe = (v) => {
    if (v === undefined || v === null || typeof v !== 'object') return v
    try { return JSON.parse(JSON.stringify(v)) } catch { return String(v) }
  }
  const textOutput = {
    schema: { type: 'object', properties: {}, additionalProperties: true },
    render: (_args, value) => [{
      type: 'text',
      text: typeof value === 'string' ? value : JSON.stringify(value, null, 2),
    }],
  }
  if (!defineTool) {
    log('⚠️ 宿主树里拿不到 @deepseek-ai/dsh-tools —— 工具不注册（HTTP 路由不受影响）')
  }
  const registerOne = (spec) => {
    try {
      ctx.tools.register(defineTool({
        ...spec,
        output: spec.output || textOutput,
        async execute(args, exec) { return safe(await spec.execute(args, exec)) },
      }))
      log(`tool 已注册：${spec.name}`)
    } catch (e) {
      log(`tool ${spec.name} 注册失败：${e?.message ?? e}`)
    }
  }
  if (defineTool) {
    registerOne({
      name: 'draw_card',
      description: '抽卡。deck=lunch（中午吃什么）或 bili_featured（B站精选视频，只读 dsh-bili-scroll 已标注的结果）。'
        + 'count 只能是 1 或 3；3 张时从返回里拣一张，用 mark_result 记 picked:<id>。'
        + '返回 draw_id、cards（含 title / reason「为什么抽给你」/ face / watch_variant）、pity、weights。只出建议，不打开、不播放、不下单。',
      parameters: {
        deck: { type: 'string', description: 'lunch | bili_featured', required: true },
        count: { type: 'number', description: '1 或 3（默认 1）' },
        constraints: {
          type: 'object',
          description: '可选。lunch：tag（清淡/荤…）、budget（元）、want_walk（yes/no）、avoid_yesterday（默认 true，避开昨天抽过的）；bili_featured：zone（如 ai）、max_duration_seconds、tier',
          properties: {
            tag: { type: 'string' },
            budget: { type: 'number' },
            want_walk: { type: 'string' },
            avoid_yesterday: { type: 'boolean' },
            zone: { type: 'string' },
            max_duration_seconds: { type: 'number' },
            tier: { type: 'string' },
          },
          additionalProperties: false,
        },
      },
      async execute(args) {
        const deck = String(args?.deck || '')
        let count = Number(args?.count ?? 1) || 1
        if (count !== 1 && count !== 3) count = count === 5 ? 5 : 1
        const rawC = args?.constraints
        const constraints = {}
        if (rawC && typeof rawC === 'object') {
          // 按牌的白名单过滤，避免把午饭约束塞给精选（引擎会整单拒绝）
          const ok = deck === 'lunch'
            ? ['tag', 'budget', 'want_walk', 'avoid_yesterday']
            : ['zone', 'tier', 'max_duration_seconds']
          for (const key of ok) {
            if (rawC[key] == null) continue
            if (key === 'budget' || key === 'max_duration_seconds') constraints[key] = Number(rawC[key])
            else if (key === 'avoid_yesterday') constraints[key] = Boolean(rawC[key])
            else constraints[key] = String(rawC[key])
          }
        }
        return callEngine({ op: 'draw', deck, count, constraints })
      },
    })

    registerOne({
      name: 'mark_result',
      description: '记录一次抽取的结果。result=did（照做了）/ skipped（跳过）/ picked:<卡片id>（抽了多张时先拣中哪张，之后再补 did）。抽 1 张不要发 picked。',
      parameters: {
        draw_id: { type: 'string', description: 'draw_card 返回的 draw_id', required: true },
        result: { type: 'string', description: 'did | skipped | picked:<id>', required: true },
      },
      async execute(args) {
        return callEngine({ op: 'mark', draw_id: String(args?.draw_id || ''), result: String(args?.result || '') })
      },
    })

    registerOne({
      name: 'chouka_add_lunch',
      description: '往午饭卡池加一张牌（人工确认过的真实选项）。典型用法：用户在 IM 里发餐厅照片 + 文字说明（标签/预算/步行时间），'
        + '你从照片认出店名和菜品、按文字补全属性后调用。同名已存在会报错；budget 未知可省略（默认 25）。',
      parameters: {
        name: { type: 'string', description: '店名或菜品名（卡牌标题），如「老乡鸡(阳光天地店)」', required: true },
        tags: { type: 'string', description: '类型标签，逗号分隔，如 "清淡" 或 "荤,重口"', required: true },
        notes: { type: 'string', description: '备注：来源、推荐菜、照片里的补充信息等' },
        budget: { type: 'number', description: '预算（元）；不知道就别传，占位 25' },
        walk_minutes: { type: 'number', description: '步行分钟数' },
      },
      async execute(args) {
        const tags = String(args?.tags || '').split(/[,，、]/).map((s) => s.trim()).filter(Boolean)
        return callEngine({
          op: 'add_lunch',
          name: String(args?.name || '').slice(0, 40),
          tags,
          notes: String(args?.notes || ''),
          budget: args?.budget != null ? Number(args.budget) : 25,
          walk_minutes: args?.walk_minutes != null ? Number(args.walk_minutes) : 10,
        })
      },
    })
  }

  // ── 2. 给侧栏面板的 HTTP 路由 ────────────────────────────────────────────
  const sendJson = (res, code, body) => {
    try {
      res.statusCode = code
      res.setHeader('content-type', 'application/json; charset=utf-8')
      res.end(JSON.stringify(body))
    } catch { /* 客户端断开就算了 */ }
  }
  const readBody = async (req) => new Promise((resolve) => {
    let buf = ''
    req.on('data', (c) => { buf += c })
    req.on('end', () => { try { resolve(JSON.parse(buf || '{}')) } catch { resolve({}) } })
    req.on('error', () => resolve({}))
  })

  // 信任栅栏：能拿到宿主 connection.requestRejection 就用它（真鉴权），拿不到退回本机同源
  const getConnection = () => {
    for (const fn of [
      () => (typeof ctx.get === 'function' ? ctx.get('connection') : null),
      () => Reflect.get(ctx, 'connection'),
      () => ctx.root?.connection,
    ]) {
      try { const c = fn(); if (c && typeof c.requestRejection === 'function') return c } catch { /* 下一个 */ }
    }
    return null
  }
  const gate = (req, res) => {
    const conn = getConnection()
    if (conn) {
      try {
        const rejection = conn.requestRejection({ headers: req.headers })
        if (rejection !== undefined) { sendJson(res, typeof rejection === 'number' ? rejection : 403, { ok: false, error: '未授权' }); return true }
        return false
      } catch { /* 落到同源检查 */ }
    }
    const host = String(req.headers.host || '')
    const pick = String(req.headers.origin || req.headers.referer || '')
    if (!/^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/i.test(host)) { sendJson(res, 403, { ok: false, error: '只接受本机请求' }); return true }
    if (pick) {
      try {
        const u = new URL(pick)
        if (String(u.host || '').toLowerCase() !== host.toLowerCase()) { sendJson(res, 403, { ok: false, error: '只接受本机同源请求' }); return true }
      } catch { /* 忽略 */ }
    }
    return false
  }

  const handle = async (req, res, url) => {
    const path = url.pathname
    if (req.method === 'GET' && path === '/api/chouka/draw') {
      const q = url.searchParams
      const constraints = {}
      for (const key of ['tag', 'zone', 'want_walk', 'tier']) if (q.get(key)) constraints[key] = q.get(key)
      if (q.get('budget')) constraints.budget = Number(q.get('budget'))
      if (q.get('max_duration_seconds')) constraints.max_duration_seconds = Number(q.get('max_duration_seconds'))
      if ((q.get('deck') || 'lunch') === 'lunch' && q.get('allow_yesterday')) constraints.avoid_yesterday = false // 兼容旧参数名：放开昨天
      return sendJson(res, 200, callEngine({
        op: 'draw', deck: q.get('deck') || 'lunch', count: Number(q.get('count') || 1) || 1, constraints,
      }))
    }
    if (req.method === 'GET' && path === '/api/chouka/categories') {
      return sendJson(res, 200, callEngine({ op: 'categories', deck: url.searchParams.get('deck') || '' }))
    }
    if (req.method === 'GET' && path === '/api/chouka/pack') {
      // 开一包：抽 5 张，返回 preview 卡面格式（kicker/rarity/lines 与 python -m chouka preview 同一套）
      const q = url.searchParams
      const req_ = { op: 'pack', deck: q.get('deck') || '', category: q.get('category') || '' }
      if (q.get('deck') === 'lunch' && q.get('avoid_yesterday') === 'false') req_.avoid_yesterday = false
      return sendJson(res, 200, callEngine(req_))
    }

    // ── 附近候选（可选开关，默认关；关 = 零网络请求） ──
    const stateDir = join(process.env.DSH_HOME || join(homedir(), '.dsh'), 'chouka')
    const nearbyFile = join(stateDir, 'nearby.json')
    const readNearby = () => {
      try {
        const raw = JSON.parse(readFileSync(nearbyFile, 'utf8'))
        return {
          enabled: raw.enabled === true, amapKey: String(raw.amapKey || ''),
          location: String(raw.location || ''), radius: Math.max(100, Math.min(5000, Number(raw.radius) || 1000)),
          autoAdd: raw.autoAdd === true, autoAddTag: String(raw.autoAddTag || '附近'),
          autoKeywords: String(raw.autoKeywords || '快餐,轻食,面馆,小吃'),
        }
      } catch { return { enabled: false, amapKey: '', location: '', radius: 1000, autoAdd: false, autoAddTag: '附近', autoKeywords: '快餐,轻食,面馆,小吃' } }
    }
    const writeNearby = (cfg) => {
      mkdirSync(stateDir, { recursive: true })
      writeFileSync(nearbyFile, JSON.stringify(cfg, null, 2), 'utf8')
    }
    const LOC_RE = /^\d{1,3}\.\d+,\d{1,3}\.\d+$/

    if (path === '/api/chouka/nearby/config') {
      if (req.method === 'GET') return sendJson(res, 200, { ok: true, config: readNearby() })
      if (req.method === 'POST') {
        const body = await readBody(req)
        const cur = readNearby()
        const next = {
          enabled: body.enabled === true,
          amapKey: body.amapKey != null ? String(body.amapKey).trim() : cur.amapKey,
          location: body.location != null ? String(body.location).trim() : cur.location,
          radius: body.radius != null ? Math.max(100, Math.min(5000, Number(body.radius) || 1000)) : cur.radius,
          autoAdd: body.autoAdd === true,
          autoAddTag: body.autoAddTag != null ? (String(body.autoAddTag).trim() || '附近') : cur.autoAddTag,
          autoKeywords: body.autoKeywords != null ? (String(body.autoKeywords).trim() || '快餐,轻食,面馆,小吃') : cur.autoKeywords,
        }
        if (next.enabled) {
          if (!next.amapKey) return sendJson(res, 200, { ok: false, error: '需要高德 Web 服务 Key（lbs.amap.com 免费申请）' })
          if (!LOC_RE.test(next.location)) return sendJson(res, 200, { ok: false, error: '位置格式应为「经度,纬度」，如 121.47,31.23（高德坐标拾取器可查）' })
        }
        writeNearby(next)
        return sendJson(res, 200, { ok: true, config: next })
      }
    }

    /* 高德周边搜索（搜索路由与每日自动导入共用） */
    const amapPois = async (cfg, keyword) => {
      const u = 'https://restapi.amap.com/v3/place/around?key=' + encodeURIComponent(cfg.amapKey)
        + '&location=' + encodeURIComponent(cfg.location)
        + '&keywords=' + encodeURIComponent(keyword)
        + '&radius=' + cfg.radius + '&offset=20&types=050000|050100|050200|050300'
      const r = await fetch(u, { signal: AbortSignal.timeout(10_000) })
      const data = await r.json()
      if (data.status !== '1') {
        const hints = {
          USERKEY_PLAT_NOMATCH: 'Key 的服务平台类型不对：需要「Web服务」类型的 Key（控制台创建时服务平台选 Web服务，不是 Web端(JS API)）',
          INVALID_USER_KEY: 'Key 无效，检查是否复制完整',
          DAILY_QUERY_OVER_LIMIT: '今日配额用完了，明天再试或升级配额',
        }
        throw new Error('高德返回错误：' + (data.info || '未知') + (hints[data.info] ? ' —— ' + hints[data.info] : ''))
      }
      const [lng0, lat0] = cfg.location.split(',').map(Number)
      return (data.pois || []).map((p) => {
        const [lng, lat] = String(p.location || '').split(',').map(Number)
        const dist = (Number.isFinite(lng) && Number.isFinite(lat))
          ? Math.round(6371000 * Math.acos(Math.min(1,
              Math.sin(lat0 * Math.PI / 180) * Math.sin(lat * Math.PI / 180)
              + Math.cos(lat0 * Math.PI / 180) * Math.cos(lat * Math.PI / 180) * Math.cos((lng - lng0) * Math.PI / 180))))
          : null
        return {
          name: String(p.name || ''), address: [p.pname, p.cityname, p.adname, p.address].filter(Boolean).join('').replace(/undefined/g, ''),
          type: String(p.type || '').split(';')[0] || '',
          distance_m: dist, walk_minutes: dist != null ? Math.max(1, Math.round(dist / 80)) : null,
        }
      }).filter((p) => p.name)
    }

    if (req.method === 'GET' && path === '/api/chouka/nearby/search') {
      const cfg = readNearby()
      if (!cfg.enabled || !cfg.amapKey || !LOC_RE.test(cfg.location)) {
        return sendJson(res, 200, { ok: false, error: '附近候选未开启或配置不全（Key / 位置）' })
      }
      const q = url.searchParams
      const keyword = String(q.get('keyword') || '快餐').slice(0, 32)
      try {
        const pois = await amapPois(cfg, keyword)
        // 自动入池：搜索结果里的新店直接进卡池（同名跳过），打 autoAddTag 标签
        let auto = null
        if (cfg.autoAdd && pois.length) {
          const r2 = callEngine({
            op: 'add_lunch_batch',
            tags: [cfg.autoAddTag || '附近'],
            items: pois.map((p) => ({
              name: p.name,
              notes: '来自高德附近候选：' + String(p.address || '').slice(0, 60) + '。预算是占位，请自己改。',
              walk_minutes: p.walk_minutes ?? 10,
            })),
          })
          if (r2.ok) {
            auto = { added: r2.data.added, existed: r2.data.existed }
            const inPool = new Set([...r2.data.added.map((a) => a.name), ...r2.data.existed])
            for (const p of pois) if (inPool.has(p.name)) p.in_pool = true
          }
        }
        return sendJson(res, 200, { ok: true, pois, radius: cfg.radius, keyword, auto })
      } catch (e) {
        return sendJson(res, 200, { ok: false, error: '请求高德失败：' + String(e?.message || e) })
      }
    }

    // 每日自动导入：选午饭卡组时由面板触发，一天只跑一次。
    // 用 autoKeywords 里的关键词逐个搜，按距离取最近的，去重后批量入池（打 autoAddTag 标签）
    if (req.method === 'POST' && path === '/api/chouka/nearby/import') {
      const cfg = readNearby()
      if (!cfg.enabled || !cfg.amapKey || !LOC_RE.test(cfg.location)) {
        return sendJson(res, 200, { ok: false, error: '附近候选未开启或配置不全（Key / 位置）' })
      }
      if (!cfg.autoAdd) {
        return sendJson(res, 200, { ok: false, error: '自动入池开关没开（在「附近候选」里打开并保存）' })
      }
      const stateFile = join(stateDir, 'nearby-state.json')
      let state = {}
      try { state = JSON.parse(readFileSync(stateFile, 'utf8')) } catch { /* 第一次 */ }
      const today = new Date().toLocaleDateString('sv-SE')
      if (state.lastImport === today) {
        return sendJson(res, 200, { ok: true, skipped: true, added: [], existed: [] })
      }
      const keywords = cfg.autoKeywords.split(/[,，]/).map((s) => s.trim()).filter(Boolean).slice(0, 4)
      const seen = new Map()
      try {
        for (const kw of keywords) {
          const pois = await amapPois(cfg, kw)
          pois.sort((a, b) => (a.distance_m ?? 9e9) - (b.distance_m ?? 9e9))
          for (const p of pois.slice(0, 8)) {
            if (!seen.has(p.name)) seen.set(p.name, p)
          }
          if (seen.size >= 20) break
        }
      } catch (e) {
        return sendJson(res, 200, { ok: false, error: String(e?.message || e) })
      }
      const items = [...seen.values()].slice(0, 20)
      let out = { added: [], existed: [] }
      if (items.length) {
        const r2 = callEngine({
          op: 'add_lunch_batch',
          tags: [cfg.autoAddTag || '附近'],
          items: items.map((p) => ({
            name: p.name,
            notes: '来自高德每日自动导入（' + today + '）：' + String(p.address || '').slice(0, 50) + '。预算是占位，请自己改。',
            walk_minutes: p.walk_minutes ?? 10,
          })),
        })
        if (!r2.ok) return sendJson(res, 200, r2)
        out = r2.data
      }
      try { writeFileSync(stateFile, JSON.stringify({ ...state, lastImport: today, lastImportCount: out.added.length }, null, 2), 'utf8') } catch { /* 状态写不进就算了 */ }
      return sendJson(res, 200, { ok: true, keywords, ...out })
    }

    if (req.method === 'POST' && path === '/api/chouka/nearby/add') {
      const body = await readBody(req)
      const tag = String(body.tag || '').trim()
      if (!tag) return sendJson(res, 200, { ok: false, error: '先选一个类型标签（清淡/荤/…）' })
      return sendJson(res, 200, callEngine({
        op: 'add_lunch',
        name: String(body.name || '').slice(0, 40),
        tags: [tag],
        notes: '来自高德附近候选：' + String(body.address || '').slice(0, 60) + '。预算是占位，请自己改。',
        budget: 25,
        walk_minutes: Math.max(1, Math.min(120, Number(body.walk_minutes) || 10)),
      }))
    }

    // 系统定位：按平台选助手。macOS = CoreLocation（要包成带 bundle 身份的 .app，
    // macOS 13+ 对无身份 CLI 直接拒绝定位）；Windows = WinRT Geolocation（PowerShell，零依赖）。
    // 都返回 WGS-84，GCJ-02 转换在面板里做。首次运行 macOS 会弹系统授权框。
    if (req.method === 'GET' && path === '/api/chouka/nearby/locate') {
      const isMac = process.platform === 'darwin'
      const isWin = process.platform === 'win32'
      if (!isMac && !isWin) {
        return sendJson(res, 200, { ok: false, error: '系统定位目前支持 macOS 和 Windows；Linux 请用「浏览器定位」或手动填坐标' })
      }
      try {
        let r
        if (isMac) {
          const src = join(pluginDir, 'locate.swift')
          const appDir = join(stateDir, 'ChoukaLocate.app')
          const bin = join(appDir, 'Contents', 'MacOS', 'locate-core')
          if (!existsSync(bin)) {
            mkdirSync(join(appDir, 'Contents', 'MacOS'), { recursive: true })
            const c = spawnSync('xcrun', ['swiftc', '-O', '-o', bin, src], { encoding: 'utf8', timeout: 60_000 })
            if (c.status !== 0) {
              return sendJson(res, 200, { ok: false, error: '编译定位助手失败（需要 Xcode Command Line Tools，可 xcode-select --install）：' + String(c.stderr || '').slice(0, 200) })
            }
            writeFileSync(join(appDir, 'Contents', 'Info.plist'), `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.dsh.chouka.locate</string>
  <key>CFBundleName</key><string>ChoukaLocate</string>
  <key>CFBundleDisplayName</key><string>抽卡定位助手</string>
  <key>CFBundleExecutable</key><string>locate-core</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>NSLocationWhenInUseUsageDescription</key><string>「今日抽卡」的附近候选需要你的位置来搜索附近餐厅。只在点击定位按钮时读取一次。</string>
</dict>
</plist>
`, 'utf8')
            spawnSync('codesign', ['--force', '-s', '-', appDir], { encoding: 'utf8', timeout: 30_000 })
          }
          r = spawnSync(bin, [], { encoding: 'utf8', timeout: 32_000 })
        } else {
          const script = join(pluginDir, 'locate-win.ps1')
          r = spawnSync('powershell.exe',
            ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script],
            { encoding: 'utf8', timeout: 32_000 })
        }
        const line = (r.stdout || '').trim().split(/\r?\n/).filter(Boolean).pop() || ''
        let out
        try { out = JSON.parse(line) } catch {
          return sendJson(res, 200, { ok: false, error: '定位助手没有返回有效结果：' + String((r.stderr || line || '无输出')).slice(0, 200) })
        }
        if (out.error) {
          const denied = /拒绝|denied|授权|AccessDenied/i.test(String(out.error))
          const hint = isMac
            ? '。如果刚才没弹授权框：这个弹框偶尔要等几秒才出现；如果一直不弹，去 系统设置 → 隐私与安全性 → 定位服务 看列表里有没有「ChoukaLocate / 抽卡定位助手」，手动设为允许。'
            : '。去 设置 → 隐私和安全性 → 位置，打开「位置服务」和「允许桌面应用访问位置」后重试。'
          return sendJson(res, 200, { ok: false, error: '系统定位失败：' + out.error + (denied ? hint : '') })
        }
        return sendJson(res, 200, { ok: true, lat: out.lat, lng: out.lng, accuracy: out.accuracy })
      } catch (e) {
        return sendJson(res, 200, { ok: false, error: '定位助手出错：' + String(e?.message || e) })
      }
    }
    if (req.method === 'POST' && path === '/api/chouka/mark') {
      const body = await readBody(req)
      return sendJson(res, 200, callEngine({ op: 'mark', draw_id: String(body.draw_id || ''), result: String(body.result || '') }))
    }
    if (req.method === 'GET' && path === '/api/chouka/status') {
      const py = findPython()
      return sendJson(res, 200, {
        ok: true,
        mode: repoValid ? 'repo' : 'bundled',
        repo: repoValid ? repo : null,
        dataHome: engineRoot,
        engineReady: repoValid || bundledValid,
        python: py ? (py.pre.length ? py.cmd + ' ' + py.pre.join(' ') : py.cmd) : null,
        runner,
      })
    }
    return sendJson(res, 404, { ok: false, error: `unknown ${req.method} ${path}` })
  }

  try {
    ctx.effect(() => ctx.webServer.register({
      kind: 'prefix',
      path: '/api/chouka',
      handler: async (req, res) => {
        if (gate(req, res)) return
        try { await handle(req, res, new URL(req.url, 'http://127.0.0.1')) }
        catch (err) { sendJson(res, 500, { ok: false, error: err?.message ?? String(err) }) }
      },
    }), 'chouka: /api/chouka 路由')
    log('HTTP 路由已挂：/api/chouka/*')
  } catch (e) {
    log(`HTTP 路由没挂上：${e?.message ?? e}`)
  }
}
