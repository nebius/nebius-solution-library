"""Deterministic discrete-event engine for catalog switch simulation.

Time is integer microseconds. Every request is tracked from external arrival
(T0) to its first complete semantically valid response, with causal per-phase
timestamps: queue wait, drain/GPU release, L2 fetch, local prewarm, restore or
conventional load, and inference. Preemptible node failures wipe node state
and force retries. Invariants are enforced during the run and at the end;
violations raise ``InvariantViolation`` instead of producing silent garbage.
"""

from __future__ import annotations

import heapq
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .catalog import CatalogModel, pipeline_successor
from .policies import L1Cache, PolicyConfig, choose_node, warm_pin_assignments
from .traces import Trace
from .units import transfer_micros

MAX_RETRIES = 3
NO_CAPACITY_BACKOFF_MICROS = 5_000_000
MAX_NO_CAPACITY_ATTEMPTS = 200


class InvariantViolation(AssertionError):
    """A simulator invariant was broken; the run result is invalid."""


@dataclass
class Request:
    req_id: int
    model_id: str
    arrival: int
    retries: int = 0
    capacity_attempts: int = 0
    dispatch: Optional[int] = None
    ready_at: Optional[int] = None
    response_at: Optional[int] = None
    node_id: Optional[int] = None
    outcome: str = "pending"  # completed | rejected | failed
    cache_tier: Optional[str] = None  # L0 | L1-warm | L1-cold | L2
    phases: Dict[str, int] = field(default_factory=dict)
    bytes_fetched: int = 0


@dataclass
class Node:
    node_id: int
    cache: L1Cache
    online: bool = True
    l0_model: Optional[str] = None
    l0_first_call_pending: bool = False
    busy: bool = False
    busy_kind: Optional[str] = None  # serve | warm-setup
    busy_since: int = 0
    current_req: Optional[Request] = None
    queue: deque = field(default_factory=deque)
    expected_free_at: int = 0
    epoch: int = 0  # bumped on failure to invalidate stale completions
    online_since: int = 0
    online_micros: int = 0
    busy_micros: int = 0
    warm_setup_micros: int = 0
    failures: int = 0
    pinned_model: Optional[str] = None


