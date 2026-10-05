"""Polling loop for the simulation-only Jetson Wi-Fi agent."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypeVar
from uuid import UUID, uuid4

from command_validator import (
    CommandValidationError,
    DuplicateCommandError,
    DuplicateTracker,
    ValidatedCommand,
    validate_command,
)
from config import AgentConfig, ConfigError, load_config
from handlers import HandlerError, HandlerRegistry
from http_transport import TemporaryTransportError, TransportError
from transports.wifi import WifiTransport


MAX_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 0.25
MAX_BACKOFF_SECONDS = 2.0
T = TypeVar("T")


class JetsonAgent:
    """Validate and simulate commands while keeping all outputs safely off."""

    def __init__(
        self,
        *,
        config: AgentConfig,
        transport: Any,
        handlers: HandlerRegistry,
        duplicate_tracker: Optional[DuplicateTracker] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not config.dry_run:
            raise ConfigError(
                "DRY_RUN=false is unavailable until real hardware is explicitly implemented and tested"
            )
        self.config = config
        self.transport = transport
        self.handlers = handlers
        self.duplicate_tracker = duplicate_tracker or DuplicateTracker()
        self._sleep = sleep
        self._logger = logging.getLogger("jetson_agent")
        self._telemetry_sequence = 0

    def run_once(self) -> str:
        """Perform one poll cycle and return a short simulation outcome."""

        device_timestamp = datetime.now(timezone.utc).isoformat()
        simulated_telemetry = self._next_simulated_telemetry()
        try:
            self._with_bounded_retry(
                lambda: self.transport.send_heartbeat(
                    device_timestamp=device_timestamp,
                )
            )
            self._with_bounded_retry(
                lambda: self.transport.send_telemetry(
                    device_timestamp=device_timestamp,
                    data=simulated_telemetry,
                )
            )
        except TransportError:
            self.handlers.enter_safe_state("communication_lost")
            self._logger.warning(
                "Heartbeat or telemetry communication failed; safe state is active"
            )
            return "communication_lost"

        try:
            raw_command = self._with_bounded_retry(self.transport.poll_next)
        except TransportError:
            self.handlers.enter_safe_state("communication_lost")
            self._logger.warning("Backend communication failed; safe state is active")
            return "communication_lost"

        if raw_command is None:
            return "idle"

        try:
            command = validate_command(
                raw_command,
                expected_device_id=self.config.device_id,
            )
        except CommandValidationError:
            self.handlers.enter_safe_state("invalid_command")
            self._best_effort_failed_acknowledgement(raw_command, "validation_failed")
            self._logger.warning("A command failed independent agent validation")
            return "rejected"

        try:
            self.duplicate_tracker.reject_if_duplicate(command.command_id)
        except DuplicateCommandError:
            self.handlers.enter_safe_state("duplicate_command")
            self._best_effort_failed_acknowledgement(raw_command, "duplicate_command")
            self._logger.warning("A duplicate command ID was rejected")
            return "duplicate"

        try:
            self._acknowledge(command, status="running", result={"simulated": True})
        except TransportError:
            self.handlers.enter_safe_state("communication_lost_before_execution")
            self._logger.warning(
                "Running acknowledgement failed; command was not handled and safe state is active"
            )
            return "communication_lost"

        # Mark before the handler so this process cannot repeat the simulated action.
        self.duplicate_tracker.mark_handled(command.command_id)
        try:
            result = self.handlers.handle(command)
        except HandlerError:
            self.handlers.enter_safe_state("handler_failure")
            self._best_effort_acknowledge(command, status="failed", result={
                "simulated": True,
                "error": "handler_failure",
            })
            self._logger.warning("A simulation handler failed; safe state is active")
            return "failed"

        try:
            self._acknowledge(command, status="completed", result=result)
        except TransportError:
            self.handlers.enter_safe_state("communication_lost_after_simulation")
            self._logger.warning(
                "Completion acknowledgement failed; safe state is active"
            )
            return "communication_lost"
        return "completed"

    def _next_simulated_telemetry(self) -> Dict[str, float]:
        """Return deterministic, bounded readings without touching Jetson hardware."""

        phase = self._telemetry_sequence % 5
        self._telemetry_sequence += 1
        return {
            "cpu_temperature_c": 44.0 + phase * 0.4,
            "memory_used_percent": 36.0 + phase,
            "supply_voltage_v": 5.02,
            "wifi_signal_dbm": -54.0 - phase,
        }

    def run_forever(self) -> None:
        """Poll until interrupted, returning to safe state before shutdown."""

        self._logger.info("Simulation-only Jetson agent started")
        try:
            while True:
                self.run_once()
                self._sleep(self.config.poll_interval_seconds)
        except KeyboardInterrupt:
            self.handlers.enter_safe_state("operator_shutdown")
            self._logger.info("Jetson agent stopped with safe state active")

    def _acknowledge(
        self,
        command: ValidatedCommand,
        *,
        status: str,
        result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        acknowledgement_id = str(uuid4())
        return self._with_bounded_retry(
            lambda: self.transport.acknowledge(
                command.command_id,
                acknowledgement_id=acknowledgement_id,
                status=status,
                result=result,
            )
        )

    def _best_effort_acknowledge(
        self,
        command: ValidatedCommand,
        *,
        status: str,
        result: Dict[str, Any],
    ) -> None:
        try:
            self._acknowledge(command, status=status, result=result)
        except TransportError:
            self.handlers.enter_safe_state("communication_lost")

    def _best_effort_failed_acknowledgement(
        self,
        raw_command: Any,
        error_code: str,
    ) -> None:
        if not isinstance(raw_command, dict):
            return
        command_id = raw_command.get("id")
        if not isinstance(command_id, str):
            return
        try:
            normalized_id = str(UUID(command_id))
        except (ValueError, AttributeError):
            return
        try:
            self._with_bounded_retry(
                lambda: self.transport.acknowledge(
                    normalized_id,
                    acknowledgement_id=str(uuid4()),
                    status="failed",
                    result={"simulated": True, "error": error_code},
                )
            )
        except TransportError:
            self.handlers.enter_safe_state("communication_lost")

    def _with_bounded_retry(self, operation: Callable[[], T]) -> T:
        delay = INITIAL_BACKOFF_SECONDS
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return operation()
            except TemporaryTransportError:
                if attempt == MAX_ATTEMPTS:
                    raise
                self._sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
        raise RuntimeError("Bounded retry loop ended unexpectedly")


def build_agent(config: AgentConfig) -> JetsonAgent:
    """Construct the real HTTP polling path with simulation-only handlers."""

    handlers = HandlerRegistry(dry_run=config.dry_run)
    transport = WifiTransport(
        backend_url=config.backend_url,
        device_id=config.device_id,
        device_token=config.device_token,
        request_timeout_seconds=config.request_timeout_seconds,
    )
    return JetsonAgent(config=config, transport=transport, handlers=handlers)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config()
        build_agent(config).run_forever()
    except (ConfigError, HandlerError) as exception:
        # Configuration messages mention setting names, never secret values.
        logging.getLogger("jetson_agent").error("Agent configuration error: %s", exception)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
