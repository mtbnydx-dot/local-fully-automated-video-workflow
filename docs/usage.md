# 使用与运行记录

## 安装与输入

从仓库根目录安装；三个 CLI 共用应用环境。FFmpeg 由 `imageio-ffmpeg` 提供。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
source .venv/bin/activate
# GPU 成片转写需要额外安装：
python -m pip install -e '.[asr]'
```

`scriptpipe` 默认使用 Ark `deepseek-v4.1-flash`、环境变量或 `.env` 中的 `DEEPSEEK-KEY`，endpoint 为 `https://ark.cn-beijing.volces.com/api/coding/v3`。请求显式开启 thinking；规划、写作、修复、审阅均继承 `--reasoning-effort high`。`--model glm-5.3` 自动选择 `GLMKEY`，也可通过 `--key-name` 指定。`--max-tokens` 默认 393216，包含思考与最终输出的预算。`imagepipe` 默认使用官方 GPT Image 2.6 Sunburst，读取环境变量或 `.env` 中的 `OPENAI`，配置见 [imagepipe.yaml](../configs/imagepipe.yaml)。`--provider qwen` 使用原本地部署服务，键名为 `QWEN-IMAGE`，配置见 [imagepipe_qwen.yaml](../configs/imagepipe_qwen.yaml)。本地视频服务准备见 [部署](deployment.md)。

## 顺序运行

```bash
# 长剧：原文 → 整季剧本和图片槽位；短剧去掉 --long-form
scriptpipe --source /data/project/source.txt --notes /data/project/editor_notes.md \
  --long-form --episodes 8 --episode-minutes 5 --output /data/runs/script \
  --delivery /data/season --production-config configs/b200.yaml

# 补图：输入为含 image_slots.json 的整季或单集目录
ulimit -n 16384  # 高并发任务会同时打开多张参考图
imagepipe run /data/season --config configs/imagepipe.yaml --output /data/runs/images
imagepipe status /data/runs/images
imagepipe resume /data/runs/images

# 选择原 Qwen 图片服务
imagepipe run /data/season --provider qwen --output /data/runs/images-qwen

# 先验证一集，再运行整季；每集读取自身 production.yaml
videopipe validate /data/season/episodes/ep01/package.json \
  --config /data/season/episodes/ep01/production.yaml
videopipe run-season /data/season --output /data/runs/video-season

# 从已有记录重新收集交付
videopipe collect /data/runs/video-season
```

模型请求默认并发 20，可通过 `--concurrency` 覆盖。当前 DeepSeek 配额为 5,000,000 TPM，每 1,000,000 TPM 允许并发 5，最大并发 25，默认取其 80%。`--notes` 可省略。短剧交付到 `<output>/delivery/`；长剧可以指定 `--delivery`，也可用 `--stop-after season|plans|drafts|review` 在阶段结束时暂停。剧本续跑使用相同命令和输出目录，复用已存阶段；调整素材、创作 brief 或模板后用新输出目录开始，避免复用旧稿。

图片的 `run` 遇到已有 `tasks.json` 会读取已存计划；目标图片存在即复用。默认运行目录为 `runs/imagepipe/<包名>/<provider>/`，按集运行再追加集范围。切换后端时使用对应运行目录；`resume` 使用原记录的后端，兼容旧 Qwen 任务。`--config` 可指定对应后端的自定义 YAML，与显式 `--provider` 保持一致。全剧包内的状态字段保留文字导出时的快照；分批交付包在图片齐备后写入实际交付状态。视频入口按实际文件是否存在校验。

在 Codex 会话中可使用内置生图工具补图，配置见 [imagepipe_codex.yaml](../configs/imagepipe_codex.yaml)。该模式由 imagepipe 管理提示词、参考图依赖、图片保存和交付；Codex 读取 `pending` 返回的 `tool_args` 并调用 `image_gen.imagegen`，再用 `accept` 交回生成文件的本地路径。工具最多接收 5 张参考图，更多参考图会按原顺序、原像素横排到最多 5 张输入拼板，在提示词前附上编号映射，原始提示词保存在任务计划中。默认最多同时等待 16 张图片，复用已有图片，流程使用本地文件交换而无需 API 密钥。

