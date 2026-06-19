import os
import sys
import re
import json
import shutil
import glob
import logging
import datetime
import threading
import subprocess
import webbrowser
from urllib.parse import urlparse
import customtkinter
from PIL import Image

def get_short_path(long_path):
    try:
        import ctypes
        from ctypes import wintypes
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        GetShortPathNameW.restype = wintypes.DWORD
        
        buf_size = GetShortPathNameW(long_path, None, 0)
        if buf_size > 0:
            buffer = ctypes.create_unicode_buffer(buf_size)
            if GetShortPathNameW(long_path, buffer, buf_size) > 0:
                return buffer.value
    except Exception:
        pass
    return long_path

INSTALL_LOG_PATTERNS = [
    (re.compile(r"\[SUCCESS\] Installed (.+?) via Winget\."), "Winget"),
    (re.compile(r"\[SUCCESS\] Installed (.+?) via local installer\."), "Local Installer"),
    (re.compile(r"\[SUCCESS\] Copied (.+?) Portable to "), "Portable-Copy"),
    (re.compile(r"\[SUCCESS\] Copied (.+?) to "), "Portable-Copy"),
]

METHOD_LABELS = {
    "Winget": "Winget",
    "Local Installer": "Local Installer",
    "Portable-Copy": "Portable Copy",
    "Portable (Local)": "Portable (Local)",
}

def normalize_homepage_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url

def get_homepage_display(url):
    normalized = normalize_homepage_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    host = parsed.netloc or parsed.path
    if host.startswith("www."):
        host = host[4:]
    return host

# Setup standard logging
logger = logging.getLogger("SoftwareManager")
logger.setLevel(logging.INFO)

class CustomFormatter(logging.Formatter):
    def format(self, record):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{now}] {record.getMessage()}"

# File logging
file_handler = logging.FileHandler("activity_log.txt", mode="a", encoding="utf-8")
file_handler.setFormatter(CustomFormatter())
logger.addHandler(file_handler)

# Custom GUI log handler
class GUIHandler(logging.Handler):
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        log_entry = self.format(record) + "\n"
        # Thread-safe GUI update
        if self.textbox.winfo_exists():
            self.textbox.after(0, self.update_textbox, log_entry)

    def update_textbox(self, text):
        try:
            self.textbox.configure(state="normal")
            self.textbox.insert("end", text)
            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        except Exception:
            pass

class AppDetailPopup(customtkinter.CTkToplevel):
    def __init__(self, parent, app_data, install_status=None):
        super().__init__(parent)
        self.title("Application Details")
        self.geometry("420x360")
        self.resizable(False, False)
        
        # Keep on top of main app window
        self.attributes("-topmost", True)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        frame = customtkinter.CTkFrame(self, corner_radius=12, fg_color=("#f1f5f9", "#1e293b"))
        frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        
        # Name
        name_lbl = customtkinter.CTkLabel(
            frame, text=app_data.get("Name", "Unknown Application"),
            font=customtkinter.CTkFont(size=18, weight="bold")
        )
        name_lbl.grid(row=0, column=0, padx=15, pady=(15, 2), sticky="w")
        
        # Type
        type_lbl = customtkinter.CTkLabel(
            frame, text=f"Type: {app_data.get('Type', 'Unknown')}",
            font=customtkinter.CTkFont(size=12, slant="italic"),
            text_color=("#64748b", "#94a3b8")
        )
        type_lbl.grid(row=1, column=0, padx=15, pady=2, sticky="w")

        # Installation status
        if install_status:
            if install_status.get("installed"):
                status_text = f"Status: Installed"
                method = install_status.get("method")
                if method:
                    status_text += f" via {METHOD_LABELS.get(method, method)}"
                status_color = ("#059669", "#34d399")
            else:
                status_text = "Status: Not installed"
                status_color = ("#94a3b8", "#64748b")

            status_lbl = customtkinter.CTkLabel(
                frame, text=status_text,
                font=customtkinter.CTkFont(size=12, weight="bold"),
                text_color=status_color
            )
            status_lbl.grid(row=2, column=0, padx=15, pady=2, sticky="w")
            desc_row = 3
            desc_box_row = 4
            close_row = 5
        else:
            desc_row = 2
            desc_box_row = 3
            close_row = 4
        
        # Description
        desc_lbl = customtkinter.CTkLabel(
            frame, text="Description:",
            font=customtkinter.CTkFont(size=12, weight="bold")
        )
        desc_lbl.grid(row=desc_row, column=0, padx=15, pady=(10, 0), sticky="w")
        
        desc_box = customtkinter.CTkTextbox(
            frame, width=360, height=90, wrap="word",
            fg_color="transparent", border_width=0,
            font=customtkinter.CTkFont(size=12)
        )
        desc_box.insert("0.0", app_data.get("Description", "No description provided."))
        desc_box.configure(state="disabled")
        desc_box.grid(row=desc_box_row, column=0, padx=15, pady=(0, 10), sticky="nsew")

        homepage = app_data.get("Homepage", "").strip()
        if homepage:
            homepage_row = desc_box_row + 1
            close_row = homepage_row + 1
            homepage_lbl = customtkinter.CTkLabel(
                frame, text="Homepage:",
                font=customtkinter.CTkFont(size=12, weight="bold")
            )
            homepage_lbl.grid(row=homepage_row, column=0, padx=15, pady=(0, 2), sticky="w")

            homepage_btn = customtkinter.CTkButton(
                frame, text=get_homepage_display(homepage), anchor="w",
                fg_color="transparent", text_color=("#2563eb", "#60a5fa"),
                hover_color=("#e2e8f0", "#334155"),
                command=lambda url=homepage: webbrowser.open(normalize_homepage_url(url))
            )
            homepage_btn.grid(row=homepage_row, column=0, padx=(95, 15), pady=(0, 10), sticky="w")
        else:
            close_row = desc_box_row + 1
        
        # Close Button
        close_btn = customtkinter.CTkButton(
            frame, text="Close", width=90, command=self.destroy,
            fg_color=("#1f538d", "#1f538d"), hover_color=("#2b6cb0", "#2b6cb0")
        )
        close_btn.grid(row=close_row, column=0, padx=15, pady=(0, 15), sticky="e")


