# 手工工作流与动态工作流

日常使用优先从前端选择模型，由平台构建并预检 API 图。本页面向需要直接操作 ComfyUI 的使用者。模板编号是历史文件名，不代表必须按顺序执行，也不代表全平台只支持 Wan。

## 1. 两类文件

| 目录 | 格式与用途 |
| --- | --- |
| [workflows/ready/](workflows/ready/) | ComfyUI 编辑器 JSON，含界面节点/连线，可在兼容编辑器中打开 |
| [workflows/mac/](workflows/mac/) | 带 `_api.json` 的执行图，供 API/工具调用 |
| [workflows/comfyui_blueprints/](workflows/comfyui_blueprints/) | 原始参考蓝图，不承诺直接满足当前运行时 |

API JSON 与编辑器 JSON 不等价。不要假设每个 JSON 都能直接拖入编辑器显示，也不要将编辑器 JSON 原样 POST 到 `/prompt`。

前端动态工作流由代码生成，H3 创作扩展、LTX 2.5、Qwen 编辑等不必有一张同名静态 ready 文件。原理见[模型工作流](MODEL_WORKFLOWS.md)。

## 2. ready 模板目录

| 文件 | 作用 | 手动检查 |
| --- | --- | --- |
| `01_Wan22_I2V_A14B_720p_4step_READY.json` | Wan A14B 图生视频，成对高低噪声与 4 步 LoRA | 首帧、I2V 主模型/LoRA 配对 |
| `02_Wan22_T2V_A14B_720p_4step_READY.json` | Wan A14B 文生视频 | T2V 主模型/LoRA 配对 |
| `03_Wan22_TI2V_5B_720p_DRAFT_READY.json` | Wan 5B 图片输入示例 | 模型、Wan2.2 VAE 与输入图 |
| `04_RIFE_2x_Postprocess_READY.json` | RIFE 2x 插帧 | 原片、rife49 权重、输出 FPS |
| `05_MiniMax_H3_FL2VA_T2V_INT8_READY.json` | H3 FL2VA 文字音视频 | 四类 H3 权重与节点 |
| `06_MiniMax_H3_FL2VA_I2V_INT8_READY.json` | H3 FL2VA 首帧/首尾帧 | 首帧必需，尾帧按需，音频开关 |

模板中的示例图片/视频和权重不包含在 GitHub 发布包。文件名中 READY 表示模板已预设，不保证你的运行时已经就绪。

## 3. 手动运行方法

1. 按需要安装当前模型与节点，确认 ComfyUI 已成功加载。
2. 在 ComfyUI 中打开对应编辑器 JSON。
3. 把模板中的示例输入替换成自己的素材。
4. 从当前加载器下拉选择实际模型，避免跨系统复制硬编码路径。
5. 核对画布、帧数、FPS、步数、LoRA 版本与输出目录。
6. 已获 GPU 使用授权后，先用低分辨率短片段排队测试。
7. 检查输出可完整播放，再提高参数。

新版本节点可能增加必填参数或更改 widgets。手工模板不会自动获得平台的全部 schema 兼容修正；失败时优先使用前端动态图，或按当前 `/object_info` 修正模板。

RIFE 模板示例是 24 → 48 FPS。原视频是 16 FPS 时，2x 应对应 32 FPS；只改输出帧率不等于正确插帧。

## 4. Mac API 图

| 文件 | 作用 |
| --- | --- |
| `mac_ltx_smoke_test_api.json` | 极短轻量链路示例 |
| `mac_ltx_t2v_512x320_api.json` | LTX 文字短片 |
| `mac_ltx_i2v_512x320_api.json` | LTX 图片短片 |
| `mac_wan5b_ti2v_480p_api.json` | 高内存 Mac Wan5B 实验示例 |

Mac 图仍依赖 MPS、匹配 dtype、节点和实际模型名。检查文件可解析不代表当前 Mac 可以生成。优先从前端 Mac 推荐档构建图，避免绕过硬件预检。

## 5. 怎样核查

- 静态：JSON 可解析、节点引用有效、模型清单一致。
- 运行时：ComfyUI 已加载节点，模型名在实际下拉中，必填输入完整。
- 实机：获得资源使用授权后完成短片，并核对视频/声音。

`scripts/verify_wan22_setup.ps1` 是历史 Wan 基础检查入口，不能代替全平台 H3/LTX/Qwen 验收。通用 CPU 检查见[维护与验证](TECHNICAL_ARCHITECTURE.md#10-维护与验证)；「生成链路测试」会真实提交推理。

---

[返回 README](README.md) · [使用教程](BEGINNER_FRONTEND_GUIDE.md) · [API 指南](AI_PLATFORM_USAGE_GUIDE.md)