```bash
imagepipe run projects/my_drama --provider codex --episodes ep01-ep20 \
  --delivery deliveries/my_drama_ep01-ep20

# 在另一个终端或 Codex 工具中获取已满足依赖的任务
imagepipe pending runs/imagepipe/my_drama/codex/ep01-ep20

# Codex 按任务的 tool_args 调用内置生图后，将对应结果交回系统
imagepipe accept runs/imagepipe/my_drama/codex/ep01-ep20 \
  first-frame-ep01-ep01_s001 /path/to/generated/image.png
```

需要按批启动 Codex CLI 时，准备包含 `run_dir` 和 `remaining_asset_ids` 的交接 JSON；对应请求已保存在运行目录的 `requests/`。以下脚本生成固定的 `jobs.json`、`prompt.md` 和 `command.sh`，默认每个 worker 顺序处理最多 5 张，按 assignment 去重并跳过已有图片或回执。命令固定使用 `gpt-6.1-sol`、`high` 推理、`--enable image_generation`、`approval_policy=never` 和 `danger-full-access`；Python 使用仓库 `.venv/bin/python`。原生工具实际暴露 `quality` 时设置 `high`，当前 schema 未暴露时记录实情。

```bash
.venv/bin/python scripts/prepare_codex_image_jobs.py /data/image_handoff.json \
  --output runs/imagepipe/my_drama/codex/ep01-ep20/cli_workers

# 先启动两个 worker；后续可按同样方式逐对启动
bash runs/imagepipe/my_drama/codex/ep01-ep20/cli_workers/worker_01/command.sh &
bash runs/imagepipe/my_drama/codex/ep01-ep20/cli_workers/worker_02/command.sh &
wait
```

## 可配置的制作参数

在 `--production-config` 指定的 YAML 中设置：

```yaml
comfyui:
  maximum_duration_seconds: 10
media:
  width: 576
  height: 1024
  fps: 24
  upscale_factor: 2
script:
  language: Chinese
  non_diegetic_music: N/A
  on_screen_text: Include story-relevant writing. Subtitles and watermarks follow the editor's delivery requirements.
max_attempts: 3
```

时长上限由部署工作流能力决定，请求上限按 `frame_multiple/frame_offset` 和帧率计算。`max_attempts` 为每镜生成预算，可设置任意正整数；`upscale_factor` 为正整数，默认 2。单句 `dialogue[].language` 和单镜 `non_diegetic_music_en` 可指定各自语言和配乐。

GPT 默认参数为 `quality: max`、`complexity: high`、`native_width/height: 1152/2048`，输出单张不透明 PNG；交付直接复制 API 原图，保留原始尺寸与文件内容。HTTP 并发和在途窗口均为 140，请求超时 900 秒。按账户额度的 70% 平滑发送：105 张/分钟、210 万 TPM；单张预估 20,000 token，返回 usage 超过预估时，后续请求按观测峰值降低发送速率。TPM 是基于估算的调度预算，实际限流以服务端为准。限速在单进程内生效；已有运行继续使用保存的配置。`api.max_reference_images` 默认 GPT 16、Qwen 10；GPT 输入支持 PNG/JPEG/WebP，每张小于 50 MB，prompt 最长 32000 字符。GPT 请求使用 generations 或 edits 接口，省略 Qwen 的 steps/seed 及旧模型的 input_fidelity。每次生成请求调用一次，失败记录后可用 resume 续跑。

同一 GPT 运行内的后续任务优先使用 `originals/` 中的原生参考图；已有资产只有交付图时使用交付图。GPT 和 Qwen 均原样交付；续跑时会用已保存原图恢复旧的缩放交付图。`continuity.auto_scene_anchors` 控制自动空间参考；`continuity.reference_priority` 可按首帧资产 ID 指定参考资产优先顺序。剧本和图像描述决定可见人物、背景群众、姿态与构图。

