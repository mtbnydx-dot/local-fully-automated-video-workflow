# 生产流程

本文按当前代码说明 `scriptpipe`、`imagepipe`、`videopipe` 的输入、执行顺序、分支和产物，供阅读、运行与修改代码时对照。三个 CLI 独立启动，通过磁盘文件交接；前一段完成后，由调用方启动下一段。

| 阶段 | 读取什么 | 交给下一段什么 |
| --- | --- | --- |
| `scriptpipe` | 原文、可选 `--notes`、写作参数、导出用的视频配置 | 整季设定、逐集剧本与镜头包、图片槽位、各集 `production.yaml` |
| `imagepipe` | 整季或单集目录中的 `image_slots.json`、季风格、图片配置 | 写入槽位路径的共享参考图和镜头首帧；单集目录中的参考图副本 |
| `videopipe` | 单集 `package.json`、其中引用的剧本与图片、视频配置；整季运行另读 `overview.json` | 成片、独立 SRT、生产报告；整季运行还收集汇总与日志压缩包 |

以下生成与审核流程以默认的 Ark DeepSeek、图片任务 API、ComfyUI / vLLM 后端为主。视频另有 CPU 后端：生成参考图缩放预览，审核检查媒体信息和抽帧解码，供本地流程验证。服务地址与模型由配置决定。写作参数来自 CLI 和代码中的 brief；`--production-config` 只决定导出的视频配置。

## scriptpipe：原文到剧本包

```mermaid
flowchart TD
    S0["原文 + 可选 notes + CLI 参数"] --> S1["清理嵌入的 MediaWiki CSS<br/>保存 source.cleaned.txt，构造写作 brief"]
    S1 --> S2["LLM 整季规划，或读取已有 season.json<br/>人物、服装、地点、道具、分集状态"]
    S2 --> S3{"写作模式"}
    S3 -->|短剧| S4["并发写各集分镜<br/>保存或复用 drafts"]
    S4 --> S5["代码结构检查 + LLM 整季文字审核"]
    S5 --> S6{"有 error 且仍有修正轮数？"}
    S6 -->|是| S7["按问题修正相关集<br/>合并指定镜头的补丁"]
    S7 --> S5
    S3 -->|长剧| SO["按本集 source_ranges 取原文<br/>每集独立创作开场，保存 openings"]
    SO --> S8["该集开场完成后，P2 接着续写正文<br/>保存 plans，程序合并两段 events"]
    S8 --> S9["按本场定稿与相关资产设计视听<br/>首镜完整承载开场，生成首帧与配乐"]
    S9 --> S10["程序回填台词、服装与中文事件<br/>编号、检查并合并各集 drafts"]
    S10 --> S11{"long-review 模式"}
    S11 -->|off 默认| S15
    S11 -->|report| S12["P4 每集一次 + P5 整季一次<br/>保存诊断报告"]
    S6 -->|否| S15["汇总最终检查与审核记录"]
    S12 --> S15
    S15 --> S16["导出剧本、图片槽位、镜头包和视频配置<br/>保存 quality.json 与运行状态"]
    S16 --> S17["图片待生成<br/>交给 imagepipe"]
```

### 写作与检查

短剧默认 12 集，长剧默认 8 集，由 `--episodes` 配置。长剧每集目标分钟数由 `--episode-minutes` 配置（默认 5），包含开场时长。长剧每集先写独立开场，P2 只写开场之后的正式事件；程序合并两段，P3 把开场完整放入首个片段并安排后续视听。场景数量与正文片段数量由内容决定，组装时统一编号并更新锚点和实际场次范围，保存到 `assembled_plans/`。长短剧共用制作配置的 `comfyui.maximum_duration_seconds`，默认 10 秒；按当前 24fps、5+17n 帧对齐，brief 中请求上限为 9.4 秒。开场请求时长范围为 5 秒至单次请求上限与 10 秒的较小值。视频交付使用生成结果的实测时长。

