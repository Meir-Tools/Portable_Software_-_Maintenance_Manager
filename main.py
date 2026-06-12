import os
import sys
import json
import shutil
import glob
import logging
import datetime
import threading
import subprocess
import customtkinter
from PIL import Image

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
    def __init__(self, parent, app_data):
        super().__init__(parent)
        self.title("Application Details")
        self.geometry("420x280")
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
        
        # Description
        desc_lbl = customtkinter.CTkLabel(
            frame, text="Description:",
            font=customtkinter.CTkFont(size=12, weight="bold")
        )
        desc_lbl.grid(row=2, column=0, padx=15, pady=(10, 0), sticky="w")
        
        desc_box = customtkinter.CTkTextbox(
            frame, width=360, height=90, wrap="word",
            fg_color="transparent", border_width=0,
            font=customtkinter.CTkFont(size=12)
        )
        desc_box.insert("0.0", app_data.get("Description", "No description provided."))
        desc_box.configure(state="disabled")
        desc_box.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="nsew")
        
        # Close Button
        close_btn = customtkinter.CTkButton(
            frame, text="Close", width=90, command=self.destroy,
            fg_color=("#1f538d", "#1f538d"), hover_color=("#2b6cb0", "#2b6cb0")
        )
        close_btn.grid(row=4, column=0, padx=15, pady=(0, 15), sticky="e")


