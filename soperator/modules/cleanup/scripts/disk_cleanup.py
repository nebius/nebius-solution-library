#!/usr/bin/env python3
import asyncio
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Optional

ALLOWED_CLEANUP_NAMESPACES: tuple[str, ...] = (
    "logs-system",
    "monitoring-system",
    "soperator",
    "nfs-system",
)

NOT_FOUND_PATTERNS: tuple[str, ...] = (
    "ResourceNotFound",
    "disk not found",
)

DEFAULT_PARALLELISM: Final[int] = 200
DEFAULT_PAGE_SIZE: Final[int] = 999
DEFAULT_CLI_RETRIES: Final[int] = 5
DEFAULT_MAX_REQUEUE: Final[int] = 3
DEFAULT_INITIAL_REQUEUE_BACKOFF_SECONDS: Final[float] = 1.0
DEFAULT_MAX_REQUEUE_BACKOFF_SECONDS: Final[float] = 60.0
DEFAULT_START_RATE_PER_SECOND: Final[float] = 100.0
DEFAULT_OPERATION_WAIT_TIMEOUT: Final[str] = "5m"


class CleanupError(Exception):
    pass


class CommandError(CleanupError):
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str):
        super().__init__(format_command_error(command, returncode, stdout, stderr))
        self.command: list[str] = command
        self.returncode: int = returncode
        self.stdout: str = stdout
        self.stderr: str = stderr

    @property
    def combined_output(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


class TaskStatus(StrEnum):
    COMPLETE = "complete"
    REQUEUE = "requeue"


@dataclass(frozen=True)
class Config:
    parent_id: str
    parallelism: int
    page_size: int
    cli_retries: int
    max_requeue: int
    initial_requeue_backoff_seconds: float
    max_requeue_backoff_seconds: float
    start_rate_per_second: float
    operation_wait_timeout: str


@dataclass(frozen=True)
class Disk:
    id: str
    name: str
    namespace: str


@dataclass(frozen=True)
class DeleteTask:
    disk: Disk
    requeues: int = 0


@dataclass(frozen=True)
class TaskResult:
    status: TaskStatus
    reason: str = ""


class StartRateLimiter:
    def __init__(self, rate_per_second: float):
        self._interval: int | float = 0 if rate_per_second <= 0 else 1 / rate_per_second
        self._lock = asyncio.Lock()
        self._next_start: float = 0.0

    async def wait(self) -> None:
        if self._interval == 0:
            return

        async with self._lock:
            now: float = time.monotonic()

            if self._next_start > now:
                await asyncio.sleep(self._next_start - now)
                now = time.monotonic()

            self._next_start = max(now, self._next_start) + self._interval


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw_value: str = os.environ.get(name, str(default))

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise CleanupError(f"{name} must be an integer, got: {raw_value}") from exc

    if value < minimum:
        raise CleanupError(f"{name} must be >= {minimum}, got: {value}")

    return value


def load_config() -> Config:
    parent_id: Optional[str] = os.environ.get("PARENT_ID")
    if not parent_id:
        raise CleanupError("PARENT_ID is required")

    return Config(
        parent_id=parent_id,
        parallelism=env_int("DISK_CLEANUP_PARALLELISM", DEFAULT_PARALLELISM),
        page_size=DEFAULT_PAGE_SIZE,
        cli_retries=DEFAULT_CLI_RETRIES,
        max_requeue=DEFAULT_MAX_REQUEUE,
        initial_requeue_backoff_seconds=DEFAULT_INITIAL_REQUEUE_BACKOFF_SECONDS,
        max_requeue_backoff_seconds=DEFAULT_MAX_REQUEUE_BACKOFF_SECONDS,
        start_rate_per_second=DEFAULT_START_RATE_PER_SECOND,
        operation_wait_timeout=DEFAULT_OPERATION_WAIT_TIMEOUT,
    )


def format_command_error(
    command: list[str], returncode: int, stdout: str, stderr: str
) -> str:
    details = [f"command failed with exit code {returncode}: {' '.join(command)}"]

    if stdout.strip():
        details.append(f"stdout: {stdout.strip()}")

    if stderr.strip():
        details.append(f"stderr: {stderr.strip()}")

    return "\n".join(details)


def is_not_found(error: CommandError) -> bool:
    return any(
        pattern.lower() in error.combined_output.lower()
        for pattern in NOT_FOUND_PATTERNS
    )


def parse_operation_id(output: str) -> str:
    stripped_output: str = output.strip()
    if not stripped_output:
        raise CleanupError("delete command returned an empty operation id")

    try:
        payload = json.loads(stripped_output)
    except json.JSONDecodeError as exc:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) == 1 and is_operation_id(lines[0]):
            return lines[0]
        raise CleanupError(
            f"delete command returned unexpected output: {stripped_output}"
        ) from exc

    if not isinstance(payload, dict):
        raise CleanupError(f"delete command returned non-object JSON: {payload}")

    operation_id = payload.get("id")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise CleanupError(f"delete operation JSON does not contain id: {payload}")

    return operation_id.strip()


