# dsh-chouka

「今日抽卡」DSH 插件：本地抽卡引擎 + 炉石式开包面板 + 可选的高德附近候选。

## 功能

- **Agent tools**：`draw_card({ deck, count, constraints })`、`mark_result(draw_id, result)`
  - deck：`lunch`（中午吃什么）/ `bili_featured`（B站精选视频，只读 dsh-bili-scroll 已标注的结果）
  - count：1 / 3（面板开包是 5 张）
  - lunch constraints：`tag`（清淡/荤…）、`budget`、`want_walk`（yes/no）、`avoid_yesterday`（默认 true）
  - bili constraints：`zone`（如 ai）、`max_duration_seconds`、`tier`
  - mark_result：`did` / `skipped` / `picked:<卡片id>`（多张先 picked 再 did）
- **侧栏面板**：左侧栏 🎴「今日抽卡」。选卡组 → 选主题 → 炉石式开包（摇晃、爆开、白闪、五张牌飞到五角星尖、hover 发光、点击翻面）；稀有度按播放量分档（≥500 传说金 / ≥200 史诗紫 / ≥50 稀有天蓝 / 其余普通白；无播放量数据和午饭牌为荧光绿）
- **附近候选（可选，默认关）**：高德周边搜索找附近餐厅 → 人审加入午饭卡池。位置可系统定位（macOS CoreLocation / Windows WinRT）、浏览器定位或手动填坐标（WGS-84 自动转 GCJ-02）

## 安装

```bash
# 从 tarball（本仓库 plugin/dsh-chouka 打包产物）
dsh plugin --profile <name> add /path/to/dsh-chouka-<version>.tgz
# 或发布到 npm 后
dsh plugin --profile <name> add dsh-chouka
```

依赖：Python ≥ 3.10（自动探测 `python3` / `python` / `py -3`，也可在插件设置里指定 `pythonPath`）。

## 数据放哪

发布模式（默认）：引擎随包走（`engine/`），用户数据在 `~/.dsh/chouka/`：

- `data/lunch.json` 午饭卡池（第一次自动播种示例，附近候选加的店也写在这）
- `data/draws.jsonl` 抽取记录
- `data/bili_zones.json` 视频分区关键词
- `nearby.json` 附近候选配置（含高德 Key，明文存本机）

精选视频只读 `~/.dsh/bili-duty/`（dsh-bili-scroll 写下的 seen.md / 日报），不重新请求 B 站。

开发模式：插件设置里把 `repoPath` 指到引擎仓库根（含 `chouka/`、`data/`），引擎和数据都用仓库那份。

## 定位权限

- **macOS**：首次点「系统定位」会弹授权框（归属 ChoukaLocate）；助手已包成带 bundle 身份的 .app，直接拒绝的裸 CLI 是拿不到定位的
- **Windows**：设置 → 隐私和安全性 → 位置 → 打开「位置服务」+「允许桌面应用访问位置」（桌面应用不弹框，由总开关控制）
- **Linux**：不支持系统定位，用浏览器定位或手动填坐标

## 约束

不重写权重 / 保底 / 卡池格式；不改 dsh-bili-scroll 的爬取；核心抽卡零网络请求；不自动播放、不下单、不发帖。附近候选是唯一联网的功能，且默认关闭。

## 卸载

```bash
dsh plugin --profile <name> remove dsh-chouka
```

`~/.dsh/chouka/` 里的卡池和抽取记录会留下，想清就整个删掉该目录。
