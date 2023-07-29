#!/bin/env python3
"""thonny-edulint, adds edulint warnings to Thonny"""
import logging
import subprocess
import sys
import json
from functools import lru_cache
from typing import Dict

from thonny import get_workbench, ui_utils
from thonny.assistance import SubprocessProgramAnalyzer, add_program_analyzer

from thonny import rst_utils
import edulint
import m2r2


class EdulintAnalyzer(SubprocessProgramAnalyzer):
    """The analyzer itself"""

    def is_enabled(self):
        """Returns if the user has the option enabled"""
        enabled = get_workbench().get_option("assistance.use_edulint")
        if enabled == None:  # The option is currently not in UI.
            enabled = True
        return enabled

    def start_analysis(self, main_file_path, imported_file_paths):
        """Runs edulint on the currently open file."""
        python_executable_path = sys.executable

        self._proc = ui_utils.popen_with_ui_thread_callback(
            [ python_executable_path, "-m", "edulint", "--json", main_file_path ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            on_completion=self._parse_and_output_warnings,
        )

    def _parse_and_output_warnings(self, _, out_lines, err_lines):
        """Parses the edulint output and sends it to thonny"""

        warnings = []
        for error in err_lines:
            logging.getLogger("thonny").error("Edulint: %s", error)

        edulint_findings = json.loads("\n".join(out_lines))

        for edulint_finding in edulint_findings:
            thonny_finding = self._edulint_finding_to_thonny_format(edulint_finding)
            warnings.append(thonny_finding)

        self.completion_handler(self, warnings)

    @classmethod
    def _edulint_finding_to_thonny_format(cls, edulint_finding):
        text_headline = edulint_finding['text']
        text_explanation = cls._get_single_edulint_explanation_in_rst(edulint_finding['code'])

        atts = {}
        # atts["explanation"] = text_explanation
        atts["explanation_rst"] = text_explanation
        atts["msg"] = text_headline   # note that this cut outs after first newline https://github.com/thonny/thonny/issues/1186

        atts["filename"] = edulint_finding["path"]
        
        atts["lineno"] = edulint_finding["line"]
        atts["col_offset"] = edulint_finding["column"]

        if "end_line" in edulint_finding:
            atts["end_lineno"] = edulint_finding["end_line"]
        if "end_column" in edulint_finding:
            atts["end_col_offset"] = edulint_finding["end_column"]

        # remaining from edulint JSON: source, code, symbol
        # remaining in thonny dict: more_info_url

        return atts

    @classmethod
    def _get_single_edulint_explanation_in_rst(cls, code: str) -> str:
        specific_explanation: Dict[str, str] = cls._get_all_edulint_explanations().get(code, {})
        text_explanation_md: str = \
            specific_explanation.get('why', '') + '\n\n' + \
            specific_explanation.get('examples', '')

        text_explanation_rst = m2r2.convert(text_explanation_md)
        text_explanation_rst = text_explanation_rst.replace(".. code-block:: py", "::")  # Thonny doesn't show code block in Assistant correctly.

        return text_explanation_rst


    @staticmethod
    @lru_cache
    def _get_all_edulint_explanations():
        return edulint.get_explanations()

def load_plugin():
    """Adds the edulint analyzer"""
    add_program_analyzer(EdulintAnalyzer)
