#!/bin/env python3
"""thonny-edulint, adds edulint warnings to Thonny"""
import logging
import subprocess
import sys
import json
from functools import lru_cache, partial
from typing import Dict
from pathlib import Path
from threading import Thread
import traceback
import os
import importlib

from tkinter import ttk

from thonny import get_workbench, ui_utils
from thonny.config_ui import ConfigurationPage
from thonny.languages import tr
from thonny.running import get_front_interpreter_for_subprocess

from thonnycontrib.edulint.view import EduLintView, SubprocessProgramAnalyzer, add_program_analyzer
from thonnycontrib.edulint.update_dialog import check_updates_with_notification, UpdateDialog
from thonnycontrib.edulint.edulint_unavailable_dialog import EdulintUnavailableDialog
from thonnycontrib.edulint.reporting import get_reporting_user_id, send_code, send_results, send_errors, EdulintReportingFirstTimeDialog
from thonnycontrib.edulint.utils import add_path, get_pylint_plugins_dir

import m2r2


class LintingError(Exception):
    pass


class EdulintAnalyzer(SubprocessProgramAnalyzer):
    """The analyzer itself"""

    def is_enabled(self):
        """Returns if the user has the option enabled"""
        return get_workbench().get_option("edulint.enabled")

    # kudos for env preparation goes to @ettore-galli https://github.com/ettore-galli/thonny-black-formatter/blob/main/thonnycontrib/black_formatter/__init__.py#L41
    # we just copy the env and pass it as variable, instead of overwriting os.environ thonny-wide
    def prepare_run_environment(self):
        env = os.environ.copy()

        plugins_folders = [folder for folder in sys.path if "plugins" in folder]
        plugins_folder = os.path.join(plugins_folders[0])
        binfolder = plugins_folder.replace("lib/python/site-packages", "bin")

        env["PYTHONPATH"] = plugins_folder + (
            ":" + env["PYTHONPATH"] if "PYTHONPATH" in env.keys() else ""
        )
        env["PATH"] = binfolder + ":" + plugins_folder + ":" + env["PATH"]
        return env

    def start_analysis(self, main_file_path, imported_file_paths):
        """Runs edulint on the currently open file."""
        python_executable_path = get_front_interpreter_for_subprocess()

        if get_workbench().get_option("edulint.enable_code_remote_reporting", default=False):
            send_code(main_file_path)

        self._proc = ui_utils.popen_with_ui_thread_callback(
            [python_executable_path, "-m", "edulint", "check", "--disable-version-check", "--json", main_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=self.prepare_run_environment(),
            on_completion=partial(self._parse_and_output_warnings, main_file_path),
        )

    def _parse_and_output_warnings(self, main_file_path, _, out_lines, err_lines):
        """Parses the edulint output and sends it to thonny"""

        for error in err_lines:
            logging.getLogger("EduLint").error(error)

        if get_workbench().get_option("edulint.enable_exception_remote_reporting", default=False):
            err_str = "".join(err_lines) # TODO: can the join itself fail?
            if err_str:
                send_errors(main_file_path, err_str)  
                # TODO: This is covering edulint errors, but not thonny edulint errors

        out = "".join(out_lines)
        if get_workbench().get_option("edulint.enable_result_remote_reporting", default=False):
            send_results(main_file_path, out)

        try:
            edulint_result = json.loads(out)
        except json.decoder.JSONDecodeError as e:
            logging.getLogger("EduLint").error("failed to parse output:\n%s\n", out)
            logging.getLogger("EduLint").error(e)

            if get_workbench().get_option("edulint.enable_exception_remote_reporting", default=False):
                send_errors(main_file_path, traceback.format_exc())
        
            warnings = [{
                "explanation_rst": "" 
                    "Unable to decode results of linting. Install edulint as a package:\n"
                    "  Tools -> Manage packages... -> search edulint -> Install",
                "msg": "Linting failed. Check description with instructions how to fix it.",
                "filename": "EMPTY",
                "lineno": 1, 
                "col_offset": 1,
                "code": "X000",
                "enabled_by": "thonny-edulint",
            }]
            get_workbench().event_generate("<<EduLintOpenEdulintUnavailableDialog>>", when="tail")
            self.completion_handler(self, warnings, config=None)
            raise LintingError(
                "Unable to decode results of linting. "
                "Try installing edulint as a package: "
                "Tools -> Manage packages... -> search edulint -> Install"
            ) from None

        warnings = []
        for edulint_finding in edulint_result["problems"]:
            thonny_finding = self._edulint_finding_to_thonny_format(edulint_finding)
            warnings.append(thonny_finding)

        if len(edulint_result["configs"]) != 1:
            config = None
        else:
            config = edulint_result["configs"][0]

        number_of_succesful_lints = get_workbench().get_option("assistance.number_of_successful_lints", 0) + 1
        get_workbench().set_option("assistance.number_of_successful_lints", number_of_succesful_lints)   

        if number_of_succesful_lints == 8 and get_workbench().get_option("assistance.has_user_seen_reporting_dialog", False) is False:
            get_workbench().set_option("assistance.has_user_seen_reporting_dialog", True)
            get_workbench().event_generate("<<EduLintOpenReportingFirstTimeDialog>>", when="tail")

        self.completion_handler(self, warnings, config)

    @classmethod
    def _edulint_finding_to_thonny_format(cls, edulint_finding):
        text_explanation = cls._get_single_edulint_explanation_in_rst(edulint_finding["code"])

        atts = {}
        atts["explanation_rst"] = text_explanation
        # note that this cut outs after first newline https://github.com/thonny/thonny/issues/1186
        atts["msg"] = edulint_finding["text"]

        atts["filename"] = edulint_finding["path"]

        atts["lineno"] = edulint_finding["line"]
        atts["col_offset"] = edulint_finding["column"]

        if "end_line" in edulint_finding:
            atts["end_lineno"] = edulint_finding["end_line"]
        if "end_column" in edulint_finding:
            atts["end_col_offset"] = edulint_finding["end_column"]

        # remaining from edulint JSON: source, code, symbol
        # remaining in thonny dict: more_info_url
        atts["code"] = edulint_finding["code"]
        atts["enabled_by"] = edulint_finding["enabled_by"]

        return atts

    @classmethod
    def _get_single_edulint_explanation_in_rst(cls, code: str) -> str:
        specific_explanation: Dict[str, str] = cls._get_all_edulint_explanations().get(code, {})
        text_explanation_md: str = specific_explanation.get("why", "") + "\n"

        if "examples" in specific_explanation:
            text_explanation_md += "\n" + specific_explanation["examples"] + "\n"

        text_explanation_rst = m2r2.convert(text_explanation_md)
        # This can be used to replace code-block with literal block.
        # text_explanation_rst = text_explanation_rst.replace(".. code-block:: py", "::")
        text_explanation_rst = text_explanation_rst.replace(".. code-block:: py", ".. code::")

        # Syntax can be checked for example here:
        # https://raw.githubusercontent.com/thonny/thonny/66b3cb853cfc28ec504d29090d55ec86eee3f178/thonny/plugins/help/debugging.rst

        return text_explanation_rst

    @staticmethod
    @lru_cache
    def _get_all_edulint_explanations():
        with add_path(get_pylint_plugins_dir()):
            edulint = importlib.import_module('edulint')
        return edulint.get_explanations()


class EdulintConfigPage(ConfigurationPage):
    def __init__(self, master):
        super().__init__(master)

        self.add_checkbox(
            "edulint.enabled",
            "Enable EduLint analysis\n"
            "Enabling EduLint analysis disables PyLint for Assistant, "
            "as EduLint provides equivalent and improved functionality.",
            row=2,
            columnspan=2,
        )

        self.add_checkbox(
            "edulint.open_edulint_on_warnings",
            tr("Open EduLint automatically when it has warnings for your code"),
            row=3,
            columnspan=2,
        )
        self.add_checkbox(
            "edulint.disable_version_check",
            tr("Disable checks for a new version."),
            row=4,
            columnspan=2,
        )

        empty_space = ttk.Label(self, text="")
        empty_space.grid(row=5, columnspan=2, pady=20)

        reporting_headline = ttk.Label(self, text=tr("Report to EduLint servers"), font="BoldTkDefaultFont")
        reporting_headline.grid(row=6, columnspan=2)

        reporting_intro = ttk.Label(self, text=tr("To futher improve EduLint and research code quality we need data about your usage of EduLint. Will you help us collect this anonymous data?"))
        reporting_intro.grid(row=7, columnspan=2)

        self.add_checkbox(
            "edulint.enable_result_remote_reporting",
            tr("Send the linting results, i.e. which issues appeared in you code."),
            row=8,
            columnspan=2,
        )

        self.add_checkbox(
            "edulint.enable_code_remote_reporting",
            tr("Send the code itself."),
            row=9,
            columnspan=2,
        )
        self.add_checkbox(
            "edulint.enable_exception_remote_reporting",
            tr("Send the logs for exceptions/errors."),
            row=10,
            columnspan=2,
        )

        reporting_outro = ttk.Label(self, text=tr(
            "The data is used for the following purposes:\n"
            " - Improvement of EduLint\n"
            " - Academic research\n"
            "All data used for academic research undergoes additional anonymization first to ensure it doesn't contain any personally identifiable information.\n"
            "\n"
            "If you previously submitted some data and wish to remove them, send an email to privacy@edulint.com\n"
            "with subject 'Thonny-Edulint Data Request'. In the body of the email include the following identifier:\n"
            f"   {get_reporting_user_id()}"
            ), justify="left", anchor="w"
        )
        reporting_outro.grid(row=11, columnspan=2, sticky = "W")


    def apply(self):
        if get_workbench().get_option("edulint.enabled"):
            get_workbench().set_option("assistance.use_pylint", False)


def check_current_script():
    editor = get_workbench().get_editor_notebook().get_current_editor()
    if not editor:
        return

    if not editor.get_filename():
        return

    filename = editor.save_file()
    if not filename:
        # user has cancelled file saving
        return

    get_workbench().event_generate(
        "ToplevelResponse",
        filename=filename,
    )

    get_workbench().show_view("EduLintView")


def load_plugin():
    """Adds the edulint analyzer"""
    get_workbench().add_view(EduLintView, "EduLint", "se", visible_by_default=False)
    add_program_analyzer(EdulintAnalyzer)

    get_workbench().add_configuration_page("edulint", "EduLint", EdulintConfigPage, 81)
    get_workbench().set_default("edulint.enabled", True)
    get_workbench().set_default("edulint.open_edulint_on_warnings", False)
    get_workbench().set_default("edulint.disable_version_check", False)
    get_workbench().set_default("edulint.enable_code_remote_reporting", False)
    get_workbench().set_default("edulint.enable_result_remote_reporting", False)
    get_workbench().set_default("edulint.enable_exception_remote_reporting", False)
    get_workbench().set_default("edulint.has_user_seen_reporting_dialog", False)
    get_workbench().set_default("edulint.number_of_successful_lints", 0)

    if get_workbench().get_option("edulint.enabled"):
        get_workbench().set_default("assistance.use_pylint", False)
        get_workbench().set_option("assistance.use_pylint", False)

    def toggle_view_visibility(view_id):
        visibility_flag = get_workbench().get_variable("view." + view_id + ".visible")

        if visibility_flag.get():
            get_workbench().hide_view(view_id)
        else:
            get_workbench().show_view(view_id)

    get_workbench().add_command(
        "check_current_script",
        "EduLint",
        tr("Check with EduLint"),
        caption=tr("Check with EduLint"),
        handler=check_current_script,
        default_sequence="<F9>",
        group=0,
        image=str(Path(__file__).parent / "broom-green.png"),
        include_in_toolbar=not get_workbench().in_simple_mode(),
    )
    get_workbench().add_command(
        "view_edulint_tab",
        "EduLint",
        tr("View EduLint tab"),
        handler=lambda: toggle_view_visibility("EduLintView"),
        flag_name="view.EduLintView.visible",
        group=1,
    )
    get_workbench().add_command(
        "show_edulint_options",
        "EduLint",
        tr("EduLint Options..."),
        lambda: get_workbench().show_options("edulint"),
        group=180
    )
    get_workbench().add_command(
        "show_update_window",
        "EduLint",
        tr("Check for updates"),
        lambda: partial(check_updates_with_notification, ttl = 0, open_window_always = True)(),
        group=200
    )

    # Always use <<event>> for call that may come from threads. Tkinter ensures it runs on main thread. Thonny's custom implementation (i.e. without <<event>>) doesn't and it may get  processed on non-main thread.
    get_workbench().bind("<<EduLintOpenUpdateWindow>>", lambda _: ui_utils.show_dialog(UpdateDialog(get_workbench())), add=True)  
    get_workbench().bind("<<EduLintOpenEdulintUnavailableDialog>>", lambda _: ui_utils.show_dialog(EdulintUnavailableDialog(get_workbench())), add=True)  
    get_workbench().bind("<<EduLintOpenReportingFirstTimeDialog>>", lambda _: ui_utils.show_dialog(EdulintReportingFirstTimeDialog(get_workbench())), add=True)
    Thread(target=check_updates_with_notification).start() # note: might want to call this only after event WorkbenchReady
