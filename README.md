# 抽卡

本地抽卡引擎。同一套规则挂多副牌，第一期只有两副：午饭 `lunch`，以及 dsh-bili-scroll 已经标成精选的视频 `bili_featured`。

规则在 Python 里，能单测。这个项目不调用任何模型接口，也不改 DeepSeek Harness，也不改 dsh-bili-scroll 的爬取和滚动。

## 运行

在仓库根目录：

```text
python -m chouka categories lunch
python -m chouka categories bili_featured
python -m chouka draw lunch --count 5 --tag 清淡
python -m chouka draw bili_featured --count 5 --zone ai
python -m chouka draw lunch --count 1
python -m chouka draw lunch --count 3 --budget 25 --walk yes
python -m chouka preview
python -m chouka mark <draw_id> did
python -m chouka mark <draw_id> skipped
python -m chouka mark <draw_id> picked:<卡片 id>
python -m unittest discover -s tests
```

`count` 只能是 1、3 或 5。开一包是 5 张，并且要先选定午饭类型或视频区。命令行不提问，用 `--tag` / `--zone` 把选择传进来。页面上的询问在 `python -m chouka preview`。

午饭默认避开昨天抽过的；`--allow-yesterday` 关掉这条。`--walk yes` 只要出门的，`--walk no` 只要不用走的。

库接口不读标准输入：

```python
from chouka import draw_card, mark_result

result = draw_card({"deck": "lunch", "count": 1, "constraints": {"budget": 30}})
mark_result(result["draw_id"], "did")
# 抽了 3 张或 5 张时，先记下选了哪张，再记有没有照做：
mark_result(result["draw_id"], "picked:tomato-egg-noodle")
mark_result(result["draw_id"], "did")
```

返回里有 `draw_id`、`cards`（含 `title`、`reason`、`face`、`watch_variant`）、`pity`、`weights`。`reason` 就是「为什么抽给你」。

## 改哪个文件

路径只写在 [`config/paths.json`](config/paths.json)。

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `lunch_pool` | `data/lunch.json` | 午饭卡池 |
| `draws` | `data/draws.jsonl` | 抽取记录，第一次抽的时候自动创建 |
| `bili_zones` | `data/bili_zones.json` | 精选视频的区，按关键词归类 |
| `bili_home` | 空 | 空则用环境变量 `BILI_DUTY_HOME`，再没有就用 `%USERPROFILE%\.dsh\bili-duty` |

午饭只改 [`data/lunch.json`](data/lunch.json)。现在的条目都是示例菜名，notes 以「示例」开头。把 `name`、`tags`、`notes`、`budget`、`walk_minutes` 换成你自己的，不想被抽到就把 `enabled` 设为 `false`。程序不会补餐厅，也不会现编条目。`清淡` 和 `荤` 各留了至少 5 条，这样这两类能各开一包。别的标签不够 5 张时，开包页会写还差几张，不会拿别的类型来凑。

每条至少要有：`id`、`name`、`tags`、`notes`、`budget`、`walk_minutes`、`enabled`。

偏荤、清淡靠 tags，不用另开字段：

- 偏荤：含 `荤` 或 `重口`，并且不含 `清淡`、`蔬菜`、`素`
- 清淡：含 `清淡`、`蔬菜` 或 `素`

## 精选视频读哪里

只读 dsh-bili-scroll 已经写下的文件，不重新请求 B 站。

家目录默认是 `C:\Users\XPENG\.dsh\bili-duty`（也就是 `%USERPROFILE%\.dsh\bili-duty`）。

| 文件 | 用它做什么 |
| --- | --- |
| `seen.md` | 判重表。一行 `| 日期 | BV号 | 标题 | UP | 状态 |`。状态是「挑了」才进卡池，和插件 `parseSeenTable` 的 picked 同一套判断（含「挑 / 收 / 选」，排除「跳过」） |
| `out/YYYY-MM-DD.md` | 日报。`### BV号` 开头的一块是一条。补标题、UP、链接、播放量、档位、为什么值得、评语 |
| `reports/BV-日期.md` | 单条笔记。日报里缺「为什么值得」时才用来补 |

卡面字段对着这些写法：

