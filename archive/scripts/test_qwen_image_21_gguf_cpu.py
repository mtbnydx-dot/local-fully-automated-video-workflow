"""Check the installed GGUF loader with real norm vectors, without ComfyUI or CUDA."""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import logging
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch


def run_check(plugin_dir: Path, model_path: Path) -> dict:
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import gguf
    import torch

    assert not torch.cuda.is_initialized(), "Run this test in a fresh CPU-only process"

    def forbid_cuda(*args, **kwargs):
        raise AssertionError("CUDA initialization is forbidden in this test")

    # Import real loader/dequant code but not the plugin entrypoint or ComfyUI.
    package_name = "_qwen21_gguf_cpu_check"
    package = types.ModuleType(package_name)
    package.__path__ = [str(plugin_dir)]
    sys.modules[package_name] = package
    ops = types.ModuleType(f"{package_name}.ops")
    ops.__dict__.update(torch=torch, logging=logging)
    tree = ast.parse((plugin_dir / "ops.py").read_text(encoding="utf-8"))
    tensor_class = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "GGMLTensor")
    exec(compile(ast.Module(body=[tensor_class], type_ignores=[]), str(plugin_dir / "ops.py"), "exec"), ops.__dict__)
    sys.modules[ops.__name__] = ops

    with patch.object(torch.cuda, "_lazy_init", side_effect=forbid_cuda):
        loader = importlib.import_module(f"{package_name}.loader")
        reader = gguf.GGUFReader(str(model_path), mode="r")
        norms = [tensor for tensor in reader.tensors if ".attn.norm_" in tensor.name]
        assert norms, "Model has no Qwen attention norm vectors"
        quantized_norm = next(tensor for tensor in norms if tensor.tensor_type == gguf.GGMLQuantizationType.Q8_0)
        logical_shape = tuple(int(value) for value in reversed(quantized_norm.shape))
        packed = ops.GGMLTensor(torch.from_numpy(quantized_norm.data.copy()),
                               tensor_type=quantized_norm.tensor_type, tensor_shape=torch.Size(logical_shape))
        x = torch.ones((1, 2, logical_shape[0]), device="cpu")
        try:
            torch.nn.functional.rms_norm(x, logical_shape, packed, 1e-6)
        except RuntimeError as exc:
            reproduced = str(exc)
            assert "normalized_shape" in reproduced, reproduced
        else:
            raise AssertionError("Original packed norm should reproduce the shape error")

        vectors = [tensor for tensor in reader.tensors if len(tensor.shape) <= 1]
        matrix = min((tensor for tensor in reader.tensors if len(tensor.shape) > 1), key=lambda tensor: tensor.n_bytes)
        # Mmap only the selected vectors and one matrix; never instantiate the full model.
        reader.tensors = [*vectors, matrix]
        with patch.object(gguf, "GGUFReader", return_value=reader):
            state, metadata = loader.gguf_sd_loader(str(model_path))
        assert metadata["arch_str"] == "qwen_image21", metadata["arch_str"]
        for tensor in vectors:
            weight = state[tensor.name]
            shape = tuple(int(value) for value in reversed(tensor.shape))
            assert type(weight) is torch.Tensor and weight.device.type == "cpu" and weight.dtype == torch.float32
            assert tuple(weight.shape) == shape
            reference = torch.from_numpy(gguf.quants.dequantize(tensor.data, tensor.tensor_type).copy()).reshape(shape)
            torch.testing.assert_close(weight, reference, rtol=0, atol=0)
        assert isinstance(state[matrix.name], ops.GGMLTensor), "Matrix weights must remain quantized"
        assert state[matrix.name].tensor_type == matrix.tensor_type
        for tensor in norms:
            weight = state[tensor.name]
            output = torch.nn.functional.rms_norm(x, tuple(weight.shape), weight, 1e-6)
            assert torch.isfinite(output).all()
        convert = importlib.import_module(f"{package_name}.tools.convert")
        with patch.object(gguf, "GGUFReader", return_value=reader), patch.object(
            convert, "detect_arch", return_value=types.SimpleNamespace(arch="qwen_image")
        ):
            other_state, _ = loader.gguf_sd_loader(str(model_path))
        assert isinstance(other_state[quantized_norm.name], ops.GGMLTensor), "Non-Qwen-2.1 behavior must remain unchanged"
        assert "comfy.model_management" not in sys.modules and not torch.cuda.is_initialized()
    return {
        "ok": True,
        "cpu_only": True,
        "reproduced_error": reproduced,
        "norm_vectors_passed": len(norms),
        "decoded_vectors": len(vectors),
        "decoded_bytes": sum(state[t.name].numel() * 4 for t in vectors),
        "matrices_remain_quantized": True,
        "other_architectures_unchanged": True,
        "cuda_initialized": False,
        "full_generation_tested": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gguf-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_check(args.gguf_dir.resolve(), args.model.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
