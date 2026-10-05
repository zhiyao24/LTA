# Hardware-safety gate

Real hardware is intentionally disabled. This file defines questions that must be answered, reviewed, and tested before any GPIO, PWM, serial, relay, motor controller, or other actuator implementation is accepted.

## Required answers

1. What exact Jetson model, carrier board, actuator, driver, power supply, load, and wiring diagram will be used?
2. Which pins and electrical levels are valid, and what physical pull-ups/pull-downs guarantee an off state during boot, crash, disconnect, and shutdown?
3. What are the verified minimum/maximum speed, current, voltage, acceleration, travel, temperature, and duty-cycle limits in physical units?
4. What local controller owns the deterministic real-time loop? Wi-Fi and the laptop must not own motor timing or safety interlocks.
5. Where is the physical, hard-wired emergency stop or power disconnect, and does it work without the laptop, network, Jetson, or application?
6. What independent watchdog disables energy if commands, heartbeats, sensors, or controller execution stop?
7. What end stops, limit switches, guards, brakes, fault relays, and redundant sensors are required?
8. Which operating modes may energize hardware, who may select them, and what explicit arming procedure is required?
9. How are device identity, distinct credentials, rotation, revocation, and local-network access provisioned on the real Jetson?
10. How are replay, delayed packets, duplicate delivery, reboot recovery, clock error, and partial acknowledgements handled?
11. What test fixture, current limit, unloaded test, exclusion zone, and observer procedure will be used for first power-on?
12. What evidence proves safe state on Wi-Fi loss, backend crash, agent crash, Jetson reboot, brownout, sensor failure, and stuck output?

## Required evidence before enabling outputs

- Reviewed electrical schematic and pin map.
- Risk assessment identifying foreseeable hazards and severity.
- Physical emergency-stop test independent of software.
- Local watchdog and hardware interlock test results.
- Bench tests with energy/current mechanically limited.
- Fault-injection results for network loss, process crash, reboot, stale command, duplicated command, and invalid sensor data.
- Explicit approval identifying the owner of the real hardware and the allowed test scope.

The software STOP command is a useful supervisory request only. It is not an emergency-stop system. Bluetooth, if later added, has the same limitation and must use the same backend/agent validation and safety boundaries.
