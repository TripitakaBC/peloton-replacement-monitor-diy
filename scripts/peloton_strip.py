#!/usr/bin/env python3
"""
Peloton Stats Strip — Dual Corner Edition
- Two separate windows, each 1/3 screen width
- Left strip:  HR value + bpm | Zn | progress bar | CAL
- Right strip: PWR | CAD | RES | TIME
- Middle third completely clear for GNOME dock icons
- Both sit within the 87px GNOME taskbar band
- X11/Xorg required
"""

import tkinter as tk
import sys
import serial
import threading
import time
import math
from pathlib import Path
from openant.easy.node import Node
from openant.easy.channel import Channel

# ── Configuration ─────────────────────────────────────────────────────────────

SCOSCHE_ADDRESS = "D5:1B:B1:5B:E1:B7"
HR_CHAR_UUID    = "00002a37-0000-1000-8000-00805f9b34fb"

TASKBAR_H  = 87
STRIP_H    = 83   # 2px breathing room top and bottom within taskbar band
EDGE_PAD   = 40   # px from screen edges

ZONE_COLOURS = ["#2196F3", "#4CAF50", "#FFEB3B", "#FF9800", "#F44336"]
ZONE_NAMES   = ["Z1", "Z2", "Z3", "Z4", "Z5"]
ZONE_BPM     = [(0,129),(129,149),(149,169),(169,189),(189,999)]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_taskbar_top():
    try:
        from Xlib import display as xdisplay
        d    = xdisplay.Display()
        root = d.screen().root
        wa   = root.get_full_property(d.intern_atom('_NET_WORKAREA'), 0)
        if wa:
            vals = wa.value
            return vals[1] + vals[3]
    except Exception as ex:
        print(f"[geometry] {ex}")
    return 1353

def get_zone_and_progress(hr):
    if hr <= 0:
        return 0, 0.0
    for i, (lo, hi) in enumerate(ZONE_BPM):
        if hr < hi:
            progress = (hr - lo) / (hi - lo)
            return i, max(0.0, min(1.0, progress))
    return 4, 1.0

def set_window_hints(root, sw, strip_y, sh):
    """Set dock type and strut on a Tk window before mapping."""
    try:
        from Xlib import display as xdisplay
        d   = xdisplay.Display()
        wid = root.winfo_id()
        win = d.create_resource_object('window', wid)
        strut_bottom = sh - strip_y
        win.change_property(
            d.intern_atom('_NET_WM_WINDOW_TYPE'),
            d.intern_atom('ATOM'), 32,
            [d.intern_atom('_NET_WM_WINDOW_TYPE_DOCK')])
        win.change_property(
            d.intern_atom('_NET_WM_STRUT_PARTIAL'),
            d.intern_atom('CARDINAL'), 32,
            [0, 0, 0, strut_bottom,
             0, 0, 0, 0, 0, 0,
             0, sw])
        win.change_property(
            d.intern_atom('_NET_WM_STRUT'),
            d.intern_atom('CARDINAL'), 32,
            [0, 0, 0, strut_bottom])
        d.sync()
        print(f"[hints] strut {strut_bottom}px, DOCK type set")
    except Exception as ex:
        print(f"[hints] failed: {ex}")

# ── ANT+ Manager (Unified RX/TX) ─────────────────────────────────────────────

ANTPLUS_NETWORK_KEY = [0xB9, 0xA5, 0x21, 0xFB, 0xBD, 0x72, 0xC3, 0x45]

