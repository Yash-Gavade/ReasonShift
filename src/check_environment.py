from __future__ import annotations

import sys
from importlib.metadata import version, PackageNotFoundError

def pkgver(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "NOT INSTALLED"

def main():
    print("=== ReasonShift environment check ===")
    print("Python:", sys.version.replace("\n", " "))
    print("torch:", pkgver("torch"))
    print("torchvision:", pkgver("torchvision"))
    print("torchaudio:", pkgver("torchaudio"))
    print("transformers:", pkgver("transformers"))
    print("accelerate:", pkgver("accelerate"))
    print("protobuf:", pkgver("protobuf"))

    try:
        import torch
        print("torch.__version__:", torch.__version__)
        print("torch.version.cuda:", torch.version.cuda)
        print("torch.cuda.is_available():", torch.cuda.is_available())

        if torch.cuda.is_available():
            print("GPU:", torch.cuda.get_device_name(0))
            props = torch.cuda.get_device_properties(0)
            print(f"GPU memory: {props.total_memory / (1024**3):.2f} GiB")
        else:
            print("\n[FAIL] CUDA is not available to PyTorch.")
            print("Repair PyTorch with the CUDA 11.8 command in FIX_ENVIRONMENT_WINDOWS.txt.")
            raise SystemExit(2)
    except Exception as e:
        if isinstance(e, SystemExit):
            raise
        print("[FAIL] torch import failed:", repr(e))
        raise SystemExit(2)

    try:
        import torchvision
        print("torchvision import: OK")
    except Exception as e:
        print("[FAIL] torchvision import failed:", repr(e))
        print("The torch/torchvision versions are probably mismatched.")
        raise SystemExit(3)

    try:
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        print("transformers text-model imports: OK")
    except Exception as e:
        print("[FAIL] transformers import failed:", repr(e))
        raise SystemExit(4)

    print("\n[PASS] Environment is ready for ReasonShift inference.")

if __name__ == "__main__":
    main()
