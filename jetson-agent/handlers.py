"""Allowlisted simulation handlers with safe/off initial hardware state."""

from typing import Any, Callable, Dict

from command_validator import ValidatedCommand


class HandlerError(ValueError):
    """Raised when a command has no safe simulation handler."""


class SimulatedHardwareState:
    """In-memory state only; it never writes GPIO, PWM, serial, or shell commands."""

    def __init__(self):
        self.outputs_enabled = False
        self.stopped = True
        self.mode = "standby"
        self.speed_percent = 0.0
        self.last_message = ""
        self.safe_state_reason = "startup"

    def to_dict(self):
        return {
            "outputs_enabled": self.outputs_enabled,
            "stopped": self.stopped,
            "mode": self.mode,
            "speed_percent": self.speed_percent,
            "last_message": self.last_message,
            "safe_state_reason": self.safe_state_reason,
        }


Handler = Callable[[ValidatedCommand], Dict[str, Any]]


class HandlerRegistry:
    """Route only known command types to simulation-only functions."""

    def __init__(self, *, dry_run: bool = True) -> None:
        if not dry_run:
            raise HandlerError(
                "DRY_RUN=false is unavailable because real hardware handlers are not implemented"
            )
        self.state = SimulatedHardwareState()
        self._handlers: Dict[str, Handler] = {
            "STOP": self._handle_stop,
            "SET_MODE": self._handle_set_mode,
            "SET_SPEED": self._handle_set_speed,
            "SEND_MESSAGE": self._handle_send_message,
        }

    def handle(self, command: ValidatedCommand) -> Dict[str, Any]:
        handler = self._handlers.get(command.command_type)
        if handler is None:
            raise HandlerError("Command type has no allowlisted handler")
        return handler(command)

    def enter_safe_state(self, reason: str) -> Dict[str, Any]:
        """Reset every simulated hardware output to its safe/off state."""

        self.state.outputs_enabled = False
        self.state.stopped = True
        self.state.mode = "standby"
        self.state.speed_percent = 0.0
        self.state.safe_state_reason = reason
        return self._result("SAFE_STATE")

    def _handle_stop(self, _command: ValidatedCommand) -> Dict[str, Any]:
        return self.enter_safe_state("stop_command")

    def _handle_set_mode(self, command: ValidatedCommand) -> Dict[str, Any]:
        self.state.mode = command.payload["mode"]
        self.state.safe_state_reason = "simulation_only"
        return self._result("SET_MODE")

    def _handle_set_speed(self, command: ValidatedCommand) -> Dict[str, Any]:
        self.state.speed_percent = command.payload["speed_percent"]
        self.state.safe_state_reason = "simulation_only"
        # outputs_enabled stays False: this value is never written to hardware.
        return self._result("SET_SPEED")

    def _handle_send_message(self, command: ValidatedCommand) -> Dict[str, Any]:
        # Store text as inert data. It is never passed to a shell or code evaluator.
        self.state.last_message = command.payload["message"]
        self.state.safe_state_reason = "simulation_only"
        return self._result("SEND_MESSAGE")

    def _result(self, action: str) -> Dict[str, Any]:
        return {
            "simulated": True,
            "action": action,
            "hardware_outputs_changed": False,
            "state": self.state.to_dict(),
        }