class AntManager:
    def __init__(self, tx_device_number=12345):
        self.tx_device_number = tx_device_number
        self.node = None
        
        # TX (Power/Cadence) State
        self.tx_channel = None
        self.event_count = 0
        self.accumulated_power = 0
        self.current_power = 0
        self.current_cadence = 0
        
        # TX (Speed/Distance) State
        self.spd_channel = None
        self.current_distance_m = 0.0
        self.current_speed_mph = 0.0
        self.wheel_circumference_m = 2.105 # Standard 700c tire
        
        # RX (Heart Rate) State
        self.rx_channel = None
        self.current_hr = 0
        self.last_hr_rx_time = 0
        
        self.lock = threading.Lock()
        
        # Start the ANT+ node manager in a daemon thread
        threading.Thread(target=self._run, daemon=True).start()

    # --- Interfaces for UI and BikeData ---
    
    def get_hr(self):
        with self.lock:
            # If no signal for 5 seconds, clear the HR
            if time.time() - getattr(self, 'last_hr_rx_time', 0) > 5.0:
                self.current_hr = 0
            return self.current_hr

    def update_metrics(self, power, cadence, speed_mph, distance_m):
        with self.lock:
            self.current_power = int(power)
            self.current_cadence = int(cadence)
            self.current_speed_mph = speed_mph
            self.current_distance_m = distance_m

    # --- Internal ANT+ Thread ---

    def _run(self):
        print("[ant+] Initializing Unified ANT+ Manager...")
        try:
            self.node = Node()
            self.node.set_network_key(0x00, ANTPLUS_NETWORK_KEY)
            
            # 1. Setup RX Channel (Heart Rate)
            self.rx_channel = self.node.new_channel(Channel.Type.BIDIRECTIONAL_RECEIVE)
            self.rx_channel.on_broadcast_data = self.on_rx_data
            self.rx_channel.on_burst_data = self.on_rx_data
            # 0, 120, 0 means search for any Heart Rate monitor
            self.rx_channel.set_id(0, 120, 0)
            self.rx_channel.set_search_timeout(255) # Infinite
            self.rx_channel.set_period(8070) # 4.06Hz standard HR period
            self.rx_channel.set_rf_freq(57)
            
            # 2. Setup TX Channel (Power Meter)
            self.tx_channel = self.node.new_channel(Channel.Type.BIDIRECTIONAL_TRANSMIT)
            self.tx_channel.on_broadcast_tx_data = self.on_tx_data
            self.tx_channel.set_id(self.tx_device_number, 11, 5) # 11: Power Meter
            self.tx_channel.set_period(8182) # 4Hz standard Power period
            self.tx_channel.set_rf_freq(57)
            
            # 3. Setup TX Channel 2 (Bike Speed)
            # Garmin uses wheel revolutions to calculate distance natively.
            self.spd_channel = self.node.new_channel(Channel.Type.BIDIRECTIONAL_TRANSMIT)
            self.spd_channel.on_broadcast_tx_data = self.on_spd_tx_data
            self.spd_channel.set_id(self.tx_device_number + 1, 123, 5) # 123: Bike Speed
            self.spd_channel.set_period(8118) # 4Hz standard Speed period
            self.spd_channel.set_rf_freq(57)
            
            self.rx_channel.open()
            self.tx_channel.open()
            self.spd_channel.open()
            
            print("[ant+] Channels Opened: HR (RX), Power (TX), Speed/Distance (TX)")
            self.node.start() 
        except Exception as e:
            print(f"[ant+] Manager failed: {e}")

    # --- Callbacks ---

    def on_rx_data(self, data):
        # Data page is in data[0]. For HR (type 120), byte 7 is the HR value.
        # It's standard across pages (0, 4, etc.) for basic HR.
        if len(data) >= 8:
            hr_val = data[7]
            with self.lock:
                self.last_hr_rx_time = time.time()
                if hr_val > 0:
                    self.current_hr = hr_val

    def on_tx_data(self, data):
        with self.lock:
            pwr = self.current_power
            cad = self.current_cadence
            
        self.event_count = (self.event_count + 1) % 256
        self.accumulated_power = (self.accumulated_power + pwr) % 65536
        
        payload = [0] * 8
        payload[0] = 0x10  # Page 16 (Standard Power)
        payload[1] = self.event_count
        payload[2] = 0xFF
        payload[3] = cad if cad <= 254 else 254
        payload[4] = self.accumulated_power & 0xFF
        payload[5] = (self.accumulated_power >> 8) & 0xFF
        payload[6] = pwr & 0xFF
        payload[7] = (pwr >> 8) & 0xFF
        
        self.tx_channel.send_broadcast_data(payload)

    def on_spd_tx_data(self, data):
        """
        Device Type 123 (Bike Speed) format:
        Byte 0-3: Reserved/unused for standard distance
        Byte 4-5: Cumulative Operating Time (1/1024s)
        Byte 6-7: Cumulative Wheel Revolutions
        """
        with self.lock:
            dist_m = self.current_distance_m
            
        # Time in 1/1024 seconds
        current_time = time.time()
        time_1024 = int(current_time * 1024) % 65536
        
        # Cumulative Wheel Revolutions
        wheel_revs = int(dist_m / self.wheel_circumference_m) % 65536
        
        payload = [0] * 8
        payload[4] = time_1024 & 0xFF
        payload[5] = (time_1024 >> 8) & 0xFF
        payload[6] = wheel_revs & 0xFF
        payload[7] = (wheel_revs >> 8) & 0xFF
        
        self.spd_channel.send_broadcast_data(payload)

