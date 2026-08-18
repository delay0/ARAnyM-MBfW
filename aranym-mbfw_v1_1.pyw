# ARAnyM-MBfW - ARAnyM Midi Bridge for Windows (GUI) V1.1
# by delay0 , 2026
# Co-Developed by Gemini (Google AI)

TITEL = "ARAnyM MIDI Bridge (GUI) V1.1"
import os
import time
import mido
import subprocess
import sys
import ctypes
import threading
import configparser
import tkinter as tk
from tkinter import scrolledtext, ttk

prefix = "[MBfW] "
CONFIG_FILE = "aranym-mbfw.cfg"

# Configuration file manager
class ConfigManager:
    def __init__(self, filename):
        self.filename = filename
        self.config = configparser.ConfigParser()
        
        # Default fallback values
        self.defaults = {
            "BATCH_NAME": "run_win.bat",
            "EMULATOR_EXE_NAME": "aranym-jit.exe",
            "MIDI_FILE_PATH": "Aranym_files/midiOut.mid",
            "DEFAULT_DEVICE_NAME": "Microsoft GS Wavetable Synth",
            "LED_PULSE_DURATION": "0.25",
            "WINDOW_WIDTH": "700",
            "WINDOW_HEIGHT": "200",
            "WINDOW_POS_X": "100",
            "WINDOW_POS_Y": "100",
            "AUTO_RECONNECT": "0",
            "AUTO_EXIT": "0",
            "START_EMULATOR": "1"
        }

        self.load()

    # Loads config or creates defaults
    def load(self):
        if not os.path.exists(self.filename):
            self.config["SETTINGS"] = self.defaults
            self.save()
        else:
            self.config.read(self.filename, encoding="utf-8")
            if "SETTINGS" not in self.config:
                self.config["SETTINGS"] = {}
            for key, val in self.defaults.items():
                if key not in self.config["SETTINGS"]:
                    self.config["SETTINGS"][key] = val

    # Saves current configuration
    def save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                self.config.write(f)
        except IOError as e:
            print(f"Error saving configuration: {e}")

    # Get string values
    def get(self, key):
        return self.config["SETTINGS"].get(key, self.defaults.get(key))

    # Get integer values
    def getint(self, key):
        try:
            return self.config["SETTINGS"].getint(key, int(self.defaults.get(key)))
        except ValueError:
            return int(self.defaults.get(key))

    # Get float values
    def getfloat(self, key):
        try:
            return self.config["SETTINGS"].getfloat(key, float(self.defaults.get(key)))
        except ValueError:
            return float(self.defaults.get(key))

    # Set and save a value
    def set(self, key, value):
        self.config["SETTINGS"][key] = str(value)
        self.save()

# MIDI device handling engine
class MidiEngine:
    def __init__(self, cfg, log_callback, activity_callback):
        self.cfg = cfg
        self.log_cb = log_callback
        self.activity_cb = activity_callback
        self.output_port = None
        self.midi_file = None
        self.parser = mido.Parser()

    # Returns available system ports
    @staticmethod
    def get_available_ports():
        try:
            return mido.get_output_names()
        except Exception:
            return []

    # Binds new MIDI port
    def bind_port(self, port_name):
        self.close_port()
        try:
            self.output_port = mido.open_output(port_name)
            self.log_cb(prefix + f"✅ Successfully connected to: '{port_name}'")
            return True
        except IOError as e:
            self.log_cb(prefix + f"❌ Device connection failed: {e}")
            return False

    # Opens dump file in stream mode
    def open_stream(self):
        file_path = self.cfg.get("MIDI_FILE_PATH")
        try:
            self.midi_file = open(file_path, "rb")
            return True
        except IOError as e:
            self.log_cb(prefix + f"❌ Stream file could not be opened: {e}")
            return False

    # Reads cache bytes and sends to port
    def stream_bytes(self):
        if not self.midi_file or not self.output_port:
            return
        try:
            new_bytes = self.midi_file.read()
            if new_bytes:
                self.parser.feed(new_bytes)
                while True:
                    message = self.parser.get_message()
                    if message is None:
                        break
                    self.output_port.send(message)
                    self.activity_cb()
        except IOError:
            pass

    # Closes active MIDI port
    def close_port(self):
        if self.output_port:
            try: self.output_port.close()
            except: pass
            self.output_port = None

    # Closes opened stream file
    def close_stream(self):
        if self.midi_file:
            try: self.midi_file.close()
            except: pass
            self.midi_file = None

