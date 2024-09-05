from logging import getLogger

from tkinter import ttk

from thonny import get_workbench
from thonny.ui_utils import CommonDialog

from thonnycontrib.edulint.version_checker import PackageInfoManager, update_awaiting

logger = getLogger(__name__)


def check_updates_with_notification(ttl: int = 600, open_window_always: bool = False):
    if get_workbench().get_option("edulint.disable_version_check", default=False) and not open_window_always:
        return

    is_update_waiting = update_awaiting(ttl)
    if is_update_waiting or open_window_always:
        get_workbench().event_generate("<<EduLintOpenUpdateWindow>>", when="tail")


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
            thonny_edulint_latest_version = PackageInfoManager.get_latest_version("thonny-edulint")
        except Exception:
            error_label = ttk.Label(
                main_frame,
                text="An error occurred while checking for current and latest version. Maybe you're "
                     "not connected to Internet?",
            )
            error_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 15))
            return

        no_updates = "You have the newest version.\n\n"      
        
        update_thonny_edulint_instructions = """
New version of Thonny-EduLint is available.
You can update through:
   Main menu -> Tools -> Manage plug-ins... -> search for Thonny-EduLint -> click Upgrade.
After that, you have to restart Thonny.\n\n
"""

        update_just_edulint_instructions = """
New version of EduLint is available.
You can update through:
   Main menu -> Tools -> Manage plug-ins... -> search for Thonny-EduLint -> click '...' -> select the newest version and check 'Upgrade dependencies' -> click Install
After that, you have to restart Thonny.\n\n
"""

        current_state = f"""\nCurrent state:
EduLint: installed version = {edulint_local_version}; newest version = {edulint_latest_version}
Thonny-EduLint: installed version = {thonny_edulint_local_version}; newest version = {thonny_edulint_latest_version}"""

        intro_label = ttk.Label(
            main_frame,
            text=(
                (update_thonny_edulint_instructions if thonny_edulint_is_outdated else "") +
                (update_just_edulint_instructions if edulint_is_outdated and not thonny_edulint_is_outdated else "") +
                (no_updates if not edulint_is_outdated and not thonny_edulint_is_outdated else "") +
                current_state
            ),
            wraplength=550,
        )
        intro_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 15))

    def _close(self, event=None):
        self.destroy()
