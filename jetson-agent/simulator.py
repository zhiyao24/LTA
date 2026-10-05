"""Offline-first simulator, with an optional one-cycle local backend mode."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agent import JetsonAgent, build_agent
from config import AgentConfig, load_config
from handlers import HandlerRegistry
from http_transport import TemporaryTransportError


class ScriptedTransport:
    """In-memory transport for simulation without a backend or network."""

    def __init__(self, commands: List[Dict[str, Any]]) -> None:
        self.commands = list(commands)
        self.acknowledgements: List[Dict[str, Any]] = []
        self.heartbeats: List[str] = []
        self.telemetry: List[Dict[str, Any]] = []

    def send_heartbeat(self, *, device_timestamp: str) -> Dict[str, Any]:
        self.heartbeats.append(device_timestamp)
        return {"status": "online", "simulated": True}

    def send_telemetry(
        self,
        *,
        device_timestamp: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.telemetry.append({
            "device_timestamp": device_timestamp,
            "data": dict(data),
        })
        return {"stored": True, "simulated": True}

    def poll_next(self) -> Optional[Dict[str, Any]]:
        return self.commands.pop(0) if self.commands else None

    def acknowledge(
        self,
        command_id: str,
        *,
        acknowledgement_id: str,
        status: str,
        result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        acknowledgement = {
            "command_id": command_id,
            "acknowledgement_id": acknowledgement_id,
            "status": status,
            "result": result,
        }
        self.acknowledgements.append(acknowledgement)
        return acknowledgement


def run_offline_simulation() -> int:
    """Run one safe command entirely in memory."""

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    transport = ScriptedTransport(
        [
            {
                "id": str(uuid4()),
                "device_id": "jetson-simulator",
                "command_type": "SET_SPEED",
                "payload": {"speed_percent": 20.0},
                "status": "delivered",
                "expires_at": expires_at.isoformat(),
                "simulation_only": True,
            }
        ]
    )
    config = AgentConfig(
        backend_url="http://localhost:8000",
        device_id="jetson-simulator",
        device_token="",
        dry_run=True,
    )
    handlers = HandlerRegistry(dry_run=True)
    outcome = JetsonAgent(
        config=config,
        transport=transport,
        handlers=handlers,
        sleep=lambda _seconds: None,
    ).run_once()
    print(json.dumps({
        "mode": "offline simulation",
        "outcome": outcome,
        "acknowledgement_statuses": [
            item["status"] for item in transport.acknowledgements
        ],
        "heartbeats_sent": len(transport.heartbeats),
        "telemetry_samples_sent": len(transport.telemetry),
        "safe_hardware_outputs": not handlers.state.outputs_enabled,
        "simulated_speed_percent": handlers.state.speed_percent,
    }, indent=2, sort_keys=True))
    return 0 if outcome == "completed" else 1


class LostConnectionTransport(ScriptedTransport):
    """A deterministic network outage used to verify the fail-safe path."""

    def send_heartbeat(self, *, device_timestamp: str) -> Dict[str, Any]:
        raise TemporaryTransportError("simulated lost connection")


def run_lost_connection_simulation() -> int:
    """Show that an unreachable backend activates the simulated safe state."""

    config = AgentConfig(
        backend_url="http://localhost:8000",
        device_id="jetson-simulator",
        device_token="simulated-only",
        dry_run=True,
    )
    handlers = HandlerRegistry(dry_run=True)
    outcome = JetsonAgent(
        config=config,
        transport=LostConnectionTransport([]),
        handlers=handlers,
        sleep=lambda _seconds: None,
    ).run_once()
    print(json.dumps({
        "mode": "lost connection simulation",
        "outcome": outcome,
        "safe_hardware_outputs": not handlers.state.outputs_enabled,
        "safe_state_reason": handlers.state.safe_state_reason,
    }, indent=2, sort_keys=True))
    return 0 if outcome == "communication_lost" else 1


def run_backend_simulation_once() -> int:
    """Poll one command from the configured local backend, still in dry-run mode."""

    agent = build_agent(load_config())
    outcome = agent.run_once()
    print(json.dumps({
        "mode": "local backend simulation",
        "outcome": outcome,
        "safe_hardware_outputs": not agent.handlers.state.outputs_enabled,
        "state": agent.handlers.state.to_dict(),
    }, indent=2, sort_keys=True))
    return 0 if outcome in {"idle", "completed"} else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulation-only Jetson command client")
    parser.add_argument(
        "--backend-once",
        action="store_true",
        help="Poll one command from BACKEND_URL instead of using an in-memory command",
    )
    parser.add_argument(
        "--simulate-lost-connection",
        action="store_true",
        help="Simulate a backend outage and verify the agent enters its safe state",
    )
    arguments = parser.parse_args()
    if arguments.backend_once and arguments.simulate_lost_connection:
        parser.error("choose either --backend-once or --simulate-lost-connection")
    if arguments.backend_once:
        return run_backend_simulation_once()
    if arguments.simulate_lost_connection:
        return run_lost_connection_simulation()
    return run_offline_simulation()


if __name__ == "__main__":
    raise SystemExit(main())
