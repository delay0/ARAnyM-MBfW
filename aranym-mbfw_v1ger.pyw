# ARAnyM-MBfW - ARAnyM Midi Bridge for Windows (GUI) V1.0
# by delay0 , 2026
# Co-Developed by Gemini (Google AI)

TITEL = "ARAnyM MIDI Bridge (GUI) V1.0"
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

# Verwaltung der Konfigurationsdatei
class ConfigManager:
    def __init__(self, filename):
        self.filename = filename
        self.config = configparser.ConfigParser()
        
        # Standardwerte bei fehlender Datei
        self.defaults = {
            "BATCH_NAME": "run_win.bat",
            "EMULATOR_EXE_NAME": "aranym-jit.exe",
            "MIDI_FILE_PATH": "Aranym_files/midiOut.mid",
            "DEFAULT_DEVICE_NAME": "Microsoft GS Wavetable Synth",
            "LED_PULSE_DURATION": "0.25",
            "WINDOW_WIDTH": "700",
            "WINDOW_HEIGHT": "200",
            "WINDOW_POS_X": "100",
            "WINDOW_POS_Y": "100"
        }
        self.load()

    # Lädt Einstellungen oder erstellt Defaults
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

    # Speichert aktuelle Konfiguration
    def save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                self.config.write(f)
        except IOError as e:
            print(f"Fehler beim Speichern der Konfiguration: {e}")

    # Rückgabe von String-Werten
    def get(self, key):
        return self.config["SETTINGS"].get(key, self.defaults.get(key))

    # Rückgabe von Float-Werten
    def getfloat(self, key):
        try:
            return self.config["SETTINGS"].getfloat(key, float(self.defaults.get(key)))
        except ValueError:
            return float(self.defaults.get(key))

    # Ändert und speichert einen Wert
    def set(self, key, value):
        self.config["SETTINGS"][key] = str(value)
        self.save()

# Logik für die MIDI-Geräteverwaltung
class MidiEngine:
    def __init__(self, cfg, log_callback, activity_callback):
        self.cfg = cfg
        self.log_cb = log_callback
        self.activity_cb = activity_callback
        self.output_port = None
        self.midi_file = None
        self.parser = mido.Parser()

    # Gibt verfügbare System-Ports zurück
    @staticmethod
    def get_available_ports():
        try:
            return mido.get_output_names()
        except Exception:
            return []

    # Verbindet neuen MIDI-Port
    def bind_port(self, port_name):
        self.close_port()
        try:
            self.output_port = mido.open_output(port_name)
            self.log_cb(prefix + f"✅ Erfolgreich verbunden mit: '{port_name}'")
            return True
        except IOError as e:
            self.log_cb(prefix + f"❌ Geräte-Verbindung fehlgeschlagen: {e}")
            return False

    # Öffnet die Dump-Datei im Stream-Modus
    def open_stream(self):
        file_path = self.cfg.get("MIDI_FILE_PATH")
        try:
            self.midi_file = open(file_path, "rb")
            return True
        except IOError as e:
            self.log_cb(prefix + f"❌ Stream-Datei konnte nicht geöffnet werden: {e}")
            return False

    # Liest Cache-Bytes und sendet sie an Port
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
    # Schließt den aktiven MIDI-Port
    def close_port(self):
        if self.output_port:
            try: self.output_port.close()
            except: pass
            self.output_port = None

    # Schließt die geöffnete Stream-Datei
    def close_stream(self):
        if self.midi_file:
            try: self.midi_file.close()
            except: pass
            self.midi_file = None

