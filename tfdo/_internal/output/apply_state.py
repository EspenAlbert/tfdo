from __future__ import annotations

import logging
import time
from enum import StrEnum
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from tfdo._internal.output.diagnostic_link import resolve_resource_addr
from tfdo._internal.output.models import Change, PlanOutput, ResourceAction, ResourceChange
from tfdo._internal.output.stream_models import (
    ApplyHookEvent,
    ApplyOutputValue,
    ChangeSummaryEvent,
    DiagnosticBody,
    DiagnosticEvent,
    OutputsEvent,
    PlannedChangeEvent,
    RefreshEvent,
    parse_stream_line,
)
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

MANAGED_HOOK_ACTIONS = frozenset({"create", "update", "delete", "replace"})
REPLACE_PLAN_ACTIONS = frozenset({ResourceAction.REPLACE_DESTROY_FIRST, ResourceAction.REPLACE_CREATE_FIRST})
PRE_APPLY_REFRESH_START = "apply: refreshing state…"
PRE_APPLY_REFRESH_COMPLETE = "apply: refresh complete"
_PLANNED_READ = "read"


class ApplyResourceStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERRORED = "errored"


_UNRESOLVED_BLOCKER_STATUSES = frozenset({ApplyResourceStatus.PENDING, ApplyResourceStatus.IN_PROGRESS})


class ApplyPhase(StrEnum):
    PRE_APPLY = "pre_apply"
    APPLYING = "applying"
    DONE = "done"


class ApplyResourceState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    addr: str
    status: ApplyResourceStatus = ApplyResourceStatus.PENDING
    plan_action: ResourceAction
    hook_action: str | None = None
    started_at: float | None = None
    elapsed_seconds: float | None = None
    diagnostic: DiagnosticBody | None = None


class DiagnosticEmission(NamedTuple):
    diagnostic: DiagnosticBody
    resource_addr: str | None


class CompletionEmission(NamedTuple):
    addr: str
    errored: bool
    elapsed_seconds: float | None
    hook_action: str | None