代码检查覆盖字段类型、非空说明、唯一 ID、人物/服装/地点/道具引用和配置中的工作流时长上限。对白按发言顺序记录，可有多轮、多位说话者，长度和语速由创作决定。长剧从 events 解析逐字对白与中文动作，旧短剧仍使用原动作说明字段；英文描述可引用剧情需要的中文专名或文字。LLM 文字审核依据实际对白、动作、因果和连续性提出问题。

修正与请求重试有三种计数：

| 机制 | 当前行为 |
| --- | --- |
| 文字审核后的局部修正 | 短剧的 `--repair-rounds` 默认 2。长剧默认关闭 LLM 审核，`--long-review report` 只生成一次报告 |
| 长剧结构校正 | 开场、分集正文与分场视听各最多生成 3 次，携带上一版结构错误再请求；仍有结构错误则抛出异常，运行记为 `failed` |
| LLM 请求重试 | 每次 `complete` 最多请求 3 次，处理 HTTP、输出截断、JSON 等错误；请求、响应、用量和错误保存到 `api/` |

短剧局部补丁替换指定的已有镜头，可更新集标题、梗概、开始/结束状态，审核循环只因 `severity=error` 触发。长剧采纳诊断意见后，在对应 P1、开场、P2 或 P3 创作源修改并重建下游；独立 P6 修补 prompt 已移除。

### 导出、状态与续跑

导出器将人物、服装、镜头内容、声音描述和对白编译为 H3 prompt；对白按顺序写入 `<d>[语言]原台词</d>`，长剧从开场与 P2 的正式原文及 `script.language` 装配，旧格式可按句指定 `language`。长剧 P3 每镜填写 `non_diegetic_music_en`，缺省配乐和画面文字要求来自 `script` 配置。每镜绑定一张 `first_frame`，人物、地点、道具参考绑定为 `review_only`。导出只创建文本、清单与资产目录，图片文件由后续阶段写入。

| 位置 | 主要内容 |
| --- | --- |
| 剧本运行目录 | `run.json`、`source.cleaned.txt`、`season.json`、`drafts/`、`reviews/`、`quality.json`、`api/`；长剧另有 `source.paragraphs.json`、`creative_brief.json`、`openings/`、`plans/`、`scenes/`、`checks/`、`assembled_plans/`、`rejected/`、`review_inputs/` 等阶段记录 |
| 导出根目录 | `overview.json`、`season.json`、`season_bible.md`、`screenplay.md`、`image_slots.json`、`quality.json` |
| `episodes/<集ID>/` | `script.md`、`storyboard.json`、`package.json`、`image_slots.json`、`production.yaml` |

完成检查且导出成功后，`run.json.status` 为 `text_ready` 或 `needs_text_revision`，未消除的错误列在 `quality.json.open_errors`。导出索引相应为 `text_complete_images_pending` 或 `needs_text_revision_images_pending`，`render_ready` 初始为 `false`；文字审核仍有错误时，代码也会导出可导出的包并保留这些记录。

`scriptpipe` 没有单独的 `resume` 子命令，重新使用同一输出目录运行会复用阶段文件。短剧复用已有 `season.json` 和 `drafts`，重新进入审核；长剧会检查缓存的开场、正文和分场结果，并在审核输入与保存的输入相同时复用对应审核。长剧支持 `--stop-after source|season|openings|plans|drafts|review`；`openings` 保存各集开场后停止，`review` 在写完 `quality.json` 后、导出前停止。短剧导出到 `<output>/delivery`；长剧可用 `--delivery` 指定交接目录。

代码依据：[入口](../scriptpipe/cli.py)、[短剧流程](../scriptpipe/pipeline.py)、[长剧流程](../scriptpipe/long_pipeline.py)、[通用检查](../scriptpipe/checks.py)、[长剧检查](../scriptpipe/long_checks.py)、[导出](../scriptpipe/export.py)、[LLM 请求](../scriptpipe/llm.py)。

## imagepipe：图片槽位到实际资产