| 卡面 | 来源 |
| --- | --- |
| `bvid` / `url` | `seen.md` 的 BV 列；链接优先用日报里的 `https://www.bilibili.com/video/BV…`，没有就按 BV 拼 |
| `title` | 日报「标题」，没有就用判重表 |
| `up` | 日报「UP」行里 `·` 前面的名字，没有就用判重表 |
| `play` | UP 行里的「播放」 |
| `tier` | 「档位」：值得看 / 可以看 / 不值当 |
| `why` | 「为什么值得」。这是精选原因 |
| `comment` | 「我的话」或「我的一句话」 |
| `featured_on` | 判重表里的日期 |
| `status` | 判重表状态，精选这里是「挑了」 |
| `duration_seconds` | 日报没有单独的时长字段。只从标题、为什么值得、评语里的「N分钟 / N分半 / N小时」解析；解析不到就是 `null` |
| `tags` | 这些文件里没有标签，固定是 `[]`。分区不写在这里，见下一节 |
| `zones` | 由 [`data/bili_zones.json`](data/bili_zones.json) 的关键词打上。一条视频可以进多个区 |
| `cover` | 插件不把封面落盘，只在打开设置页时临时向 B 站要。本引擎不联网，所以是 `null`。若你自己放了 `bili_home/covers/<BV>.jpg`（也接受 png / webp），会填本地路径 |
| `watch_variant` | 解析到的时长 ≥ 15 分钟时为 `first_3_min`，表示「只看前 3 分钟」。只做标记，不裁剪，不播放 |

`tests/fixtures/bili` 是按上述文件缩小的解析样例。本机没有 bili-duty 目录时，可以把 `bili_home` 指到一份同样结构的目录。

## 先选类型，再开一包

午饭的类型就是 `tags` 里的词，比如 `清淡`、`荤`。视频日报里没有 B 站分区，所以区写在 [`data/bili_zones.json`](data/bili_zones.json)：标题、为什么值得、评语里出现任一关键词，就进这个区。改关键词即可，不用改爬虫。

当前示例里，`ai`（AI编程）覆盖现在这批已挑视频。`tool`、`workflow` 往往不够 5 条，页面上不能开包。一个区至少 5 条才能抽一包。

页面会先问，再开包：

```text
python -m chouka preview
```

它只在本机开一个页面，打印 `http://127.0.0.1:8765/` 这类地址。先选午饭或精选，再选类型或区，然后点卡包。卡包会晃、裂开，5 张牌背面朝上，落到五角星的五个尖上。鼠标移上去才发光，每张牌一种颜色，值得看是金色。点一下才翻开牌面。牌面理由只留短短两行，视频牌上有可点的链接。关掉这个命令，页面就停。

直接双击 `preview/index.html` 问不了卡池，只能重播上一包的开包动画。`python -m chouka preview --file` 会把最近一次抽取写进这个文件并打印路径。

## 规则

数字以 [`chouka/rules.py`](chouka/rules.py) 为准。

- 基础权重 1。每次 `did` 加 0.8，最多加 4（基础最高到 5），然后再乘下面的惩罚。
- 上一手刚出现过的牌 ×0.25，避免连续抽到同一家或同一条视频。更早的最近 4 手里，每出现一次再 ×0.6。刚出现过的那一手只乘 0.25，不和 0.6 叠乘。
- 同一张牌连续 `skipped` 达到 2 次就冷藏：从最近这次跳过的日期 D 起，D、D+1、D+2 不参与抽取，D+3 回来。`did` 或 `picked` 会打断连续跳过。
- `picked` 只表示抽了多张时选了哪张，本身不加权重。抽 3 张或 5 张要记照做，先 `picked:<id>` 再 `did`，权重加在选中的那张上。抽了多张直接 `skipped`，这一手里的每张都算跳过。
- 午饭保底：昨天和前天都 `did` 了偏荤，今天把清淡牌的权重 ×4。跳过不算照做。
- 视频保底：今天之前，连续 3 个有抽取记录、并且日历相连的日子都没有 `did`，下一手至少第一张是较短的。有 ≤8 分钟的就从里面抽；都更长就取已知时长里最短的。完全没有时长时，保底记一笔但不会硬抽。
- ≥15 分钟的视频打上 `first_3_min`。

标记 `did` 会提高它以后的权重，但刚抽过的惩罚更猛，所以下一手仍可能让开，避免总是同一家。测试 `test_mark_did_changes_next_weight` 和 `test_did_raises_weight_and_same_roll_switches_card` 用同一记随机数对比了这一点。

## 还没做

留给以后接 DeepSeek Harness 的部分，这次故意不做：

- 不把 `draw_card` / `mark_result` 包成 DSH tool
- 不做侧栏
- 不做预设

也不做自动发帖、自动播放、自动下单、自动打开外卖。抽到视频只给出链接和标记。