class AddProgramDialog(customtkinter.CTkToplevel):
    def __init__(self, parent, edit_app_data=None):
        super().__init__(parent)
        self.parent = parent
        self.edit_app_data = edit_app_data # If provided, we are editing this app
        
        self.title("Edit Program" if self.edit_app_data else "Add New Program")
        self.geometry("520x560")
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
        
        # Buttons (Row 6)
        buttons_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        buttons_frame.grid(row=6, column=0, columnspan=3, padx=15, pady=(20, 15), sticky="ew")
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
            
            # Select Type
            app_type = self.edit_app_data.get("Type", "Installer")
            self.type_var.set(app_type)
            self.on_type_changed(app_type)
            
            # Fill type specific fields
            if app_type == "Installer":
                self.winget_entry.insert(0, self.edit_app_data.get("WingetID", ""))
                self.loc_inst_entry.insert(0, self.edit_app_data.get("LocalInstaller", ""))
                self.args_entry.insert(0, self.edit_app_data.get("SilentArgs", ""))
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
        
        if not name:
            messagebox.showwarning("Validation Error", "Application Name is required.")
            return
            
        app_data = {
            "Name": name,
            "Type": app_type,
            "Logo": logo if logo else "Assets/default_logo.png",
            "Description": desc if desc else "No description provided."
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
        
        self.load_config()
        self.create_layout()
        
        # Connect logger to GUI terminal view
        gui_handler = GUIHandler(self.log_textbox)
        gui_handler.setFormatter(CustomFormatter())
        logger.addHandler(gui_handler)
        
        # Set active tab to Software Installation on startup
        self.tabview.set("🚀 Software Installation")
        logger.info("Application started successfully.")

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
        self.tabview.add(tab_maintenance)
        self.tabview.add(tab_installers)
        
        # Configure Tab content layout
        self.tabview.tab(tab_maintenance).grid_columnconfigure(0, weight=1)
        self.tabview.tab(tab_maintenance).grid_rowconfigure(0, weight=1)
        
        self.tabview.tab(tab_installers).grid_columnconfigure(0, weight=1)
        self.tabview.tab(tab_installers).grid_rowconfigure(0, weight=0) # row 0: static header
        self.tabview.tab(tab_installers).grid_rowconfigure(1, weight=1) # row 1: scroll frame
        
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
        
        # RIGHT AREA: Sidebar Panel
        self.sidebar = customtkinter.CTkFrame(self, width=250, corner_radius=12, fg_color=("#f1f5f9", "#0f172a"))
        self.sidebar.grid(row=0, column=1, padx=(5, 15), pady=15, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(2, weight=1) # Log textbox expands
        
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
        
        # Real-time Terminal Log Title
        self.log_title = customtkinter.CTkLabel(
            self.sidebar, text="ACTIVITY MONITOR",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            text_color=("#64748b", "#94a3b8")
        )
        self.log_title.grid(row=2, column=0, padx=15, pady=(15, 5), sticky="w")
        
        # Real-time Terminal Textbox
        self.log_textbox = customtkinter.CTkTextbox(
            self.sidebar, height=380,
            font=customtkinter.CTkFont(family="Consolas", size=11),
            fg_color=("#f8fafc", "#020617"), text_color=("#0f172a", "#10b981"),
            border_width=1, border_color=("#cbd5e1", "#1e293b")
        )
        self.log_textbox.grid(row=3, column=0, padx=15, pady=(0, 20), sticky="nsew")
        self.log_textbox.configure(state="disabled")

    def show_app_popup(self, app_data):
        AppDetailPopup(self, app_data)

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
            
            # Action buttons panel
            actions_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            actions_frame.grid(row=0, column=2, padx=10, pady=10, sticky="e")
            
            # 1. Winget Install
            winget_id = tool.get("WingetID", "")
            winget_btn = customtkinter.CTkButton(
                actions_frame, text="Winget", width=65, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#3b82f6", "#2563eb") if winget_id else ("#cbd5e1", "#334155"),
                text_color="white" if winget_id else ("#94a3b8", "#64748b"),
                state="normal" if winget_id else "disabled",
                command=lambda t=tool: self.install_via_winget_clicked(t)
            )
            winget_btn.grid(row=0, column=0, padx=2)
            
            # 2. Local Install
            local_inst = tool.get("LocalInstaller", "")
            local_btn = customtkinter.CTkButton(
                actions_frame, text="Local", width=60, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#10b981", "#059669") if local_inst else ("#cbd5e1", "#334155"),
                text_color="white" if local_inst else ("#94a3b8", "#64748b"),
                state="normal" if local_inst else "disabled",
                command=lambda t=tool: self.install_via_local_clicked(t)
            )
            local_btn.grid(row=0, column=1, padx=2)
            
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
            portable_btn.grid(row=0, column=2, padx=2)
            
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
            
            # Action buttons panel
            actions_frame = customtkinter.CTkFrame(row_frame, fg_color="transparent")
            actions_frame.grid(row=0, column=2, padx=10, pady=10, sticky="e")
            
            # 1. Winget Install
            winget_id = inst.get("WingetID", "")
            winget_btn = customtkinter.CTkButton(
                actions_frame, text="Winget", width=65, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#3b82f6", "#2563eb") if winget_id else ("#cbd5e1", "#334155"),
                text_color="white" if winget_id else ("#94a3b8", "#64748b"),
                state="normal" if winget_id else "disabled",
                command=lambda a=inst: self.install_via_winget_clicked(a)
            )
            winget_btn.grid(row=0, column=0, padx=2)
            
            # 2. Local Install
            local_inst = inst.get("LocalInstaller", "")
            local_btn = customtkinter.CTkButton(
                actions_frame, text="Local", width=60, height=28, font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=("#10b981", "#059669") if local_inst else ("#cbd5e1", "#334155"),
                text_color="white" if local_inst else ("#94a3b8", "#64748b"),
                state="normal" if local_inst else "disabled",
                command=lambda a=inst: self.install_via_local_clicked(a)
            )
            local_btn.grid(row=0, column=1, padx=2)
            
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
            portable_btn.grid(row=0, column=2, padx=2)
            
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
    def start_bulk_installation(self):
        # Gather all selected installers
        selected_apps = []
        installers = self.config_data.get("Installers_After_Format", [])
        for inst in installers:
            name = inst.get("Name")
            if self.checkbox_vars.get(name) and self.checkbox_vars.get(name).get():
                selected_apps.append(inst)
                
        if not selected_apps:
            logger.info("No applications selected for installation.")
            return
            
        # Run bulk process in background thread
        threading.Thread(target=self.process_installations, args=(selected_apps,), daemon=True).start()

    def process_installations(self, apps):
        # UI Button update (Thread-safe)
        self.install_btn.after(0, lambda: self.install_btn.configure(state="disabled", text="Installing..."))
        
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
        
        # Restore UI button (Thread-safe)
        self.install_btn.after(0, lambda: self.install_btn.configure(state="normal", text="Install Selected (V)"))

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