def is_operation_id(value: str) -> bool:
    return value.startswith("computeoperation-")


def requeue_delay(config: Config, requeues: int) -> float:
    exponential = config.initial_requeue_backoff_seconds * (2**requeues)
    capped = min(exponential, config.max_requeue_backoff_seconds)
    return random.uniform(0, capped)


async def run_command(command: list[str]) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise CommandError(command, process.returncode or 1, stdout, stderr)
    return stdout


def disk_from_item(item: dict) -> Optional[Disk]:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    labels = metadata.get("labels") or {}

    disk_id = metadata.get("id") or ""
    name = metadata.get("name") or ""
    namespace = labels.get("kubernetes.io/created-for/pvc/namespace") or ""
    attachment = status.get("read_write_attachment")

    if (
        disk_id
        and not attachment
        and namespace in ALLOWED_CLEANUP_NAMESPACES
        and name.startswith("pvc-")
    ):
        return Disk(id=disk_id, name=name, namespace=namespace)
    return None


async def list_disks(config: Config) -> list[Disk]:
    page_token = ""
    result: list[Disk] = []
    page_number = 0

    while True:
        page_number += 1
        command = [
            "nebius",
            "compute",
            "disk",
            "list",
            "--parent-id",
            config.parent_id,
            "--page-size",
            str(config.page_size),
            "--format",
            "json",
            "--no-progress",
            "--retries",
            str(config.cli_retries),
        ]
        if page_token:
            command.extend(["--page-token", page_token])

        output = await run_command(command)
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise CleanupError(
                f"failed to parse disk list JSON page {page_number}: {exc}"
            ) from exc

        items = payload.get("items") or []
        for item in items:
            disk = disk_from_item(item)
            if disk is not None:
                result.append(disk)

        page_token = payload.get("next_page_token") or ""
        print(
            f"Scanned disk page {page_number}: {len(items)} items, "
            f"{len(result)} cleanup candidates so far",
            flush=True,
        )
        if not page_token:
            return result


async def disk_exists(disk: Disk, config: Config) -> bool:
    command = [
        "nebius",
        "compute",
        "disk",
        "get",
        "--id",
        disk.id,
        "--format",
        "json",
        "--no-progress",
        "--retries",
        str(config.cli_retries),
    ]
    try:
        await run_command(command)
        return True
    except CommandError as error:
        if is_not_found(error):
            return False
        raise


async def start_delete_operation(
    disk: Disk,
    config: Config,
    start_limiter: StartRateLimiter,
) -> Optional[str]:
    command = [
        "nebius",
        "compute",
        "disk",
        "delete",
        "--id",
        disk.id,
        "--async",
        "--format",
        "json",
        "--no-progress",
        "--retries",
        str(config.cli_retries),
    ]
    await start_limiter.wait()
    try:
        output = await run_command(command)
    except CommandError as error:
        if is_not_found(error):
            return None
        raise

    return parse_operation_id(output)


async def wait_delete_operation(
    operation_id: str,
    config: Config,
) -> bool:
    command = [
        "nebius",
        "compute",
        "disk",
        "operation",
        "wait",
        "--id",
        operation_id,
        "--timeout",
        config.operation_wait_timeout,
        "--no-progress",
        "--retries",
        str(config.cli_retries),
    ]
    try:
        await run_command(command)
        return True
    except CommandError as error:
        if is_not_found(error):
            return False
        raise


