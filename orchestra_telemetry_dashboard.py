import sys
import socket
import struct
import threading
import time
from collections import deque

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QGroupBox, QGridLayout)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
import pyqtgraph as pg

class CanReceiver(QObject):
    """Independent background thread for CAN communication to avoid blocking GUI"""
    # Emits: motor_id, current, pos, vel
    data_received = Signal(int, int, int, int)

    def __init__(self, interface='can0'):
        super().__init__()
        self.interface = interface
        self.socket = None
        self.running = False

    def start_listening(self):
        try:
            self.socket = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            self.socket.bind((self.interface,))
            self.socket.settimeout(0.1)
            self.running = True
            
            # Start background thread
            threading.Thread(target=self._listen_loop, daemon=True).start()
        except Exception as e:
            print(f"CAN Initialization Failed: {e}")

    def _listen_loop(self):
        while self.running:
            try:
                frame = self.socket.recv(16)
                rcv_id, can_dlc, rcv_data = struct.unpack("<I B 3x 8s", frame)
                rcv_id &= 0x7FF
                
                # Parse left and right motor generic data
                if rcv_id in [0x201, 0x202]:
                    # Bytes 0-3: 32-bit Signed Little-Endian Current/Torque
                    current = struct.unpack("<i", rcv_data[0:4])[0]
                    # Bytes 4-5: 16-bit Unsigned Big-Endian Absolute Position
                    pos = (rcv_data[4] << 8) | rcv_data[5]
                    # Bytes 6-7: 16-bit Signed Big-Endian Velocity
                    vel = struct.unpack(">h", bytes(rcv_data[6:8]))[0]
                    
                    self.data_received.emit(rcv_id, current, pos, vel)
                    
            except socket.timeout:
                continue
            except Exception:
                pass

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()

class MotorPanel(QGroupBox):
    """UI Component for a single motor's numerical telemetry"""
    def __init__(self, title, motor_id):
        super().__init__(f" {title} (ID: {hex(motor_id)}) ")
        self.motor_id = motor_id
        
        layout = QGridLayout()
        
        label_style = "font-size: 14px; color: gray;"
        value_style = "font-size: 24px; font-weight: bold; color: #2ecc71;"
        
        self.lbl_pos = QLabel("0")
        self.lbl_pos.setStyleSheet(value_style)
        self.lbl_vel = QLabel("0 RPM")
        self.lbl_vel.setStyleSheet(value_style)
        self.lbl_cur = QLabel("0")
        self.lbl_cur.setStyleSheet(value_style)
        
        layout.addWidget(QLabel("Position (Encoder):", styleSheet=label_style), 0, 0)
        layout.addWidget(self.lbl_pos, 0, 1)
        
        layout.addWidget(QLabel("Velocity (RPM):", styleSheet=label_style), 1, 0)
        layout.addWidget(self.lbl_vel, 1, 1)
        
        layout.addWidget(QLabel("Torque (Amp/Raw):", styleSheet=label_style), 2, 0)
        layout.addWidget(self.lbl_cur, 2, 1)
        
        self.setLayout(layout)
        self.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #34495e;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #3498db;
            }
        """)

    def update_data(self, current, pos, vel):
        """Thread-safe UI update slot"""
        self.lbl_pos.setText(f"{pos}")
        self.lbl_vel.setText(f"{vel} RPM")
        self.lbl_cur.setText(f"{current}")

class HistoryPlotWidget(QGroupBox):
    """Real-time signal charting module powered by PyQtGraph"""
    def __init__(self):
        super().__init__(" Kinematic Position Trajectory ")
        layout = QVBoxLayout()
        
        # Configure PyQtGraph environment
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.setLabel('left', 'Absolute Position')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        
        # Safety kinematic walls (Red dashed lines) from our previous reverse-engineering
        limit_high = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', style=Qt.DashLine))
        limit_high.setPos(8787)
        self.plot_widget.addItem(limit_high)
        
        limit_low = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', style=Qt.DashLine))
        limit_low.setPos(1959)
        self.plot_widget.addItem(limit_low)
        
        # Plot curves for Left and Right Motors
        self.curve_left = self.plot_widget.plot(pen=pg.mkPen('#3498db', width=2), name="Left Joint (0x202)")
        self.curve_right = self.plot_widget.plot(pen=pg.mkPen('#e67e22', width=2), name="Right Joint (0x201)")
        
        # Historical Data Buffers (store last 300 data points)
        self.max_pts = 300
        self.time_data = deque(maxlen=self.max_pts)
        self.left_pos_data = deque(maxlen=self.max_pts)
        self.right_pos_data = deque(maxlen=self.max_pts)
        self.start_time = time.time()
        
        # Holders for asynchronous real-time values
        self.current_left_pos = 5000
        self.current_right_pos = 5000
        
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)
        self.setStyleSheet("""
            QGroupBox {
                border: 2px solid #34495e;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                font-weight: bold;
                color: #e67e22;
            }
        """)

    def update_left(self, pos):
        self.current_left_pos = pos
        
    def update_right(self, pos):
        self.current_right_pos = pos
        
    def tick(self):
        """Timer callback to advance the plot along the X axis"""
        t = time.time() - self.start_time
        self.time_data.append(t)
        self.left_pos_data.append(self.current_left_pos)
        self.right_pos_data.append(self.current_right_pos)
        
        # Flush to graph
        self.curve_left.setData(list(self.time_data), list(self.left_pos_data))
        self.curve_right.setData(list(self.time_data), list(self.right_pos_data))

class ExoskeletonDashboard(QMainWindow):
    """Main Application Window"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Orchestra Exoskeleton - Real-Time Telemetry Dashboard")
        self.setMinimumSize(900, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header
        header = QLabel("Dual Joint Servo Telemetry")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 22px; font-weight: bold; padding: 10px; background-color: #2c3e50; color: white; border-radius: 4px;")
        main_layout.addWidget(header)
        
        # Top Container: Numerical Panels
        motors_layout = QHBoxLayout()
        self.panel_left = MotorPanel("Left Joint", 0x202)
        self.panel_right = MotorPanel("Right Joint", 0x201)
        motors_layout.addWidget(self.panel_left)
        motors_layout.addWidget(self.panel_right)
        main_layout.addLayout(motors_layout)
        
        # Middle Container: The History Signal Chart
        self.history_plot = HistoryPlotWidget()
        main_layout.addWidget(self.history_plot, stretch=1)
        
        # Status Bar
        self.status_bar = QLabel("System Status: Listening actively on can0...")
        self.status_bar.setStyleSheet("color: #7f8c8d; padding-top: 5px;")
        main_layout.addWidget(self.status_bar)

        # 1. Start the actual communication thread
        self.can_receiver = CanReceiver('can0')
        self.can_receiver.data_received.connect(self.on_can_data_received)
        self.can_receiver.start_listening()
        
        # 2. Start the Graph UI Timer (30 FPS to save CPU)
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.history_plot.tick)
        self.plot_timer.start(33) 

    def on_can_data_received(self, motor_id, current, pos, vel):
        """Distribute packets from the background thread to the corresponding UI modules"""
        if motor_id == 0x202:
            self.panel_left.update_data(current, pos, vel)
            self.history_plot.update_left(pos)
        elif motor_id == 0x201:
            self.panel_right.update_data(current, pos, vel)
            self.history_plot.update_right(pos)

    def closeEvent(self, event):
        """Clean shutdown to release CAN socket"""
        self.can_receiver.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Force dark modern theme across OS platforms
    app.setStyle("Fusion")
    
    window = ExoskeletonDashboard()
    window.show()
    sys.exit(app.exec())
