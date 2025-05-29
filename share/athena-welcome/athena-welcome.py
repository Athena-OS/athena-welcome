#!/usr/bin/env python3
# =================================================================
# =          Authors: Brad Heffernan & Erik Dubois                =
# =================================================================
import gi
import os

# import conflicts
# import sys

# import wnck
import subprocess
import threading
import shutil
import socket
from time import sleep
from queue import Queue

import ui.GUI as GUI

gi.require_version("Gtk", "3.0")
# gi.require_version("Wnck", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib, Gdk  # Wnck

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
REMOTE_SERVER = "www.bing.com"
# css = """
# box#stack_box{
#     padding: 10px 10px 10px 10px;
# }
# button#button_grub_boot_enabled{
#      font-weight: bold;
#      background-color: @theme_base_color_button;
# }
# button#button_systemd_boot_enabled{
#      font-weight: bold;
#      background-color: @theme_base_color_button;
# }
# button#button_easy_install_enabled{
#      font-weight: bold;
#      background-color: @theme_base_color_button;
# }
# button#button_adv_install_enabled{
#      font-weight: bold;
#      background-color: @theme_base_color_button;
# }
# label#label_style {
#     background-color: @theme_base_color;
#     border-top: 1px solid @borders;
#     border-bottom: 1px solid @borders;
#     border-left: 1px solid @borders;
#     border-right: 1px solid @borders;
#     padding: 10px 10px 10px 10px;
#     border-radius: 100px;
#     font-weight: bold;
#     color: #fcfcfc;
#     font-family: 'Open Sans', 'Helvetica', sans-serif;
# }
# """

css = """ """

CHECK_COMMANDS = {
    "pacman": lambda pkg: ["pacman", "-Qi", pkg],
    "dnf": lambda pkg: ["rpm", "-q", pkg],
    "rpm-ostree": lambda pkg: ["rpm", "-q", pkg],  # rpm-ostree still uses RPM DB
    "apt": lambda pkg: ["dpkg", "-s", pkg],
    "zypper": lambda pkg: ["rpm", "-q", pkg],
    "apk": lambda pkg: ["apk", "info", pkg],
    "nixos": lambda pkg: ["nix-env", "-q", pkg],
}

UPDATE_COMMANDS = {
    "pacman": "pkexec pacman -Syyu",
    "dnf": "pkexec dnf upgrade -y",
    "rpm-ostree": "pkexec rpm-ostree upgrade",
    "apt": "pkexec bash -c 'apt update && apt upgrade -y'",
    "zypper": "pkexec bash -c 'zypper refresh && zypper update -y'",
    "apk": "pkexec bash -c 'apk update && apk upgrade'",
    "nixos": "pkexec bash -c 'nix-channel --update && nixos-rebuild switch'",
}