async def recheck_after_not_found(disk: Disk, config: Config) -> TaskResult:
    exists = await disk_exists(disk, config)
    if not exists:
        print(f"Disk {disk.id} is absent; task complete", flush=True)
        return TaskResult(TaskStatus.COMPLETE)
    return TaskResult(TaskStatus.REQUEUE, "disk still exists after not-found response")


async def run_delete_task(
    task: DeleteTask,
    config: Config,
    start_limiter: StartRateLimiter,
) -> TaskResult:
    disk = task.disk

    exists = await disk_exists(disk, config)
    if not exists:
        print(f"Disk {disk.id} is already absent; task complete", flush=True)
        return TaskResult(TaskStatus.COMPLETE)

    print(
        f"Starting deletion of leftover disk {disk.id} "
        f"({disk.namespace}/{disk.name})",
        flush=True,
    )
    operation_id = await start_delete_operation(disk, config, start_limiter)
    if operation_id is None:
        return await recheck_after_not_found(disk, config)

    print(f"Waiting for disk {disk.id} delete operation {operation_id}", flush=True)
    operation_wait_completed = await wait_delete_operation(operation_id, config)
    if not operation_wait_completed:
        return await recheck_after_not_found(disk, config)

    print(f"Deleted leftover disk {disk.id}", flush=True)
    return TaskResult(TaskStatus.COMPLETE)


async def worker(
    name: str,
    queue: asyncio.Queue[DeleteTask],
    config: Config,
    start_limiter: StartRateLimiter,
    failures: dict[str, str],
) -> None:
    while True:
        task = await queue.get()
        disk = task.disk
        try:
            result = await run_delete_task(task, config, start_limiter)
        except Exception as exc:
            result = TaskResult(TaskStatus.REQUEUE, str(exc))

        if result.status == TaskStatus.REQUEUE:
            if task.requeues >= config.max_requeue:
                failures[disk.id] = result.reason
                print(
                    f"{name}: disk {disk.id} exceeded max requeue "
                    f"({config.max_requeue}): {result.reason}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                delay = requeue_delay(config, task.requeues)
                print(
                    f"{name}: requeue disk {disk.id} in {delay:.1f}s "
                    f"({task.requeues + 1}/{config.max_requeue}): {result.reason}",
                    flush=True,
                )
                await asyncio.sleep(delay)
                queue.put_nowait(DeleteTask(disk=disk, requeues=task.requeues + 1))

        queue.task_done()


async def cleanup_disks(config: Config, disks: list[Disk]) -> int:
    queue: asyncio.Queue[DeleteTask] = asyncio.Queue()
    for disk in disks:
        queue.put_nowait(DeleteTask(disk=disk))

    failures: dict[str, str] = {}
    worker_count = min(config.parallelism, len(disks))
    start_limiter = StartRateLimiter(config.start_rate_per_second)
    workers = [
        asyncio.create_task(
            worker(f"worker-{index + 1}", queue, config, start_limiter, failures)
        )
        for index in range(worker_count)
    ]

    await queue.join()
    for task in workers:
        task.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    if failures:
        print("Failed disk deletions:", file=sys.stderr)
        for disk_id, error in sorted(failures.items()):
            print(f"- {disk_id}: {error}", file=sys.stderr)
        return 1
    return 0


async def async_main() -> int:
    config = load_config()
    print(
        "Disk cleanup config: "
        f"parallelism={config.parallelism}, "
        f"page_size={config.page_size}, "
        f"cli_retries={config.cli_retries}, "
        f"max_requeue={config.max_requeue}, "
        f"start_rate_per_second={config.start_rate_per_second}",
        flush=True,
    )

    disks = await list_disks(config)
    if not disks:
        print("No leftover disks to delete", flush=True)
        return 0

    print(f"Found {len(disks)} leftover disks to delete", flush=True)
    return await cleanup_disks(config, disks)


def main() -> int:
    try:
        return asyncio.run(async_main())
    except CleanupError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