class ApplyProgressState:
    def __init__(
        self,
        plan: PlanOutput,
        blockers: dict[str, frozenset[str]] | None = None,
        *,
        hide_provision_output: bool = False,
        settings: TfDoSettings | None = None,
    ) -> None:
        self._settings = settings or TfDoSettings.from_env()
        seeded = seed_apply_addrs(plan)
        self.resources: dict[str, ApplyResourceState] = {
            addr: ApplyResourceState(addr=addr, plan_action=action) for addr, action in seeded.items()
        }
        self.blockers = blockers or {}
        self.phase = ApplyPhase.PRE_APPLY
        self.hide_provision_output = hide_provision_output
        self.terminal_summary: ChangeSummaryEvent | None = None
        self.post_apply_outputs: dict[str, ApplyOutputValue] | None = None
        self._post_apply_outputs_received = False
        self.orphan_diagnostic: DiagnosticBody | None = None
        self._provision_logs: list[tuple[str, str]] = []
        self.pre_apply_logs: list[str] = []
        self._carry = ""
        self._refresh_in_flight: set[str] = set()
        self._refresh_start_logged = False
        self._refresh_end_logged = False
        self._saw_plan_change_summary = False
        self._saw_planned_change = False
        self._pending_error_addr: str | None = None
        self._diagnostic_emissions: list[DiagnosticEmission] = []
        self._completion_emissions: list[CompletionEmission] = []
        self._interim_replace_addrs: set[str] = set()

    @property
    def total_count(self) -> int:
        return len(self.resources)

    @property
    def completed_count(self) -> int:
        return sum(1 for addr in self.resources if self.counts_toward_completed(addr))

    def drain_completion_emissions(self) -> list[CompletionEmission]:
        emissions = self._completion_emissions
        self._completion_emissions = []
        return emissions

    def ingest_line(self, line: str) -> None:
        stripped = line.strip()
        if stripped:
            self._handle_line(stripped)

    def counts_toward_completed(self, addr: str) -> bool:
        resource = self.resources[addr]
        if resource.status not in (ApplyResourceStatus.COMPLETED, ApplyResourceStatus.ERRORED):
            return False
        return addr not in self._interim_replace_addrs

    def drain_pre_apply_logs(self) -> list[str]:
        logs = self.pre_apply_logs
        self.pre_apply_logs = []
        return logs

    def drain_provision_logs(self) -> list[tuple[str, str]]:
        logs = self._provision_logs
        self._provision_logs = []
        return logs

    def resolved_output_values(self) -> dict[str, object] | None:
        if not self.post_apply_outputs:
            return None
        values = {name: entry.value for name, entry in self.post_apply_outputs.items() if entry.value is not None}
        return values or None

    @property
    def post_apply_outputs_received(self) -> bool:
        return self._post_apply_outputs_received

    def drain_diagnostic_emissions(self) -> list[DiagnosticEmission]:
        emissions = self._diagnostic_emissions
        self._diagnostic_emissions = []
        return emissions

    def active_blockers(self, addr: str) -> list[str]:
        predecessors = self.blockers.get(addr, frozenset())
        waiting_on = {other for other in predecessors if self.resources[other].status in _UNRESOLVED_BLOCKER_STATUSES}
        return sorted(waiting_on)

    def pending_resources_sorted(self) -> list[ApplyResourceState]:
        pending = [resource for resource in self.resources.values() if resource.status == ApplyResourceStatus.PENDING]
        pending_addrs = frozenset(resource.addr for resource in pending)
        depth_memo: dict[str, int] = {}

        def sort_key(resource: ApplyResourceState) -> tuple[int, int, int, str]:
            unresolved = self._unresolved_blockers(resource.addr)
            in_progress_count = sum(
                1 for other in unresolved if self.resources[other].status == ApplyResourceStatus.IN_PROGRESS
            )
            depth = self._pending_depth(resource.addr, pending_addrs, depth_memo)
            return (len(unresolved), in_progress_count, depth, resource.addr)

        return sorted(pending, key=sort_key)

    def _unresolved_blockers(self, addr: str) -> list[str]:
        predecessors = self.blockers.get(addr, frozenset())
        return [other for other in predecessors if self.resources[other].status in _UNRESOLVED_BLOCKER_STATUSES]

    def _pending_depth(self, addr: str, pending_addrs: frozenset[str], memo: dict[str, int]) -> int:
        if addr in memo:
            return memo[addr]
        predecessors = self.blockers.get(addr, frozenset()) & pending_addrs
        if not predecessors:
            memo[addr] = 0
        else:
            memo[addr] = 1 + max(self._pending_depth(other, pending_addrs, memo) for other in predecessors)
        return memo[addr]

    def feed_line(self, chunk: str) -> None:
        self._carry += chunk
        while "\n" in self._carry:
            line, self._carry = self._carry.split("\n", 1)
            stripped = line.strip()
            if stripped:
                self._handle_line(stripped)

    def flush(self) -> None:
        if self._carry.strip():
            self._handle_line(self._carry.strip())
        self._carry = ""

    def _handle_line(self, line: str) -> None:
        data = parse_stream_line(line, settings=self._settings)
        if data is None:
            return
        msg_type = data.get("type")
        if not isinstance(msg_type, str):
            return
        if self.phase == ApplyPhase.PRE_APPLY and self._handle_pre_apply(msg_type, data):
            return
        if msg_type == "outputs":
            self._on_outputs(OutputsEvent.model_validate(data))
            return
        if self.phase == ApplyPhase.DONE:
            return
        self._dispatch_applying(msg_type, data)

    def _dispatch_applying(self, msg_type: str, data: dict[str, object]) -> None:
        match msg_type:
            case "apply_start":
                self._on_apply_start(ApplyHookEvent.model_validate(data))
            case "apply_progress":
                self._on_apply_progress(ApplyHookEvent.model_validate(data))
            case "apply_complete":
                self._on_apply_complete(ApplyHookEvent.model_validate(data))
            case "apply_errored":
                self._on_apply_errored(ApplyHookEvent.model_validate(data))
            case "diagnostic":
                self._on_diagnostic(DiagnosticEvent.model_validate(data))
            case "provision_start" | "provision_progress" | "provision_complete" | "provision_errored":
                self._on_provision(msg_type, ApplyHookEvent.model_validate(data))
            case "change_summary":
                self._on_change_summary(ChangeSummaryEvent.model_validate(data))
            case _:
                pass

    def _handle_pre_apply(self, msg_type: str, data: dict[str, object]) -> bool:
        match msg_type:
            case "refresh_start":
                event = RefreshEvent.model_validate(data)
                self._on_pre_apply_refresh_start(event)
            case "refresh_complete":
                event = RefreshEvent.model_validate(data)
                self._on_pre_apply_refresh_complete(event)
            case "planned_change":
                self._saw_planned_change = True
                self._maybe_end_pre_apply_refresh()
            case "change_summary":
                summary = ChangeSummaryEvent.model_validate(data)
                if summary.changes and summary.changes.operation == "plan":
                    self._saw_plan_change_summary = True
                    self._maybe_end_pre_apply_refresh()
            case "apply_start":
                if self._try_enter_applying(ApplyHookEvent.model_validate(data)):
                    self._handle_line_after_applying(data)
                    return True
            case "diagnostic":
                self._on_diagnostic(DiagnosticEvent.model_validate(data))
            case _:
                pass
        return False

    def _handle_line_after_applying(self, data: dict[str, object]) -> None:
        msg_type = data.get("type")
        if not isinstance(msg_type, str):
            return
        match msg_type:
            case "apply_start":
                self._on_apply_start(ApplyHookEvent.model_validate(data))
            case _:
                pass

    def _try_enter_applying(self, event: ApplyHookEvent) -> bool:
        if self.phase != ApplyPhase.PRE_APPLY:
            return True
        if not self._is_managed_apply_start(event):
            return False
        if not self._ready_for_applying_phase():
            return False
        self.phase = ApplyPhase.APPLYING
        return True

    def _ready_for_applying_phase(self) -> bool:
        if self._saw_plan_change_summary:
            return True
        if self._saw_planned_change:
            return True
        return not self._refresh_start_logged

    def _on_pre_apply_refresh_start(self, event: RefreshEvent) -> None:
        if event.hook and event.hook.resource:
            self._refresh_in_flight.add(event.hook.resource.addr)
        if not self._refresh_start_logged:
            self._refresh_start_logged = True
            self.pre_apply_logs.append(PRE_APPLY_REFRESH_START)

    def _on_pre_apply_refresh_complete(self, event: RefreshEvent) -> None:
        if event.hook and event.hook.resource:
            self._refresh_in_flight.discard(event.hook.resource.addr)
        if not self._refresh_in_flight:
            self._maybe_end_pre_apply_refresh()

    def _maybe_end_pre_apply_refresh(self) -> None:
        if self._refresh_start_logged and not self._refresh_end_logged:
            self._refresh_end_logged = True
            self.pre_apply_logs.append(PRE_APPLY_REFRESH_COMPLETE)

    def _is_managed_apply_start(self, event: ApplyHookEvent) -> bool:
        if event.hook is None or event.hook.resource is None:
            return False
        action = event.hook.action
        return action in MANAGED_HOOK_ACTIONS

    def _tracked_addr(self, event: ApplyHookEvent) -> str | None:
        if event.hook is None or event.hook.resource is None:
            return None
        addr = event.hook.resource.addr
        if addr not in self.resources:
            return None
        if event.hook.action == "read":
            return None
        return addr

    def _on_apply_start(self, event: ApplyHookEvent) -> None:
        if self.phase == ApplyPhase.PRE_APPLY and not self._try_enter_applying(event):
            return
        addr = self._tracked_addr(event)
        if addr is None:
            return
        resource = self.resources[addr]
        if resource.status == ApplyResourceStatus.PENDING:
            resource.status = ApplyResourceStatus.IN_PROGRESS
        elif addr in self._interim_replace_addrs:
            self._interim_replace_addrs.discard(addr)
            resource.status = ApplyResourceStatus.IN_PROGRESS
        else:
            return
        resource.started_at = time.monotonic()
        if event.hook:
            resource.hook_action = event.hook.action

    def _on_apply_progress(self, event: ApplyHookEvent) -> None:
        addr = self._tracked_addr(event)
        if addr is None or event.hook is None:
            return
        if event.hook.elapsed_seconds is not None:
            self.resources[addr].elapsed_seconds = event.hook.elapsed_seconds

    def _on_apply_complete(self, event: ApplyHookEvent) -> None:
        addr = self._tracked_addr(event)
        if addr is None:
            return
        resource = self.resources[addr]
        hook_action = event.hook.action if event.hook else None
        if event.hook and event.hook.elapsed_seconds is not None:
            resource.elapsed_seconds = event.hook.elapsed_seconds
        if resource.plan_action in REPLACE_PLAN_ACTIONS and hook_action == "delete":
            resource.status = ApplyResourceStatus.COMPLETED
            self._interim_replace_addrs.add(addr)
        else:
            resource.status = ApplyResourceStatus.COMPLETED
            self._interim_replace_addrs.discard(addr)
        self._enqueue_completion(addr, errored=False, resource=resource, hook_action=hook_action)
        self._pending_error_addr = None

    def _on_apply_errored(self, event: ApplyHookEvent) -> None:
        addr = self._tracked_addr(event)
        if addr is None:
            return
        resource = self.resources[addr]
        hook_action = event.hook.action if event.hook else None
        if event.hook and event.hook.elapsed_seconds is not None:
            resource.elapsed_seconds = event.hook.elapsed_seconds
        resource.status = ApplyResourceStatus.ERRORED
        self._interim_replace_addrs.discard(addr)
        self._enqueue_completion(addr, errored=True, resource=resource, hook_action=hook_action)
        self._pending_error_addr = addr

    def _enqueue_completion(
        self,
        addr: str,
        *,
        errored: bool,
        resource: ApplyResourceState,
        hook_action: str | None,
    ) -> None:
        self._completion_emissions.append(
            CompletionEmission(
                addr=addr,
                errored=errored,
                elapsed_seconds=resource.elapsed_seconds,
                hook_action=hook_action,
            )
        )

    def _on_diagnostic(self, event: DiagnosticEvent) -> None:
        diag = event.diagnostic
        if diag is None:
            return
        candidates = frozenset(self.resources)
        resource_addr = resolve_resource_addr(
            diag,
            pending_hook_addr=self._pending_error_addr,
            candidate_addrs=candidates,
        )
        self._diagnostic_emissions.append(DiagnosticEmission(diag, resource_addr))
        addr = resource_addr
        if addr is None:
            self.orphan_diagnostic = diag
            self._pending_error_addr = None
            return
        resource = self.resources.get(addr)
        if resource is None:
            self.orphan_diagnostic = diag
            self._pending_error_addr = None
            return
        resource.diagnostic = diag
        if resource.status in (ApplyResourceStatus.PENDING, ApplyResourceStatus.IN_PROGRESS):
            resource.status = ApplyResourceStatus.ERRORED
        self._pending_error_addr = None

    def _on_provision(self, msg_type: str, event: ApplyHookEvent) -> None:
        if self.hide_provision_output or event.hook is None or event.hook.resource is None:
            return
        addr = event.hook.resource.addr
        text = event.hook.output if msg_type == "provision_progress" else event.message
        self._provision_logs.append((addr, text or msg_type))

    def _on_change_summary(self, event: ChangeSummaryEvent) -> None:
        if event.changes is None:
            return
        operation = event.changes.operation
        if operation not in ("apply", "destroy"):
            return
        self.terminal_summary = event
        self.phase = ApplyPhase.DONE

    def _on_outputs(self, event: OutputsEvent) -> None:
        if self.terminal_summary is None:
            return
        self.post_apply_outputs = event.outputs
        self._post_apply_outputs_received = True