```mermaid
flowchart TD
    I0["整季或单集目录 + 图片配置"] -->|新计划| I1["读取槽位与季风格"]
    I1 --> I2["确定母图、派生图、首帧引用<br/>检查缺失引用、循环和参考数量"]
    I2 --> I3{"任务目标文件已存在？"}
    I0 -->|已有运行| I17["恢复 tasks.json 中的计划和配置"]
    I17 --> I3
    I3 -->|是| I4["直接记为 completed"]
    I3 -->|否| I5["等待本任务的参考图任务结束"]
    I5 --> I6{"参考图均 completed？"}
    I6 -->|否| I7["本任务 blocked<br/>独立任务继续"]
    I6 -->|是| I16["取得在途窗口，持有至本任务结束"]
    I16 --> P{"图片后端"}
    P -->|GPT，默认| G["复用已保存原图<br/>或等待 generations / edits 返回"]
    G -->|成功| G1["保存 base64 原图、request ID 和 usage"]
    G -->|请求异常| I11
    G1 --> D["原文件复制交付"]
    P -->|Qwen| I8["恢复已有 job_id<br/>或提交并保存 job_id"]
    I8 --> I9["轮询远端任务"]
    I9 -->|排队或执行中| I9
    I9 -->|failed 或 cancelled| I10{"提交次数仍小于 max_attempts？"}
    I10 -->|是| I8
    I10 -->|否| I11["任务 failed"]
    I9 -->|completed| I12["取第一个结果，下载到 originals"]
    I8 -->|提交异常| I11
    I12 -->|下载或交付失败| I11
    I12 --> D
    D -->|交付失败| I11
    D --> I13["写入槽位路径，任务 completed<br/>后续依赖可继续"]
    I4 --> I14["所有任务结束后<br/>复制共享参考图到单集路径"]
    I7 --> I14
    I11 --> I14
    I13 --> I14
    I14 --> I15["保存 state / events / report<br/>图片齐备后交给 videopipe"]
```

### 依赖与生成模式

整季输入从 `shared_assets` 和 `first_frames` 建任务；单集输入从 `slots` 建任务，并可从上级季目录补入缺少的母图依赖。依赖规则如下：

| 图片类型 | 引用与生成方式 |
| --- | --- |
| 人物母图 | 资产目录中同一 `character_id` 首个出现的槽位；使用 scriptpipe 导出的清单时，对应该人物第一套服装 |
| 其他服装 | 自动把该人物母图加到参考列表首位；沿用清单和配置中的其他引用 |
| 地点、道具 | 读取清单中的引用；导出器将 `reference_prop_ids` 转为道具资产引用，可形成道具派生关系 |
| 镜头首帧 | 组合槽位中的人物、地点、道具引用；`continuity.sets` 可指定某张首帧作为同组其他首帧的布景锚点，`additional_reference_assets` 可补充引用 |

引用去重后按重要性排序，取 `api.max_reference_images` 配置的数量（GPT 默认 16、Qwen 默认 10）。剧本的 `reference_priority` 按人物、地点或道具 ID 指定重要性，图片配置的 `continuity.reference_priority` 可按首帧资产 ID 指定参考资产顺序；其余引用保留原有顺序。排序后的列表对应实际上传和 prompt 中的编号。GPT 无引用走 `/v1/images/generations`，所有有引用任务走 `/v1/images/edits`，按顺序上传 `image[]`；Qwen 保留原 jobs、edits、references 接口。每个任务请求 `n=1`，沿用原有图片交付流程。

### 调度、尺寸与恢复

GPT 默认 HTTP 并发和在途窗口均为 140，请求超时 900 秒。按账户额度的 70% 平滑发送：105 张/分钟、210 万 TPM；单张预估 20,000 token，返回 usage 超过预估时，后续请求按观测峰值降低发送速率。TPM 是基于估算的调度预算，实际限流以服务端为准。限速在单进程内生效；已有运行继续使用保存的配置。一个任务的依赖完成并落盘后即可推进；使用本运行的原生参考图，有待交付原图时直接继续交付。每次生成请求提交一次，保存 request ID、usage 和原图；请求异常记录为失败，resume 从已保存的结果继续。目标文件已经存在时直接复用。

