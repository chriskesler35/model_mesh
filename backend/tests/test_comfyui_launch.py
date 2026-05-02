from pathlib import Path

from app.routes.images import _build_comfyui_launch_cmd


def test_build_comfyui_launch_cmd_adds_remote_safe_defaults_when_args_empty():
    cmd = _build_comfyui_launch_cmd(Path("python"), "")

    assert cmd == [
        "python",
        "main.py",
        "--listen",
        "0.0.0.0",
        "--default-device",
        "0",
        "--preview-method",
        "auto",
        "--enable-cors-header",
        "*",
    ]


def test_build_comfyui_launch_cmd_preserves_remote_safe_defaults_with_custom_args():
    cmd = _build_comfyui_launch_cmd(Path("python"), "--highvram --port 8188")

    assert cmd[:10] == [
        "python",
        "main.py",
        "--listen",
        "0.0.0.0",
        "--default-device",
        "0",
        "--preview-method",
        "auto",
        "--enable-cors-header",
        "*",
    ]
    assert cmd[-3:] == ["--highvram", "--port", "8188"]


def test_build_comfyui_launch_cmd_respects_explicit_listen_override():
    cmd = _build_comfyui_launch_cmd(Path("python"), "--listen 100.106.217.99 --port 8188")

    assert cmd.count("--listen") == 1
    assert "0.0.0.0" not in cmd
    assert ["--listen", "100.106.217.99"] == cmd[2:4]