# Controls and detects the ARAnyM process
class AranymProcess:
    def __init__(self, cfg, log_callback):
        self.cfg = cfg
        self.log_cb = log_callback
        self.process = None
        self.already_running = False

    # Checks via Windows tasklist if exe is active
    def _is_exe_running(self):
        exe_name = self.cfg.get("EMULATOR_EXE_NAME")
        try:
            output = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {exe_name}"', shell=True)
            return exe_name.lower() in output.decode('utf-8', errors='ignore').lower()
        except Exception:
            return False

    # Spawns emulator only on cold start, otherwise uses hot-plugging
    def spawn(self, script_dir):
        exe_name = self.cfg.get("EMULATOR_EXE_NAME")
        if self._is_exe_running():
            self.already_running = True
            self.log_cb(prefix + f"ℹ️ '{exe_name}' is already running. Hooking up asynchronously...")
            return True

        self.already_running = False
        batch_name = self.cfg.get("BATCH_NAME")
        batch_path = os.path.join(script_dir, batch_name)
        self.log_cb(prefix + f"Spawning emulator process: {batch_path}")
        try:
            self.process = subprocess.Popen(
                [batch_path], cwd=script_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, shell=True
            )
            os.set_blocking(self.process.stdout.fileno(), False)
            return True
        except Exception as e:
            self.log_cb(prefix + f"❌ Process spawn failed: {e}")
            return False

    # Reads log line if process was spawned by us
    def read_log_line(self):
        if self.already_running or not self.process:
            return None
        try:
            line_bytes = self.process.stdout.readline()
            if line_bytes:
                return line_bytes.decode('utf-8', errors='ignore').strip()
        except IOError:
            pass
        return None

    # Periodically checks if emulator has exited
    def is_terminated(self):
        if self.already_running:
            return not self._is_exe_running()
        if not self.process:
            return True
        return self.process.poll() is not None

    # Kills process if spawned by us
    def terminate(self):
        if self.process and not self.already_running:
            try: self.process.terminate()
            except: pass
            self.process = None

class AranymMidiGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(TITEL)

        # 1. Initialize configuration manager
        self.cfg = ConfigManager(CONFIG_FILE)

        # Load dimensions and coordinates from config
        width = int(self.cfg.get("WINDOW_WIDTH"))
        height = int(self.cfg.get("WINDOW_HEIGHT"))
        pos_x = int(self.cfg.get("WINDOW_POS_X"))
        pos_y = int(self.cfg.get("WINDOW_POS_Y"))
        
        # Query current desktop layout dimensions
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        # Hard constraint: Reset to zero if dimensions drastically changed or corrupted
        if width > screen_w: width = 600
        if height > screen_h: height = 200

        # Boundary check: Ensure the left edge is visible
        if pos_x < 0: 
            pos_x = 0
            
        # Boundary check: If right edge or whole window falls off-screen due to smaller resolution
        if pos_x > screen_w - width or (pos_x + width) > screen_w: 
            pos_x = screen_w - width

        # Boundary check: Ensure the top title bar edge is visible
        if pos_y < 0: 
            pos_y = 0
            
        # Boundary check: If bottom edge falls off-screen (leaving 40px margin for Windows taskbar)
        if pos_y > screen_h - height - 40 or (pos_y + height) > screen_h - 40: 
            pos_y = screen_h - height - 40
            
        # Emergency backup: If any calculation failed or went negative, enforce desktop anchoring
        if pos_x < 0: pos_x = 0
        if pos_y < 0: pos_y = 0
        
        # Apply fully validated coordinates to geometry execution string
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.root.configure(bg="#2e2e2e")



        # Instantiate logic engines
        self.midi_engine = MidiEngine(self.cfg, self.append_log, self.signal_midi_activity)
        self.emulator = AranymProcess(self.cfg, self.append_log)
        
        self.running = True
        self.last_midi_activity_time = 0.0
        self.emulator_active_state = False # Intern tracker for UI LED syncing
        
        # LED color codes
        self.COLOR_OFF = "#4a0000"       # Inactive
        self.COLOR_READY = "#00ff00"     # Ready (IDLE)
        self.COLOR_ACTIVE = "#ff0000"    # MIDI activity

        # Build user interface layout
        self._build_status_bar()
        self._build_controls_area()      
        self._build_log_area()

        # Intercept window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Start asynchronous update loops
        self.root.after(100, self.start_worker_thread)
        self.root.after(150, self.update_gui_loop)

    # Creates the top LED status bar
    def _build_status_bar(self):
        self.status_frame = tk.Frame(self.root, bg="#1e1e1e", height=50)
        self.status_frame.pack_propagate(False)
        self.status_frame.pack(fill=tk.X, side=tk.TOP, padx=5, pady=5)

        self.status_label = tk.Label(
            self.status_frame, text="MIDI Bridge Status: ", 
            font=("Consolas", 12, "bold"), fg="#ffffff", bg="#1e1e1e", anchor="w"
        )
        self.status_label.pack(side=tk.LEFT, padx=(10, 5), pady=10)

        self.led_canvas = tk.Canvas(self.status_frame, width=25, height=25, bg="#1e1e1e", bd=0, highlightthickness=0)
        self.led_canvas.pack(side=tk.LEFT, padx=5, pady=12)
        self.led_circle = self.led_canvas.create_oval(3, 3, 22, 22, fill=self.COLOR_OFF, outline="")

    # Creates device dropdown and options button
    def _build_controls_area(self):
        self.menu_frame = tk.Frame(self.root, bg="#2e2e2e")
        self.menu_frame.pack(fill=tk.X, side=tk.TOP, padx=10, pady=5)
        label = tk.Label(self.menu_frame, text="Active MIDI Output Device:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10))
        label.pack(side=tk.LEFT, padx=(0, 10))

        self.port_var = tk.StringVar()
        self.dropdown = ttk.Combobox(self.menu_frame, textvariable=self.port_var, state="readonly", width=35)
        self.dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.dropdown.bind("<<ComboboxSelected>>", self.on_port_changed)

        self.options_btn = ttk.Button(self.menu_frame, text="⚙ Options", command=self.open_options_window, width=12)
        self.options_btn.pack(side=tk.RIGHT)

        self.refresh_midi_ports()

    # Creates the console log text field
    def _build_log_area(self):
        log_label = tk.Label(self.root, text="ARAnyM Console Log:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10))
        log_label.pack(anchor="w", padx=10, pady=(5,0))

        self.log_area = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # Opens settings window (Centering fixed over main window)
    def open_options_window(self):
        options_win = tk.Toplevel(self.root)
        options_win.title("Configuration")
        
        # Set static dimensions for option dialog layout
        opt_width = 400
        opt_height = 500 
        options_win.resizable(False, False)
        options_win.configure(bg="#2e2e2e")

        # Fetch current coordinates and size of main window context
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()

        # Calculate exact center positioning over parent window
        pos_x = main_x + (main_width // 2) - (opt_width // 2)
        pos_y = main_y + (main_height // 2) - (opt_height // 2)

        # Query screen size metrics to safeguard layout visibility
        screen_w = options_win.winfo_screenwidth()
        screen_h = options_win.winfo_screenheight()

        # Enforce boundary checking constraints for options dialog coordinates
        if pos_x < 0: pos_x = 0
        if pos_x > screen_w - opt_width: pos_x = screen_w - opt_width
        
        if pos_y < 0: pos_y = 0
        if pos_y > screen_h - opt_height - 40: pos_y = screen_h - opt_height - 40

        # Apply safe geometry mapping to dialog view controller
        options_win.geometry(f"{opt_width}x{opt_height}+{pos_x}+{pos_y}")
        
        # Force modal window state
        options_win.transient(self.root)
        options_win.grab_set()
        options_win.columnconfigure(1, weight=1)
        
        # ... (Rest of labels and input fields follow unchanged from here)


        # 1. BATCH_NAME
        tk.Label(options_win, text="Batch File Name:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=0, column=0, sticky="w", padx=15, pady=8)
        batch_entry = ttk.Entry(options_win)
        batch_entry.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=8)
        batch_entry.insert(0, self.cfg.get("BATCH_NAME"))

        # 2. EMULATOR_EXE_NAME
        tk.Label(options_win, text="Process Name (.exe):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=1, column=0, sticky="w", padx=15, pady=8)
        exe_entry = ttk.Entry(options_win)
        exe_entry.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=8)
        exe_entry.insert(0, self.cfg.get("EMULATOR_EXE_NAME"))

        # 3. MIDI_FILE_PATH
        tk.Label(options_win, text="MIDI Dump Path:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=2, column=0, sticky="w", padx=15, pady=8)
        path_entry = ttk.Entry(options_win)
        path_entry.grid(row=2, column=1, sticky="ew", padx=(0, 15), pady=8)
        path_entry.insert(0, self.cfg.get("MIDI_FILE_PATH"))

        # 4. LED_PULSE_DURATION
        tk.Label(options_win, text="LED Pulse (Sec.):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=3, column=0, sticky="w", padx=15, pady=8)
        pulse_entry = ttk.Entry(options_win)
        pulse_entry.grid(row=3, column=1, sticky="ew", padx=(0, 15), pady=8)
        pulse_entry.insert(0, self.cfg.get("LED_PULSE_DURATION"))

        # 5. WINDOW_WIDTH
        tk.Label(options_win, text="Window Width (px):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=4, column=0, sticky="w", padx=15, pady=8)
        width_entry = ttk.Entry(options_win)
        width_entry.grid(row=4, column=1, sticky="ew", padx=(0, 15), pady=8)
        width_entry.insert(0, self.cfg.get("WINDOW_WIDTH"))

        # 6. WINDOW_HEIGHT
        tk.Label(options_win, text="Window Height (px):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=5, column=0, sticky="w", padx=15, pady=8)
        height_entry = ttk.Entry(options_win)
        height_entry.grid(row=5, column=1, sticky="ew", padx=(0, 15), pady=8)
        height_entry.insert(0, self.cfg.get("WINDOW_HEIGHT"))

        # 7. WINDOW_POS_X
        tk.Label(options_win, text="Start Position X:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=6, column=0, sticky="w", padx=15, pady=8)
        x_entry = ttk.Entry(options_win)
        x_entry.grid(row=6, column=1, sticky="ew", padx=(0, 15), pady=8)
        x_entry.insert(0, self.cfg.get("WINDOW_POS_X"))

        # 8. WINDOW_POS_Y
        tk.Label(options_win, text="Start Position Y:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=7, column=0, sticky="w", padx=15, pady=8)
        y_entry = ttk.Entry(options_win)
        y_entry.grid(row=7, column=1, sticky="ew", padx=(0, 15), pady=8)
        y_entry.insert(0, self.cfg.get("WINDOW_POS_Y"))

        # Process Automation Radio Button Management
        tk.Label(options_win, text="Startup Behaviour:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10, "bold")).grid(row=8, column=0, sticky="w", padx=15, pady=(10, 2))
        
        start_emu_var = tk.IntVar()
        start_emu_var.set(self.cfg.getint("START_EMULATOR"))
        
        style = ttk.Style()
        style.configure("Dark.TCheckbutton", background="#2e2e2e", foreground="#ffffff", font=("Arial", 10))
        style.configure("Dark.TRadiobutton", background="#2e2e2e", foreground="#ffffff", font=("Arial", 10))

        cb_start = ttk.Checkbutton(options_win, text="Start ARAnyM automatically if not running", variable=start_emu_var, style="Dark.TCheckbutton")
        cb_start.grid(row=9, column=0, columnspan=2, sticky="w", padx=30, pady=2)

        # Process Automation Radio Button Management (Reihe nach unten verschoben)
        tk.Label(options_win, text="Process Automation:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10, "bold")).grid(row=10, column=0, sticky="w", padx=15, pady=(10, 2))
        
        auto_mode = tk.IntVar()
        if self.cfg.getint("AUTO_RECONNECT") == 1:
            auto_mode.set(1)
        else:
            auto_mode.set(2)

        rb_recon = ttk.Radiobutton(options_win, text="Auto Reconnect (Stand by silently for next session)", variable=auto_mode, value=1, style="Dark.TRadiobutton")
        rb_recon.grid(row=11, column=0, columnspan=2, sticky="w", padx=30, pady=2)
        
        rb_exit = ttk.Radiobutton(options_win, text="Auto Exit (Terminate bridge on emulator close)", variable=auto_mode, value=2, style="Dark.TRadiobutton")
        rb_exit.grid(row=12, column=0, columnspan=2, sticky="w", padx=30, pady=2)

        # Saves parameters from entry fields
        def save_options():
            self.cfg.set("BATCH_NAME", batch_entry.get().strip())
            self.cfg.set("EMULATOR_EXE_NAME", exe_entry.get().strip()) 
            self.cfg.set("MIDI_FILE_PATH", path_entry.get().strip())
            self.cfg.set("LED_PULSE_DURATION", pulse_entry.get().strip())
            
            w = width_entry.get().strip()
            h = height_entry.get().strip()
            x = x_entry.get().strip()
            y = y_entry.get().strip()
            
            self.cfg.set("WINDOW_WIDTH", w)
            self.cfg.set("WINDOW_HEIGHT", h)
            self.cfg.set("WINDOW_POS_X", x)
            self.cfg.set("WINDOW_POS_Y", y)

            # Neue Werte aus Checkbox und Radios sichern
            self.cfg.set("START_EMULATOR", str(start_emu_var.get()))
            selection = auto_mode.get()
            self.cfg.set("AUTO_RECONNECT", "1" if selection == 1 else "0")
            self.cfg.set("AUTO_EXIT", "1" if selection == 2 else "0")
            
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.append_log(prefix + "⚙️ Configuration and process automation updated.")
            options_win.destroy()

        btn_frame = tk.Frame(options_win, bg="#2e2e2e")
        btn_frame.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        
        ttk.Button(btn_frame, text="Cancel", command=options_win.destroy, width=12).pack(side=tk.RIGHT, padx=15)
        ttk.Button(btn_frame, text="Save", command=save_options, width=12).pack(side=tk.RIGHT)



    # Refreshes the list of MIDI devices
    def refresh_midi_ports(self):
        ports = self.midi_engine.get_available_ports()
        self.dropdown['values'] = ports
        
        self.append_log(prefix + "==============================================")
        self.append_log(prefix + "=     Available Windows MIDI Outputs         =")
        self.append_log(prefix + "==============================================")
        if not ports:
            self.append_log(prefix + "⚠️ No MIDI devices found in Windows!")
            return

        target_name = self.cfg.get("DEFAULT_DEVICE_NAME")
        selected_index = 0
        
        for idx, name in enumerate(ports):
            self.append_log(prefix + f"ID {idx}: '{name}'")
            if target_name.lower() in name.lower():
                selected_index = idx

        self.dropdown.current(selected_index)
        self.midi_engine.bind_port(ports[selected_index])

    def on_port_changed(self, event=None):
        new_port = self.port_var.get()
        self.midi_engine.bind_port(new_port)

    def signal_midi_activity(self):
        self.last_midi_activity_time = time.time()

    def append_log(self, text):
        if self.running:
            self.root.after(0, lambda: self._safe_append(text))

    def _safe_append(self, text):
        self.log_area.insert(tk.END, text + "\n")
        self.log_area.see(tk.END)

    def start_worker_thread(self):
        self.worker_thread = threading.Thread(target=self.monitor_and_stream_core, daemon=True)
        self.worker_thread.start()

    def set_led_color(self, color):
        if self.led_canvas.itemcget(self.led_circle, "fill") != color:
            self.led_canvas.itemconfig(self.led_circle, fill=color)

    def update_gui_loop(self):
        if not self.running:
            return

        now = time.time()
        pulse_duration = self.cfg.getfloat("LED_PULSE_DURATION")
        
        if not self.emulator_active_state:
            self.set_led_color(self.COLOR_OFF)
        elif now - self.last_midi_activity_time <= pulse_duration:
            self.set_led_color(self.COLOR_ACTIVE)
        else:
            self.set_led_color(self.COLOR_READY)

        self.root.after(10, self.update_gui_loop)

    # Core background processing stream loop (Updated with Startup and Auto-Exit validation guards)
    def monitor_and_stream_core(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        midi_path = self.cfg.get("MIDI_FILE_PATH")

        is_first_round = True
        has_hooked_at_least_once = False  # Verhindert sofortiges Schließen durch Auto-Exit

        while self.running:
            # Entscheidung beim allerersten Durchlauf
            if is_first_round:
                is_first_round = False
                # Nur spawnen, wenn "Start ARAnyM" in der Config aktiviert ist
                if self.cfg.getint("START_EMULATOR") == 1:
                    if not self.emulator.spawn(script_dir):
                        time.sleep(2.0)
                        is_first_round = True # Bei totalem Spawn-Fehler Re-try erlauben
                        continue
                else:
                    # Wenn nicht gewählt, direkt lautlos in den Reconnect-Wartemodus schalten
                    self.append_log(prefix + "Startup without emulator launch. Entering silent monitoring...")
                    if not self.emulator._is_exe_running():
                        time.sleep(1.5)
                        continue
            else:
                # Reconnect-Modus für alle weiteren Runden: Lautloses Polling der Prozessliste
                if not self.emulator._is_exe_running():
                    time.sleep(1.0)
                    continue
                self.emulator.already_running = True
                self.append_log(prefix + "New emulator session detected! Re-hooking stream...")

            # Wenn wir hier ankommen, läuft der Emulator aktiv im System
            has_hooked_at_least_once = True

            if not self.emulator.already_running:
                if os.path.exists(midi_path):
                    try:
                        os.remove(midi_path)
                        self.append_log(prefix + f"Purged old MIDI dump: {midi_path}")
                    except Exception as e:
                        self.append_log(prefix + f"⚠️ Error deleting old dump: {e}")

            self.append_log(prefix + f"Waiting for creation of: {midi_path} ...")
            file_ready = True
            while os.path.exists(midi_path) is False and self.running:
                if self.emulator.is_terminated():
                    self.append_log(prefix + "⏹️ Emulator terminated before file creation.")
                    file_ready = False
                    break
                log_line = self.emulator.read_log_line()
                if log_line:
                    self.append_log(f"[Aranym] {log_line}")
                time.sleep(0.1)

            if not file_ready or not self.running:
                # Auto-Exit Schutz: Nur schließen, wenn er vorab wirklich aktiv gekoppelt war
                if self.cfg.getint("AUTO_EXIT") == 1 and has_hooked_at_least_once:
                    self.append_log(prefix + "Automated Auto-Exit triggered.")
                    self.root.after(0, self.root.destroy)
                    return
                time.sleep(2.0)
                continue

            self.append_log(prefix + f"Target verified. Starting real-time stream: {midi_path}")
            
            if not self.midi_engine.open_stream():
                time.sleep(2.0)
                continue
            
            self.emulator_active_state = True

            while self.running:
                if self.emulator.is_terminated():
                    self.append_log(prefix + "🏁 Emulator process terminated.")
                    break

                log_line = self.emulator.read_log_line()
                if log_line:
                    self.append_log(f"[Aranym] {log_line}")

                self.midi_engine.stream_bytes()
                time.sleep(0.005)

            self.emulator_active_state = False
            self.midi_engine.close_stream()
            
            # Endgütiges Verhalten beim Beenden des Emulators auswerten
            if self.cfg.getint("AUTO_EXIT") == 1 and has_hooked_at_least_once:
                self.append_log(prefix + "Automated Auto-Exit closing application...")
                self.root.after(0, self.root.destroy)
                return
            elif self.cfg.getint("AUTO_RECONNECT") == 1:
                self.append_log(prefix + "Auto-Reconnect active. Standing by silently for a new manual session...")
                time.sleep(1.0)
            else:
                self.append_log(prefix + "Bridge entering absolute idle state. Ready for manual shutdown.")
                break


    def on_closing(self):
        self.running = False
        current_port = self.port_var.get()
        if current_port:
            self.cfg.set("DEFAULT_DEVICE_NAME", current_port)
            
        self.emulator.terminate()
        self.midi_engine.close_stream()
        self.midi_engine.close_port()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('vista')
    
    app = AranymMidiGUI(root)
    root.mainloop()
