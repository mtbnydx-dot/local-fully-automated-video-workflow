# macOS Apple Silicon workflows

These are ComfyUI API-format reference workflows for the beginner frontend.
The frontend generates the same graph shape dynamically with the user's prompt,
keyframe, seed, frame count, and selected resolution.

- `mac_ltx_smoke_test_api.json`: smallest LTX I2V smoke test.
- `mac_ltx_i2v_512x320_api.json`: Mac default image-to-video route.
- `mac_ltx_t2v_512x320_api.json`: Mac text-to-video fallback.
- `mac_wan5b_ti2v_480p_api.json`: high-memory Apple Silicon Wan2.2 5B experiment.

Put LTX files in:

- `models/checkpoints/ltxv-2b-0.9.8-distilled-fp8.safetensors`
- `models/text_encoders/t5xxl_fp16.safetensors`

Wan5B experiment additionally needs:

- `models/diffusion_models/Wan2.2/wan2.2_ti2v_5B_fp16.safetensors`
- `models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`
- `models/vae/wan2.2_vae.safetensors`