Qwen 的 HTTP 并发为 16、在途窗口为 64、轮询间隔为 5 秒。远端任务 `failed` / `cancelled` 时清除 job ID，在 `max_attempts`（默认 3）内重新提交；查询、结果读取和下载另有 HTTP 重试。提交异常会记录为任务失败。存在 job ID 时续跑继续查询该任务。

图片按 API 返回尺寸原样交付。GPT Image 2.6 Sunburst 使用 `quality=max`、`complexity=high`，原生尺寸由 `native_width/native_height` 设置，默认 1152×2048；prompt 画布同步使用原生尺寸。Qwen 按 `generation.width/height` 向上对齐 32 像素且至少为 256，默认请求 736×1280，保留 steps/seed。原图保存后，交付器直接复制文件，保留像素、色彩模式和元数据；续跑时用已保存原图恢复旧的缩放交付图。图片尺寸与视频镜头的生成画布分别配置。

运行目录保存 `tasks.json`（最终 prompt、引用、seed、路径、后端及配置）、`state.json`、`events.jsonl`、`originals/` 和 `report.json`。seed 仅随 Qwen 请求发送。`imagepipe resume <运行目录>` 读取保存的计划和配置，旧记录按 Qwen 恢复；再次 `run` 到已有 `tasks.json` 的目录也会复用它们，并核对后端、包目录和集范围。所有生成任务 `completed` 且参考图复制无缺项时，报告的 `success` 才为 `true`。