class AddProgramDialog(customtkinter.CTkToplevel):
    def __init__(self, parent, edit_app_data=None):
        super().__init__(parent)
        self.parent = parent
        self.edit_app_data = edit_app_data # If provided, we are editing this app
        
        self.title("Edit Program" if self.edit_app_data else "Add New Program")
        self.geometry("520x650")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Main container
        self.main_frame = customtkinter.CTkFrame(self, corner_radius=12, fg_color=("#f1f5f9", "#1e293b"))
        self.main_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_text = f"Edit Program: {self.edit_app_data.get('Name')}" if self.edit_app_data else "Register New Program"
        title_lbl = customtkinter.CTkLabel(
            self.main_frame, text=title_text,
            font=customtkinter.CTkFont(size=18, weight="bold")
        )
        title_lbl.grid(row=0, column=0, columnspan=3, padx=15, pady=(15, 15))
        
        # Name
        name_lbl = customtkinter.CTkLabel(self.main_frame, text="Name:", font=customtkinter.CTkFont(weight="bold"))
        name_lbl.grid(row=1, column=0, padx=15, pady=8, sticky="w")
        self.name_entry = customtkinter.CTkEntry(self.main_frame, placeholder_text="e.g. VLC Media Player")
        self.name_entry.grid(row=1, column=1, columnspan=2, padx=15, pady=8, sticky="ew")
        
        # Type OptionMenu
        type_lbl = customtkinter.CTkLabel(self.main_frame, text="Type:", font=customtkinter.CTkFont(weight="bold"))
        type_lbl.grid(row=2, column=0, padx=15, pady=8, sticky="w")
        self.type_var = customtkinter.StringVar(value="Installer")
        self.type_menu = customtkinter.CTkOptionMenu(
            self.main_frame, values=["Installer", "Portable-Copy", "Portable-Run"],
            variable=self.type_var, command=self.on_type_changed
        )
        self.type_menu.grid(row=2, column=1, padx=15, pady=8, sticky="w")
        
        # Logo Path
        logo_lbl = customtkinter.CTkLabel(self.main_frame, text="Logo Path:", font=customtkinter.CTkFont(weight="bold"))
        logo_lbl.grid(row=3, column=0, padx=15, pady=8, sticky="w")
        self.logo_entry = customtkinter.CTkEntry(self.main_frame, placeholder_text="Assets/logo.png")
        self.logo_entry.grid(row=3, column=1, padx=(15, 5), pady=8, sticky="ew")
        self.logo_browse = customtkinter.CTkButton(self.main_frame, text="Browse", width=70, command=self.browse_logo)
        self.logo_browse.grid(row=3, column=2, padx=(0, 15), pady=8, sticky="e")
        
        # Dynamic Frames Container (Row 4)
        self.dynamic_container = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.dynamic_container.grid(row=4, column=0, columnspan=3, padx=0, pady=5, sticky="ew")
        self.dynamic_container.columnconfigure(1, weight=1)
        
        # 1. Installer Frame
        self.installer_frame = customtkinter.CTkFrame(self.dynamic_container, fg_color="transparent")
        self.installer_frame.columnconfigure(1, weight=1)
        
        winget_lbl = customtkinter.CTkLabel(self.installer_frame, text="Winget ID:", font=customtkinter.CTkFont(weight="bold"))
        winget_lbl.grid(row=0, column=0, padx=15, pady=8, sticky="w")
        self.winget_entry = customtkinter.CTkEntry(self.installer_frame, placeholder_text="e.g. VideoLAN.VLC")
        self.winget_entry.grid(row=0, column=1, columnspan=2, padx=15, pady=8, sticky="ew")
        
        loc_inst_lbl = customtkinter.CTkLabel(self.installer_frame, text="Local Installer:", font=customtkinter.CTkFont(weight="bold"))
        loc_inst_lbl.grid(row=1, column=0, padx=15, pady=8, sticky="w")
        self.loc_inst_entry = customtkinter.CTkEntry(self.installer_frame, placeholder_text="LocalInstallers/setup.exe")
        self.loc_inst_entry.grid(row=1, column=1, padx=(15, 5), pady=8, sticky="ew")
        self.loc_inst_browse = customtkinter.CTkButton(self.installer_frame, text="Browse", width=70, command=self.browse_local_installer)
        self.loc_inst_browse.grid(row=1, column=2, padx=(0, 15), pady=8, sticky="e")
        
        args_lbl = customtkinter.CTkLabel(self.installer_frame, text="Silent Args:", font=customtkinter.CTkFont(weight="bold"))
        args_lbl.grid(row=2, column=0, padx=15, pady=8, sticky="w")
        self.args_entry = customtkinter.CTkEntry(self.installer_frame, placeholder_text="e.g. /S or /silent")
        self.args_entry.grid(row=2, column=1, columnspan=2, padx=15, pady=8, sticky="ew")
        
        settings_lbl = customtkinter.CTkLabel(self.installer_frame, text="Settings File:", font=customtkinter.CTkFont(weight="bold"))
        settings_lbl.grid(row=3, column=0, padx=15, pady=8, sticky="w")
        self.settings_entry = customtkinter.CTkEntry(self.installer_frame, placeholder_text="e.g. LocalInstallers/notepad_settings.bat")
        self.settings_entry.grid(row=3, column=1, padx=(15, 5), pady=8, sticky="ew")
        self.settings_browse = customtkinter.CTkButton(self.installer_frame, text="Browse", width=70, command=self.browse_settings_installer)
        self.settings_browse.grid(row=3, column=2, padx=(0, 15), pady=8, sticky="e")
        
        # 2. Portable-Copy Frame
        self.copy_frame = customtkinter.CTkFrame(self.dynamic_container, fg_color="transparent")
        self.copy_frame.columnconfigure(1, weight=1)
        
        src_lbl = customtkinter.CTkLabel(self.copy_frame, text="Source Folder:", font=customtkinter.CTkFont(weight="bold"))
        src_lbl.grid(row=0, column=0, padx=15, pady=8, sticky="w")
        self.src_entry = customtkinter.CTkEntry(self.copy_frame, placeholder_text="PortableApps/AppName")
        self.src_entry.grid(row=0, column=1, padx=(15, 5), pady=8, sticky="ew")
        self.src_browse = customtkinter.CTkButton(self.copy_frame, text="Browse", width=70, command=self.browse_source_folder)
        self.src_browse.grid(row=0, column=2, padx=(0, 15), pady=8, sticky="e")
        
        dst_lbl = customtkinter.CTkLabel(self.copy_frame, text="Target Dest:", font=customtkinter.CTkFont(weight="bold"))
        dst_lbl.grid(row=1, column=0, padx=15, pady=8, sticky="w")
        self.dst_entry = customtkinter.CTkEntry(self.copy_frame, placeholder_text="C:\\PortablePrograms\\AppName")
        self.dst_entry.grid(row=1, column=1, padx=(15, 5), pady=8, sticky="ew")
        self.dst_browse = customtkinter.CTkButton(self.copy_frame, text="Browse", width=70, command=self.browse_target_destination)
        self.dst_browse.grid(row=1, column=2, padx=(0, 15), pady=8, sticky="e")
        
        # 3. Portable-Run Frame
        self.run_frame = customtkinter.CTkFrame(self.dynamic_container, fg_color="transparent")
        self.run_frame.columnconfigure(1, weight=1)
        
        run_path_lbl = customtkinter.CTkLabel(self.run_frame, text="Local Path:", font=customtkinter.CTkFont(weight="bold"))
        run_path_lbl.grid(row=0, column=0, padx=15, pady=8, sticky="w")
        self.run_path_entry = customtkinter.CTkEntry(self.run_frame, placeholder_text="PortableApps/AppName/app.exe")
        self.run_path_entry.grid(row=0, column=1, padx=(15, 5), pady=8, sticky="ew")
        self.run_path_browse = customtkinter.CTkButton(self.run_frame, text="Browse", width=70, command=self.browse_run_path)
        self.run_path_browse.grid(row=0, column=2, padx=(0, 15), pady=8, sticky="e")
        
        # Description (Row 5)
        desc_lbl = customtkinter.CTkLabel(self.main_frame, text="Description:", font=customtkinter.CTkFont(weight="bold"))
        desc_lbl.grid(row=5, column=0, padx=15, pady=8, sticky="nw")
        self.desc_entry = customtkinter.CTkEntry(self.main_frame, placeholder_text="Brief description of the app...")
        self.desc_entry.grid(row=5, column=1, columnspan=2, padx=15, pady=8, sticky="ew")

        # Homepage (Row 6)
        homepage_lbl = customtkinter.CTkLabel(self.main_frame, text="Homepage:", font=customtkinter.CTkFont(weight="bold"))
        homepage_lbl.grid(row=6, column=0, padx=15, pady=8, sticky="w")
        self.homepage_entry = customtkinter.CTkEntry(self.main_frame, placeholder_text="https://example.com")
        self.homepage_entry.grid(row=6, column=1, columnspan=2, padx=15, pady=8, sticky="ew")
        
        # Buttons (Row 7)
        buttons_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        buttons_frame.grid(row=7, column=0, columnspan=3, padx=15, pady=(20, 15), sticky="ew")
        buttons_frame.columnconfigure(0, weight=1)
        
        self.cancel_btn = customtkinter.CTkButton(
            buttons_frame, text="Cancel", width=90, fg_color=("#94a3b8", "#475569"),
            hover_color=("#788896", "#334155"), command=self.destroy
        )
        self.cancel_btn.grid(row=0, column=1, padx=5, pady=5)
        
        self.save_btn = customtkinter.CTkButton(
            buttons_frame, text="Save Changes" if self.edit_app_data else "Save Program", width=110,
            fg_color=("#10b981", "#059669"), hover_color=("#059669", "#047857"), command=self.save_program
        )
        self.save_btn.grid(row=0, column=2, padx=5, pady=5)
        
        self.load_values_and_layout()

    def load_values_and_layout(self):
        if self.edit_app_data:
            # Pre-fill standard fields
            self.name_entry.insert(0, self.edit_app_data.get("Name", ""))
            self.logo_entry.insert(0, self.edit_app_data.get("Logo", ""))
            self.desc_entry.insert(0, self.edit_app_data.get("Description", ""))
            self.homepage_entry.insert(0, self.edit_app_data.get("Homepage", ""))
            
            # Select Type
            app_type = self.edit_app_data.get("Type", "Installer")
            self.type_var.set(app_type)
            self.on_type_changed(app_type)
            
            # Fill type specific fields
            if app_type == "Installer":
                self.winget_entry.insert(0, self.edit_app_data.get("WingetID", ""))
                self.loc_inst_entry.insert(0, self.edit_app_data.get("LocalInstaller", ""))
                self.args_entry.insert(0, self.edit_app_data.get("SilentArgs", ""))
                self.settings_entry.insert(0, self.edit_app_data.get("SettingsInstaller", ""))
            elif app_type == "Portable-Copy":
                self.src_entry.insert(0, self.edit_app_data.get("SourceFolder", ""))
                self.dst_entry.insert(0, self.edit_app_data.get("TargetDestination", ""))
            elif app_type == "Portable-Run":
                self.run_path_entry.insert(0, self.edit_app_data.get("LocalPath", ""))
        else:
            self.on_type_changed("Installer")

    def on_type_changed(self, selected_type):
        self.installer_frame.grid_forget()
        self.copy_frame.grid_forget()
        self.run_frame.grid_forget()
        
        if selected_type == "Installer":
            self.installer_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        elif selected_type == "Portable-Copy":
            self.copy_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        elif selected_type == "Portable-Run":
            self.run_frame.grid(row=0, column=0, columnspan=3, sticky="ew")

    def make_relative(self, path):
        try:
            rel = os.path.relpath(path, os.getcwd())
            if not rel.startswith(".."):
                return rel
        except Exception:
            pass
        return path

    def browse_logo(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("PNG Images", "*.png"), ("All Files", "*.*")])
        if path:
            self.logo_entry.delete(0, "end")
            self.logo_entry.insert(0, self.make_relative(path))

    def browse_local_installer(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Executables", "*.exe;*.msi"), ("All Files", "*.*")])
        if path:
            self.loc_inst_entry.delete(0, "end")
            self.loc_inst_entry.insert(0, self.make_relative(path))

    def browse_settings_installer(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Executables & Scripts", "*.exe;*.bat;*.cmd;*.reg;*.msi;*.ps1"), ("All Files", "*.*")])
        if path:
            self.settings_entry.delete(0, "end")
            self.settings_entry.insert(0, self.make_relative(path))

    def browse_source_folder(self):
        from tkinter import filedialog
        path = filedialog.askdirectory()
        if path:
            self.src_entry.delete(0, "end")
            self.src_entry.insert(0, self.make_relative(path))

    def browse_target_destination(self):
        from tkinter import filedialog
        path = filedialog.askdirectory()
        if path:
            self.dst_entry.delete(0, "end")
            self.dst_entry.insert(0, path)

    def browse_run_path(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        if path:
            self.run_path_entry.delete(0, "end")
            self.run_path_entry.insert(0, self.make_relative(path))

    def save_program(self):
        from tkinter import messagebox
        name = self.name_entry.get().strip()
        app_type = self.type_var.get()
        logo = self.logo_entry.get().strip()
        desc = self.desc_entry.get().strip()
        homepage = self.homepage_entry.get().strip()
        
        if not name:
            messagebox.showwarning("Validation Error", "Application Name is required.")
            return
            
        app_data = {
            "Name": name,
            "Type": app_type,
            "Logo": logo if logo else "Assets/default_logo.png",
            "Description": desc if desc else "No description provided.",
            "Homepage": homepage
        }
        
        if app_type == "Installer":
            winget_id = self.winget_entry.get().strip()
            local_inst = self.loc_inst_entry.get().strip()
            args = self.args_entry.get().strip()
            
            if not winget_id and not local_inst:
                messagebox.showwarning("Validation Error", "Either Winget ID or Local Installer Path must be provided.")
                return
                
            app_data["WingetID"] = winget_id
            app_data["LocalInstaller"] = local_inst
            app_data["SilentArgs"] = args
            app_data["SettingsInstaller"] = self.settings_entry.get().strip()
            
        elif app_type == "Portable-Copy":
            src = self.src_entry.get().strip()
            dst = self.dst_entry.get().strip()
            
            if not src or not dst:
                messagebox.showwarning("Validation Error", "Both Source Folder and Target Destination paths are required.")
                return
                
            app_data["SourceFolder"] = src
            app_data["TargetDestination"] = dst
            
        elif app_type == "Portable-Run":
            run_path = self.run_path_entry.get().strip()
            
            if not run_path:
                messagebox.showwarning("Validation Error", "Local Path is required.")
                return
                
            app_data["LocalPath"] = run_path
            
        # If in edit mode, remove the old registry item first
        if self.edit_app_data:
            old_name = self.edit_app_data.get("Name")
            
            if "Maintenance_Tools" in self.parent.config_data:
                self.parent.config_data["Maintenance_Tools"] = [
                    t for t in self.parent.config_data["Maintenance_Tools"] if t.get("Name") != old_name
                ]
            if "Installers_After_Format" in self.parent.config_data:
                self.parent.config_data["Installers_After_Format"] = [
                    i for i in self.parent.config_data["Installers_After_Format"] if i.get("Name") != old_name
                ]
            
        # Append to configuration registry lists
        if app_type == "Portable-Run":
            if "Maintenance_Tools" not in self.parent.config_data:
                self.parent.config_data["Maintenance_Tools"] = []
            self.parent.config_data["Maintenance_Tools"].append(app_data)
        else:
            if "Installers_After_Format" not in self.parent.config_data:
                self.parent.config_data["Installers_After_Format"] = []
            self.parent.config_data["Installers_After_Format"].append(app_data)
            
        self.parent.save_config()
        
        if self.edit_app_data:
            logger.info(f"Updated configuration for: {name} (Type: {app_type})")
        else:
            logger.info(f"Added application to registry: {name} (Type: {app_type})")
            
        self.parent.refresh_ui()
        self.destroy()


class PortableManagerApp(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Portable Software & Maintenance Manager")
        self.geometry("950x650")
        self.resizable(False, False)
        
        # Theme configuration
        customtkinter.set_appearance_mode("system")
        customtkinter.set_default_color_theme("blue")
        
        # Registry and UI lists
        self.config_data = {}
        self.checkbox_vars = {} # Maps installer name -> BooleanVar
        self.install_status_cache = {}  # Maps app name -> status dict
        self.install_history = {}
        self.status_scan_in_progress = False
        
        self.load_config()
        self.create_layout()
        
        # Connect logger to GUI terminal view
        gui_handler = GUIHandler(self.log_textbox)
        gui_handler.setFormatter(CustomFormatter())
        logger.addHandler(gui_handler)
        
        # Set active tab to Software Installation on startup
        self.tabview.set("🚀 Software Installation")
        logger.info("Application started successfully.")
        self.after(500, lambda: self.start_installation_scan(show_log=False))

    def load_config(self):
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config_data = json.load(f)
            except Exception as e:
                print(f"Error loading config.json: {e}")
                self.config_data = {}
        else:
            self.config_data = {}

    def save_config(self):
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)
        except Exception as e:
            logger.error(f"[ERROR] Failed to save config.json: {e}")

    def refresh_ui(self):
        self.populate_maintenance_tab()
        self.populate_installers_tab()
        self.populate_installed_tab()

    def parse_install_history(self):
        history = {}
        log_path = "activity_log.txt"
        if not os.path.exists(log_path):
            return history

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    for pattern, method in INSTALL_LOG_PATTERNS:
                        match = pattern.search(line)
                        if match:
                            history[match.group(1).strip()] = method
        except Exception as e:
            logger.error(f"[ERROR] Failed to read install history from log: {e}")

        return history

    def is_winget_installed(self, winget_id):
        if not winget_id:
            return False
        try:
            res = subprocess.run(
                f'winget list --id "{winget_id}" --disable-interactivity',
                shell=True, capture_output=True, text=True, timeout=45
            )
            return res.returncode == 0
        except Exception:
            return False

    def is_portable_copy_installed(self, target_destination):
        if not target_destination:
            return False
        try:
            return os.path.isdir(target_destination) and bool(os.listdir(target_destination))
        except Exception:
            return False

    def detect_installation_status(self, app):
        name = app.get("Name", "Unknown")
        app_type = app.get("Type", "")
        log_method = self.install_history.get(name)
        result = {"installed": False, "method": None, "details": ""}

        if app_type == "Installer":
            winget_id = app.get("WingetID", "")
            if winget_id and self.is_winget_installed(winget_id):
                result["installed"] = True
                result["method"] = log_method or "Winget"
                result["details"] = f"Detected via Winget ({winget_id})"
                return result

            target = app.get("TargetDestination", "")
            if self.is_portable_copy_installed(target):
                result["installed"] = True
                result["method"] = log_method or "Portable-Copy"
                result["details"] = f"Found at {target}"
                return result

            if log_method == "Local Installer":
                result["installed"] = True
                result["method"] = "Local Installer"
                result["details"] = "Recorded in activity log"
                return result

        elif app_type == "Portable-Copy":
            target = app.get("TargetDestination", "")
            if self.is_portable_copy_installed(target):
                result["installed"] = True
                result["method"] = log_method or "Portable-Copy"
                result["details"] = f"Found at {target}"
                return result

        elif app_type == "Portable-Run":
            local_path = app.get("LocalPath", "")
            if local_path and os.path.exists(local_path):
                result["installed"] = True
                result["method"] = "Portable (Local)"
                result["details"] = f"Available at {local_path}"
                return result

        return result

    def get_all_registry_apps(self):
        apps = []
        for tool in self.config_data.get("Maintenance_Tools", []):
            apps.append(tool)
        for inst in self.config_data.get("Installers_After_Format", []):
            apps.append(inst)
        return apps

    def get_install_status(self, app):
        name = app.get("Name")
        if name in self.install_status_cache:
            return self.install_status_cache[name]
        return {"installed": False, "method": None, "details": "Not scanned yet"}

    def create_status_badge(self, parent, install_status):
        if install_status.get("checking"):
            text = "Checking..."
            fg_color = ("#f59e0b", "#d97706")
            text_color = "white"
        elif install_status.get("installed"):
            method = install_status.get("method")
            method_label = METHOD_LABELS.get(method, method) if method else "Installed"
            text = f"✓ {method_label}"
            fg_color = ("#10b981", "#059669")
            text_color = "white"
        else:
            text = "Not Installed"
            fg_color = ("#e2e8f0", "#334155")
            text_color = ("#64748b", "#94a3b8")

        return customtkinter.CTkLabel(
            parent, text=text, corner_radius=6,
            font=customtkinter.CTkFont(size=10, weight="bold"),
            fg_color=fg_color, text_color=text_color,
            padx=8, pady=2
        )

    def start_installation_scan(self, show_log=True):
        if self.status_scan_in_progress:
            return

        self.status_scan_in_progress = True
        self.install_history = self.parse_install_history()
        apps = self.get_all_registry_apps()

        for app in apps:
            name = app.get("Name")
            self.install_status_cache[name] = {"installed": False, "method": None, "details": "", "checking": True}

        self.refresh_ui()

        if show_log:
            logger.info("Scanning installed applications...")

        threading.Thread(target=self._run_installation_scan, args=(apps, show_log), daemon=True).start()

    def _run_installation_scan(self, apps, show_log):
        try:
            for app in apps:
                name = app.get("Name")
                status = self.detect_installation_status(app)
                status["checking"] = False
                self.install_status_cache[name] = status
                self.after(0, self._update_app_status_ui, app, status)
        finally:
            self.status_scan_in_progress = False
            if show_log:
                installed_count = sum(1 for s in self.install_status_cache.values() if s.get("installed"))
                logger.info(f"Scan complete: {installed_count} of {len(apps)} applications are installed.")
            self.after(0, self.populate_installed_tab)
            if hasattr(self, "refresh_status_btn"):
                self.after(0, lambda: self.refresh_status_btn.configure(state="normal", text="🔄 Refresh Scan"))

    def _update_app_status_ui(self, app, status):
        name = app.get("Name")
        for scroll_frame in [getattr(self, "maint_scroll", None), getattr(self, "inst_scroll", None)]:
            if not scroll_frame:
                continue
            badge = getattr(scroll_frame, f"status_badge_{name}", None)
            if badge and badge.winfo_exists():
                new_badge = self.create_status_badge(badge.master, status)
                new_badge.grid(row=badge.grid_info().get("row", 0), column=badge.grid_info().get("column", 0),
                               padx=badge.grid_info().get("padx", 0), pady=badge.grid_info().get("pady", 0), sticky="w")
                setattr(scroll_frame, f"status_badge_{name}", new_badge)
                badge.destroy()

    def create_layout(self):
        # Configure Main Grid: Left panel (main) vs Right panel (sidebar)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=270)
        self.grid_rowconfigure(0, weight=1)
        
        # LEFT AREA: Container Frame
        self.left_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.left_frame.grid(row=0, column=0, padx=(15, 5), pady=15, sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(0, weight=1)
        
        # Tabview (Top/Left alignment)
        self.tabview = customtkinter.CTkTabview(self.left_frame, corner_radius=12)
        self.tabview.grid(row=0, column=0, sticky="nsew")
        
        # Add Tabs
        tab_maintenance = "🛠️ Diagnostics & Maintenance"
        tab_installers = "🚀 Software Installation"
        tab_installed = "📦 Installed Apps"
        self.tabview.add(tab_maintenance)
        self.tabview.add(tab_installers)
        self.tabview.add(tab_installed)
        
        # Configure Tab content layout
        self.tabview.tab(tab_maintenance).grid_columnconfigure(0, weight=1)
        self.tabview.tab(tab_maintenance).grid_rowconfigure(0, weight=1)
        
        self.tabview.tab(tab_installers).grid_columnconfigure(0, weight=1)
        self.tabview.tab(tab_installers).grid_rowconfigure(0, weight=0) # row 0: static header
        self.tabview.tab(tab_installers).grid_rowconfigure(1, weight=1) # row 1: scroll frame

        self.tabview.tab(tab_installed).grid_columnconfigure(0, weight=1)
        self.tabview.tab(tab_installed).grid_rowconfigure(0, weight=0)
        self.tabview.tab(tab_installed).grid_rowconfigure(1, weight=1)
        
        # Populate Maintenance Tab (Scrollable Frame)
        self.maint_scroll = customtkinter.CTkScrollableFrame(self.tabview.tab(tab_maintenance), fg_color="transparent")
        self.maint_scroll.grid(row=0, column=0, sticky="nsew")
        self.maint_scroll.grid_columnconfigure(0, weight=1)
        self.populate_maintenance_tab()
        
        # Software Installation static header panel
        self.inst_header = customtkinter.CTkFrame(self.tabview.tab(tab_installers), fg_color="transparent")
        self.inst_header.grid(row=0, column=0, padx=5, pady=(5, 10), sticky="ew")
        
        # Add Program button
        self.add_btn = customtkinter.CTkButton(
            self.inst_header, text="➕ Add Program", width=120,
            fg_color=("#1f538d", "#1e40af"), hover_color=("#2b6cb0", "#1d4ed8"),
            command=self.open_add_program_dialog
        )
        self.add_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        # Populate Installers Tab (Scrollable Frame)
        self.inst_scroll = customtkinter.CTkScrollableFrame(self.tabview.tab(tab_installers), fg_color="transparent")
        self.inst_scroll.grid(row=1, column=0, sticky="nsew")
        self.inst_scroll.grid_columnconfigure(0, weight=1)
        self.populate_installers_tab()

        # Installed Apps tab header
        self.installed_header = customtkinter.CTkFrame(self.tabview.tab(tab_installed), fg_color="transparent")
        self.installed_header.grid(row=0, column=0, padx=5, pady=(5, 10), sticky="ew")
        self.installed_header.grid_columnconfigure(0, weight=1)

        self.installed_summary_lbl = customtkinter.CTkLabel(
            self.installed_header,
            text="Shows applications from your registry that are already installed on this PC.",
            font=customtkinter.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8"),
            anchor="w"
        )
        self.installed_summary_lbl.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.refresh_status_btn = customtkinter.CTkButton(
            self.installed_header, text="🔄 Refresh Scan", width=130,
            fg_color=("#1f538d", "#1e40af"), hover_color=("#2b6cb0", "#1d4ed8"),
            command=self.on_refresh_scan_clicked
        )
        self.refresh_status_btn.grid(row=0, column=1, padx=5, pady=5, sticky="e")

        self.installed_scroll = customtkinter.CTkScrollableFrame(self.tabview.tab(tab_installed), fg_color="transparent")
        self.installed_scroll.grid(row=1, column=0, sticky="nsew")
        self.installed_scroll.grid_columnconfigure(0, weight=1)
        self.populate_installed_tab()
        
        # RIGHT AREA: Sidebar Panel
        self.sidebar = customtkinter.CTkFrame(self, width=250, corner_radius=12, fg_color=("#f1f5f9", "#0f172a"))
        self.sidebar.grid(row=0, column=1, padx=(5, 15), pady=15, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(4, weight=1) # Log textbox expands
        
        # Sidebar Title
        self.sidebar_title = customtkinter.CTkLabel(
            self.sidebar, text="CONTROL PANEL",
            font=customtkinter.CTkFont(size=16, weight="bold")
        )
        self.sidebar_title.grid(row=0, column=0, padx=15, pady=(20, 10))
        
        # Install Selected Button
        self.install_btn = customtkinter.CTkButton(
            self.sidebar, text="Install Selected (V)", height=45,
            font=customtkinter.CTkFont(size=14, weight="bold"),
            fg_color=("#10b981", "#059669"), hover_color=("#059669", "#047857"),
            command=self.start_bulk_installation
        )
        self.install_btn.grid(row=1, column=0, padx=15, pady=10, sticky="ew")

        # Uninstall Selected Button
        self.uninstall_btn = customtkinter.CTkButton(
            self.sidebar, text="Uninstall Selected", height=45,
            font=customtkinter.CTkFont(size=14, weight="bold"),
            fg_color=("#ef4444", "#dc2626"), hover_color=("#dc2626", "#b91c1c"),
            command=self.start_bulk_uninstallation
        )
        self.uninstall_btn.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        
        # Real-time Terminal Log Title
        self.log_title = customtkinter.CTkLabel(
            self.sidebar, text="ACTIVITY MONITOR",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            text_color=("#64748b", "#94a3b8")
        )
        self.log_title.grid(row=3, column=0, padx=15, pady=(15, 5), sticky="w")
        
        # Real-time Terminal Textbox
        self.log_textbox = customtkinter.CTkTextbox(
            self.sidebar, height=330,
            font=customtkinter.CTkFont(family="Consolas", size=11),
            fg_color=("#f8fafc", "#020617"), text_color=("#0f172a", "#10b981"),
            border_width=1, border_color=("#cbd5e1", "#1e293b")
        )
        self.log_textbox.grid(row=4, column=0, padx=15, pady=(0, 20), sticky="nsew")
        self.log_textbox.configure(state="disabled")

    def show_app_popup(self, app_data):
        AppDetailPopup(self, app_data, self.get_install_status(app_data))

    def on_refresh_scan_clicked(self):
        self.refresh_status_btn.configure(state="disabled", text="Scanning...")
        self.start_installation_scan(show_log=True)

    def open_add_program_dialog(self):
        if hasattr(self, "add_dialog") and self.add_dialog.winfo_exists():
            self.add_dialog.attributes("-topmost", True)
        else:
            self.add_dialog = AddProgramDialog(self)

    def open_edit_program_dialog(self, app_data):
        if hasattr(self, "add_dialog") and self.add_dialog.winfo_exists():
            self.add_dialog.attributes("-topmost", True)
        else:
            self.add_dialog = AddProgramDialog(self, app_data)

    def confirm_and_remove_app(self, app_data):
        from tkinter import messagebox
        name = app_data.get("Name")
        if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove '{name}' from the registry?"):
            self.remove_app(app_data)

    def remove_app(self, app_data):
        name = app_data.get("Name")
        app_type = app_data.get("Type")
        removed = False
        
        if app_type == "Portable-Run":
            if "Maintenance_Tools" in self.config_data:
                self.config_data["Maintenance_Tools"] = [t for t in self.config_data["Maintenance_Tools"] if t.get("Name") != name]
                removed = True
        else:
            if "Installers_After_Format" in self.config_data:
                self.config_data["Installers_After_Format"] = [i for i in self.config_data["Installers_After_Format"] if i.get("Name") != name]
                removed = True
                
        if removed:
            self.save_config()
            logger.info(f"Removed application from registry: {name}")
            self.refresh_ui()

    def get_logo_button(self, parent, app_data):
        logo_path = app_data.get("Logo")
        name = app_data.get("Name", "App")
        
        image = None
        if logo_path and os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                image = customtkinter.CTkImage(light_image=img, dark_image=img, size=(40, 40))
            except Exception as e:
                print(f"Error loading logo {logo_path}: {e}")
                
        if image:
            btn = customtkinter.CTkButton(
                parent, text="", image=image, width=40, height=40,
                corner_radius=8, fg_color="transparent", hover_color=("#e2e8f0", "#334155"),
                command=lambda: self.show_app_popup(app_data)
            )
        else:
            # Generate initials
            words = name.split()
            initials = words[0][0] + words[1][0] if len(words) >= 2 else name[:2]
            initials = initials.upper()
            
            # Select color based on app name hash
            import hashlib
            name_hash = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
            palette = ["#1e3a8a", "#0f766e", "#1d4ed8", "#374151", "#4b5563", "#047857", "#6d28d9", "#a16207"]
            color = palette[name_hash % len(palette)]
            
            btn = customtkinter.CTkButton(
                parent, text=initials, width=40, height=40,
                corner_radius=20, fg_color=color, text_color="white",
                font=customtkinter.CTkFont(size=14, weight="bold"),
                command=lambda: self.show_app_popup(app_data)
            )
        return btn

    def add_status_badge_to_detail_frame(self, scroll_frame, detail_frame, app):
        name = app.get("Name")
        status = self.get_install_status(app)
        badge = self.create_status_badge(detail_frame, status)
        badge.grid(row=2, column=0, sticky="w", pady=(2, 0))
        setattr(scroll_frame, f"status_badge_{name}", badge)

    def open_homepage(self, app):
        homepage = normalize_homepage_url(app.get("Homepage", ""))
        if not homepage:
            return
        try:
            webbrowser.open(homepage)
            logger.info(f"Opened homepage for {app.get('Name')}: {homepage}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to open homepage for {app.get('Name')}: {e}")

    def add_homepage_link_to_detail_frame(self, detail_frame, app):
        homepage = app.get("Homepage", "").strip()
        if not homepage:
            return

        homepage_btn = customtkinter.CTkButton(
            detail_frame, text=f"🌐 {get_homepage_display(homepage)}",
            height=22, anchor="w",
            font=customtkinter.CTkFont(size=10),
            fg_color="transparent", text_color=("#2563eb", "#60a5fa"),
            hover_color=("#e2e8f0", "#334155"),
            command=lambda a=app: self.open_homepage(a)
        )
        homepage_btn.grid(row=3, column=0, sticky="w", pady=(2, 0))

    def add_homepage_action_button(self, actions_frame, app, column):
        homepage = app.get("Homepage", "").strip()
        if not homepage:
            return column

        homepage_btn = customtkinter.CTkButton(
            actions_frame, text="🌐 Web", width=58, height=28,
            font=customtkinter.CTkFont(size=11, weight="bold"),
            fg_color=("#0ea5e9", "#0284c7"), hover_color=("#0284c7", "#0369a1"),
            command=lambda a=app: self.open_homepage(a)
        )
        homepage_btn.grid(row=0, column=column, padx=2)
        return column + 1

    def populate_maintenance_tab(self):
        for widget in self.maint_scroll.winfo_children():
            widget.destroy()
            
        tools = self.config_data.get("Maintenance_Tools", [])
        for i, tool in enumerate(tools):
            # Row frame
            row_frame = customtkinter.CTkFrame(self.maint_scroll, height=70, corner_radius=8)
            row_frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            row_frame.grid_columnconfigure(1, weight=1)
            row_frame.grid_rowconfigure(0, weight=1)
            
            # Logo Button
            logo_btn = self.get_logo_button(row_frame, tool)
            logo_btn.grid(row=0, column=0, padx=12, pady=10, sticky="w")
            
            # App details
            detail_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            detail_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")
            detail_frame.grid_columnconfigure(0, weight=1)
            
            name_lbl = customtkinter.CTkLabel(
                detail_frame, text=tool.get("Name", "Tool"),
                font=customtkinter.CTkFont(size=14, weight="bold"),
                anchor="w"
            )
            name_lbl.grid(row=0, column=0, sticky="w")
            
            desc_lbl = customtkinter.CTkLabel(
                detail_frame, text=tool.get("Description", ""),
                font=customtkinter.CTkFont(size=11),
                text_color=("#475569", "#94a3b8"),
                anchor="w"
            )
            desc_lbl.grid(row=1, column=0, sticky="w")

            self.add_status_badge_to_detail_frame(self.maint_scroll, detail_frame, tool)
            self.add_homepage_link_to_detail_frame(detail_frame, tool)
            
            # Action buttons panel
            actions_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            actions_frame.grid(row=0, column=2, padx=10, pady=10, sticky="e")
            
            action_col = self.add_homepage_action_button(actions_frame, tool, 0)
            
            # 1. Winget Install
            winget_id = tool.get("WingetID", "")
            winget_btn = customtkinter.CTkButton(
                actions_frame, text="Winget", width=65, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#3b82f6", "#2563eb") if winget_id else ("#cbd5e1", "#334155"),
                text_color="white" if winget_id else ("#94a3b8", "#64748b"),
                state="normal" if winget_id else "disabled",
                command=lambda t=tool: self.install_via_winget_clicked(t)
            )
            winget_btn.grid(row=0, column=action_col, padx=2)
            
            # 2. Local Install
            local_inst = tool.get("LocalInstaller", "")
            local_btn = customtkinter.CTkButton(
                actions_frame, text="Local", width=60, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#10b981", "#059669") if local_inst else ("#cbd5e1", "#334155"),
                text_color="white" if local_inst else ("#94a3b8", "#64748b"),
                state="normal" if local_inst else "disabled",
                command=lambda t=tool: self.install_via_local_clicked(t)
            )
            local_btn.grid(row=0, column=action_col + 1, padx=2)
            
            # 3. Portable open / copy
            source_folder = tool.get("SourceFolder", "")
            local_path = tool.get("LocalPath", "")
            is_portable = bool(source_folder or local_path)
            
            portable_btn = customtkinter.CTkButton(
                actions_frame, text="Portable", width=65, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#8b5cf6", "#7c3aed") if is_portable else ("#cbd5e1", "#334155"),
                text_color="white" if is_portable else ("#94a3b8", "#64748b"),
                state="normal" if is_portable else "disabled",
                command=lambda t=tool: self.install_via_portable_clicked(t)
            )
            portable_btn.grid(row=0, column=action_col + 2, padx=2)
            
            # Inline Edit Button
            edit_btn = customtkinter.CTkButton(
                row_frame, text="⚙️", width=30, height=30,
                fg_color="transparent", text_color=("#1f538d", "#60a5fa"),
                hover_color=("#e2e8f0", "#334155"), corner_radius=6,
                command=lambda t=tool: self.open_edit_program_dialog(t)
            )
            edit_btn.grid(row=0, column=3, padx=(0, 5), pady=10, sticky="e")
            
            # Inline Delete Button
            del_btn = customtkinter.CTkButton(
                row_frame, text="🗑️", width=30, height=30,
                fg_color="transparent", text_color=("#ef4444", "#f87171"),
                hover_color=("#fee2e2", "#7f1d1d"), corner_radius=6,
                command=lambda t=tool: self.confirm_and_remove_app(t)
            )
            del_btn.grid(row=0, column=4, padx=(0, 12), pady=10, sticky="e")

    def populate_installers_tab(self):
        for widget in self.inst_scroll.winfo_children():
            widget.destroy()
            
        self.checkbox_vars = {}
        installers = self.config_data.get("Installers_After_Format", [])
        for i, inst in enumerate(installers):
            # Row frame
            row_frame = customtkinter.CTkFrame(self.inst_scroll, height=70, corner_radius=8)
            row_frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            row_frame.grid_columnconfigure(1, weight=1)
            row_frame.grid_rowconfigure(0, weight=1)
            
            # Logo Button
            logo_btn = self.get_logo_button(row_frame, inst)
            logo_btn.grid(row=0, column=0, padx=12, pady=10, sticky="w")
            
            # App details
            detail_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            detail_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")
            detail_frame.grid_columnconfigure(0, weight=1)
            
            name_lbl = customtkinter.CTkLabel(
                detail_frame, text=inst.get("Name", "Installer"),
                font=customtkinter.CTkFont(size=14, weight="bold"),
                anchor="w"
            )
            name_lbl.grid(row=0, column=0, sticky="w")
            
            desc_lbl = customtkinter.CTkLabel(
                detail_frame, text=inst.get("Description", ""),
                font=customtkinter.CTkFont(size=11),
                text_color=("#475569", "#94a3b8"),
                anchor="w"
            )
            desc_lbl.grid(row=1, column=0, sticky="w")

            self.add_status_badge_to_detail_frame(self.inst_scroll, detail_frame, inst)
            self.add_homepage_link_to_detail_frame(detail_frame, inst)
            
            # Action buttons panel
            actions_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            actions_frame.grid(row=0, column=2, padx=10, pady=10, sticky="e")
            
            action_col = self.add_homepage_action_button(actions_frame, inst, 0)
            
            # 1. Winget Install
            winget_id = inst.get("WingetID", "")
            winget_btn = customtkinter.CTkButton(
                actions_frame, text="Winget", width=65, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#3b82f6", "#2563eb") if winget_id else ("#cbd5e1", "#334155"),
                text_color="white" if winget_id else ("#94a3b8", "#64748b"),
                state="normal" if winget_id else "disabled",
                command=lambda a=inst: self.install_via_winget_clicked(a)
            )
            winget_btn.grid(row=0, column=action_col, padx=2)
            
            # 2. Local Install
            local_inst = inst.get("LocalInstaller", "")
            local_btn = customtkinter.CTkButton(
                actions_frame, text="Local", width=60, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#10b981", "#059669") if local_inst else ("#cbd5e1", "#334155"),
                text_color="white" if local_inst else ("#94a3b8", "#64748b"),
                state="normal" if local_inst else "disabled",
                command=lambda a=inst: self.install_via_local_clicked(a)
            )
            local_btn.grid(row=0, column=action_col + 1, padx=2)
            
            # 3. Portable open / copy
            source_folder = inst.get("SourceFolder", "")
            local_path = inst.get("LocalPath", "")
            is_portable = bool(source_folder or local_path)
            
            portable_btn = customtkinter.CTkButton(
                actions_frame, text="Portable", width=65, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#8b5cf6", "#7c3aed") if is_portable else ("#cbd5e1", "#334155"),
                text_color="white" if is_portable else ("#94a3b8", "#64748b"),
                state="normal" if is_portable else "disabled",
                command=lambda a=inst: self.install_via_portable_clicked(a)
            )
            portable_btn.grid(row=0, column=action_col + 2, padx=2)
            
            # 4. Settings Installer
            settings_inst = inst.get("SettingsInstaller", "")
            settings_btn = customtkinter.CTkButton(
                actions_frame, text="⚙️ Settings", width=75, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#f59e0b", "#d97706") if settings_inst else ("#cbd5e1", "#334155"),
                text_color="white" if settings_inst else ("#94a3b8", "#64748b"),
                state="normal" if settings_inst else "disabled",
                command=lambda a=inst: self.install_settings_clicked(a)
            )
            settings_btn.grid(row=0, column=action_col + 3, padx=2)
            
            # Checkbox for bulk select
            var = customtkinter.BooleanVar(value=False)
            self.checkbox_vars[inst.get("Name")] = var
            chk = customtkinter.CTkCheckBox(row_frame, text="", variable=var, width=24)
            chk.grid(row=0, column=3, padx=12, pady=10, sticky="e")
            
            # Inline Edit Button
            edit_btn = customtkinter.CTkButton(
                row_frame, text="⚙️", width=30, height=30,
                fg_color="transparent", text_color=("#1f538d", "#60a5fa"),
                hover_color=("#e2e8f0", "#334155"), corner_radius=6,
                command=lambda k=inst: self.open_edit_program_dialog(k)
            )
            edit_btn.grid(row=0, column=4, padx=(0, 5), pady=10, sticky="e")
            
            # Inline Delete Button
            del_btn = customtkinter.CTkButton(
                row_frame, text="🗑️", width=30, height=30,
                fg_color="transparent", text_color=("#ef4444", "#f87171"),
                hover_color=("#fee2e2", "#7f1d1d"), corner_radius=6,
                command=lambda k=inst: self.confirm_and_remove_app(k)
            )
            del_btn.grid(row=0, column=5, padx=(0, 12), pady=10, sticky="e")

    def populate_installed_tab(self):
        if not hasattr(self, "installed_scroll"):
            return

        for widget in self.installed_scroll.winfo_children():
            widget.destroy()

        installed_apps = []
        for app in self.get_all_registry_apps():
            status = self.get_install_status(app)
            if status.get("installed"):
                installed_apps.append((app, status))

        if hasattr(self, "installed_summary_lbl"):
            if self.status_scan_in_progress:
                summary = "Scanning installed applications..."
            elif installed_apps:
                summary = f"{len(installed_apps)} installed application(s) found in your registry."
            else:
                summary = "No installed applications found yet. Try Refresh Scan."
            self.installed_summary_lbl.configure(text=summary)

        if not installed_apps:
            empty_lbl = customtkinter.CTkLabel(
                self.installed_scroll,
                text="No installed apps to display.\nUse Refresh Scan or check the other tabs for status badges.",
                font=customtkinter.CTkFont(size=13),
                text_color=("#64748b", "#94a3b8")
            )
            empty_lbl.grid(row=0, column=0, padx=20, pady=40)
            return

        for i, (app, status) in enumerate(installed_apps):
            row_frame = customtkinter.CTkFrame(self.installed_scroll, height=80, corner_radius=8)
            row_frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            row_frame.grid_columnconfigure(1, weight=1)

            logo_btn = self.get_logo_button(row_frame, app)
            logo_btn.grid(row=0, column=0, padx=12, pady=10, sticky="nw")

            detail_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            detail_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")
            detail_frame.grid_columnconfigure(0, weight=1)

            name_lbl = customtkinter.CTkLabel(
                detail_frame, text=app.get("Name", "Application"),
                font=customtkinter.CTkFont(size=14, weight="bold"),
                anchor="w"
            )
            name_lbl.grid(row=0, column=0, sticky="w")

            method = status.get("method")
            method_label = METHOD_LABELS.get(method, method) if method else "Unknown"
            method_lbl = customtkinter.CTkLabel(
                detail_frame, text=f"Installed via: {method_label}",
                font=customtkinter.CTkFont(size=12, weight="bold"),
                text_color=("#059669", "#34d399"),
                anchor="w"
            )
            method_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

            details = status.get("details", "")
            detail_row = 2
            if details:
                details_lbl = customtkinter.CTkLabel(
                    detail_frame, text=details,
                    font=customtkinter.CTkFont(size=11),
                    text_color=("#475569", "#94a3b8"),
                    anchor="w"
                )
                details_lbl.grid(row=detail_row, column=0, sticky="w")
                detail_row += 1

            homepage = app.get("Homepage", "").strip()
            if homepage:
                homepage_btn = customtkinter.CTkButton(
                    detail_frame, text=f"🌐 {get_homepage_display(homepage)}",
                    height=22, anchor="w",
                    font=customtkinter.CTkFont(size=10),
                    fg_color="transparent", text_color=("#2563eb", "#60a5fa"),
                    hover_color=("#e2e8f0", "#334155"),
                    command=lambda a=app: self.open_homepage(a)
                )
                homepage_btn.grid(row=detail_row, column=0, sticky="w", pady=(2, 0))

            actions_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            actions_frame.grid(row=0, column=2, padx=12, pady=10, sticky="e")
            type_col = self.add_homepage_action_button(actions_frame, app, 0)

            type_lbl = customtkinter.CTkLabel(
                actions_frame, text=app.get("Type", ""),
                font=customtkinter.CTkFont(size=11),
                text_color=("#64748b", "#94a3b8")
            )
            type_lbl.grid(row=0, column=type_col, padx=(8, 0), sticky="e")

    # Manual installation/execution handlers
    def install_via_winget_clicked(self, app):
        threading.Thread(target=self.run_single_winget, args=(app,), daemon=True).start()

    def run_single_winget(self, app):
        name = app.get("Name")
        winget_id = app.get("WingetID")
        logger.info(f"Manual Installation Triggered: {name} via Winget.")
        try:
            res = subprocess.run(
                f'winget install --id "{winget_id}" --silent --accept-package-agreements --accept-source-agreements',
                shell=True
            )
            if res.returncode == 0:
                logger.info(f"[SUCCESS] Installed {name} via Winget.")
            else:
                logger.error(f"[ERROR] Failed to install {name} via Winget. Exit code: {res.returncode}")
        except Exception as e:
            logger.error(f"[ERROR] Failed executing Winget install for {name}: {e}")

    def install_via_local_clicked(self, app):
        threading.Thread(target=self.run_single_local, args=(app,), daemon=True).start()

    def run_single_local(self, app):
        name = app.get("Name")
        local_path = app.get("LocalInstaller")
        silent_args = app.get("SilentArgs", "")
        logger.info(f"Manual Installation Triggered: {name} via local installer.")
        
        if not local_path or not os.path.exists(local_path):
            logger.error(f"[ERROR] Local installer file not found for {name} at '{local_path}'")
            return
            
        try:
            full_path = os.path.abspath(local_path)
            res = subprocess.run(f'"{full_path}" {silent_args}', shell=True)
            if res.returncode == 0:
                logger.info(f"[SUCCESS] Installed {name} via local installer.")
            else:
                logger.error(f"[ERROR] Local installer for {name} exited with code {res.returncode}")
        except Exception as e:
            logger.error(f"[ERROR] Failed running local installer for {name}: {e}")

    def install_settings_clicked(self, app):
        threading.Thread(target=self.run_settings_installer, args=(app,), daemon=True).start()

    def run_settings_installer(self, app):
        name = app.get("Name")
        settings_path = app.get("SettingsInstaller")
        logger.info(f"Settings Installation Triggered: {name} settings.")
        
        if not settings_path or not os.path.exists(settings_path):
            logger.error(f"[ERROR] Settings file not found for {name} at '{settings_path}'")
            return
            
        try:
            full_path = os.path.abspath(settings_path)
            cwd_dir = os.path.dirname(full_path)
            short_path = get_short_path(full_path)
            _, ext = os.path.splitext(full_path.lower())
            
            if ext == '.reg':
                res = subprocess.run(f'regedit.exe /s "{short_path}"', cwd=cwd_dir)
            elif ext == '.ps1':
                res = subprocess.run(f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{short_path}"', cwd=cwd_dir)
            elif ext in ('.bat', '.cmd'):
                res = subprocess.run(f'cmd.exe /c {short_path}', cwd=cwd_dir)
            else:
                res = subprocess.run(f'"{short_path}"', cwd=cwd_dir)
                
            if res.returncode == 0:
                logger.info(f"[SUCCESS] Installed settings for {name}.")
            else:
                logger.error(f"[ERROR] Settings installer for {name} exited with code {res.returncode}")
        except Exception as e:
            logger.error(f"[ERROR] Failed running settings installer for {name}: {e}")

    def install_via_portable_clicked(self, app):
        if app.get("SourceFolder"):
            threading.Thread(target=lambda: self.execute_portable_copy(app), daemon=True).start()
        elif app.get("LocalPath"):
            self.run_maintenance_tool(app)

    # Portable-Run Execution Logic (used for Maintenance & manual trigger)
    def run_maintenance_tool(self, tool):
        def _run():
            name = tool.get("Name", "Tool")
            local_path = tool.get("LocalPath", "")
            full_path = os.path.abspath(local_path)
            
            logger.info(f"Launching maintenance tool: {name} ({local_path})")
            
            if not os.path.exists(full_path):
                logger.error(f"[ERROR] Launching {name} failed: File not found at '{local_path}'")
                return
                
            try:
                # Attempt to launch requesting administrator rights (UAC elevation)
                os.startfile(full_path, "runas")
                logger.info(f"[SUCCESS] Launched {name} with administrator permissions.")
            except OSError as e:
                # Windows error code 1223 represents UAC cancel/decline
                if getattr(e, 'winerror', 0) == 1223:
                    logger.error(f"[ERROR] Launching {name} failed: User declined UAC administrator elevation.")
                else:
                    # Fallback to normal execution if UAC elevation fails
                    try:
                        os.startfile(full_path)
                        logger.info(f"[SUCCESS] Launched {name} normally (No elevation).")
                    except Exception as ex:
                        logger.error(f"[ERROR] Failed to launch {name}: {str(ex)}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to launch {name}: {str(e)}")

        threading.Thread(target=_run, daemon=True).start()

    # Bulk installation initiation
    def get_selected_installer_apps(self):
        selected_apps = []
        installers = self.config_data.get("Installers_After_Format", [])
        for inst in installers:
            name = inst.get("Name")
            if self.checkbox_vars.get(name) and self.checkbox_vars.get(name).get():
                selected_apps.append(inst)
        return selected_apps

    def set_bulk_action_buttons_state(self, installing=False, uninstalling=False):
        if installing:
            self.install_btn.configure(state="disabled", text="Installing...")
            self.uninstall_btn.configure(state="disabled")
        elif uninstalling:
            self.uninstall_btn.configure(state="disabled", text="Uninstalling...")
            self.install_btn.configure(state="disabled")
        else:
            self.install_btn.configure(state="normal", text="Install Selected (V)")
            self.uninstall_btn.configure(state="normal", text="Uninstall Selected")

    def start_bulk_installation(self):
        selected_apps = self.get_selected_installer_apps()
        if not selected_apps:
            logger.info("No applications selected for installation.")
            return
            
        # Run bulk process in background thread
        threading.Thread(target=self.process_installations, args=(selected_apps,), daemon=True).start()

    def start_bulk_uninstallation(self):
        from tkinter import messagebox

        selected_apps = self.get_selected_installer_apps()
        if not selected_apps:
            logger.info("No applications selected for uninstallation.")
            return

        app_list = "\n".join(f" - {app.get('Name')}" for app in selected_apps)
        if not messagebox.askyesno(
            "Confirm Uninstall",
            f"Uninstall {len(selected_apps)} selected application(s) from this PC?\n\n{app_list}"
        ):
            logger.info("Bulk uninstallation cancelled by user.")
            return

        threading.Thread(target=self.process_uninstallations, args=(selected_apps,), daemon=True).start()

    def process_installations(self, apps):
        self.install_btn.after(0, lambda: self.set_bulk_action_buttons_state(installing=True))
        
        logger.info(f"Initiating bulk installation cycle for {len(apps)} apps:")
        for app in apps:
            logger.info(f" - {app.get('Name')}")
            
        for app in apps:
            name = app.get("Name")
            app_type = app.get("Type")
            
            if app_type == "Installer":
                self.execute_installer(app)
            elif app_type == "Portable-Copy":
                self.execute_portable_copy(app)
            else:
                logger.error(f"[ERROR] Unknown application type '{app_type}' for {name}")
                
        logger.info("Bulk installation cycle completed.")
        self.after(0, lambda: self.set_bulk_action_buttons_state())
        self.after(0, lambda: self.start_installation_scan(show_log=False))

    def process_uninstallations(self, apps):
        self.uninstall_btn.after(0, lambda: self.set_bulk_action_buttons_state(uninstalling=True))

        logger.info(f"Initiating bulk uninstallation cycle for {len(apps)} apps:")
        for app in apps:
            logger.info(f" - {app.get('Name')}")

        for app in apps:
            name = app.get("Name")
            app_type = app.get("Type")

            if app_type == "Installer":
                self.execute_uninstaller(app)
            elif app_type == "Portable-Copy":
                self.remove_portable_copy(app)
            else:
                logger.error(f"[ERROR] Cannot uninstall '{name}': unsupported type '{app_type}'")

        logger.info("Bulk uninstallation cycle completed.")
        self.after(0, lambda: self.set_bulk_action_buttons_state())
        self.after(0, lambda: self.start_installation_scan(show_log=False))

    # Installer Execution Logic (used for bulk installation)
    def execute_installer(self, app):
        name = app.get("Name")
        winget_id = app.get("WingetID")
        local_path = app.get("LocalInstaller")
        silent_args = app.get("SilentArgs", "")
        
        logger.info(f"Checking if {name} is already installed...")
        
        # Check if already installed using winget list
        is_installed = False
        if winget_id:
            try:
                res = subprocess.run(
                    f'winget list --id "{winget_id}"',
                    shell=True, capture_output=True, text=True
                )
                if res.returncode == 0:
                    is_installed = True
            except Exception as e:
                logger.info(f"Could not query winget for {name}: {e}")
                
        if is_installed:
            logger.info(f"[SUCCESS] {name} is already installed on this machine.")
            return
            
        # Try local installer first
        if local_path and os.path.exists(local_path):
            full_local_path = os.path.abspath(local_path)
            logger.info(f"Running local installer for {name}: {local_path} with args '{silent_args}'")
            try:
                # Execute local installer and wait for exit code
                res = subprocess.run(f'"{full_local_path}" {silent_args}', shell=True)
                if res.returncode == 0:
                    logger.info(f"[SUCCESS] Installed {name} via local installer.")
                    return
                else:
                    logger.error(f"[ERROR] Local installer for {name} exited with code {res.returncode}. Trying winget fallback...")
            except Exception as e:
                logger.error(f"[ERROR] Failed running local installer for {name}: {e}. Trying winget fallback...")
                
        # Winget fallback
        if winget_id:
            logger.info(f"Installing {name} via winget (ID: {winget_id})...")
            try:
                # Winget installation in silent mode
                res = subprocess.run(
                    f'winget install --id "{winget_id}" --silent --accept-package-agreements --accept-source-agreements',
                    shell=True
                )
                if res.returncode == 0:
                    logger.info(f"[SUCCESS] Installed {name} via winget.")
                else:
                    logger.error(f"[ERROR] Failed to install {name}. Local installer failed/missing and winget failed (Exit code: {res.returncode}).")
            except Exception as e:
                logger.error(f"[ERROR] Failed to install {name}. Local installer failed/missing and winget execution failed: {e}")
        else:
            logger.error(f"[ERROR] Failed to install {name}. Local installer missing and no WingetID provided.")

    def execute_uninstaller(self, app):
        name = app.get("Name")
        winget_id = app.get("WingetID", "")
        target_destination = app.get("TargetDestination", "")

        logger.info(f"Attempting to uninstall {name}...")
        removed = False

        if winget_id and self.is_winget_installed(winget_id):
            try:
                res = subprocess.run(
                    f'winget uninstall --id "{winget_id}" --silent --disable-interactivity',
                    shell=True
                )
                if res.returncode == 0:
                    logger.info(f"[SUCCESS] Uninstalled {name} via Winget.")
                    removed = True
                else:
                    logger.error(f"[ERROR] Failed to uninstall {name} via Winget. Exit code: {res.returncode}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to uninstall {name} via Winget: {e}")

        if self.is_portable_copy_installed(target_destination):
            if self.remove_portable_copy(app):
                removed = True

        if not removed:
            logger.info(f"[INFO] {name} is not installed or could not be removed.")

    def remove_portable_copy(self, app):
        name = app.get("Name")
        target_destination = app.get("TargetDestination", "")

        if not target_destination or not os.path.exists(target_destination):
            return False

        try:
            shutil.rmtree(target_destination)
            logger.info(f"[SUCCESS] Removed {name} portable copy from '{target_destination}'.")

            shortcut_path = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.lnk")
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                logger.info(f"[SUCCESS] Removed desktop shortcut for {name}.")

            return True
        except Exception as e:
            logger.error(f"[ERROR] Failed to remove portable copy for {name}: {e}")
            return False

    # Portable-Copy Execution Logic (used for bulk and manual portable)
    def execute_portable_copy(self, app):
        name = app.get("Name")
        src_folder = app.get("SourceFolder")
        target_destination = app.get("TargetDestination")
        
        if not src_folder or not os.path.exists(src_folder):
            logger.error(f"[ERROR] Failed to copy {name}. Source folder '{src_folder}' not found.")
            return
            
        try:
            src_abs = os.path.abspath(src_folder)
            dst_abs = os.path.abspath(target_destination)
            
            logger.info(f"Copying {name} from '{src_folder}' to '{target_destination}'...")
            
            # Ensure target directory parent folder exists
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            
            # Copy folder contents recursively
            shutil.copytree(src_abs, dst_abs, dirs_exist_ok=True)
            logger.info(f"[SUCCESS] Copied {name} Portable to {target_destination}.")
            
            # Locate main executable inside target folder for desktop shortcut creation
            exes = glob.glob(os.path.join(dst_abs, "**", "*.exe"), recursive=True)
            if exes:
                main_exe = exes[0]
                for exe in exes:
                    exe_name = os.path.basename(exe).lower()
                    if name.lower() in exe_name or "portable" in exe_name:
                        main_exe = exe
                        break
                        
                logger.info(f"Creating Desktop shortcut for {name} pointing to '{main_exe}'...")
                
                # PowerShell Native Shortcut Creator
                shortcut_path = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.lnk")
                ps_cmd = f"""
                $WshShell = New-Object -ComObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
                $Shortcut.TargetPath = "{main_exe}"
                $Shortcut.WorkingDirectory = "{dst_abs}"
                $Shortcut.Save()
                """
                
                shortcut_res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
                if shortcut_res.returncode == 0:
                    logger.info(f"[SUCCESS] Created Windows Desktop Shortcut for {name}.")
                else:
                    logger.error(f"[ERROR] Failed to create shortcut: {shortcut_res.stderr.strip()}")
            else:
                logger.warning(f"[WARNING] Copied successfully, but no executable (.exe) found in {target_destination} to create shortcut.")
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to copy {name} to {target_destination}: {str(e)}")

if __name__ == "__main__":
    app = PortableManagerApp()
    app.mainloop()