def seed_apply_addrs(plan: PlanOutput) -> dict[str, ResourceAction]:
    result: dict[str, ResourceAction] = {}
    for rc in plan.resource_changes:
        action = rc.change.action()
        if action in (ResourceAction.NO_OP, ResourceAction.READ):
            continue
        result[rc.address] = action
    return result


def plan_has_applyable_changes(plan: PlanOutput) -> bool:
    if plan.applyable is not None:
        return plan.applyable
    if seed_apply_addrs(plan):
        return True
    return any(oc.actions != ["no-op"] for oc in plan.output_changes.values())


def plan_from_planned_changes(lines: list[str], *, settings: TfDoSettings | None = None) -> PlanOutput:
    settings = settings or TfDoSettings.from_env()
    changes: list[ResourceChange] = []
    seen: set[str] = set()
    for line in lines:
        data = parse_stream_line(line, settings=settings)
        if data is None or data.get("type") != "planned_change":
            continue
        event = PlannedChangeEvent.model_validate(data)
        if event.change is None:
            continue
        addr = event.change.resource.addr
        if addr in seen:
            continue
        hook_action = event.change.action
        if hook_action == _PLANNED_READ:
            continue
        actions = _hook_action_to_plan_actions(hook_action)
        seen.add(addr)
        changes.append(
            ResourceChange(
                address=addr,
                mode="managed",
                type="unknown",
                name="unknown",
                change=Change(actions=actions),
            )
        )
    return PlanOutput(format_version="1.2", errored=False, resource_changes=changes)


def _hook_action_to_plan_actions(hook_action: str) -> list[str]:
    match hook_action:
        case "replace":
            return ["delete", "create"]
        case "delete+create" | "create+delete":
            return list(hook_action.split("+"))
        case _:
            return [hook_action]
