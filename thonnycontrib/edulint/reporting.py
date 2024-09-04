import platform
import os
import hashlib
import json
import logging
import threading
import re

from thonnycontrib.edulint.version_checker import PackageInfoManager
from platformdirs import PlatformDirs
import requests
from tkinter import ttk

from thonny import get_workbench
from thonny.ui_utils import CommonDialog
from thonny.languages import tr

REPORTING_URL = 'https://edulint.com/api/reporting'

class EdulintReportingFirstTimeDialog(CommonDialog):
    def __init__(self, master):
        super().__init__(master=master)
        main_frame = ttk.Frame(self)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.title("Thonny-EduLint - Will you help us?")

        error_label = ttk.Label(
            main_frame,
            text="""To improve EduLint and research code quality we need data about your usage of EduLint.

Will you help us collect this anonymous data?

Clicking Yes will open settings dialog, where you can fine tune which things should be sent to us.

Clicking No will keep settings of reporting as is (disabled by default). You can later enable it EduLints settings.
""")
        error_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=15, pady=(15, 15))

        self._yes_button = ttk.Button(main_frame, text=tr("Yes"), command=self._yes)
        self._yes_button.grid(row=2, column=0, sticky="ne", padx=15, pady=15)

        self._no_button = ttk.Button(main_frame, text=tr("No"), command=self._no)
        self._no_button.grid(row=2, column=1, sticky="ne", padx=15, pady=15)

        self.bind("<Escape>", self._no, True)
        self.bind("<Return>", self._yes, True)

    def _yes(self, event=None):
        get_workbench().set_option("edulint.enable_code_remote_reporting", True)
        get_workbench().set_option("edulint.enable_result_remote_reporting", True)
        get_workbench().set_option("edulint.enable_exception_remote_reporting", True)
        get_workbench().show_options("edulint")
        self._close()

    def _no(self, event=None):
        self._close()

    def _close(self, event=None):
        self.destroy()

def str_to_sha256(text: str, digest_length: int = 20) -> str:
    return hashlib.sha256(str.encode(text)).hexdigest()[:digest_length]  # We don't need the whole hash


def get_reporting_user_id() -> str:
    ID_FAILURE = "thonny:ID_FAILURE"

    def generate_new_id() -> str:
        try:
            machine_name = str_to_sha256(platform.node())
            username = str_to_sha256(os.getlogin())
            return f"thonny:{machine_name}:{username}"
        except Exception as e:
            return ID_FAILURE

    def ensure_persistent_id() -> str:
        filepath = os.path.join(PlatformDirs(appname="thonny-edulint").user_data_dir, "user_id.json")
        PackageInfoManager._create_json_file_if_doesnt_exist(filepath)  # TODO: This method should probably be in utils file

        with open(filepath, "r", encoding="utf8") as f:
            user_id_content = json.load(f)
        if user_id_content.get("user_id", None):
            return user_id_content.get("user_id")
        
        user_id = generate_new_id()
        if user_id != ID_FAILURE:
            with open(filepath, "w", encoding="utf8") as f:
                json.dump({'user_id': user_id}, f, indent=4)
        return user_id

    try:
        return ensure_persistent_id()
    except Exception as e:
        return ID_FAILURE

def get_file_session_id(filepath) -> str:
    fileid = str_to_sha256(filepath, 10)
    return f"{get_reporting_user_id()}:{fileid}"


def _post_sync(url: str, json_data: dict, headers: dict):
    try:
        requests.post(url, json=json_data, headers=headers)
    except Exception as e:
        logging.getLogger("EduLint").error(str(e))

def post_async(url: str, json_data: dict, headers: dict = None): 
    threading.Thread(target=_post_sync, args=(url, json_data, headers)).start()

def _send_generic(filepath: str, type: str, data: dict):
    common_data = {
        'type': type,
        'session_id': get_file_session_id(filepath),
    }
    post_async(REPORTING_URL, json_data={**common_data, **data})

# WARNING: The following functions MUST NEVER fail and be ASYNC

def send_code(filepath: str):
    try:
        with open(filepath, 'r') as f:  # TODO: do we need to set encoding (especially on Windows?)
            file_content = f.read()
    except Exception as e:
        logging.getLogger("EduLint").error(str(e))
    _send_generic(filepath, 'code', {
        'code': file_content, # TODO: Should we base64 this? 
    })

def send_results(filepath: str, results: str):
    _send_generic(filepath, 'result', {
        'results': results, # TODO: Should we base64 this? 
    })

def send_errors(filepath: str, err: str):
    def sanitize_stacktrace(text: str) -> str:
        # Partial local scrub of some personally identifiable information from stacktraces
        # Additional cleanup is done server side
        try:
            answer = text
            answer = re.sub(r'[a-zA-Z]\:\\Users\\[a-zA-Z0-9]+\\', r'C:\\Users\\REDACTED\\', answer)
            answer = re.sub(r'/home/[a-zA-Z0-9]+/', r'/home/REDACTED/', answer)
            return answer
        except Exception as e:
            logging.getLogger("EduLint").error(str(e))
            return text
    
    err = sanitize_stacktrace(err)
    _send_generic(filepath, 'result', {
        'errors': err,  # TODO: Should we base64 this? 
    })
