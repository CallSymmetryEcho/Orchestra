# Orchestra Exoskeleton GUI Module

**Welcome to the `Orchestra` Exoskeleton Control Station.**

This repository branch/module contains the standalone GUI dashboard used to visualize and control the dual-motor Exoskeleton system. It is built strictly for high-speed, thread-safe asynchronous CAN bus communication.

## 🌟 Core Features
- **Parallel Loop Monitors**: Side-by-side comparison of **Actual (Rx)** feedback vs **Target (Tx)** setpoints for Position, Velocity, and Torque.
- **Bi-directional Transceiver**: Capable of streaming sensory data from `0x201` and `0x202` at 100Hz while simultaneously emitting strictly clamped torque commands to `0x601` and `0x602`.
- **High-Speed Realtime Tracking**: Powered by `pyqtgraph`, rendering kinematic tracking curves at 30 FPS.
- **Mechanical Safety Enclosures**: Absolute kinematic bounds (1959 to 8787) are visually baked into the telemetry radar to ensure the operator never pushes the joints past hardware limits.
- **Hardware Emergency Stop**: Global E-STOP button to instantly cut all torque setpoints to zero.

## 🛠️ Installation & Setup

Because this UI interfaces directly with native Linux SocketCAN, it is highly recommended to run it in a **Python Virtual Environment**.

1. **Activate Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. **Install Qt Dependencies**:
   ```bash
   pip install PySide6 pyqtgraph
   ```
3. **Launch the Telemetry Station**:
   ```bash
   python orchestra_telemetry_dashboard.py
   ```
*(Requires the `can0` interface to be Up, running at the correct Baud Rate, and terminated with a 120-ohm resistor).*

## 🏗️ Architecture Pattern
This module breaks the Python GIL limitations by separating network loops from UI rendering:
- `CanTransceiver`: A purely background `<threading.Thread>` handling non-blocking raw `socket.recv()` and `socket.send()`.
- **Qt Signals**: Used exclusively to safely pass tuples of telemetry across the thread barrier into the UI.
- `QTimer` Event Loops: Deque-based buffers flush to the screen at a steady 33ms cadence to keep the CPU cool.

---
*Developed for the Orchestra Exoskeleton Integration Layer.*