## 全剧文本、分批补图与交付

集数由 `--episodes` 决定，长剧每集目标时长由 `--episode-minutes` 决定。场景数、镜头数和时长由对白、动作与剧情需要决定。分场写作可以调整计划中的预计镜头数，组装时统一更新镜号和空间锚点，实际范围保存到运行目录的 `assembled_plans/`。以下 64 是调用参数示例。

```bash
EPISODES=64
scriptpipe --source /data/project/source.txt --notes /data/project/editor_notes.md \
  --long-form --episodes "$EPISODES" --episode-minutes 5 \
  --reasoning-effort high --review-reasoning-effort high \
  --output runs/scriptpipe/my_drama --delivery projects/my_drama \
  --production-config configs/b200.yaml

imagepipe run projects/my_drama --episodes ep01-ep10 \
  --config configs/imagepipe.yaml --output runs/imagepipe/my_drama/ep01-ep10 \
  --delivery deliveries/剧本my_drama_ep01-ep10

# 后续批次沿用同一个全剧目录及已经生成的参考图
imagepipe run projects/my_drama --episodes ep11-ep20 \
  --config configs/imagepipe.yaml --output runs/imagepipe/my_drama/ep11-ep20 \
  --delivery deliveries/剧本my_drama_ep11-ep20

videopipe run-season deliveries/剧本my_drama_ep01-ep10 --output runs/video/my_drama/ep01-ep10
```

`--episodes` 同时接受 `1-10`。只为选中集生成首帧及其所需的共享参考、场景锚点和依赖图；同一全剧目录中的人物、服装、场景和道具图直接复用。补图完成后，`--delivery` 导出仅含选中集的索引、剧本、配置和实际图片，保持原有 ID、prompt、seed 和图片内容。全剧 `season.json` / `season_bible.md` 随包保留，供后续衔接。

`projects/my_drama` 保存全剧文本和长期复用的资产；`runs/scriptpipe`、`runs/imagepipe` 保存阶段记录；`deliveries/剧本my_drama_ep01-ep10` 是交给视频端的独立目录。`imagepipe resume runs/imagepipe/my_drama/ep01-ep10` 会续跑补图并完成同一批次交付。调整补图范围时使用对应的新运行目录。

对于仍在连载的原文，可使用现有 `--notes` 明确当前素材的阶段终点、保留的悬念和改编取舍，使全剧规划沿用素材的实际范围。

## 单集、返工与批准

```bash
videopipe run /data/season/episodes/ep01/package.json \
  --config /data/season/episodes/ep01/production.yaml --output /data/runs/episode
videopipe status /data/runs/episode
videopipe resume /data/runs/episode
videopipe retry /data/runs/episode --shot ep01_s003 --feedback "记录返工原因"
# 本轮预算耗尽后，明确开始新一轮：
videopipe retry /data/runs/episode --shot ep01_s003 --new-round
# 仅 human_approval: true 的运行会进入 awaiting_approval：
videopipe approve /data/runs/episode
```

`run` 要求新的输出目录。默认自动交付；`--auto-approve` 可覆盖人工批准配置。`run-season --config CONFIG` 为新建的各集运行统一选配置，已有运行继续使用自身快照。整季按索引顺序执行，未完成时返回非零退出码；每集内部仍并发生成。

## 交接文件

```text
season/
  season.json / season_bible.md     整季结构数据与可读设定
  screenplay.md / quality.json      全季剧本与文字检查结果
  overview.json                     集顺序、package 路径、数量和计划时长
  image_slots.json                  shared_assets + first_frames
  assets/review/                    共享人物、服装、地点与道具图
  episodes/<episode_id>/
    script.md / storyboard.json     单集可读剧本与结构化镜头
    package.json / production.yaml 视频输入与配置
    image_slots.json                slots；共享引用带 source_path
    assets/                         实际首帧与集内审核参考
```

