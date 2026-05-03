import tkinter as tk
import json
import os
import threading
import re
import traceback
import sys

from pywebostv.connection import WebOSClient
from pywebostv.controls import MediaControl, SystemControl, InputControl, ApplicationControl

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(__file__)

STORE_FILE = os.path.join(BASE_DIR, "tv_store.json")
print("STORE PATH:",STORE_FILE)

class LGRemoteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LG TV Remote")
        self.root.geometry("500x700")
        self.root.resizable(True, True)

        # State
        self.client = None
        self.media = None
        self.system = None
        self.input_control = None
        self.muted = False
        self.typing_mode = False

        # Load store safely
        self.store = self.load_store()
        
        #App Storage
        self.apps = {}
        
        # UI
        self.control_buttons = []
        self.build_ui()
       
    # ---------- STORE ----------
    def load_store(self):
        if os.path.exists(STORE_FILE):
            try:
                with open(STORE_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_store(self):
        with open(STORE_FILE, "w") as f:
            json.dump(self.store, f)
            
    # ---------- VOL ----------
    def update_volume(self):
        if not self.media:
            return

        try:
            vol = self.media.get_volume()
            self.volume_label.config(text=f"Volume: {vol['volume']}")
        except Exception as e:
            print(e)
    
    def start_volume_polling(self):
        self.poll_volume()

    def poll_volume(self):
        if self.media:
            try:
                vol = self.media.get_volume()
                self.volume_label.config(text=f"Volume: {vol['volume']}")
            except Exception as e:
                print(e)

        self.root.after(1500, self.poll_volume)
    # ---------- UI ----------
    def build_ui(self):
        #IP
        ip_frame = tk.Frame(self.root)
        ip_frame.pack(pady=5)

        tk.Label(ip_frame, text="TV IP:").pack(side="left")

        self.ip_entry = tk.Entry(ip_frame, width=15)
        self.ip_entry.pack(side="left")
        self.ip_entry.insert(0, "192.168.1.")

        tk.Button(self.root, text="Connect", command=self.connect_thread).pack(pady=5)
        tk.Button(self.root, text="Auto Detect TV", command=self.auto_detect).pack(pady=3)
        
        # Connection indicator
        self.indicator = tk.Label(self.root, text="●", fg="red", font=("Arial", 16))
        self.indicator.pack()

        nav = tk.Frame(self.root)
        nav.pack(pady=10)

        self.add_btn(nav, "↑", self.up).grid(row=0, column=1)
        self.add_btn(nav, "←", self.left).grid(row=1, column=0)
        self.add_btn(nav, "OK", self.ok).grid(row=1, column=1)
        self.add_btn(nav, "→", self.right).grid(row=1, column=2)
        self.add_btn(nav, "↓", self.down).grid(row=2, column=1)
        self.add_btn(nav, "Back", self.back).grid(row=3, column=0)
        self.add_btn(nav, "Home", self.home).grid(row=3, column=2)

        #Volume
        vol = tk.Frame(self.root)
        vol.pack(pady=10)

        self.add_btn(vol, "Volume +", self.vol_up).pack(pady=3)
        self.add_btn(vol, "Volume -", self.vol_down).pack(pady=3)
        self.add_btn(vol, "Mute", self.mute_toggle).pack(pady=3)

        # App Launcher UI
        self.app_var = tk.StringVar()
        self.app_var.set("Select App")

        self.app_menu = tk.OptionMenu(self.root, self.app_var, "Loading...")
        self.app_menu.config(width=20)

        self.app_menu.pack(pady=5)
        tk.Button(self.root, text="Launch App", command=self.launch_app).pack(pady=3)

        #Power off
        self.add_btn(self.root, "Power Off", self.power_off).pack(pady=8)

        #Typing mode
        tk.Button(self.root, text="Toggle Typing Mode", command=self.toggle_typing).pack()

        self.status = tk.Label(self.root, text="Not connected", fg="red")
        self.status.pack(pady=10)

        self.volume_label = tk.Label(self.root, text="Volume: --")
        self.volume_label.pack(pady=5)

        self.set_controls(False)

        self.root.bind("<Key>", self.handle_key)

    def add_btn(self, parent, text, cmd):
        btn = tk.Button(parent, text=text, width=10, command=cmd)
        self.control_buttons.append(btn)
        return btn

    def set_controls(self, enabled):
        state = "normal" if enabled else "disabled"
        for b in self.control_buttons:
            b.config(state=state)

    def set_status(self, msg, color="black"):
        self.status.config(text=msg, fg=color)

    def set_indicator(self, connected):
        self.indicator.config(fg="green" if connected else "red")
                    
    # ---------- VALIDATION ----------
    def valid_ip(self, ip):
        pattern = r"^(?:\d{1,3}\.){3}\d{1,3}$"
        if not re.match(pattern, ip):
            return False
        return all(0 <= int(part) <= 255 for part in ip.split("."))

    # ---------- CONNECTION ----------
    def connect_thread(self):
        threading.Thread(target=self.connect_tv, daemon=True).start()

    def connect_tv(self):
        ip = self.ip_entry.get().strip()

        if not self.valid_ip(ip):
            self.set_status("Invalid IP", "red")
            return

        self.set_status("Connecting...", "orange")

        try:
            self.client = WebOSClient(ip)
            self.client.connect()

            connected = False

            for status in self.client.register(self.store):
                print("STATUS:", status)
                if status == WebOSClient.PROMPTED:
                    self.set_status("Accept on TV", "blue")
                elif status == WebOSClient.REGISTERED:
                    connected = True

            if not connected:
                self.reset()
                return

            self.save_store()

            self.media = MediaControl(self.client)
            self.system = SystemControl(self.client)
            self.input_control = InputControl(self.client)
            self.app_control = ApplicationControl(self.client)

            self.input_control.connect_input()

            self.root.after(0, lambda: self.set_status("Connected!", "green"))
            self.root.after(0, lambda: self.set_indicator(True))
            self.root.after(0, lambda: self.set_controls(True))

            self.load_apps()
            
            self.root.after(0, self.populate_apps)
            
            self.start_volume_polling()
    
        except Exception as e:
            traceback.print_exc()
            self.reset()
            self.set_status(f"Error: {e}", "red")

    def reset(self):
        self.client = None
        self.media = None
        self.system = None
        self.input_control = None
        self.set_controls(False)
        self.set_indicator(False)
        self.set_status("Disconnected", "red")

    # ---------- DISCOVERY ----------
    def discover_tv(self):
        import socket

        msg = '\r\n'.join([
            'M-SEARCH * HTTP/1.1',
            'HOST: 239.255.255.250:1900',
            'MAN: "ssdp:discover"',
            'MX: 1',
            'ST: urn:schemas-upnp-org:device:MediaRenderer:1',
            '', ''
        ])

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.settimeout(2)

        try:
            s.sendto(msg.encode('utf-8'), ('239.255.255.250', 1900))

            while True:
                data, addr = s.recvfrom(1024)

                if b"LG" in data or b"webOS" in data:
                    return addr[0]

        except socket.timeout:
            return None

        finally:
            s.close()

    # ---------- WRAPPER ----------
    def auto_detect(self):
        self.set_status("Searching for TV...", "orange")

        ip = self.discover_tv()

        if ip:
            self.ip_entry.delete(0, tk.END)
            self.ip_entry.insert(0, ip)
            self.set_status(f"Found TV: {ip}", "green")
        else:
            self.set_status("No TV found", "red")
            
    # ---------- SAFE CALL ----------
    def safe(self, func, label=None):
        if not self.input_control:
            return
        try:
            func()
            if label:
                self.set_status(label)
        except Exception as e:
            print("ERROR OCCURRED:")
            traceback.print_exc()
            self.set_status(f"Error: {e}", "red")
        
    # ---------- APP FETCH ----------
    def load_apps(self):
        if not self.app_control:
            return

        try:
            app_list = self.app_control.list_apps()
            self.apps = {app['title']: app for app in app_list}
            print("APPS:", self.apps)
        except Exception:
            print("APP LOAD ERROR:")
            traceback.print_exc()
            self.apps = {}
        
    # ---------- APP DROPDOWN ----------
    def populate_apps(self):
        menu = self.app_menu["menu"]
        menu.delete(0, "end")

        if not self.apps:
            menu.add_command(label="No Apps Found", command=lambda: None)
            return

        for name in sorted(self.apps.keys()):
            menu.add_command(
                label=name,
                command=lambda n=name: self.app_var.set(n)
            )
        if self.apps:
            first_app = sorted(self.apps.keys())[0]
            self.app_var.set(first_app)

    # ---------- APP DROPDOWN ----------
    def launch_app(self):
        app_name = self.app_var.get()

        if app_name in ["Select App","Loading..."]:
            self.set_status("Select a valid app", "red")
            return

        app_obj = self.apps[app_name]

        def action():
            self.app_control.launch(app_obj)
            self.input_control.connect_input()  # reconnect input

        self.safe(action, f"Launching {app_name}")
    
    # ---------- CONTROLS ----------
    def up(self): self.safe(lambda: self.input_control.up(), "Up")
    def down(self): self.safe(lambda: self.input_control.down(), "Down")
    def left(self): self.safe(lambda: self.input_control.left(), "Left")
    def right(self): self.safe(lambda: self.input_control.right(), "Right")
    def ok(self): self.safe(lambda: self.input_control.ok(), "OK")
    def back(self): self.safe(lambda: self.input_control.back(), "Back")
    def home(self): self.safe(lambda: self.input_control.home(), "Home")

    def vol_up(self):
        self.safe(lambda: self.media.volume_up(), "Volume +")
        self.update_volume()

    def vol_down(self):
        self.safe(lambda: self.media.volume_down(), "Volume -")
        self.update_volume()

    def mute_toggle(self):
        def action():
            self.muted = not self.muted
            self.media.mute(self.muted)
            self.set_status("Muted" if self.muted else "Unmuted")
        self.safe(action)

    def power_off(self):
        self.safe(lambda: self.system.power_off(), "TV Off")

    def toggle_typing(self):
        self.typing_mode = not self.typing_mode
        self.set_status("Typing ON" if self.typing_mode else "Typing OFF")

    # ---------- HOTKEY ----------
    def handle_key(self, event):
        if not self.input_control:
            return

        key = event.keysym

        if self.typing_mode:
            try:
                if len(event.char) == 1:
                    self.input_control.type(event.char)
                elif key == "BackSpace":
                    self.input_control.delete()
                elif key == "Return":
                    self.input_control.enter()
            except:
                self.reset()
            return

        if key.lower() == "w": self.up()
        elif key.lower() == "a": self.left()
        elif key.lower() == "s": self.down()
        elif key.lower() == "d": self.right()
        elif key.lower() == "h": self.home()
        elif key == "Return": self.ok()
        elif key == "Escape": self.back()


# ---------- RUN ----------
root = tk.Tk()
app = LGRemoteApp(root)
root.mainloop()
