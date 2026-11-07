# 自动化与 API 使用指南

面向接手本平台的 AI 助手、脚本作者和维护者。本文只说明接口与执行约束，不提供内容创作指导。人工操作见[使用教程](BEGINNER_FRONTEND_GUIDE.md)，图与数据流见[技术架构](TECHNICAL_ARCHITECTURE.md)。

整理日期：2026-10-28。接口以当前运行服务的 `/openapi.json` 为准，运行版本查 `GET /api/health`。不要把源码版本当作进程已更新的证据。

## 1. 操作边界

- 优先调用本平台 API，保留模型解析、预检、任务记录和输出管理；不要无故绕过平台直接提交 ComfyUI `/prompt`。
- 未获 GPU 授权时，不启动 ComfyUI、不生成、不卸载模型，也不运行会触发硬件探测的环境/预检接口。
- 更新 ComfyUI、安装依赖、删除文件、取消任务、释放显存和付费云端请求分别需要适当授权。
- 队列为空不等于 GPU 空闲；平台不负责自动关闭 vLLM 等外部服务。
- 远程 AI 的 `127.0.0.1` 不是用户电脑。必须有实际可达、受控的平台地址。
- 不把 token、素材内容、本地配置或历史输出纳入 Git 发布。

## 2. 连接与认证

默认平台地址为 `http://127.0.0.1:7860`，ComfyUI 常见地址为 `http://127.0.0.1:8188`。两者不是同一 API。

局域网脚本根据部署配置使用 `X-Local-AI-Token` 或 `Authorization: Bearer ...`。令牌应来自安全环境变量，不在命令历史/文档中硬编码。不要把查询参数带 token 的媒体或事件 URL 当作公开分享链接。

服务端应能访问自己的 ComfyUI 文件。仅更换 `COMFY_URL` 不等于远程文件已经可读。

## 3. 接口地图与副作用

| 接口 | 用途 | 边界 |
| --- | --- | --- |
| `GET /api/health` | 版本和进程基本信息 | 已运行服务的轻量查询 |
| `GET /api/video-params` | 视频模式、能力和参数 schema | 不依赖 ComfyUI 生成 |
| `GET /api/social-presets` | 发布配方 | 不执行发帖 |
| `GET /api/jobs` | 平台任务列表 | 已保存状态，可能不是最新推理状态 |
| `GET /api/jobs/{id}?refresh=false` | 单任务快照 | 不主动刷新推理生命周期 |
| `GET /api/jobs/{id}` | 刷新任务 | 默认 refresh=true，收尾可能触发配置允许的模型释放 |
| `GET /api/jobs/{id}/events` | SSE 事件流 | 同样会刷新生命周期 |
| `GET /api/environment`、`/api/bootstrap` | 运行时和环境 | 可能探测硬件，不当作禁止 GPU 阶段的纯静态检查 |
| `GET /api/workflow` | 动态建图与预检 | 查询运行时并做硬件相关校验，不直接生成 |
| `POST /api/generate` | 提交视频生成/支持的后期 | 表单，可能占用 GPU 或调用云端 |
| `POST /api/jobs/{id}/cancel` | 取消特定任务 | 写操作，只处理获授权的任务 |
| `GET /api/image-studio/workflow` | 图片预检 | 用图片 schema，不照抄视频字段 |
| `POST /api/image-studio/generate` | 图片生成/编辑 | 表单，多图任务可能对应多个 prompt |
| `GET /api/outputs`、`/api/view` | 作品列表与媒体 | 遵守媒体路径与访问控制 |
| `POST /api/bootstrap/full-setup` | 一键准备 | 真实安装，可能尝试启动 ComfyUI |
| `POST /api/video-smoke-test` | 生成链路测试 | 会提交实际生成，不是静态验证 |

检查配置时先确定是否允许资源探测；不要仅根据 HTTP 的 GET/POST 方法判断是否无副作用。

## 4. 视频请求契约

### 三种身份

安装 profile、运行 `model_profile`、`mode` 是不同概念。先从当前目录、界面和 schema 获取正确 ID。

| 任务 | mode | model_profile |
| --- | --- | --- |
| H3 T2V | `minimax_h3_t2v` | `minimax_h3_fl2va_int8_t2v` |
| H3 I2V | `minimax_h3_i2v` | `minimax_h3_fl2va_int8_i2v` |
| H3 Ref2VA | `minimax_h3_r2v` | `minimax_h3_ref2va_int8_r2v` |
| LTX 2.5 INT8 T2V | `ltx25_t2v` | `ltx25_distilled_int8_t2v` |
| LTX 2.5 INT8 I2V | `ltx25_i2v` | `ltx25_distilled_int8_i2v` |

不要依赖默认 mode，尤其不要把新导入的模型文件名当成 profile ID。

### 提交格式

`POST /api/generate` 使用表单；带文件时用 `multipart/form-data`，不是整个 body 直接传 JSON。

| 类别 | 字段 |
| --- | --- |
| 基础 | `mode`、`model_profile`、`prompt`、`negative`、`width`、`height`、`length`、`fps`、`seed`、`steps`、`cfg`、`project` |
| 高级 | `advanced`：JSON 字符串 |
| 首尾帧 | `image`、`end_image` 文件 |
| Ref2VA | 可重复的 `reference_media` 文件 |
| H3 控制 | `h3_control_video` 文件 |
| H3 重绘 | `h3_source_video`、`h3_mask` 文件 |
| 现有视频后期 | `video` 文件，或合法的 `source_video_filename/subfolder/type` |
| 多片拼接 | `clips` 文件列表；具体参数由该工具 schema 决定 |

同一个来源不要同时传互相冲突的上传与已存文件引用。返回的媒体引用应完整保留，不能自己猜绝对路径。

