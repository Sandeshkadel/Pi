"""Validated core-agent state transitions."""

from enum import StrEnum
from types import MappingProxyType


class AgentState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESPONDING = "responding"
    ERROR = "error"
    STOPPED = "stopped"


class InvalidStateTransition(ValueError):
    """Raised when a requested state transition is not part of the state graph."""


_TRANSITIONS = MappingProxyType(
    {
        AgentState.IDLE: frozenset({AgentState.LISTENING}),
        AgentState.LISTENING: frozenset(
            {AgentState.TRANSCRIBING, AgentState.RESPONDING, AgentState.ERROR}
        ),
        AgentState.TRANSCRIBING: frozenset(
            {AgentState.THINKING, AgentState.RESPONDING, AgentState.ERROR}
        ),
        AgentState.THINKING: frozenset(
            {
                AgentState.WAITING_FOR_PERMISSION,
                AgentState.EXECUTING,
                AgentState.RESPONDING,
                AgentState.ERROR,
            }
        ),
        AgentState.WAITING_FOR_PERMISSION: frozenset(
            {AgentState.EXECUTING, AgentState.RESPONDING, AgentState.ERROR}
        ),
        AgentState.EXECUTING: frozenset({AgentState.VERIFYING, AgentState.ERROR}),
        AgentState.VERIFYING: frozenset({AgentState.RESPONDING, AgentState.ERROR}),
        AgentState.RESPONDING: frozenset(
            {AgentState.IDLE, AgentState.LISTENING, AgentState.ERROR}
        ),
        AgentState.ERROR: frozenset({AgentState.IDLE}),
        AgentState.STOPPED: frozenset({AgentState.IDLE}),
    }
)


class AgentStateMachine:
    """Per-agent state holder; it deliberately retains no conversation content."""

    def __init__(self) -> None:
        self._state = AgentState.IDLE

    @property
    def state(self) -> AgentState:
        return self._state

    def transition(self, target: AgentState) -> AgentState:
        if target is self._state:
            return self._state
        if target is AgentState.STOPPED and self._state is not AgentState.STOPPED:
            self._state = target
            return self._state
        if target not in _TRANSITIONS[self._state]:
            raise InvalidStateTransition(
                f"Cannot transition from {self._state.value} to {target.value}."
            )
        self._state = target
        return self._state