# ── Real Bike Data (USB Serial) ───────────────────────────────────────────────────

POLL_COMMANDS = [
    b'\xf6\xf5\x41\x36', # CADENCE
    b'\xf6\xf5\x44\x39', # POWER
    b'\xf6\xf5\x4a\x3f'  # RESISTANCE
]

def calculate_checksum(packet_bytes):
    return sum(packet_bytes[:-2]) % 256

def decode_payload(payload_bytes, metric_type):
    if len(payload_bytes) == 0:
        return 0
    try:
        if metric_type == "POWER":
            precision = (payload_bytes[0] - 48) / 10.0
            int_bytes = payload_bytes[1:]
            int_val = int(int_bytes[::-1].decode('ascii'))
            return int_val + precision
        else:
            return int(payload_bytes[::-1].decode('ascii'))
    except Exception as e:
        return 0

class BikeData:
    def __init__(self, broadcaster=None, port='/dev/peloton_serial', baudrate=19200):
        self.broadcaster = broadcaster
        self.metrics = {"power": 0.0, "cadence": 0, "resistance": 0.0, "calories": 0.0, "distance_m": 0.0, "speed_mph": 0.0}
        self.elapsed = "0:00"
        self._start_time = time.time()
        self._last_calc_time = time.time()
        
        self.port = port
        self.baudrate = baudrate
        self.lock = threading.Lock()
        
        # Start the background thread
        threading.Thread(target=self._run_serial, daemon=True).start()

    def get(self):
        with self.lock:
            # Format current local time
            self.elapsed = time.strftime("%H:%M")
            
            # Format output for UI
            return {
                "power": round(self.metrics["power"], 1), 
                "cadence": self.metrics["cadence"], 
                "resistance": int(round(self.metrics["resistance"])),
                "elapsed": self.elapsed, 
                "calories": int(self.metrics["calories"]),
                "distance_m": self.metrics["distance_m"],
                "speed_mph": self.metrics["speed_mph"]
            }

    def _run_serial(self):
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
        except Exception as e:
            print(f"[bikedata] Failed to open port {self.port}: {e}")
            return
            
        print("[bikedata] Connected to Peloton Serial. Starting polling...")
        
        # Start the active polling thread
        stop_event = threading.Event()
        def poll_bike():
            cmd_idx = 0
            while not stop_event.is_set():
                try:
                    ser.write(POLL_COMMANDS[cmd_idx])
                    cmd_idx = (cmd_idx + 1) % len(POLL_COMMANDS)
                except Exception:
                    break
                time.sleep(0.1)
                
        poll_thread = threading.Thread(target=poll_bike)
        poll_thread.daemon = True
        poll_thread.start()

        buffer = bytearray()
        
        try:
            while True:
                if ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting)
                    buffer.extend(chunk)
                    
                while b'\xf6' in buffer:
                    idx_f1 = buffer.find(b'\xf1')
                    idx_f5 = buffer.find(b'\xf5')
                    
                    start_idx = -1
                    if idx_f1 != -1 and idx_f5 != -1:
                        start_idx = min(idx_f1, idx_f5)
                    elif idx_f1 != -1:
                        start_idx = idx_f1
                    elif idx_f5 != -1:
                        start_idx = idx_f5
                        
                    if start_idx == -1:
                        break
                        
                    end_idx = buffer.find(b'\xf6', start_idx)
                    if end_idx != -1:
                        packet = buffer[start_idx:end_idx + 1]
                        buffer = buffer[end_idx + 1:] 
                        
                        if len(packet) >= 5:
                            payload_len = packet[2]
                            
                            if len(packet) == payload_len + 5: 
                                expected_chk = calculate_checksum(packet)
                                actual_chk = packet[-2]
                                
                                if expected_chk == actual_chk:
                                    packet_type = packet[1]
                                    payload = packet[3:-2] 
                                    
                                    with self.lock:
                                        if packet_type == 0x41: # Cadence
                                            self.metrics["cadence"] = decode_payload(payload, "CADENCE")
                                        elif packet_type == 0x44: # Power
                                            self.metrics["power"] = decode_payload(payload, "POWER")
                                        elif packet_type == 0x4A: # Resistance
                                            raw_res = decode_payload(payload, "RESISTANCE")
                                            if isinstance(raw_res, int):
                                                # Map 500-1000 range to 0-100%
                                                if raw_res <= 500:
                                                    scaled_res = 0.0
                                                elif raw_res >= 1000:
                                                    scaled_res = 100.0
                                                else:
                                                    scaled_res = (raw_res - 500) / 5.0
                                                self.metrics["resistance"] = scaled_res
                                                
                                        # Update calories (cal/hr = Power * 3.6, roughly)
                                        now = time.time()
                                        dt = now - self._last_calc_time
                                        self._last_calc_time = now
                                        
                                        pwr = self.metrics["power"]
                                        # 1 kJ of mechanical work is roughly 1 kcal of dietary energy (assuming ~24% human efficiency)
                                        self.metrics["calories"] += (pwr * dt) / 1000.0
                                        
                                        # PeloMon Speed/Distance Math
                                        rtpower = math.sqrt(pwr) if pwr > 0 else 0
                                        
                                        if pwr < 27.0:
                                            coefs = [-0.07605, 0.74063, -0.14023, 0.04660]
                                        else:
                                            coefs = [0.00087, -0.05685, 2.23594, -1.31158]
                                            
                                        mph = 0.0
                                        if pwr > 0:
                                            for i in range(3):
                                                mph += coefs[i]
                                                mph *= rtpower
                                            mph += coefs[3]
                                            mph = max(0.0, mph) # prevent negative speeds at idle
                                            
                                        self.metrics["speed_mph"] = mph
                                        
                                        # Integrate distance (mph to m/s is 0.44704)
                                        meters_per_sec = mph * 0.44704
                                        self.metrics["distance_m"] += meters_per_sec * dt
                                        
                                        # Push updates to the ANT+ sender
                                        if self.broadcaster:
                                            self.broadcaster.update_metrics(pwr, self.metrics["cadence"], self.metrics["speed_mph"], self.metrics["distance_m"])
                time.sleep(0.01)
        except Exception as e:
            print(f"[bikedata] Error reading serial: {e}")
        finally:
            stop_event.set()
            ser.close()

