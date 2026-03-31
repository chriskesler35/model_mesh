"""Tests for workflow template variable replacement."""

import json
import random
import sys
from pathlib import Path

# Add backend to path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.routes.images import _hydrate_workflow


def test_string_replacement():
    """Test that {{prompt}}, {{negative_prompt}}, {{checkpoint}} are replaced."""
    template = {
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": "{{prompt}}"}
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": "{{negative_prompt}}"}
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "{{checkpoint}}"}
        },
    }

    result = _hydrate_workflow(template, {
        "prompt": "a beautiful sunset",
        "negative_prompt": "ugly, blurry",
        "checkpoint": "ponyDiffusionV6XL.safetensors",
        "width": "1024",
        "height": "768",
    })

    assert result["6"]["inputs"]["text"] == "a beautiful sunset"
    assert result["7"]["inputs"]["text"] == "ugly, blurry"
    assert result["4"]["inputs"]["ckpt_name"] == "ponyDiffusionV6XL.safetensors"


def test_width_height_become_integers():
    """Test that width/height are converted from string to int."""
    template = {
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": "{{height}}", "width": "{{width}}"}
        },
    }

    result = _hydrate_workflow(template, {
        "prompt": "",
        "negative_prompt": "",
        "checkpoint": "",
        "width": "1024",
        "height": "768",
    })

    assert result["5"]["inputs"]["width"] == 1024
    assert isinstance(result["5"]["inputs"]["width"], int)
    assert result["5"]["inputs"]["height"] == 768
    assert isinstance(result["5"]["inputs"]["height"], int)


def test_seed_zero_randomized():
    """Test that seed=0 gets replaced with a random value."""
    template = {
        "3": {
            "class_type": "KSampler",
            "inputs": {"seed": 0, "steps": 20}
        },
    }

    result = _hydrate_workflow(template, {
        "prompt": "test",
        "negative_prompt": "",
        "checkpoint": "",
        "width": "512",
        "height": "512",
    })

    assert result["3"]["inputs"]["seed"] != 0
    assert isinstance(result["3"]["inputs"]["seed"], int)
    assert result["3"]["inputs"]["seed"] >= 1


def test_seed_nonzero_preserved():
    """Test that a non-zero seed is left alone."""
    template = {
        "3": {
            "class_type": "KSampler",
            "inputs": {"seed": 42, "steps": 20}
        },
    }

    result = _hydrate_workflow(template, {
        "prompt": "test",
        "negative_prompt": "",
        "checkpoint": "",
        "width": "512",
        "height": "512",
    })

    assert result["3"]["inputs"]["seed"] == 42


def test_real_sdxl_template():
    """Test hydration against the real sdxl-standard workflow template."""
    template_path = Path(__file__).parent.parent.parent / "data" / "workflows" / "sdxl-standard.json"
    if not template_path.exists():
        print(f"SKIP: {template_path} not found")
        return

    data = json.loads(template_path.read_text(encoding="utf-8"))
    workflow = data["workflow"]

    result = _hydrate_workflow(workflow, {
        "prompt": "a cat in space",
        "negative_prompt": "bad quality",
        "checkpoint": "ponyDiffusionV6XL.safetensors",
        "width": "1024",
        "height": "768",
    })

    # Prompt text
    assert result["6"]["inputs"]["text"] == "a cat in space"
    # Negative prompt
    assert result["7"]["inputs"]["text"] == "bad quality"
    # Checkpoint
    assert result["4"]["inputs"]["ckpt_name"] == "ponyDiffusionV6XL.safetensors"
    # Width/height are ints
    assert result["5"]["inputs"]["width"] == 1024
    assert result["5"]["inputs"]["height"] == 768
    assert isinstance(result["5"]["inputs"]["width"], int)
    assert isinstance(result["5"]["inputs"]["height"], int)
    # Seed randomized
    assert result["3"]["inputs"]["seed"] != 0
    assert isinstance(result["3"]["inputs"]["seed"], int)

    print("PASS: sdxl-standard template hydrated correctly")


def test_real_flux_template():
    """Test hydration against the real flux-schnell workflow template."""
    template_path = Path(__file__).parent.parent.parent / "data" / "workflows" / "flux-schnell.json"
    if not template_path.exists():
        print(f"SKIP: {template_path} not found")
        return

    data = json.loads(template_path.read_text(encoding="utf-8"))
    workflow = data["workflow"]

    result = _hydrate_workflow(workflow, {
        "prompt": "a robot painting",
        "negative_prompt": "",
        "checkpoint": "flux1-schnell-fp8-e4m3fn.safetensors",
        "width": "1280",
        "height": "720",
    })

    # Prompt text
    assert result["6"]["inputs"]["text"] == "a robot painting"
    # Checkpoint via UNETLoader
    assert result["12"]["inputs"]["unet_name"] == "flux1-schnell-fp8-e4m3fn.safetensors"
    # Width/height are ints
    assert result["5"]["inputs"]["width"] == 1280
    assert result["5"]["inputs"]["height"] == 720
    assert isinstance(result["5"]["inputs"]["width"], int)
    # Seed randomized
    assert result["13"]["inputs"]["seed"] != 0

    print("PASS: flux-schnell template hydrated correctly")


if __name__ == "__main__":
    test_string_replacement()
    print("PASS: test_string_replacement")
    test_width_height_become_integers()
    print("PASS: test_width_height_become_integers")
    test_seed_zero_randomized()
    print("PASS: test_seed_zero_randomized")
    test_seed_nonzero_preserved()
    print("PASS: test_seed_nonzero_preserved")
    test_real_sdxl_template()
    test_real_flux_template()
    print("\nAll tests passed!")
