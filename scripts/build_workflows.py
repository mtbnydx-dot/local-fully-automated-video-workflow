"""Build the native ComfyUI API graphs shipped with this project."""

import json
from pathlib import Path


def node(class_type, **inputs):
    return {"class_type": class_type, "inputs": inputs}


def h3_graph(*, image_to_video):
    graph = {
        "model": node("UNETLoader", unet_name="{{diffusion_model}}", weight_dtype="default"),
        "text_encoder": node("CLIPLoader", clip_name="{{text_encoder}}", type="minimax", device="default"),
        "video_vae": node("VAELoader", vae_name="{{video_vae}}"),
        "audio_vae": node("VAELoader", vae_name="{{audio_vae}}"),
        "conditioning": node(
            "MiniMaxH3ImageToVideo", clip=["text_encoder", 0], vae=["video_vae", 0],
            prompt="{{h3_prompt}}", width="{{width}}", height="{{height}}", length="{{frames}}",
        ),
        "noise": node("RandomNoise", noise_seed="{{seed}}"),
        "guider": node("BasicGuider", model=["model", 0], conditioning=["conditioning", 0]),
        "sampler": node("KSamplerSelect", sampler_name="{{sampler}}"),
        "schedule": node("BasicScheduler", model=["model", 0], scheduler="{{scheduler}}", steps="{{steps}}", denoise=1.0),
        "sample": node(
            "SamplerCustomAdvanced", noise=["noise", 0], guider=["guider", 0],
            sampler=["sampler", 0], sigmas=["schedule", 0], latent_image=["conditioning", 1],
        ),
        "decode_video": node("VAEDecode", samples=["sample", 0], vae=["video_vae", 0]),
        "decode_audio": node("VAEDecodeAudio", samples=["sample", 0], vae=["audio_vae", 0]),
        "video": node("CreateVideo", images=["decode_video", 0], audio=["decode_audio", 0], fps=24),
        "save": node("SaveVideo", video=["video", 0], filename_prefix="{{filename_prefix}}", format="mp4", **{"format.codec": "h264", "codec": "h264"}),
    }
    if image_to_video:
        graph["reference"] = node("LoadImage", image="{{reference_image}}")
        # H3 stretches the first frame to the canvas; a centre crop keeps people's proportions.
        graph["first_frame"] = node("ImageScale", image=["reference", 0], upscale_method="lanczos",
                                    width="{{width}}", height="{{height}}", crop="center")
        graph["conditioning"]["inputs"]["first_frame"] = ["first_frame", 0]
    return graph


def upscale_graph():
    return {
        "load": node("LoadVideo", file="{{reference_video}}"),
        "components": node("GetVideoComponents", video=["load", 0]),
        "size": node("GetImageSize", image=["components", 0]),
        "width": node("ComfyMathExpression", expression="a * b", **{"values.a": ["size", 0], "values.b": "{{factor}}"}),
        "height": node("ComfyMathExpression", expression="a * b", **{"values.a": ["size", 1], "values.b": "{{factor}}"}),
        "model": node("UpscaleModelLoader", model_name="{{upscale_model}}"),
        "upscale": node("ImageUpscaleWithModel", upscale_model=["model", 0], image=["components", 0]),
        "resize": node("ImageScale", image=["upscale", 0], upscale_method="lanczos", width=["width", 1], height=["height", 1], crop="disabled"),
        "video": node("CreateVideo", images=["resize", 0], audio=["components", 1], fps=["components", 2]),
        "save": node("SaveVideo", video=["video", 0], filename_prefix="{{filename_prefix}}", format="mp4", **{"format.codec": "h264", "codec": "h264"}),
    }


def main():
    destination = Path(__file__).resolve().parents[1] / "videopipe" / "workflows"
    destination.mkdir(exist_ok=True)
    graphs = {"h3_t2v.json": h3_graph(image_to_video=False), "h3_i2v.json": h3_graph(image_to_video=True), "upscale.json": upscale_graph()}
    for name, graph in graphs.items():
        (destination / name).write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
