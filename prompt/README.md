# 生产模板

三个子目录对应三个生产模块，文件名统一为 `<模块>pipe_<用途>.txt`。模板提供通用写作、组装或审核规则；具体作品由原文、`--notes`、季设定、分镜和图片清单传入。

## script：8 个

写作和审核模板作为 system prompt，数据通过 JSON payload 传入；模板正文不做字符串格式化。当前 brief 决定集数、场数和时长。

| 文件 | 调用位置 / 用途 |
| --- | --- |
| [scriptpipe_long_season_plan_zh.txt](script/scriptpipe_long_season_plan_zh.txt) | `scriptpipe/long_pipeline.py`：长剧整季设定 |
| [scriptpipe_long_episode_opening_zh.txt](script/scriptpipe_long_episode_opening_zh.txt) | 同上：分集开场动作与对白 |
| [scriptpipe_long_episode_plan_zh.txt](script/scriptpipe_long_episode_plan_zh.txt) | 同上：分集场次、预计镜号范围和对白／动作节拍 |
| [scriptpipe_long_scene_write_zh.txt](script/scriptpipe_long_scene_write_zh.txt) | 同上：按场写镜头 |
| [scriptpipe_long_episode_review_zh.txt](script/scriptpipe_long_episode_review_zh.txt) | 同上：单集文字审核 |
| [scriptpipe_long_season_review_zh.txt](script/scriptpipe_long_season_review_zh.txt) | 同上：跨集因果与连续性审核 |
| [scriptpipe_export_h3_i2va.txt](script/scriptpipe_export_h3_i2va.txt) | `scriptpipe/export.py`：将分镜编译为 H3 输入 |
| [scriptpipe_json_retry.txt](script/scriptpipe_json_retry.txt) | `scriptpipe/llm.py`：JSON 解析失败后的重试说明 |

H3 编译模板使用 `{style}`、`{subjects}`、`{visual}`、`{camera}`、`{dialogue}`、`{soundscape}`、`{music}`、`{on_screen_text}`。编译器按发言顺序将台词放入 `<d>[语言]…</d>`，保留人物标签与对应发言回合的画外音要求；默认语言和配乐来自制作配置，单句语言和单镜配乐可覆盖。

## image：7 个

由 `imagepipe/plan.py` 根据槽位及引用选择，通过 `videopipe/prompts.py` 加载。使用 `{style}`、`{description}`、`{reference_guide}`、`{width}`、`{height}` 中需要的字段。

| 文件 | 用途 |
| --- | --- |
| [imagepipe_character_identity.txt](image/imagepipe_character_identity.txt) | 独立的人物身份近肖像，供全季服装和首帧复用 |
| [imagepipe_character_master.txt](image/imagepipe_character_master.txt) | 兼容旧清单的人物首套服装母图 |
| [imagepipe_wardrobe_edit.txt](image/imagepipe_wardrobe_edit.txt) | 保留人物身份，替换当前服装 |
| [imagepipe_location_reference.txt](image/imagepipe_location_reference.txt) | 具有固定空间特征的地点参考 |
| [imagepipe_prop_reference.txt](image/imagepipe_prop_reference.txt) | 可复用的道具外观参考 |
| [imagepipe_prop_edit.txt](image/imagepipe_prop_edit.txt) | 保留物品身份，改变所需状态 |
| [imagepipe_first_frame.txt](image/imagepipe_first_frame.txt) | 组合参考图，构成动作开始时的完整场面 |

多参考使用 `<image1>`、`<image2>` 等编号，单参考使用 “the reference image”；顺序与实际上传一致。身份图和服装图中的同一人物只在目标画面中出现一次。空场景图提供固定布景，带人物的场景锚点只贡献空间和光线，当前镜头决定出场人物、姿态与裁切。尺寸和步数由 API 配置决定，执行中直接组装模板。

新季案用 `render_style_en` 提供与内容无关的渲染风格，`style_en` 保存完整美术方向。身份近肖像决定脸，服装派生图决定衣服，同场景首帧共用空间锚点。剧本的 `reference_priority` 指定本镜重要的人物、地点和道具；图片配置 `continuity.reference_priority` 可进一步指定资产顺序。编译器按 `api.max_reference_images`（默认 10）选图，目标服装文字保留在首帧描述中。