class Main(Gtk.Window):
    def __init__(self):
        super(Main, self).__init__(title="Athena Welcome")
        self.set_border_width(10)
        self.set_default_size(860, 250)
        self.set_icon_from_file(os.path.join(base_dir, "images/athenaos.svg"))
        self.set_position(Gtk.WindowPosition.CENTER)
        self.results = ""

        if not os.path.exists(GUI.Settings):
            if not os.path.exists(GUI.home + "/.config/athena-welcome/"): # If the path does not exist, create it
                os.mkdir(GUI.home + "/.config/athena-welcome/")
            with open(GUI.Settings, "w") as f:
                lines = ["autostart=True\n", "role=none"]
                f.writelines(lines)
                f.close()

        self.style_provider = Gtk.CssProvider()
        self.style_provider.load_from_data(css, len(css))

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # a queue to store package install progress
        self.pkg_queue = Queue()

        # get the username of the user running the welcome app
        self.sudo_username = os.getlogin()

        self.session = None

        self.get_session()

        GUI.GUI(self, Gtk, GdkPixbuf)

        threading.Thread(
            target=self.internet_notifier, args=(), daemon=True
        ).start()


    # returns the login session
    def get_session(self):
        try:
            self.session = os.environ.get("XDG_SESSION_TYPE")
        except Exception as e:
            print("Exception in get_session(): %s" % e)


    def on_settings_clicked(self, widget):
        self.toggle_popover()


    def toggle_popover(self):
        if self.popover.get_visible():
            self.popover.hide()
        else:
            self.popover.show_all()

    # check if path exists
    # used to check if /sys/firmware/efi/fw_platform_size exists
    # if yes then display systemd-boot bootloader install option
    def file_check(self, path):
        if os.path.isfile(path):
            return True

        return False


    def on_role_combo_changed(self, combo):
        #GUI.role_name = combo.get_active_iter()
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = combo.get_model()
            GUI.role_name = model[tree_iter][0]
            print("Selected: role=%s" % GUI.role_name)
            if "Blue Teamer" in GUI.role_name:
                self.role_id = "blue"
            elif "Bug Bounty Hunter" in GUI.role_name:
                self.role_id = "bugbounty"
            elif "Cracker Specialist" in GUI.role_name:
                self.role_id = "cracker"
            elif "DoS Tester" in GUI.role_name:
                self.role_id = "dos"
            elif "Enthusiast Student" in GUI.role_name:
                self.role_id = "student"
            elif "Forensic Analyst" in GUI.role_name:
                self.role_id = "forensic"
            elif "Malware Analyst" in GUI.role_name:
                self.role_id = "malware"
            elif "Mobile Analyst" in GUI.role_name:
                self.role_id = "mobile"
            elif "Network Analyst" in GUI.role_name:
                self.role_id = "network"
            elif "OSINT Specialist" in GUI.role_name:
                self.role_id = "osint"
            elif "Red Teamer" in GUI.role_name:
                self.role_id = "red"
            elif "Web Pentester" in GUI.role_name:
                self.role_id = "web"


    def on_roles_clicked(self, widget):
        if GUI.command_exists("nixos-rebuild"):
            app_cmd = [
                "shell-rocket",
                "-c",
                "pkexec bash -c \"sed -i '/cyber\\s*=\\s*{/,/}/ { /enable\\s*=\\s*/s/enable\\s*=\\s*.*/enable = true;/; /role\\s*=\\s*/s/role\\s*=\\s*.*/role = \\\"" + self.role_id + "\\\";/}' /etc/nixos/configuration.nix && nixos-rebuild switch\"",
            ]
        elif GUI.command_exists("pacman"):
            app_cmd = [
                "shell-rocket",
                "-c",
                "pkexec cyber-toolkit "+self.role_id,
            ]
        elif GUI.command_exists("dnf") or GUI.command_exists("rpm-ostree"):
            app_cmd = [
                "shell-rocket",
                "-c",
                "cyber-shell -c " + self.role_id + " -s"
            ]

        threading.Thread(target=self.run_app, args=(app_cmd,), daemon=True).start()


    def on_mirror_clicked(self, widget):
        threading.Thread(target=self.mirror_update, daemon=True).start()


    def convert_to_hex(self, rgba_color):
        red = int(rgba_color.red * 255)
        green = int(rgba_color.green * 255)
        blue = int(rgba_color.blue * 255)
        return "#{r:02x}{g:02x}{b:02x}".format(r=red, g=green, b=blue)


    # install tui option
    def on_install_tui_clicked(self, widget):
        run_cmd = [
            "shell-rocket",
            "-c",
            "pkexec aegis-tui",
        ]

        threading.Thread(target=self.run_app, args=(run_cmd,), daemon=True).start()


    def on_gp_clicked(self, widget):
        app_cmd = ["gparted"]
        threading.Thread(target=self.run_app, args=(app_cmd,), daemon=True).start()


    def on_button_htb_clicked(self, widget):
        app_cmd = [
            "shell-rocket",
            "-c",
            "htb-toolkit -u",
        ]

        threading.Thread(target=self.run_app, args=(app_cmd,), daemon=True).start()


    def check_package_installed(self, package):
        manager = GUI.detect_package_manager()

        if manager not in CHECK_COMMANDS:
            raise ValueError(f"Unsupported package manager: {manager}")

        cmd = CHECK_COMMANDS[manager](package)

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                universal_newlines=True,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Error checking package: {e}")
            return False


    def on_button_update_clicked(self, widget):
        manager = GUI.detect_package_manager()

        if not manager or manager not in UPDATE_COMMANDS:
            print("Unsupported or unknown package manager.")
            return

        update_cmd = UPDATE_COMMANDS[manager]

        run_cmd = [
            "shell-rocket",
            "-c",
            update_cmd,
        ]
        threading.Thread(target=self.run_app, args=(run_cmd,), daemon=True).start()


    def run_app(self, app_cmd):
        process = subprocess.run(
            app_cmd,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        # for debugging print stdout to console
        if GUI.debug is True:
            print(process.stdout)

    def startup_toggle(self, widget):
        if widget.get_active() is True:
            if os.path.isfile(GUI.dot_desktop):
                shutil.copy(GUI.dot_desktop, GUI.autostart)
        else:
            if os.path.isfile(GUI.autostart):
                os.unlink(GUI.autostart)
        self.save_settings(widget.get_active())

    def save_settings(self, state):
        with open(GUI.Settings, "r") as f:
            contents = f.read()
            f.close()
        if "role=" in contents:
            role_state = contents.split("role=")[1]
        else:
            role_state = "none"
        with open(GUI.Settings, "w") as f:
            lines = ["autostart=" + str(state) + "\n", "role=" + str(role_state)]
            f.writelines(lines)
            f.close()

    def load_settings(self):
        line = "True"
        if os.path.isfile(GUI.Settings):
            with open(GUI.Settings, "r") as f:
                lines = f.readlines()
                for i in range(len(lines)):
                    if "autostart" in lines[i]:
                        line = lines[i].split("=")[1].strip().capitalize()
                f.close()
        return line

    def on_link_clicked(self, widget, link):
        t = threading.Thread(target=self.weblink, args=(link,))
        t.daemon = True
        t.start()

    def on_social_clicked(self, widget, event, link):
        t = threading.Thread(target=self.weblink, args=(link,))
        t.daemon = True
        t.start()

    def _on_info_clicked(self, widget, event):
        window_list = Wnck.Screen.get_default().get_windows()
        state = False
        for win in window_list:
            if "Information" in win.get_name():
                state = True
        if not state:
            w = conflicts.Conflicts()
            w.show_all()

    def weblink(self, link):
        # webbrowser.open_new_tab(link)
        try:
            # use xdg-open to use the default browser to open the weblink
            subprocess.Popen(
                ["xdg-open", link],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except Exception as e:
            print("Exception in opening weblink(): %s" % e)

    def is_connected(self):
        try:
            host = socket.gethostbyname(REMOTE_SERVER)
            s = socket.create_connection((host, 80), 2)
            s.close()

            return True
        except:  # noqa
            pass

        return False

    def tooltip_callback(self, widget, x, y, keyboard_mode, tooltip, text):
        tooltip.set_text(text)
        return True

    def internet_notifier(self):
        bb = 0
        dis = 0
        while True:
            if not self.is_connected():
                dis = 1
                GLib.idle_add(self.button_htb.set_sensitive, False)
                GLib.idle_add(self.button_mirrors.set_sensitive, False)
                GLib.idle_add(self.button_roles.set_sensitive, False)
                GLib.idle_add(self.button_update.set_sensitive, False)
                GLib.idle_add(self.button_install_tui.set_sensitive, False)
                self.label_notify.set_name("label_style")
                GLib.idle_add(
                    self.label_notify.set_markup,
                    f"<span foreground='yellow'><b>Not connected to internet</b>\n"
                    f"Some features will <b>not</b> be available</span>",
                )  # noqa
            else:
                self.label_notify.set_name("")
                if bb == 0 and dis == 1:
                    GLib.idle_add(self.button_htb.set_sensitive, True)
                    GLib.idle_add(self.button_mirrors.set_sensitive, True)
                    GLib.idle_add(self.button_roles.set_sensitive, True)
                    GLib.idle_add(self.button_update.set_sensitive, True)
                    GLib.idle_add(self.button_install_tui.set_sensitive, True)
                    GLib.idle_add(self.label_notify.set_text, "")
                    bb = 1
            sleep(3)

    def mirror_update(self):
        GLib.idle_add(self.button_mirrors.set_sensitive, False)
        if GUI.command_exists("pacman"):
            GLib.idle_add(
                self.label_notify.set_markup,
                f"<span foreground='orange'><b>Updating your mirrorlists</b>\n"
                f"This may take some time, please wait...</span>",
            )  # noqa
            
            subprocess.run(
                [
                    "pkexec",
                    "bash",
                    "-c",
                    (
                        "rate-mirrors --concurrency 40 --disable-comments --allow-root --save /etc/pacman.d/mirrorlist arch && "
                        "rate-mirrors --concurrency 40 --disable-comments --allow-root --save /etc/pacman.d/chaotic-mirrorlist chaotic-aur"
                    ),
                ],
                shell=False,
            )
            print("Update mirrors completed")
            GLib.idle_add(self.label_notify.set_markup, "<b>Mirrorlist updated</b>")
        elif GUI.command_exists("nixos-rebuild"):
            GLib.idle_add(
                self.label_notify.set_markup,
                f"<span foreground='orange'><b>Updating your Nix channels</b>\n"
                f"This may take some time, please wait...</span>",
            )  # noqa

            subprocess.run(
                [
                    "pkexec",
                    "nix-channel",
                    "--update",
                ],
                shell=False,
            )
            print("Update channels completed")
            GLib.idle_add(self.label_notify.set_markup, "<b>Channels updated</b>")
        GLib.idle_add(self.button_mirrors.set_sensitive, True)

if __name__ == "__main__":
    w = Main()
    w.connect("delete-event", Gtk.main_quit)
    w.show_all()
    Gtk.main()
