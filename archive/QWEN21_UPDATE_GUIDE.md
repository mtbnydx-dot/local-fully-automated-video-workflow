# Qwen-Image-2.1 专项说明

本页说明仓库中已经接入的 Qwen 2.1 档位，**不表示读者电脑已经下载、加载或实测这些模型**。按 2026-10-28 的代码整理；来源版本、文件大小与哈希见 [qwen21_updates.py](beginner_frontend/qwen21_updates.py)。

首次操作见[图片教程](BEGINNER_FRONTEND_GUIDE.md#4-生成或编辑图片)，条件与潜变量链路见[模型原理](MODEL_WORKFLOWS.md#4-qwen-image-21)。

## 1. 档位如何选择

| 图片菜单中的档位 | 本平台用途 | 配方与边界 |
| --- | --- | --- |
| 原生 Qwen 2.1 | 标准生成与参考编辑 | 保留基础路线，先做基准 |
| Qwen 2.1 Turbo 8 步 | 快速生成与编辑 | 8 步 / CFG 1 / Euler / Simple，需独立 Turbo 权重 |
| 社区 UC Q8 / 2026-10 | GGUF 社区扩展 | 配套 GGUF 加载器；不是原文件改名 |
| 社区 UC INT8 / 2026-10 | 原生加载器社区扩展 | 使用 UNETLoader 的独立 INT8 权重 |
| 社区 UC LoRA / 实验 | 基础模型上加载适配器 | 默认强度 0.8，保留实验标记 |
| 保构图编辑 25 步 | 约束编辑时的构图变化 | 仅编辑；Consistency 强度 1.0 |
| 照片修复 25 步 | 模糊/压缩图片修复试用 | 仅编辑；Restore 强度 0.5；约 2 MP 预算 |

普通 25 步模型不能仅改 steps 就当作 Turbo。社区模式的底模替换与额外 LoRA 是不同配置，避免在融合模型上重复叠加同一种修改。

Uncensored/UC 是社区标注，不构成效果、质量或任意内容可生成的保证。必须使用明确成年、自愿且合法授权的素材，不用于未成年人、非自愿内容或真人私密仿冒。

## 2. 前端操作

1. 打开「图片创作」，重新检查环境与可用档位。
2. 文生图选支持生成的 profile；已有图修改先切换「已有图片微调」。
3. 编辑时上传目标图，再加入附加参考，总计最多 10 张；目标图为第一个位置。
4. 核对分辨率和锁定的采样参数，首次只生成一张。
5. 若选择社区模式，先完成界面授权确认；关闭开关恢复该档的基础路线，不改写共享模型文件。
6. 等任务结束后打开原图看真实尺寸、细节和编辑结果，再扩大批量或转成视频。

保构图可能限制姿态、转头等大幅修改；照片修复可能重新生成小脸和细节，不能当作法证恢复。参考编辑按像素预算处理，不保证逐像素原位保留。

## 3. 文件位置与复用

以下相对于实际 ComfyUI base 或已注册的模型根目录，不是固定系统盘位置：

```text
models/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors
models/diffusion_models/Qwen-Image-2.1-Community-202610/qwen-image-2.1-UC-Q8_0.gguf
models/diffusion_models/Qwen-Image-2.1-Community-202610/qwen-image-2.1-UC-int8_convrot.safetensors
models/loras/Qwen-Image-2.1/qwen-image-2.1-uncensored-lora.safetensors
models/loras/Qwen-Image-2.1/qwen-image-2.1-consistency.safetensors
models/loras/Qwen-Image-2.1/qwen-image-2.1-restore.safetensors
```

新版文件独立存放，不覆盖原有 Q8。基础编码器和 VAE 可按清单复用；下载量取决于已安装内容，不把历史某台机器的剩余下载量当作所有人的需求。

## 4. 维护与核验

通用安装器与专项核验脚本不是同一个校验路径。专项 [prepare_qwen21_updates.py](scripts/prepare_qwen21_updates.py) 会检查清单中各新增文件的大小与 SHA256，不导入 torch、不启动服务。读取大文件校验仍会消耗磁盘 I/O 和时间。

使用 Python 3.11 或 3.12（脚本使用 `hashlib.file_digest`）。下载模式还需要该 Python 环境安装了 `huggingface_hub`。在项目目录替换下面的路径占位符后运行：

```powershell
# 只核对已有文件；不下载。
& '<Python路径>' -B scripts/prepare_qwen21_updates.py --base-dir '<ComfyUI数据目录>' --verify-only
# 明确需要下载缺失项时才执行。
& '<Python路径>' -B scripts/prepare_qwen21_updates.py --base-dir '<ComfyUI数据目录>'
```

校验失败会保留文件并报错。不要把失败文件直接改名成另一档模型，也不要根据文件大小就宣称 hash 已通过。

## 5. 不属于自动适配范围的项目

- 其他 4 步 LoRA：需要自己的 sigma/shift/缓存配方，不能只改步数。
- 旧 Qwen-Image、Edit-2511 等 LoRA：不能假定是 2.1 专用。
- 名称含 Qwen 但实际是编码器/mmproj 的仓库：不能装作扩散主模型。
- MLX、NVFP4、W4A8、不同 Prompt Enhancer：后端与加载器不同，不因文件名相似就直接替换。
- 新版 ComfyUI 编译、缓存、ControlNet 等功能：需单独适配和回归，不由本页文档自动启用。

## 6. 问题定位

| 现象 | 检查 |
| --- | --- |
| TextEncodeQwenImage21 缺少 resolution | 当前动态图显式提供此输入；核对运行后端是否更新、是否在使用旧模板 |
| GGUF 加载失败 | 对照实际 GGUF 节点、依赖和模型下拉列表 |
| 下载完成仍缺节点 | 看 ComfyUI 导入日志及其 Python 环境；节点目录存在不等于已加载 |
| 缓存/条件形状报错 | 确认底模、编码器、VAE、编辑节点来自匹配路线 |
| 批量部分成功 | 保留已有图片，按任务内各 prompt 状态排查，不重跑全部 |
| 编辑结果变化过大 | 回到标准档与少量参考做对照；不要同时叠多个 LoRA |

CPU 回归只能验证图与门控逻辑；实际加载、画质、耗时、显存和 MPS 兼容性需在对应机器上实测。

## 7. 来源入口

以下是清单与适配的上游来源入口，不代表本次文档整理重新评测了上游：

- [Qwen-Image-2.1](https://huggingface.co/Qwen/Qwen-Image-2.1)
- [Comfy-Org Qwen 2.1 权重](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)
- [社区量化与适配器](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-Quantized)
- [Consistency LoRA](https://huggingface.co/ausboss/Qwen-Image-2.1-Consistency-LoRA)
- [Restore LoRA](https://huggingface.co/ausboss/Qwen-Image-2.1-Restore-LoRA)

使用前分别确认模型与衍生文件许可。平台代码许可证不代替模型授权。

---

[返回 README](README.md) · [模型原理](MODEL_WORKFLOWS.md) · [使用教程](BEGINNER_FRONTEND_GUIDE.md)

created by zlk 2026