# Steuerung und Erkennung des ARAnyM-Prozesses
class AranymProcess:
    def __init__(self, cfg, log_callback):
        self.cfg = cfg
        self.log_cb = log_callback
        self.process = None
        self.already_running = False

    # Prüft via Windows-Tasklist, ob die Exe aktiv ist
    def _is_exe_running(self):
        exe_name = self.cfg.get("EMULATOR_EXE_NAME")
        try:
            output = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {exe_name}"', shell=True)
            return exe_name.lower() in output.decode('utf-8', errors='ignore').lower()
        except Exception:
            return False

    # Startet Emulator nur bei Kaltstart, sonst Hot-Plugging
    def spawn(self, script_dir):
        exe_name = self.cfg.get("EMULATOR_EXE_NAME")
        if self._is_exe_running():
            self.already_running = True
            self.log_cb(prefix + f"ℹ️ '{exe_name}' läuft bereits. Klinke mich asynchron ein...")
            return True

        self.already_running = False
        batch_name = self.cfg.get("BATCH_NAME")
        batch_path = os.path.join(script_dir, batch_name)
        self.log_cb(prefix + f"Starte Emulator-Prozess: {batch_path}")
        try:
            self.process = subprocess.Popen(
                [batch_path], cwd=script_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, shell=True
            )
            os.set_blocking(self.process.stdout.fileno(), False)
            return True
        except Exception as e:
            self.log_cb(prefix + f"❌ Prozess-Start fehlgeschlagen: {e}")
            return False

    # Liest Log-Zeile, wenn Prozess selbst gestartet wurde
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

    # Überprüft zyklisch das Beenden des Emulators
    def is_terminated(self):
        if self.already_running:
            return not self._is_exe_running()
        if not self.process:
            return True
        return self.process.poll() is not None

    # Killt Prozess, sofern selbst gestartet
    def terminate(self):
        if self.process and not self.already_running:
            try: self.process.terminate()
            except: pass
            self.process = None
			
class AranymMidiGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(TITEL)

        # Konfiguration laden
        self.cfg = ConfigManager(CONFIG_FILE)

        # Geometrie aus Config lesen
        width = self.cfg.get("WINDOW_WIDTH")
        height = self.cfg.get("WINDOW_HEIGHT")
        pos_x = self.cfg.get("WINDOW_POS_X")
        pos_y = self.cfg.get("WINDOW_POS_Y")
        
        # Fenstergröße und Position setzen
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.root.configure(bg="#2e2e2e")

        # Logik-Engines instanziieren
        self.midi_engine = MidiEngine(self.cfg, self.append_log, self.signal_midi_activity)
        self.emulator = AranymProcess(self.cfg, self.append_log)
        
        self.running = True
        self.last_midi_activity_time = 0.0
        
        # LED-Farbcodes
        self.COLOR_OFF = "#4a0000"       # Inaktiv
        self.COLOR_READY = "#00ff00"     # Bereit (IDLE)
        self.COLOR_ACTIVE = "#ff0000"    # MIDI-Aktivität

        # GUI-Layout aufbauen
        self._build_status_bar()
        self._build_controls_area()      
        self._build_log_area()

        # Schließen-Event abfangen
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Hintergrund-Schleifen starten
        self.root.after(100, self.start_worker_thread)
        self.root.after(150, self.update_gui_loop)

    # Erstellt die LED-Statuszeile
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

    # Erstellt Dropdown und Options-Button
    def _build_controls_area(self):
        self.menu_frame = tk.Frame(self.root, bg="#2e2e2e")
        self.menu_frame.pack(fill=tk.X, side=tk.TOP, padx=10, pady=5)

        label = tk.Label(self.menu_frame, text="Aktives MIDI-Ausgabegerät:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10))
        label.pack(side=tk.LEFT, padx=(0, 10))

        self.port_var = tk.StringVar()
        self.dropdown = ttk.Combobox(self.menu_frame, textvariable=self.port_var, state="readonly", width=35)
        self.dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.dropdown.bind("<<ComboboxSelected>>", self.on_port_changed)

        self.options_btn = ttk.Button(self.menu_frame, text="⚙ Optionen", command=self.open_options_window, width=12)
        self.options_btn.pack(side=tk.RIGHT)

        self.refresh_midi_ports()

    # Erstellt das Konsolen-Log-Textfeld
    def _build_log_area(self):
        log_label = tk.Label(self.root, text="ARAnyM Console Log:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10))
        log_label.pack(anchor="w", padx=10, pady=(5,0))

        self.log_area = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # Öffnet das Einstellungsfenster
    def open_options_window(self):
        options_win = tk.Toplevel(self.root)
        options_win.title("Konfiguration")
        options_win.geometry("450x410")
        options_win.configure(bg="#2e2e2e")
        options_win.resizable(False, False)
        
        # Fenster in den Vordergrund zwingen
        options_win.transient(self.root)
        options_win.grab_set()
        options_win.columnconfigure(1, weight=1)

        # 1. BATCH_NAME
        tk.Label(options_win, text="Batch-Datei Name:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=0, column=0, sticky="w", padx=15, pady=8)
        batch_entry = ttk.Entry(options_win)
        batch_entry.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=8)
        batch_entry.insert(0, self.cfg.get("BATCH_NAME"))

        # 2. EMULATOR_EXE_NAME
        tk.Label(options_win, text="Prozessname (.exe):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=1, column=0, sticky="w", padx=15, pady=8)
        exe_entry = ttk.Entry(options_win)
        exe_entry.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=8)
        exe_entry.insert(0, self.cfg.get("EMULATOR_EXE_NAME"))

        # 3. MIDI_FILE_PATH
        tk.Label(options_win, text="MIDI Dump Pfad:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=2, column=0, sticky="w", padx=15, pady=8)
        path_entry = ttk.Entry(options_win)
        path_entry.grid(row=2, column=1, sticky="ew", padx=(0, 15), pady=8)
        path_entry.insert(0, self.cfg.get("MIDI_FILE_PATH"))

        # 4. LED_PULSE_DURATION
        tk.Label(options_win, text="LED Impuls (Sek.):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=3, column=0, sticky="w", padx=15, pady=8)
        pulse_entry = ttk.Entry(options_win)
        pulse_entry.grid(row=3, column=1, sticky="ew", padx=(0, 15), pady=8)
        pulse_entry.insert(0, self.cfg.get("LED_PULSE_DURATION"))

        # 5. WINDOW_WIDTH
        tk.Label(options_win, text="Fensterbreite (px):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=4, column=0, sticky="w", padx=15, pady=8)
        width_entry = ttk.Entry(options_win)
        width_entry.grid(row=4, column=1, sticky="ew", padx=(0, 15), pady=8)
        width_entry.insert(0, self.cfg.get("WINDOW_WIDTH"))

        # 6. WINDOW_HEIGHT
        tk.Label(options_win, text="Fensterhöhe (px):", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=5, column=0, sticky="w", padx=15, pady=8)
        height_entry = ttk.Entry(options_win)
        height_entry.grid(row=5, column=1, sticky="ew", padx=(0, 15), pady=8)
        height_entry.insert(0, self.cfg.get("WINDOW_HEIGHT"))

        # 7. WINDOW_POS_X
        tk.Label(options_win, text="Startposition X:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=6, column=0, sticky="w", padx=15, pady=8)
        x_entry = ttk.Entry(options_win)
        x_entry.grid(row=6, column=1, sticky="ew", padx=(0, 15), pady=8)
        x_entry.insert(0, self.cfg.get("WINDOW_POS_X"))

        # 8. WINDOW_POS_Y
        tk.Label(options_win, text="Startposition Y:", fg="#ffffff", bg="#2e2e2e", font=("Arial", 10)).grid(row=7, column=0, sticky="w", padx=15, pady=8)
        y_entry = ttk.Entry(options_win)
        y_entry.grid(row=7, column=1, sticky="ew", padx=(0, 15), pady=8)
        y_entry.insert(0, self.cfg.get("WINDOW_POS_Y"))

        # Speichert Parameter aus Entry-Feldern
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
            
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.append_log(prefix + "⚙️ Parameter und Prozessname erfolgreich aktualisiert.")
            options_win.destroy()

        # Erstellt untere Button-Leiste
        btn_frame = tk.Frame(options_win, bg="#2e2e2e")
        btn_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        
        ttk.Button(btn_frame, text="Abbrechen", command=options_win.destroy, width=12).pack(side=tk.RIGHT, padx=15)
        ttk.Button(btn_frame, text="Speichern", command=save_options, width=12).pack(side=tk.RIGHT)

    # Aktualisiert die Liste der MIDI-Geräte
    def refresh_midi_ports(self):
        ports = self.midi_engine.get_available_ports()
        self.dropdown['values'] = ports
        
        self.append_log(prefix + "==============================================")
        self.append_log(prefix + "=     Verfügbare Windows MIDI-Ausgänge       =")
        self.append_log(prefix + "==============================================")
        if not ports:
            self.append_log(prefix + "⚠️ Keine MIDI-Geräte in Windows gefunden!")
            return

        target_name = self.cfg.get("DEFAULT_DEVICE_NAME")
        selected_index = 0
        
        for idx, name in enumerate(ports):
            self.append_log(prefix + f"ID {idx}: '{name}'")
            if target_name.lower() in name.lower():
                selected_index = idx

        self.dropdown.current(selected_index)
        self.midi_engine.bind_port(ports[selected_index])

    # Reagiert auf manuellen Portwechsel im Dropdown
    def on_port_changed(self, event=None):
        new_port = self.port_var.get()
        self.midi_engine.bind_port(new_port)

    # Setzt Zeitstempel bei MIDI-Aktivität
    def signal_midi_activity(self):
        self.last_midi_activity_time = time.time()

    # Übergibt Log-Einträge threadsicher an die GUI
    def append_log(self, text):
        if self.running:
            self.root.after(0, lambda: self._safe_append(text))

    # Schreibt Text zeilenweise in das Log-Feld
    def _safe_append(self, text):
        self.log_area.insert(tk.END, text + "\n")
        self.log_area.see(tk.END)

    # Startet den asynchronen Hintergrundthread
    def start_worker_thread(self):
        self.worker_thread = threading.Thread(target=self.monitor_and_stream_core, daemon=True)
        self.worker_thread.start()

    # Ändert Kreisfarbe der Status-LED
    def set_led_color(self, color):
        if self.led_canvas.itemcget(self.led_circle, "fill") != color:
            self.led_canvas.itemconfig(self.led_circle, fill=color)

    # Prüft Zustand und steuert LED-Farben (100Hz)
    def update_gui_loop(self):
        if not self.running:
            return

        now = time.time()
        midi_path = self.cfg.get("MIDI_FILE_PATH")
        pulse_duration = self.cfg.getfloat("LED_PULSE_DURATION")
        
        if not os.path.exists(midi_path):
            self.set_led_color(self.COLOR_OFF)
        elif now - self.last_midi_activity_time <= pulse_duration:
            self.set_led_color(self.COLOR_ACTIVE)
        else:
            self.set_led_color(self.COLOR_READY)

        self.root.after(10, self.update_gui_loop)

    # Kernschleife im Hintergrund-Thread
    def monitor_and_stream_core(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        midi_path = self.cfg.get("MIDI_FILE_PATH")

        if not self.emulator.spawn(script_dir):
            return

        if not self.emulator.already_running:
            if os.path.exists(midi_path):
                try:
                    os.remove(midi_path)
                    self.append_log(prefix + f"Alten MIDI-Dump bereinigt: {midi_path}")
                except Exception as e:
                    self.append_log(prefix + f"⚠️ Fehler beim Löschen des alten Dumps: {e}")
        else:
            self.append_log(prefix + "Klinke mich asynchron in bestehenden MIDI-Stream ein...")

        self.append_log(prefix + f"Warte auf Erstellung von: {midi_path} ...")
        while os.path.exists(midi_path) is False and self.running:
            if self.emulator.is_terminated():
                self.append_log(prefix + "⏹️ Emulator wurde vor Datei-Erstellung beendet. Abbruch.")
                return
            log_line = self.emulator.read_log_line()
            if log_line:
                self.append_log(f"[Aranym] {log_line}")
            time.sleep(0.1)

        self.append_log(prefix + f"Datei verifiziert. Starte Echtzeit-Stream: {midi_path}")
        
        if not self.midi_engine.open_stream():
            return
        
        while self.running:
            if self.emulator.is_terminated():
                self.append_log(prefix + "🏁 Emulator-Prozess beendet. Schließe Bridge...")
                break

            log_line = self.emulator.read_log_line()
            if log_line:
                self.append_log(f"[Aranym] {log_line}")

            self.midi_engine.stream_bytes()
            time.sleep(0.005)

    # Bereinigt Handles und sichert letzten Port beim Beenden
    def on_closing(self):
        self.running = False
        current_port = self.port_var.get()
        if current_port:
            self.cfg.set("DEFAULT_DEVICE_NAME", current_port)
            
        self.emulator.terminate()
        self.midi_engine.close_stream()
        self.midi_engine.close_port()
        self.root.destroy()

# Hauptprogramm-Einstiegspunkt
if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('vista')
    
    app = AranymMidiGUI(root)
    root.mainloop()
