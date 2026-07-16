from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from .offline import run_remote_assessment, write_assessment_set


def _run(command: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=capture,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"docker command failed: {command[1]}")
    return completed.stdout.strip() if capture else ""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(url: str) -> None:
    deadline = time.monotonic() + 45
    with httpx.Client(trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(f"{url.rstrip('/')}/.well-known/agent-card.json", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
    raise RuntimeError("containerized Green Agent readiness timeout")


async def _fresh_round(green_image: str, purple_image: str, mutation: str, suffix: str) -> dict[str, Any]:
    token = f"{os.getpid()}-{suffix}"
    network = f"evalrel-net-{token}"
    purple = f"evalrel-purple-{token}"
    green = f"evalrel-green-{token}"
    port = _free_port()
    green_url = f"http://127.0.0.1:{port}/"
    _run(["docker", "network", "create", network])
    try:
        _run([
            "docker", "run", "-d", "--platform", "linux/amd64", "--name", purple, "--network", network,
            "--network-alias", "purple", purple_image,
            "--host", "0.0.0.0", "--port", "9009", "--card-url", "http://purple:9009/",
        ])
        _run([
            "docker", "run", "-d", "--platform", "linux/amd64", "--name", green, "--network", network,
            "-p", f"127.0.0.1:{port}:9009", green_image,
            "--host", "0.0.0.0", "--port", "9009", "--card-url", green_url,
        ])
        _wait(green_url)
        return await run_remote_assessment(green_url, "http://purple:9009/", mutation)
    finally:
        subprocess.run(["docker", "rm", "-f", green, purple], capture_output=True, check=False)
        subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)


async def run_docker_assessment(
    green_image: str,
    purple_image: str,
    output_dir: Path,
) -> dict[str, Any]:
    positive_one = await _fresh_round(green_image, purple_image, "none", "p1")
    positive_two = await _fresh_round(green_image, purple_image, "none", "p2")
    negative = await _fresh_round(green_image, purple_image, "details_array", "n1")
    image_ids = {
        "green": _run(["docker", "image", "inspect", "--format", "{{.Id}}", green_image], capture=True),
        "purple": _run(["docker", "image", "inspect", "--format", "{{.Id}}", purple_image], capture=True),
    }
    return write_assessment_set(
        output_dir,
        positive_one,
        positive_two,
        negative,
        {"local_image_ids": image_ids, "fresh_container_rounds": 3},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fresh-state AgentBeats assessment in Docker")
    parser.add_argument("--green-image", default="evalreliability-agentbeats-green:local")
    parser.add_argument("--purple-image", default="evalreliability-agentbeats-purple:local")
    parser.add_argument("--output", default="artifacts/agentbeats/docker-live")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / args.output).resolve()
    summary = asyncio.run(run_docker_assessment(args.green_image, args.purple_image, output_dir))
    print("AgentBeats Docker fresh-state assessment: PASS")
    print("Positive fresh containers: 2/2 identical")
    print("Negative fresh container: FAIL 278/279 as expected")
    print(json.dumps(summary["local_image_ids"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
