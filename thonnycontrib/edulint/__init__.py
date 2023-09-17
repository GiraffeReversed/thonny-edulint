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

from thonny import get_workbench, ui_utils
from thonny.config_ui import ConfigurationPage
from thonny.languages import tr
from thonnycontrib.edulint.view import EduLintView, SubprocessProgramAnalyzer, add_program_analyzer
from thonnycontrib.edulint.update_dialog import check_updates_with_notification, UpdateDialog

import edulint
import m2r2


class LintingError(Exception):
    pass


class EdulintAnalyzer(SubprocessProgramAnalyzer):
    """The analyzer itself"""

    def is_enabled(self):
        """Returns if the user has the option enabled"""
        return get_workbench().get_option("edulint.enabled")

    def start_analysis(self, main_file_path, imported_file_paths):
        """Runs edulint on the currently open file."""
        python_executable_path = sys.executable

        self._proc = ui_utils.popen_with_ui_thread_callback(
            [python_executable_path, "-m", "edulint", "--disable-version-check", "--json", main_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            on_completion=partial(self._parse_and_output_warnings, main_file_path),
        )

    def _parse_and_output_warnings(self, main_file_path, _, out_lines, err_lines):
        """Parses the edulint output and sends it to thonny"""

        for error in err_lines:
            logging.getLogger("EduLint").error(error)

        out = "".join(out_lines)
        try:
            edulint_result = json.loads(out)
        except json.decoder.JSONDecodeError as e:
            logging.getLogger("EduLint").error("failed to parse output:\n%s\n", out)
            logging.getLogger("EduLint").error(e)
            raise LintingError(
                "Unable to decode results of linting. "
                "Try installing edulint as a package: "
                "Tools -> Manage packages... -> search edulint -> Install"
            ) from None

        warnings = []
        for edulint_finding in edulint_result["problems"]:
            thonny_finding = self._edulint_finding_to_thonny_format(edulint_finding)
            warnings.append(thonny_finding)

        if len(edulint_result["configs"]) != 1 or edulint_result["configs"][0][0][0] != main_file_path:
            config = None
        else:
            config = edulint_result["configs"][0][1]["config"]

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
    Thread(target=check_updates_with_notification).start() # note: might want to call this only after event WorkbenchReady
