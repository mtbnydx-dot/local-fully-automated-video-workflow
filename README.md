# 剧本、图片与视频生产流水线

从原始素材生成剧本包，补齐人物 / 场景 / 道具参考和镜头首帧，再生成带声音的视频、字幕与生产报告。三个独立 CLI 通过文件交接：

```mermaid
flowchart LR
    A["原文 + 改编说明"] --> S["scriptpipe<br/>规划、写作、文字审核"]
    S --> P["剧本包 + 图片槽位"]
    P --> I["imagepipe<br/>参考图与首帧"]
    I --> V["videopipe<br/>生成、审核、超分、拼接"]
    V --> D["视频（可烧录字幕）+ SRT + 生产报告"]
```

先看 [完整工作流](docs/workflow.md)，再看 [模块协作与代码入口](docs/architecture.md)。安装、运行和续跑见 [使用说明](docs/usage.md)，GPU 服务和离线包见 [部署说明](docs/deployment.md)。[文档索引](docs/README.md) 汇总其余入口。

| 目录 | 内容 |
| --- | --- |
| `scriptpipe/` | Ark DeepSeek / GLM 剧本写作、检查、修正和结构化导出 |
| `imagepipe/` | 图片依赖规划、在线任务调度与资产落盘 |
| `videopipe/` | ComfyUI / 视频生产、媒体、音频与交付 |
| [prompt/](prompt/README.md) | `script/`、`image/`、`videopipe/` 三组生产模板 |
| `configs/` | 通用图片配置、B200 视频配置、CPU 流程配置 |
| `deploy/`、`scripts/` | 外部服务启动、workflow 生成、离线应用包导出 |
| `tests/` | 媒体、调度、HTTP 接口与交付回归 |
| `materials/`、`runs/` | 本地原始素材和运行记录 |

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```
