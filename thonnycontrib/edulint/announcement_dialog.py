from logging import getLogger

from tkinter import ttk

from thonny import get_workbench
from thonny.ui_utils import CommonDialog

from thonnycontrib.edulint.reporting import post_async_with_session_id

import requests

logger = getLogger("EduLint")


def check_for_announcement():
    post_async_with_session_id(filepath="", type="thonny-annoucement-request", data={}, callback=process_announcement_response)

def process_announcement_response(resp: requests.Response):
    if resp.status_code != 200:
        logger.info(f"Announcement endpoint failed {resp}")
        return
    data = resp.json()
    if data.get("text", None):
        logger.info(f"Announcement is non empty - openning dialog")
        get_workbench().set_option("assistance.announcement_text", data["text"])
        get_workbench().event_generate("<<EduLintOpenAnnouncementDialog>>", when="tail")


class AnnouncementDialog(CommonDialog):
    def __init__(self, master):
        super().__init__(master=master)
        main_frame = ttk.Frame(self)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.title("Thonny-EduLint - Announcement")

        # WARNING: This 'announcement_text' option doesn't have a default value.
        #          Only open the dialog when you set the text immediately before that.

        error_label = ttk.Label(main_frame, text=get_workbench().get_option("assistance.announcement_text"))
        error_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=15, pady=(15, 15))

    def _close(self, event=None):
        self.destroy()