class Simulator:
    def __init__(
        self,
        catalog: Dict[str, CatalogModel],
        trace: Trace,
        config: PolicyConfig,
        fleet: dict,
        n_nodes: int = 24,
        seed: int = 7,
        enable_failures: bool = True,
        slo_seconds: tuple = (30.0, 60.0, 120.0),
    ) -> None:
        self.catalog = catalog
        self.trace = trace
        self.config = config
        self.fleet = fleet
        self.rng = random.Random((seed, trace.name, config.label()).__repr__())
        self.enable_failures = enable_failures
        self.slo_seconds = slo_seconds
        self.now = 0
        self._heap: List[tuple] = []
        self._seq = 0
        self.nodes = [
            Node(node_id=i, cache=L1Cache(fleet["l1_capacity_bytes"], config.eviction))
            for i in range(n_nodes)
        ]
        self.requests: List[Request] = []
        self.completed: List[Request] = []
        self.rejected: List[Request] = []
        self.failed: List[Request] = []
        self.bytes_fetched_total = 0
        self.prefetch_bytes = 0
        self.window_events: deque = deque()  # (t, model_id) for warm policy
        self._next_warm_refresh = config.warm_window_micros
        # Outstanding (non-terminal) requests; failure/recover cycles stop
        # rescheduling once this reaches zero so the event heap can drain.
        self.pending_requests = 0

    # ----- event plumbing -----

    def _push(self, t: int, kind: str, payload) -> None:
        if t < self.now:
            raise InvariantViolation(
                f"event {kind} scheduled at {t} before now={self.now}"
            )
        self._seq += 1
        heapq.heappush(self._heap, (t, self._seq, kind, payload))

    # ----- setup-cost estimation used by placement and warm policy -----

    def _est_setup_micros(self, node: Node, model: CatalogModel) -> int:
        if node.l0_model == model.model_id:
            return 0
        total = 0
        if node.l0_model is not None:
            total += self.fleet["gpu_release_micros"]
        entry = node.cache.entries.get(model.model_id)
        if entry is None:
            total += transfer_micros(
                model.artifact_bytes, self.fleet["l2_fetch_bytes_per_s"]
            )
        if self.config.strategy == "snapshot":
            if (entry is None or not entry.prewarmed) and model.local_full_read_micros:
                total += model.local_full_read_micros
            total += model.ready_dist.median_micros()
        else:
            total += model.conventional_ready_micros
        return total

    # ----- run -----

    def run(self) -> dict:
        for req_id, (t, model_id) in enumerate(self.trace.requests):
            if model_id not in self.catalog:
                raise InvariantViolation(f"trace references unknown model {model_id}")
            req = Request(req_id=req_id, model_id=model_id, arrival=t)
            self.requests.append(req)
            self._push(t, "arrival", req)
        self.pending_requests = len(self.requests)
        if self.enable_failures:
            for node in self.nodes:
                self._schedule_failure(node)
        if self.config.warm != "none":
            self._push(self._next_warm_refresh, "warm-refresh", None)

        while self._heap:
            # Once every request is terminal, the only events left are
            # far-future failure/recover/warm ticks; advancing the clock to
            # them would inflate the makespan and reserved GPU-hours.
            if self.pending_requests == 0:
                self._heap.clear()
                break
            t, _, kind, payload = heapq.heappop(self._heap)
            if t < self.now:
                raise InvariantViolation(f"time went backwards: {t} < {self.now}")
            self.now = t
            handler = getattr(self, f"_on_{kind.replace('-', '_')}")
            handler(payload)

        self._finalize_accounting()
        self.verify()
        from .report import build_report  # local import to avoid a cycle

        return build_report(self)

    # ----- event handlers -----

    def _on_arrival(self, req: Request) -> None:
        self.window_events.append((self.now, req.model_id))
        self._dispatch(req)

    def _dispatch(self, req: Request) -> None:
        model = self.catalog[req.model_id]
        node_id = choose_node(
            self.config,
            self.nodes,
            model,
            self.now,
            lambda n, m: self._est_setup_micros(n, m),
        )
        if node_id is None:
            if self.config.admission == "bounded-queue" and any(
                n.online for n in self.nodes
            ):
                req.outcome = "rejected"
                self.rejected.append(req)
                self.pending_requests -= 1
                return
            # No online capacity: back off and re-dispatch after recovery.
            req.capacity_attempts += 1
            if req.capacity_attempts > MAX_NO_CAPACITY_ATTEMPTS:
                req.outcome = "failed"
                self.failed.append(req)
                self.pending_requests -= 1
                return
            self._push(self.now + NO_CAPACITY_BACKOFF_MICROS, "redispatch", req)
            return
        node = self.nodes[node_id]
        node.queue.append(req)
        self._maybe_start(node)

    def _on_redispatch(self, req: Request) -> None:
        self._dispatch(req)

    def _maybe_start(self, node: Node) -> None:
        if node.busy or not node.online or not node.queue:
            return
        req = node.queue.popleft()
        self._start_service(node, req)

    def _start_service(self, node: Node, req: Request) -> None:
        model = self.catalog[req.model_id]
        req.dispatch = self.now
        req.node_id = node.node_id
        req.phases["wait"] = self.now - req.arrival
        if req.phases["wait"] < 0:
            raise InvariantViolation(f"negative queue wait for req {req.req_id}")

        teardown = fetch = prewarm = setup = 0
        if node.l0_model == model.model_id:
            tier = "L0"
            inference = (
                model.call1_dist.sample(self.rng)
                if node.l0_first_call_pending
                else model.call2_dist.sample(self.rng)
            )
        else:
            if node.l0_model is not None:
                teardown = self.fleet["gpu_release_micros"]
            entry = node.cache.entries.get(model.model_id)
            if entry is not None:
                self._check_digest(entry, model)
                tier = "L1-warm" if entry.prewarmed else "L1-cold"
                node.cache.touch(
                    model.model_id, self.now, model.ready_dist.median_micros()
                )
            else:
                tier = "L2"
                fetch = transfer_micros(
                    model.artifact_bytes, self.fleet["l2_fetch_bytes_per_s"]
                )
                req.bytes_fetched = model.artifact_bytes
                self.bytes_fetched_total += model.artifact_bytes
                # The current L0 model's artifact is evictable: a GPU-resident
                # model no longer needs its NVMe copy, and pinning it can make
                # two catalog-max artifacts unsatisfiable at low L1 capacity.
                node.cache.insert(
                    model.model_id,
                    model.artifact_bytes,
                    model.artifact_digest,
                    self.now,
                    model.ready_dist.median_micros(),
                    prewarmed=False,
                )
                entry = node.cache.entries[model.model_id]
            if self.config.strategy == "snapshot":
                if not entry.prewarmed and model.local_full_read_micros:
                    prewarm = model.local_full_read_micros
                entry.prewarmed = True
                setup = model.ready_dist.sample(self.rng)
            else:
                setup = model.conventional_ready_micros
            node.l0_model = model.model_id
            inference = model.call1_dist.sample(self.rng)
            node.l0_first_call_pending = False
        if tier == "L0" and node.l0_first_call_pending:
            node.l0_first_call_pending = False

        for label, value in (
            ("teardown", teardown),
            ("fetch", fetch),
            ("prewarm", prewarm),
            ("setup", setup),
            ("inference", inference),
        ):
            if value < 0:
                raise InvariantViolation(f"negative {label} phase for {req.req_id}")
            req.phases[label] = value

        req.cache_tier = tier
        total = teardown + fetch + prewarm + setup + inference
        req.ready_at = self.now + teardown + fetch + prewarm + setup
        req.response_at = self.now + total
        node.busy = True
        node.busy_kind = "serve"
        node.busy_since = self.now
        node.current_req = req
        node.expected_free_at = req.response_at
        self._push(req.response_at, "service_complete", (node.node_id, node.epoch, req))
        self._maybe_prefetch(node, model)

    def _on_service_complete(self, payload) -> None:
        node_id, epoch, req = payload
        node = self.nodes[node_id]
        if epoch != node.epoch:
            return  # canceled by a node failure
        node.busy = False
        node.busy_kind = None
        node.current_req = None
        node.busy_micros += self.now - node.busy_since
        req.outcome = "completed"
        self.completed.append(req)
        self.pending_requests -= 1
        self._maybe_start(node)

    def _maybe_prefetch(self, node: Node, model: CatalogModel) -> None:
        if self.config.prefetch != "pipeline-next":
            return
        succ_id = pipeline_successor(self.catalog, model.model_id)
        if succ_id is None or node.cache.contains(succ_id):
            return
        succ = self.catalog[succ_id]
        if succ.artifact_bytes > node.cache.capacity_bytes:
            return
        duration = transfer_micros(
            succ.artifact_bytes, self.fleet["l2_fetch_bytes_per_s"]
        )
        self._push(
            self.now + duration,
            "prefetch_complete",
            (node.node_id, node.epoch, succ_id),
        )

    def _on_prefetch_complete(self, payload) -> None:
        node_id, epoch, model_id = payload
        node = self.nodes[node_id]
        if epoch != node.epoch or not node.online or node.cache.contains(model_id):
            return
        model = self.catalog[model_id]
        pinned = {node.l0_model} if node.l0_model else set()
        if node.current_req is not None:
            pinned.add(node.current_req.model_id)
        try:
            node.cache.insert(
                model_id,
                model.artifact_bytes,
                model.artifact_digest,
                self.now,
                model.ready_dist.median_micros(),
                prewarmed=False,
                pinned=pinned,
            )
        except Exception:
            return  # prefetch is best-effort; never fail a run over it
        self.prefetch_bytes += model.artifact_bytes
        self.bytes_fetched_total += model.artifact_bytes

    # ----- warm capacity -----

    def _on_warm_refresh(self, _payload) -> None:
        cutoff = self.now - self.config.warm_window_micros
        while self.window_events and self.window_events[0][0] < cutoff:
            self.window_events.popleft()
        counts: Dict[str, int] = {}
        for _, model_id in self.window_events:
            counts[model_id] = counts.get(model_id, 0) + 1
        assignments = warm_pin_assignments(self.config, counts, self.nodes)
        for node in self.nodes:
            node.pinned_model = assignments.get(node.node_id)
        for node_id, model_id in sorted(assignments.items()):
            node = self.nodes[node_id]
            if node.online and not node.busy and node.l0_model != model_id:
                self._start_warm_setup(node, self.catalog[model_id])
        if self._heap or self.window_events:
            self._next_warm_refresh = self.now + self.config.warm_window_micros
            # Stop refreshing once no future demand exists so the run drains.
            if any(k == "arrival" for _, _, k, _ in self._heap):
                self._push(self._next_warm_refresh, "warm-refresh", None)

    def _start_warm_setup(self, node: Node, model: CatalogModel) -> None:
        teardown = self.fleet["gpu_release_micros"] if node.l0_model else 0
        fetch = 0
        entry = node.cache.entries.get(model.model_id)
        if entry is None:
            fetch = transfer_micros(
                model.artifact_bytes, self.fleet["l2_fetch_bytes_per_s"]
            )
            self.bytes_fetched_total += model.artifact_bytes
            node.cache.insert(
                model.model_id,
                model.artifact_bytes,
                model.artifact_digest,
                self.now,
                model.ready_dist.median_micros(),
                prewarmed=False,
            )
            entry = node.cache.entries[model.model_id]
        prewarm = 0
        if self.config.strategy == "snapshot":
            if not entry.prewarmed and model.local_full_read_micros:
                prewarm = model.local_full_read_micros
            entry.prewarmed = True
            setup = model.ready_dist.sample(self.rng)
        else:
            setup = model.conventional_ready_micros
        total = teardown + fetch + prewarm + setup
        node.busy = True
        node.busy_kind = "warm-setup"
        node.busy_since = self.now
        node.expected_free_at = self.now + total
        self._push(
            self.now + total, "warm_setup_complete", (node.node_id, node.epoch, model.model_id)
        )

    def _on_warm_setup_complete(self, payload) -> None:
        node_id, epoch, model_id = payload
        node = self.nodes[node_id]
        if epoch != node.epoch:
            return
        node.busy = False
        node.busy_kind = None
        elapsed = self.now - node.busy_since
        node.busy_micros += elapsed
        node.warm_setup_micros += elapsed
        node.l0_model = model_id
        node.l0_first_call_pending = True
        self._maybe_start(node)

    # ----- failures -----

    def _schedule_failure(self, node: Node) -> None:
        if self.pending_requests <= 0:
            return
        delta = self.rng.expovariate(1.0 / self.fleet["node_mtbf_micros"])
        self._push(self.now + max(1, int(delta)), "node_failure", node.node_id)

    def _on_node_failure(self, node_id: int) -> None:
        if self.pending_requests <= 0:
            return
        node = self.nodes[node_id]
        if not node.online:
            return
        node.online = False
        node.failures += 1
        node.epoch += 1
        node.online_micros += self.now - node.online_since
        if node.busy:
            node.busy_micros += self.now - node.busy_since
            node.busy = False
            node.busy_kind = None
        node.l0_model = None
        node.l0_first_call_pending = False
        node.cache.drop_all()
        victims = []
        if node.current_req is not None:
            victims.append(node.current_req)
            node.current_req = None
        victims.extend(node.queue)
        node.queue.clear()
        for req in victims:
            req.retries += 1
            req.dispatch = None
            req.ready_at = None
            req.response_at = None
            req.node_id = None
            req.cache_tier = None
            req.phases = {}
            if req.retries > MAX_RETRIES:
                req.outcome = "failed"
                self.failed.append(req)
                self.pending_requests -= 1
            else:
                self._dispatch(req)
        self._push(
            self.now + self.fleet["node_reprovision_micros"], "node_recover", node_id
        )

    def _on_node_recover(self, node_id: int) -> None:
        node = self.nodes[node_id]
        node.online = True
        node.online_since = self.now
        if self.enable_failures:
            self._schedule_failure(node)
        self._maybe_start(node)

    # ----- verification -----

    def _check_digest(self, entry, model: CatalogModel) -> None:
        if entry.digest != model.artifact_digest:
            raise InvariantViolation(
                f"stale artifact for {model.model_id}: cached {entry.digest} "
                f"!= catalog {model.artifact_digest}"
            )

    def _finalize_accounting(self) -> None:
        for node in self.nodes:
            if node.online:
                node.online_micros += self.now - node.online_since
                node.online_since = self.now
            if node.busy:
                node.busy_micros += self.now - node.busy_since
                node.busy = False

    def verify(self) -> None:
        terminal = len(self.completed) + len(self.rejected) + len(self.failed)
        if terminal != len(self.requests):
            raise InvariantViolation(
                f"request conservation broken: {len(self.requests)} arrivals, "
                f"{terminal} terminal outcomes"
            )
        for req in self.completed:
            if req.response_at is None or req.dispatch is None:
                raise InvariantViolation(f"completed req {req.req_id} lacks timestamps")
            if not (req.arrival <= req.dispatch <= req.ready_at <= req.response_at):
                raise InvariantViolation(
                    f"non-causal timestamps for req {req.req_id}"
                )
            for label, value in req.phases.items():
                if value < 0:
                    raise InvariantViolation(
                        f"negative phase {label} for req {req.req_id}"
                    )
        for node in self.nodes:
            used = sum(e.num_bytes for e in node.cache.entries.values())
            if used != node.cache.used_bytes:
                raise InvariantViolation(
                    f"node {node.node_id} cache accounting drift"
                )
            if node.cache.used_bytes > node.cache.capacity_bytes:
                raise InvariantViolation(
                    f"node {node.node_id} L1 over capacity"
                )
            if node.busy_micros > node.online_micros + 1:
                raise InvariantViolation(
                    f"node {node.node_id} busy longer than online (free capacity)"
                )