图片阶段写入资产与自身运行记录，全剧目录保留文字导出的状态快照。指定 `--episodes ep01-ep10 --delivery <批次目录>` 时，只处理这些集的首帧及引用依赖，再复制成独立视频输入包；后续批次复用全剧目录中的已有图片。批次清单标记 `images_ready`；全剧仍有待修文字问题时保留相应状态。交接时查看图片运行报告及槽位文件；视频入口会检查所引用的文件是否存在。具体命令见 [分批运行](usage.md#全剧文本分批补图与交付)。

代码依据：[入口](../imagepipe/cli.py)、[依赖计划](../imagepipe/plan.py)、[调度与恢复](../imagepipe/pipeline.py)、[接口](../imagepipe/client.py)、[图片交付](../imagepipe/delivery.py)、[配置模型](../imagepipe/models.py)。

## videopipe：镜头包到视频、字幕和报告

```mermaid
flowchart TD
    V0["package.json + 剧本 + 图片 + 视频配置"] --> V1["校验输入，建立运行目录与快照<br/>resume 则读取已保存的输入和状态"]
    V1 --> V2["按镜头状态调度"]
    V2 -->|有预算且需新 take| V3["累计 attempts 和本轮 budget_used 加一<br/>按累计次数计算 seed，保存状态"]
    V3 --> V20["ComfyUI 生成或查询已提交的任务<br/>图生视频先把首帧居中裁切到镜头画布"]
    V2 -->|已有生成任务| V20
    V2 -->|待审核 take| V4["抽帧 + 剧本、要求、参考图<br/>单镜画面审核"]
    V20 -->|可解码输出| V4
    V20 -->|生成失败，非轮询超时| V5{"本轮还有生成预算？"}
    V20 -->|轮询超时| V6["保存服务器任务 ID<br/>等待 resume 查询同一 take"]
    V4 -->|通过| V7["选中当前 take"]
    V4 -->|有明确生成问题| V5
    V4 -->|审核不可用| V8["从本轮已有可用 take 随机选择<br/>保存候选、选择 seed 与原因"]
    V2 -->|无选片且预算已耗尽| V8
    V5 -->|有| V3
    V5 -->|耗尽| V8
    V8 -->|有候选| V7
    V8 -->|无候选| V9["镜头 missing"]
    V7 --> V10["逐片超分或缩放，统一媒体格式<br/>记录实测时长，镜头 ready"]
    V2 -->|已有选片| V10
    V2 -->|镜头已 ready| V11{"任务结束后全部镜头 ready？"}
    V10 --> V11
    V9 --> V11
    V6 --> V11
    V11 -->|否| V12["needs_attention<br/>检查记录后 resume 或 retry"]
    V11 -->|是| V13["按镜头顺序拼接 draft<br/>保存实测时间轴 manifest"]
    V13 --> V14["ASR：启用时启动本地子进程<br/>complete / disabled / unavailable"]
    V14 --> V15["从有效 prompt 提取原台词生成 SRT<br/>ASR 匹配时间，未匹配部分用剧本时间窗"]
    V15 --> V16["有完整转写时进行文字台词比对<br/>保存音频、字幕和差异记录"]
    V16 --> V17{"human_approval 且未指定 auto-approve？"}
    V17 -->|是| V18["awaiting_approval<br/>等待 approve 或带 auto-approve 的 resume"]
    V17 -->|否| V21{"subtitles.burn 开启且有对白？"}
    V18 -->|收到批准| V21
    V21 -->|是| V22["SRT 排版为 episode.ass<br/>每条至多 max_lines 行，位于画面下方三分之一"]
    V22 --> V19["CPU 最终编码 final.mp4<br/>libx264，线程数取 media.finalize_threads<br/>有 ASS 时同一次编码烧录字幕<br/>复制 SRT + 写生产报告<br/>complete"]
    V21 -->|否| V19
```

图中展开镜头生产与完整交付路径；续跑时会按保存的状态跳过已完成阶段，例如已有草片、音频记录、批准或最终交付。

### 输入、生成与画面审核

`validate` 检查输入格式、ID、引用文件、参数覆盖限制和自定义 workflow 的 API 格式；内置或识别为 H3 的 workflow 还要求 24fps、宽高可被 32 整除。`run` 校验后创建新目录，保存原始包记录、有效 `package.json`、`config.json`，并复制剧本、图片和自定义 workflow 到 `inputs/`。旧格式 `negative_prompt` 在此时合入有效 prompt；旧格式 `reference_images` 的第一张转为首帧，其余转为审核参考。

生成器只把 `first_frame` 资产上传给内置图生视频 workflow；没有首帧时选择文生视频 workflow，`review_only` 图片用于审核。H3 节点把首帧直接拉伸到画布，所以内置 workflow 先用 `ImageScale` 把首帧居中裁切并缩放到镜头画布，再交给 H3；任意比例的首帧都保持人物比例，与 CPU 预览的裁切方式一致。H3 帧数按配置对齐，默认满足 `5 + 17n`，5.875 秒、24fps 对应 141 帧。脚本导出的镜头画布、帧率和超分设置读取制作配置；默认 B200 为 576×1024、24fps，使用默认 B200 的 2 倍超分时，最终画布为 1152×2048。

每镜每轮 `max_attempts` 默认为 3，可配置为任意正整数。创建 take 时先保存预算，累计 `attempts` 不归零；第 N 个 take 使用 `shot.seed + N - 1`。生成沿用快照中的 prompt 和资产，审核结果及人工 feedback 不改写生成文本。

生成与超分共用线程池和 ComfyUI 实例队列；审核使用单独线程池。生成完成后释放实例，审核期间可生成其他镜头；选片后优先安排该 take 的超分。B200 配置使用 7 个生成 worker、6 个审核 worker。

画面审核当前默认为 **48 帧、最长边 1024**，代码配置模型和 B200 YAML 一致。调用方显式传入这两个配置值；底层 `sample_frames()` 函数的 8 帧 / 640 默认参数不是生产调用的实际默认值。帧按视频等长区间的中点取样，Qwen 接收时间戳、剧本、镜头 prompt、验收要求和参考图。

只有有效结果中关联已知镜头、具有时间戳的 `generation` 问题会使审核不通过；`editing` 或没有时间戳的观察转为 warning。passed 由分类后的有效问题重新计算。未知镜头、空问题说明、不符合格式的响应以及服务错误会记为审核不可用。自动画面审核范围是单镜；主流程没有整片自动画面审核循环。

审核通过选中当前 take；审核不可用或本轮预算耗尽时，从本轮已经生成并经媒体检查得到 `source` 的 take 中随机选取，记录 `reason`、候选列表和随机 seed。没有候选则镜头为 `missing`。轮询超时保留 ComfyUI 的 `prompt_id` 和服务地址，续跑继续该任务；超分失败保留选片记录，续跑可继续超分。未捕获到审核结果的执行异常等也可能留下 `failed` 镜头；任务调度结束后，只要有镜头未 `ready`，本集即为 `needs_attention`。

### 媒体、ASR、台词比对与字幕

选中的片段按 `media.upscale` 处理：`comfyui` 调用超分 workflow；`none` 直接规范化；`lanczos` 配置走本地媒体缩放路径。统一画布使用 `media.width/height`，超分未关闭时乘以 `upscale_factor`。内置超分图保留输入音轨和帧率，FFmpeg 规范化保留实测时长，统一帧率、画布与音频格式，无音轨时补静音。全部镜头 ready 后按包内顺序拼接，`manifest.json` 保存各片段的起点、实测时长及选片原因。

内置 H3 workflow 生成视频与音轨，后续流程没有独立 TTS 配音或对白替换步骤。音频处理在拼接后执行，顺序是 **ASR → 字幕 → 台词文字比对 → 保存音频记录**：

| 环节 | 当前行为与记录 |
| --- | --- |
| ASR 调用 | `asr.enabled` 默认为 `true`，CPU 后端默认关闭。每次处理一个草片，由独立 Python 子进程加载本地 faster-whisper；默认模型 `large-v3`、GPU 7、`int8_float16`、超时 600 秒，语言默认自动识别 |
| ASR 执行 | 子进程用 `CUDA_VISIBLE_DEVICES` 选择 GPU，设置离线模式，模型以 `local_files_only=True` 加载；单输入转写开启词级时间戳和 VAD。子进程结束后其模型资源随进程释放 |
| ASR 返回 | 成功为 `complete`；关闭为 `disabled`；缺依赖、缺模型、超时、进程失败或结果校验失败为 `unavailable`，继续后续交付。无效句时间戳跳过；无效词时间戳回退到句时间戳；非空结果中所有句时间戳都无效时记为不可用 |
| 字幕正文 | 从运行快照中的有效 `shot.prompt` 提取 `<d>…</d>`，去掉语言前缀及 `scenetrans` / `cutoff` 指令标记，保留原台词文字和标点；不从画面说明推断对白，也不以 ASR 文本替换正文 |
| 字幕时间 | 用实测片长建立镜头时间窗。在窗内按顺序匹配归一化后的 ASR 词或整句；匹配的台词使用识别时间并裁到镜头窗内。其余台词按有效字符/词数量分配到整镜或相邻匹配台词之间；空间不足时整镜回退到剧本计时 |
| 字幕报告 | `subtitles.json` 记录匹配与回退条目，`timing` 为 `asr`、`script`、`mixed` 或 `none`；没有对白时状态为 `no_dialogue`，仍写出空 SRT |
| 字幕烧录 | `subtitles.burn` 开启且有对白时，交付按 SRT 生成 `episode.ass`：台词先按标点分成短语，整短语装入不超过 `max_lines` 行的字幕条，单个短语超过时才在短语内分条，时间按字数分配；行数最少、行宽均衡、优先在标点后换行。字号 `size` 为单个汉字高度占画面高度的比例，行宽占画面 80%，白字黑边、底部居中，满 `max_lines` 行时字幕块顶边落在画面下方三分之一线上；默认字体为随包提供的 Noto Sans CJK SC Bold |
| 台词文字比对 | 转写为 `complete` 时，vLLM / Qwen 接收预期对白及 ASR 的句段文本和时间，返回 `matches`、`summary`、`differences`。没有完整转写或比对服务不可用时记录 `available=false`；CPU reviewer 不调用语言模型比对 |

ASR 状态、字幕计时方式与台词差异用于报告，不触发视频返工，也不决定批准。当前版本已经保存 `state.audio` 时，`resume` 会跳过音频处理；`retry` 清除下游音频状态，重新拼接后再处理。中断发生在音频状态保存之前时，续跑可能再次执行该阶段。

### 批准、返工与整季交付

默认 `human_approval=false`，音频记录写完后自动交付；设为 `true` 且未传 `--auto-approve` 时进入 `awaiting_approval`。`approve` 只接受该状态。交付在 CPU 上进行最终 H.264/AAC 编码（libx264；B200 没有视频编码单元），写入 `final.mp4`、独立的 `episode.srt` 和 `production_report.json`。开启 `subtitles.burn` 时同一次编码用 libass 把 `episode.ass` 烧录进画面，`delivery.burned_subtitles` 记录结果；无字幕版本即 `film/version-NNN/draft.mp4`。

| 操作 | 实际作用 |
| --- | --- |
| `resume <运行目录>` | 读取输入与配置快照及状态；跳过 ready 镜头，继续已记录的生成任务、待审核 take、已选 take 的超分或后续拼接与交付；保留预算 |
| `retry <运行目录> --shot ID` | 重置指定镜头的选片及片段状态，使用本轮剩余预算；预算耗尽则拒绝该请求。其他镜头复用，清除当前草片、音频、批准和交付指针，后续生成新成片版本 |
| `retry … --new-round` | 指定镜头的 `round` 加一、`budget_used` 归零，累计尝试和旧产物保留；随机选片候选限于新一轮 |
| `--feedback` | 写入返工状态和事件，不修改快照中的生成输入 |
| `status` / `complete` | `status` 输出保存的状态；`complete` 表示交付已完成，选片原因、审核是否可用、ASR 和台词差异分别查看报告 |
| `run-season` | 按 `overview.json.episodes` 顺序逐集执行，集内并发；读取各集配置或使用指定覆盖配置。已有运行从快照恢复，已完成集跳过，某集异常后继续其余集，结束时调用交付收集 |
| `collect` | 从已有运行记录收集视频、SRT、报告和日志；用保存的剧本、实测时长与 ASR 结果重建字幕，并更新相应记录，无需调用模型 |

单集运行记录位于 `state.json`、`events.jsonl`、`shots/<镜头ID>/attempt-NNN/` 和 `shots/<镜头ID>/selection.json`。草片、时间轴及音频记录位于 `film/version-NNN/`，其中 `audio/` 按实际执行情况保存转写、子进程输出、字幕与比对记录；交付位于 `delivery/version-NNN/`。新成片版本保留旧版本文件。

整季运行将单集工作目录放在 `runs/<集ID>/`，收集结果为 `delivery/<集ID>/final.mp4`、`episode.srt`、`production_report.json`，另有 `summary.json`、`summary.md`、`logs/` 和同级 `delivery.tar.gz`。全部集完成才将汇总状态记为 `complete`，否则为 `incomplete`，各集状态和错误保留在汇总中。

代码依据：[CLI](../videopipe/cli.py)、[输入与快照](../videopipe/inputs.py)、[状态机](../videopipe/pipeline.py)、[配置模型](../videopipe/models.py)、[ComfyUI](../videopipe/backends/comfyui.py)、[审核与台词比对](../videopipe/backends/review.py)、[媒体](../videopipe/media.py)、[ASR](../videopipe/backends/asr.py)、[字幕](../videopipe/subtitles.py)、[整季编排](../videopipe/season.py)、[交付收集](../videopipe/delivery.py)。

代码模块与服务协作见 [架构](architecture.md)，具体命令和输入示例见 [使用](usage.md)，环境与模型准备见 [部署](deployment.md)。