| 输入字段 | 含义 |
| --- | --- |
| `package.title / script / shots` | 标题、剧本文件、按观看顺序排列的镜头；路径相对 `package.json` |
| `shots[].id / prompt` | 稳定镜头 ID、完整有效 H3 prompt；对白按发言顺序使用 `<d>[语言]台词</d>`，默认 Chinese |
| `duration / width / height / fps / seed` | 计划时长与生成规格；内置 H3 要求 24fps、宽高为 32 的倍数 |
| `asset_bindings[]` | `asset_id`、`path`、`role`，可选 `prompt_ref`；所有路径需要真实文件 |
| `role: first_frame` | 内置 I2VA 的唯一首帧；没有首帧时选择 T2VA |
| `role: review_only` | 审核参考；人物、服装、地点和道具先由 imagepipe 合进首帧 |
| `acceptance / parameters` | 可观察的审核要求、推理参数覆盖；文本、seed、尺寸、素材绑定使用专门字段 |
| `image_slots` 中的 `asset_id / path / prompt_en / reference_asset_ids` | 图片任务 ID、写入位置、英文描述、有序引用依赖；`source_path` 表示共享图复制来源 |

旧包的 `reference_images` 仍可读取：第一张映射为首帧，其余为审核参考。旧 `negative_prompt` 在创建视频快照时合入有效 prompt 一次。新包直接提供完整 prompt。自定义 workflow 路径相对配置文件解析。

视频 `shots[].width/height` 控制生成画布，`media.width/height` 控制统一输出基准，再乘 `upscale_factor`。剧本导出读取制作配置的 `media.width/height/fps`，同时写入镜头包和单集配置。默认 B200 为 576×1024、24fps，2 倍超分对应交付 1152×2048。GPT 图片默认 1152×2048 原样交付，作为输入参考时由视频 workflow 处理。

## 到哪里查看运行结果

| 阶段 | 文件 | 看什么 |
| --- | --- | --- |
| 剧本 | `run.json`、`season.json`、`drafts/`；长剧另有 `plans/`、`scenes/` | 当前阶段、缓存设定与镜头稿 |
| 剧本 | `api/`、`checks/`、`reviews/`、`quality.json` | 请求/响应/用量、结构错误、审核意见、最终待修项 |
| 图片 | `tasks.json`、`state.json`、`events.jsonl`、`report.json` | 冻结任务、job ID、引用失败、复用/生成/复制数量 |
| 图片 | `originals/` 与包内资产路径 | 服务原图、统一尺寸后的可用图片 |
| 单集视频 | `input-package.json`、`package.json`、`config.json`、`inputs/` | 原输入记录、有效 prompt 与配置、复制的素材和自定义 workflow |
| 单集视频 | `state.json`、`events.jsonl` | 镜头状态、预算、错误、当前成片版本与耗时 |
| 单集视频 | `shots/<id>/attempt-NNN/` | 参数、workflow、提交 ID、视频、审核请求/抽帧/结果、超分结果 |
| 单集视频 | `shots/<id>/selection.json` | 选中 take、随机候选与降级原因 |
| 单集视频 | `film/version-NNN/` | 草片、实测时间轴 `manifest.json`、`audio/` 中的转写/差异/字幕 |
| 单集视频 | `delivery/version-NNN/` | `final.mp4`、`episode.srt`、`production_report.json` |

整季输出的 `runs/<episode_id>/` 是单集工作目录；`delivery/<episode_id>/` 收集成片、SRT 和报告，`delivery/logs/` 保存精简日志，`summary.json` 汇总状态，`delivery.tar.gz` 打包本次交付文件。收集器可利用已保存的 ASR `worker-result.json` 补全字幕，不重新推理。

缺图查包内绑定路径；图片失败查 `state.json` 的任务错误；视频停在 `needs_attention` 查镜头状态与 attempt 记录；审核降级和字幕粗对齐查生产报告。具体分支见 [工作流](workflow.md)。
