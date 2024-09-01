import platform
import os
import hashlib
import json
import logging
import threading

from thonnycontrib.edulint.version_checker import PackageInfoManager
from platformdirs import PlatformDirs
import requests

REPORTING_URL = 'https://edulint.com/api/reporting'

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
    _send_generic(filepath, 'result', {
        'errors': err,  # TODO: Should we base64 this? 
    })
