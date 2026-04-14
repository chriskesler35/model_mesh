"""Tests for masked ComfyUI workflow conversion."""

import copy
import sys
from pathlib import Path

# Add backend to path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.routes.images import _convert_workflow_to_masked_inpaint, _convert_txt2img_to_img2img


def _find_node_by_type(workflow: dict, class_type: str) -> tuple[str, dict]:
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == class_type:
            return node_id, node
    raise AssertionError(f"Node {class_type} not found")


def test_masked_inpaint_composites_back_onto_original_image():
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sdxl.safetensors"},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": "old_source.png"},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["99", 0],
                "seed": 42,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "4": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["1", 2]},
        },
        "5": {
            "class_type": "SaveImage",
            "inputs": {"images": ["4", 0], "filename_prefix": "pytest"},
        },
    }
    node_schema = {
        "GrowMask": ["mask", "expand", "tapered_corners"],
        "ImpactGaussianBlurMask": ["mask", "kernel_size", "sigma"],
        "ImageCompositeMasked": ["destination", "source", "x", "y", "resize_source", "mask"],
    }

    result = _convert_workflow_to_masked_inpaint(
        copy.deepcopy(workflow),
        uploaded_image_name="fresh_source.png",
        uploaded_mask_name="protect_mask.png",
        denoise=0.35,
        node_schema=node_schema,
        mask_grow=12,
        mask_feather=4.5,
    )

    load_image_id, load_image_node = _find_node_by_type(result, "LoadImage")
    assert load_image_node["inputs"]["image"] == "fresh_source.png"

    load_mask_id, load_mask_node = _find_node_by_type(result, "LoadImageMask")
    assert load_mask_node["inputs"]["image"] == "protect_mask.png"
    assert load_mask_node["inputs"]["channel"] == "red"

    assert result["3"]["inputs"]["denoise"] == 0.35

    grow_mask_id, grow_mask_node = _find_node_by_type(result, "GrowMask")
    assert grow_mask_node["inputs"]["mask"] == [load_mask_id, 0]
    assert grow_mask_node["inputs"]["expand"] == 12

    blur_mask_id, blur_mask_node = _find_node_by_type(result, "ImpactGaussianBlurMask")
    assert blur_mask_node["inputs"]["mask"] == [grow_mask_id, 0]
    assert blur_mask_node["inputs"]["sigma"] == 4.5
    assert blur_mask_node["inputs"]["kernel_size"] == 11

    composite_id, composite_node = _find_node_by_type(result, "ImageCompositeMasked")
    assert composite_node["inputs"]["destination"] == [load_image_id, 0]
    assert composite_node["inputs"]["source"] == ["4", 0]
    assert composite_node["inputs"]["mask"] == [blur_mask_id, 0]

    assert result["5"]["inputs"]["images"] == [composite_id, 0]


def test_masked_inpaint_falls_back_cleanly_without_composite_nodes():
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sdxl.safetensors"},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": "old_source.png"},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["99", 0],
                "seed": 42,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "4": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["1", 2]},
        },
        "5": {
            "class_type": "SaveImage",
            "inputs": {"images": ["4", 0], "filename_prefix": "pytest"},
        },
    }

    result = _convert_workflow_to_masked_inpaint(
        copy.deepcopy(workflow),
        uploaded_image_name="fresh_source.png",
        uploaded_mask_name="protect_mask.png",
        denoise=0.2,
        node_schema={},
    )

    assert result["3"]["inputs"]["denoise"] == 0.2
    assert result["5"]["inputs"]["images"] == ["4", 0]
    assert all(node.get("class_type") != "ImageCompositeMasked" for node in result.values())


def test_masked_inpaint_skips_mask_refinement_when_controls_are_zero():
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sdxl.safetensors"},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": "old_source.png"},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "latent_image": ["4", 0],
                "denoise": 0.65,
            },
        },
        "4": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["2", 0], "vae": ["1", 2]},
        },
        "5": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["1", 2]},
        },
        "6": {
            "class_type": "SaveImage",
            "inputs": {"images": ["5", 0], "filename_prefix": "pytest"},
        },
    }
    node_schema = {
        "GrowMask": ["mask", "expand", "tapered_corners"],
        "ImpactGaussianBlurMask": ["mask", "kernel_size", "sigma"],
        "ImageCompositeMasked": ["destination", "source", "x", "y", "resize_source", "mask"],
    }

    result = _convert_workflow_to_masked_inpaint(
        copy.deepcopy(workflow),
        uploaded_image_name="fresh_source.png",
        uploaded_mask_name="protect_mask.png",
        denoise=0.35,
        node_schema=node_schema,
        mask_grow=0,
        mask_feather=0,
    )

    composite_id, composite_node = _find_node_by_type(result, "ImageCompositeMasked")
    load_mask_id, _ = _find_node_by_type(result, "LoadImageMask")
    assert composite_node["inputs"]["mask"] == [load_mask_id, 0]
    assert all(node.get("class_type") != "GrowMask" for node in result.values())
    assert all(node.get("class_type") != "ImpactGaussianBlurMask" for node in result.values())
    assert result["6"]["inputs"]["images"] == [composite_id, 0]


def test_existing_img2img_workflow_updates_denoise_on_sampler():
    workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": "old_source.png"},
        },
        "2": {
            "class_type": "KSampler",
            "inputs": {
                "latent_image": ["3", 0],
                "denoise": 0.65,
            },
        },
    }

    result = _convert_txt2img_to_img2img(copy.deepcopy(workflow), "fresh_source.png", denoise=0.3)

    assert result["1"]["inputs"]["image"] == "fresh_source.png"
    assert result["2"]["inputs"]["denoise"] == 0.3