### 高级参数示例

以下只是 FL2VA 原生基线参数，不会自动执行任务。把它序列化为 `advanced` 字符串：

```json
{
  "h3_acceleration_profile": "native",
  "h3_attention_backend": "pytorch",
  "h3_task": "generate",
  "h3_latent_upscale": false,
  "sampler_name": "res_multistep",
  "scheduler": "simple",
  "h3_shift_video": 12.0,
  "h3_shift_audio": 3.0,
  "denoise": 1.0,
  "h3_audio": true
}
```

同时显式设置所需 steps；Ref2VA 原生 scheduler 使用 beta，不能直接复制 FL2VA 示例。其他档位以 `/api/video-params` 返回的字段和默认值为准。

## 5. 预检与提交顺序

1. 读取运行版本、参数 schema 和已有任务，避免重复提交。
2. 构造明确的模式、尺寸、帧数和高级参数。
3. 调用 `GET /api/workflow`，使用与提交一致的设置。
4. 按真实素材设置 `has_image`、`has_end_image`、`has_reference_media`、`has_h3_control_video`、`has_h3_source_video`、`has_h3_mask`、`h3_mask_is_video`。
5. 检查 `ok`、`errors`、`risk_checks` 和标准化后的 `parameters`；`include_graph=true` 可返回实际图。
6. 预检失败停止；不要用反复 POST 来试错。
7. 预检通过且已获推理授权，再提交一次表单及素材。
8. 保存返回 `id`、`prompt_id` / `prompt_ids` 与请求参数。

预检的 has_* 只声明存在性，上传后的时长/尺寸校验仍会执行。H3 控制素材覆盖对齐后的帧数；重绘遮罩与原片同宽高。组合限制见[模型原理](MODEL_WORKFLOWS.md)。

客户端应把提交视为有副作用且不可盲目重试。当前接口没有对所有外部请求统一保证的幂等键；网页防双击不等于网络层 exactly-once。

## 6. 任务跟踪与失败恢复

任务列表：

```text
GET /api/jobs?status=active&project=PROJECT&limit=20&offset=0
GET /api/jobs/JOB_ID?refresh=false
```

项目值需要 URL 编码。当前列表结果使用 `items` 与 `count`；状态筛选包括 `active`、`success`、`failed`、`video`、`all`，先筛选后分页。

授权执行阶段可用 SSE 或每 5–10 秒刷新任务。终态判断必须包含 status 和 media，不能只看 completed：

- success 且有预期媒体：下载/打开输出，进一步验收。
- failed/error/canceled 等：记录错误与已有部分结果，不继续后期。
- 连接中断或结果未知：先用原 job ID、prompt ID 查任务和 ComfyUI 历史，再决定是否重试。

ComfyUI `/queue`、`/history/{prompt_id}` 可协助排查，但不应清空整个队列。一个图片任务可能部分成功，保留已生成内容，不把“0 张显示”直接等价为“没有任何执行”。

刷新任务可能触发配置允许的显存释放；严格只读阶段使用 `refresh=false`。不要调用 `/free` 或重启服务来代替错误定位。

## 7. 图片 API 的区别

图片提交使用 `profile`，而非视频的 `model_profile`。先看 `/api/image-studio` 和 `/openapi.json` 的结构；它们不是视频字段的别名。

| 用途 | 主要字段 |
| --- | --- |
| 文生图 | `profile`、`prompt`、`width/height`、`seed`、采样设置 |
| 单图/批量 | `generation_mode`、`batch_size`，按该模型能力 |
| 已有图编辑 | `edit_mode=true`、`source_image` 或有效源图引用 |
| 附加参考 | 重复 `reference_images` 文件字段 |
| 特定编辑强度 | 按该模型编辑 schema；不要当所有模型都支持同一种 denoise |

Qwen 2.1 目标图加附加参考最多 10 张。部分 profile 只支持编辑，缺源图不能生成。保存图片返回的 job ID，使用统一任务接口跟踪；文件历史与输出位置通过图片工作台接口查询。

## 8. 自动化后期与结果交付

网页的自动后期依赖浏览器保持打开，不是可靠的服务端批处理队列。脚本要做长批次时，应自行：

1. 保存源素材、请求快照与每一步 job ID。
2. 只在上一步明确成功时提交下一步。
3. 使用刚得到的媒体引用和实际元数据作为新输入。
4. 对未知状态停下来核对，不直接重放整个链路。
5. 区分可重试网络错误、不可重试参数错误和需要人工确认的输出质量问题。

输出验收：文件可完整解码；宽高、FPS、时长、音轨符合请求；无明显黑帧或异常裁切。中文文件名用于交付副本，保留原始索引。不得宣称仅凭预检就完成了真实生成验证。

## 9. 维护定位

| 要改什么 | 首先看 |
| --- | --- |
| 模型和安装来源 | `beginner_frontend/model_catalog.py` |
| 视频参数与 H3 配方 | `beginner_frontend/video_params.py` |
| 视频图与请求路由 | `beginner_frontend/app.py` |
| H3 扩展 | `beginner_frontend/h3_workflows.py` |
| 图片图与编辑能力 | `beginner_frontend/image_studio.py` |
| 浏览器素材和后期链 | `static/workflow-state.js`、`static/app.js` |

接口和状态逻辑的离线检查见[维护与验证](TECHNICAL_ARCHITECTURE.md#10-维护与验证)。在禁止 GPU 的阶段只运行已有的 CPU/模拟测试，不借助启动实际服务来验证说明文档。

---

[返回 README](README.md) · [人工教程](BEGINNER_FRONTEND_GUIDE.md) · [技术架构](TECHNICAL_ARCHITECTURE.md)

created by zlk 2026
