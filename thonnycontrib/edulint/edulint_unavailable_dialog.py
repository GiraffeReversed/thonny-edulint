from tkinter import ttk

from thonny.ui_utils import CommonDialog

class EdulintUnavailableDialog(CommonDialog):
    def __init__(self, master):
        super().__init__(master=master)
        main_frame = ttk.Frame(self)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.title("Thonny-EduLint - Edulint is unavailable")

        error_label = ttk.Label(
            main_frame,
            text=   "Thonny-Edulint was unable to decode results of linting. This error often occurs in new installations due to a Thonny bug.\n\n"
                    "Try to install Edulint as a package:\n"
                    "  Tools (menu in top of the window) -> Manage packages... -> search for 'edulint' -> Install",
        )
        error_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=15, pady=(15, 15))

    def _close(self, event=None):
        self.destroy()