# ── Shared style ──────────────────────────────────────────────────────────────

BG       = "#0d0d0d"
FG       = "#f0f0f0"
LABEL_FG = "#aaaaaa"
BAR_BG   = "#1e1e1e"
SEP      = "#2a2a2a"

def make_window(sw, sh, x, w, strip_y):
    """Create a bare Tk window, set hints before mapping."""
    win = tk.Tk()
    win.withdraw()
    win.overrideredirect(True)
    win.configure(bg=BG)
    win.geometry(f"{w}x{STRIP_H}+{x}+{strip_y}")
    win.update_idletasks()
    set_window_hints(win, sw, strip_y, sh)
    win.deiconify()
    win.attributes("-topmost", True)
    return win

# ── Left strip: HR + zone + calories ─────────────────────────────────────────

class HRStrip:
    def __init__(self, sw, sh, strip_w, strip_y, hr_reader, bike_data):
        self.hr_reader = hr_reader
        self.bike_data = bike_data
        self.w = strip_w

        self.root = make_window(sw, sh, 0, strip_w, strip_y)
        cy = STRIP_H // 2

        # HR + bpm
        hr_row = tk.Frame(self.root, bg=BG)
        hr_row.place(x=EDGE_PAD, y=cy - 30, width=145, height=60)
        self.lbl_hr = tk.Label(hr_row, text="--",
                                font=("Helvetica", 32, "bold"),
                                bg=BG, fg=FG)
        self.lbl_hr.pack(side=tk.LEFT)
        tk.Label(hr_row, text=" bpm", font=("Helvetica", 14),
                 bg=BG, fg=LABEL_FG).pack(side=tk.LEFT, anchor="s", pady=(0,5))

        # Zone label
        zone_x = EDGE_PAD + 152
        self.lbl_zone = tk.Label(self.root, text="Z1",
                                  font=("Helvetica", 16, "bold"),
                                  bg=BG, fg=ZONE_COLOURS[0])
        self.lbl_zone.place(x=zone_x, y=cy - 13, width=36, height=26)

        # Progress bar
        bar_x = zone_x + 40
        bar_w = 180
        bar_h = 16
        self.bar_bg = tk.Frame(self.root, bg=BAR_BG)
        self.bar_bg.place(x=bar_x, y=cy - bar_h//2, width=bar_w, height=bar_h)
        self.bar_fill = tk.Frame(self.bar_bg, bg=ZONE_COLOURS[0])
        self.bar_fill.place(x=0, y=0, width=0, height=bar_h)
        self._bar_w = bar_w

        # CAL
        cal_x = bar_x + bar_w + 50
        cal_row = tk.Frame(self.root, bg=BG)
        cal_row.place(x=cal_x, y=cy - 14, width=130, height=28)
        tk.Label(cal_row, text="CAL ", font=("Helvetica", 14),
                 bg=BG, fg=LABEL_FG).pack(side=tk.LEFT, anchor="s", pady=(0,3))
        self.lbl_cal = tk.Label(cal_row, text="--",
                                 font=("Helvetica", 18, "bold"),
                                 bg=BG, fg=FG)
        self.lbl_cal.pack(side=tk.LEFT, anchor="s", pady=(0,1))

        self._tick()

    def _tick(self):
        hr             = self.hr_reader.get_hr()
        zone, progress = get_zone_and_progress(hr)
        colour         = ZONE_COLOURS[zone]

        self.lbl_hr.config(text=str(hr) if hr > 0 else "--", fg=colour)
        self.lbl_zone.config(text=ZONE_NAMES[zone], fg=colour)

        fill_w = int(self._bar_w * progress)
        self.bar_fill.config(bg=colour)
        self.bar_fill.place(x=0, y=0, width=fill_w, height=16)

        bike = self.bike_data.get()
        self.lbl_cal.config(text=str(bike["calories"]))

        self.root.after(1000, self._tick)

# ── Right strip: bike stats ───────────────────────────────────────────────────

class BikeStrip:
    def __init__(self, sw, sh, strip_w, strip_y, bike_data):
        self.bike_data = bike_data
        right_x = sw - strip_w

        self.root = make_window(sw, sh, right_x, strip_w, strip_y)
        cy = STRIP_H // 2

        stats = [
            ("PWR",  "power",      "W"),
            ("CAD",  "cadence",    "rpm"),
            ("RES",  "resistance", "%"),
            ("TIME", "elapsed",    ""),
        ]
        cell_widths = [140, 150, 120, 150]
        total_w     = sum(cell_widths)
        # Right-align the stats within the strip
        rx = strip_w - EDGE_PAD - total_w

        self.bike_labels = {}
        for i, ((label, field, unit), cw) in enumerate(zip(stats, cell_widths)):
            if i > 0:
                tk.Frame(self.root, bg=SEP, width=1).place(
                    x=rx - 6, y=10, width=1, height=STRIP_H - 20)

            row = tk.Frame(self.root, bg=BG)
            row.place(x=rx, y=cy - 14, width=cw, height=28)
            tk.Label(row, text=f"{label} ", font=("Helvetica", 14),
                     bg=BG, fg=LABEL_FG).pack(side=tk.LEFT, anchor="s", pady=(0,3))
            lbl = tk.Label(row, text="--",
                           font=("Helvetica", 18, "bold"),
                           bg=BG, fg=FG)
            lbl.pack(side=tk.LEFT, anchor="s", pady=(0,1))
            if unit:
                tk.Label(row, text=f" {unit}", font=("Helvetica", 11),
                         bg=BG, fg=LABEL_FG).pack(
                             side=tk.LEFT, anchor="s", pady=(0,3))
            self.bike_labels[field] = lbl
            rx += cw

        self._tick()

    def _tick(self):
        bike = self.bike_data.get()
        for field, lbl in self.bike_labels.items():
            lbl.config(text=str(bike[field]))
        self.root.after(1000, self._tick)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Shared data sources (via unified ANT+)
    ant_manager = AntManager()
    hr_reader = ant_manager
    bike_data = BikeData(broadcaster=ant_manager)

    # Screen geometry
    tmp = tk.Tk()
    sw  = tmp.winfo_screenwidth()
    sh  = tmp.winfo_screenheight()
    tmp.destroy()

    taskbar_top = get_taskbar_top()
    strip_y     = taskbar_top + (TASKBAR_H - STRIP_H) // 2
    strip_w     = sw // 3

    print(f"Screen: {sw}x{sh}  Taskbar top: {taskbar_top}")
    print(f"Strip Y: {strip_y}  Strip width: {strip_w}")

    # Build both strips
    hr_strip   = HRStrip(sw, sh, strip_w, strip_y, hr_reader, bike_data)
    bike_strip = BikeStrip(sw, sh, strip_w, strip_y, bike_data)

    # Run mainloop on the HR strip's root; both windows update via after()
    hr_strip.root.mainloop()