季案的地点以单一可拍空间登记，厅堂、卧室和庭院分别建 ID。场景计划用 `anchor_shot_number` 提供预计空间参考，分场写作返回实际的 `anchor_shot_id`。组装时更新最终镜号，导出为 `scene_anchor_shot_id`；旧包保留首帧回退和手动指定方式。`continuity_en` 会附加到同场每张首帧，写固定建筑、家具、光源和轴线一侧；各镜实际出场的人物、站坐状态、视线和道具归属写在该镜描述中。生图引用表只说明每张图负责的身份、衣服、空间或道具，具体外貌和完整环境描述保留在母图任务中。

### 样板验证形成的写作经验

本轮使用实际 Qwen Image 2.1 服务、20 步验证参考图和六镜首帧，得到以下经验。模板据此明确输入含义，效果仍受模型能力影响。

- **服装写可见颜色。**“粗麻丧服”曾沿用身份肖像的灰衣；保持种子不变，改为明确的暖白、象牙白后颜色得到纠正。季案同时写材料和实际主色，换装模板明确用目标服装替换肖像中的临时衣服。
- **首帧写动作前状态。**供盒曾已经贴在案面上，与后续放盒动作冲突。明确双手支撑、与目标案面有可见间距后，起始状态得到改善。坐下、交接、开合等重要动作同样要区分开始和结果。
- **空间参考与出镜人物分开。**带人物的锚点曾把王公带入单人镜头，多个近景也沿用了全景。空场景是固定空间的基础；使用场景锚点时，目标镜头的可见人物和裁切仍是准则。这轮尚未进行去除人物锚点的效果对照。
- **每人只描述一个位置。**第六镜将坐着的王公及右下角肩膀、侧脸画成了两个王公。画面边缘人物的描述标明其身份；取景和背景人数由剧情决定。
- **重要结果进入下一镜。**物品放下、交出或收起后，后续镜头继承其位置、归属和状态；画外物品也保留状态。固定家具属于场景，道具的移动状态属于当前分镜。
- **验收抓影响理解的要求。**保留正确人物、可辨认服装、关键物品状态和主要剧情动作。普通衣褶、细微脸部变化和自然小动作允许波动，剧情需要时才指定精确姿势或装饰细节。

上述规则用于季案、场次计划、分镜写作与文字审核。`first_frame_prompt_en` 写静态开场，`visual_en` 写随后变化，`camera_en` 写景别、轴线和运镜。后续镜头承接前一镜的动作结果。

H3 编译保留官方首帧指令和三个核心字段，规范见 [MiniMax H3 提示词说明](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md)。

模板整理时沿用的上游参考：[Qwen 文生图说明](https://github.com/QwenLM/Qwen-Image-2.1/blob/main/prompt_rewrite/prompts/system_prompt_t2i.txt)、[编辑说明](https://github.com/QwenLM/Qwen-Image-2.1/blob/main/prompt_rewrite/prompts/system_prompt_edit.txt)、[ComfyUI 引用顺序](https://docs.comfy.org/tutorials/image/qwen/qwen-image-2-1)、[Qwen 参数及多参考示例](https://github.com/QwenLM/Qwen-Image-2.1/blob/main/README.md)。

## videopipe：6 个

前五个由 `videopipe/backends/review.py` 使用，最后一个由 `videopipe/inputs.py` 在保存旧包快照时使用。

| 文件 | 用途 / 格式化字段 |
| --- | --- |
| [videopipe_visual_review_system.txt](videopipe/videopipe_visual_review_system.txt) | 单镜头画面审核标准 |
| [videopipe_visual_review_user.txt](videopipe/videopipe_visual_review_user.txt) | `{duration}`、`{script}`、`{shot_specs}` |
| [videopipe_visual_review_reference.txt](videopipe/videopipe_visual_review_reference.txt) | 参考图标签：`{index}`、`{shot_id}` |
| [videopipe_visual_review_frame.txt](videopipe/videopipe_visual_review_frame.txt) | 抽帧标签：`{timestamp}` |
| [videopipe_transcript_compare_system.txt](videopipe/videopipe_transcript_compare_system.txt) | 预期对白与 ASR 文本差异 |
| [videopipe_legacy_negative.txt](videopipe/videopipe_legacy_negative.txt) | 旧负面词一次性并入有效 prompt：`{negative_prompt}` |

视觉审核模板共同组成一次请求。审核结果进入 [视频选片流程](../docs/workflow.md)，生成 prompt 由上游脚本包提供。
