#!/usr/bin/env python3
"""Minimal semantic-gated SDXL HTTP service for snapshot experiments."""

from __future__ import annotations

import argparse
import io
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageStat


class Model:
    def __init__(self, model_id: str, cache_dir: str) -> None:
        self.model_id = model_id
        self.lock = threading.Lock()
        self.pipeline = StableDiffusionXLPipeline.from_pretrained(
            model_id,
            cache_dir=cache_dir,
            torch_dtype=torch.float16,
            use_safetensors=True,
            variant="fp16",
        )
        self.pipeline.to("cuda")
        self.pipeline.set_progress_bar_config(disable=True)
        self.sleeping = False

    def sleep(self) -> None:
        """Move durable weights to host RAM and discard transient CUDA state."""
        with self.lock:
            torch.cuda.synchronize()
            self.pipeline.to("cpu")
            torch.cuda.empty_cache()
            self.sleeping = True

    def _wake(self) -> None:
        if self.sleeping:
            self.pipeline.to("cuda")
            self.sleeping = False

    def generate(self, prompt: str, steps: int, seed: int) -> bytes:
        with self.lock, torch.inference_mode():
            self._wake()
            generator = torch.Generator(device="cuda").manual_seed(seed)
            image = self.pipeline(
                prompt=prompt,
                num_inference_steps=steps,
                guidance_scale=0.0,
                height=512,
                width=512,
                generator=generator,
            ).images[0]
        validate_image(image)
        payload = io.BytesIO()
        image.save(payload, format="PNG")
        return payload.getvalue()


def validate_image(image: Image.Image) -> None:
    if image.size != (512, 512):
        raise ValueError(f"unexpected image size: {image.size}")
    extrema = ImageStat.Stat(image.convert("RGB")).extrema
    if not any(high > low for low, high in extrema):
        raise ValueError(f"generated image is constant: {extrema}")


def make_handler(model: Model) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "k301ud-sdxl/1"

        def log_message(self, format: str, *args: Any) -> None:
            print(f"http {self.address_string()} {format % args}", flush=True)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            payload = json.dumps(
                {
                    "ready": True,
                    "model": model.model_id,
                    "device": "cpu" if model.sleeping else "cuda",
                    "snapshot_sleep": model.sleeping,
                }
            ).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/generate":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                prompt = str(request["prompt"])
                steps = int(request.get("steps", 2))
                seed = int(request.get("seed", 0))
                if not prompt or not 1 <= steps <= 4:
                    raise ValueError("prompt must be non-empty and steps must be 1..4")
                payload = model.generate(prompt, steps, seed)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("X-Model", model.model_id)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="stabilityai/stable-diffusion-xl-base-1.0",
    )
    parser.add_argument("--cache-dir", default=os.environ.get("HF_HOME", "/model-cache"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ready-file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = Model(args.model, args.cache_dir)

    # A successful non-constant PNG is the semantic checkpoint gate. This also
    # warms the CUDA execution path before memory is captured.
    warmup = model.generate(
        "A red lighthouse beside a blue sea, technical benchmark image",
        steps=2,
        seed=2407,
    )
    Path("/tmp/sdxl-precheckpoint.png").write_bytes(warmup)
    model.sleep()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(model))
    if args.ready_file:
        ready_file = Path(args.ready_file)
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.touch()
    print(
        json.dumps(
            {
                "event": "ready",
                "model": args.model,
                "warmup_png_bytes": len(warmup),
                "snapshot_sleep": model.sleeping,
                "port": args.port,
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
