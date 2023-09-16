from logging import getLogger
from typing import Dict
from threading import Thread

import tkinter as tk
from tkinter import messagebox, ttk

from thonny import get_workbench, ui_utils
from thonny.ui_utils import CommonDialog

from thonnycontrib.edulint.version_checker import PackageInfoManager, update_awaiting

logger = getLogger(__name__)

def check_updates_with_notification(ttl: int = 600, open_window_always: bool = False):
    if get_workbench().get_option("edulint.disable_version_check", default=False) and not open_window_always:
        return

    is_update_waiting = update_awaiting(ttl)
    # print("---------------", is_update_waiting)
    if is_update_waiting or open_window_always:
        ui_utils.show_dialog(UpdateDialog(get_workbench()))


async_check_for_update = Thread(target=check_updates_with_notification)
async_check_for_update.start()



class UpdateDialog(CommonDialog):
    def __init__(self, master):
        super().__init__(master=master)
        main_frame = ttk.Frame(self)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.title("Thonny-EduLint - version check")

        padx = 15

        try:
            edulint_is_outdated = PackageInfoManager.is_update_waiting("edulint")
            edulint_local_version = PackageInfoManager.get_local_module_version("edulint")
            edulint_latest_version = PackageInfoManager.get_latest_version("edulint")

            thonny_edulint_is_outdated = PackageInfoManager.is_update_waiting("thonny-edulint")
            thonny_edulint_local_version = PackageInfoManager.get_local_module_version("thonny-edulint")
            thonny_edulint_latest_version = PackageInfoManager.get_local_module_version("thonny-edulint")
            
        except:
            error_label = ttk.Label(
                main_frame,
                text=f"An error occured while checking for current and latest version. Maybe you're not connected to Internet?",
            )
            error_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 15))
            return

        no_updates = "There are currently no updates available, you have the newest versions.\n"
        update_for_edulint = "New version of EduLint is available.\nYou can update it through: Main menu -> Tools -> Manage packages... -> search for EduLint -> click Upgrade. After that, you have to restart Thonny.\n\n"
        update_for_thonny_edulint = "New version of Thonny-EduLint is available.\nYou can update it through: Main menu -> Tools -> Manage plug-ins... -> search for Thonny-EduLint -> click Upgrade. After that, you have to restart Thonny.\n\n"
        current_state = f"""\nCurrent state:
EduLint: installed version = {edulint_local_version}; newest version = {edulint_latest_version}
Thonny-EduLint: installed version = {thonny_edulint_local_version}; newest version = {thonny_edulint_latest_version}"""

        intro_label = ttk.Label(
            main_frame,
            text= "" +
                (no_updates if not (thonny_edulint_is_outdated or edulint_is_outdated) else "") +
                (update_for_thonny_edulint if thonny_edulint_is_outdated  else "") +
                (update_for_edulint if edulint_is_outdated  else "") +
                current_state,
            wraplength=550,
            # width=100
        )
        intro_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 15))


    def _close(self, event=None):
        self.destroy()
