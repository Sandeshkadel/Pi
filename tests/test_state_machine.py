import pytest

from app.core.state import AgentState, AgentStateMachine, InvalidStateTransition


def test_state_machine_accepts_complete_permission_flow() -> None:
    machine = AgentStateMachine()
    path = (
        AgentState.LISTENING,
        AgentState.TRANSCRIBING,
        AgentState.THINKING,
        AgentState.WAITING_FOR_PERMISSION,
        AgentState.EXECUTING,
        AgentState.VERIFYING,
        AgentState.RESPONDING,
        AgentState.IDLE,
    )

    for state in path:
        assert machine.transition(state) is state


def test_state_machine_rejects_illegal_transition() -> None:
    machine = AgentStateMachine()

    with pytest.raises(InvalidStateTransition):
        machine.transition(AgentState.EXECUTING)

    assert machine.state is AgentState.IDLE


@pytest.mark.parametrize(
    "state",
    [
        AgentState.IDLE,
        AgentState.LISTENING,
        AgentState.TRANSCRIBING,
        AgentState.THINKING,
        AgentState.WAITING_FOR_PERMISSION,
        AgentState.EXECUTING,
        AgentState.VERIFYING,
        AgentState.RESPONDING,
        AgentState.ERROR,
    ],
)
def test_emergency_stop_is_allowed_from_every_active_state(state: AgentState) -> None:
    machine = AgentStateMachine()
    if state is not AgentState.IDLE:
        machine.transition(AgentState.LISTENING)
        if state not in {AgentState.LISTENING, AgentState.IDLE}:
            machine.transition(AgentState.TRANSCRIBING)
        if state in {
            AgentState.THINKING,
            AgentState.WAITING_FOR_PERMISSION,
            AgentState.EXECUTING,
            AgentState.VERIFYING,
            AgentState.RESPONDING,
            AgentState.ERROR,
        }:
            machine.transition(AgentState.THINKING)
        if state is AgentState.WAITING_FOR_PERMISSION:
            machine.transition(AgentState.WAITING_FOR_PERMISSION)
        elif state in {AgentState.EXECUTING, AgentState.VERIFYING}:
            machine.transition(AgentState.EXECUTING)
            if state is AgentState.VERIFYING:
                machine.transition(AgentState.VERIFYING)
        elif state is AgentState.RESPONDING:
            machine.transition(AgentState.RESPONDING)
        elif state is AgentState.ERROR:
            machine.transition(AgentState.ERROR)

    assert machine.transition(AgentState.STOPPED) is AgentState.STOPPED


def test_stopped_state_only_restarts_at_idle() -> None:
    machine = AgentStateMachine()
    machine.transition(AgentState.STOPPED)

    with pytest.raises(InvalidStateTransition):
        machine.transition(AgentState.LISTENING)

    assert machine.transition(AgentState.IDLE) is AgentState.IDLE
