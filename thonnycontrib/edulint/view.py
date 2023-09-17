import ast
import datetime
import os.path
import textwrap
import tkinter as tk
from logging import getLogger
from typing import List

from thonny import get_runner, get_workbench, rst_utils, tktextext, ui_utils
from thonny.common import STRING_PSEUDO_FILENAME, ToplevelResponse, read_source
from thonny.ui_utils import scrollbar_style

from thonnycontrib.edulint.feedback_dialog import FeedbackDialog


logger = getLogger(__name__)
_program_analyzer_classes: List["ProgramAnalyzer"] = []
ASK_FEEDBACK = False


class EduLintView(tktextext.TextFrame):
    def __init__(self, master):
        tktextext.TextFrame.__init__(
            self,
            master,
            text_class=EduLintRstText,
            vertical_scrollbar_style=scrollbar_style("Vertical"),
            horizontal_scrollbar_style=scrollbar_style("Horizontal"),
            horizontal_scrollbar_class=ui_utils.AutoScrollbar,
            read_only=True,
            wrap="word",
            font="TkDefaultFont",
            # cursor="arrow",
            padx=10,
            pady=0,
            insertwidth=0,
        )

        self._analyzer_instances = []
        self._accepted_warning_sets = []

        self._snapshots_per_main_file = {}
        self._current_snapshot = None

        main_font = tk.font.nametofont("TkDefaultFont")

        # Underline on font looks better than underline on tag
        italic_underline_font = main_font.copy()
        italic_underline_font.configure(slant="italic", size=main_font.cget("size"), underline=True)

        if ASK_FEEDBACK:
            self.text.tag_configure("feedback_link", justify="right", font=italic_underline_font)
            self.text.tag_bind("feedback_link", "<ButtonRelease-1>", self._ask_feedback, True)

        get_workbench().bind("ToplevelResponse", self.handle_toplevel_response, True)

    def handle_toplevel_response(self, msg: ToplevelResponse) -> None:
        # Can be called by event system or by Workbench
        # (if EduLint wasn't created yet but an error came)
        # TODO?
        if not msg.get("user_exception") and msg.get("command_name") in [
            "execute_system_command",
            "execute_source",
        ]:
            # Shell commands may be used to investigate the problem, don't clear assistance
            return

        self._clear()

        from thonny.plugins.cpython_frontend import LocalCPythonProxy

        if not isinstance(get_runner().get_backend_proxy(), LocalCPythonProxy):
            # TODO: add some support for MicroPython as well
            return

        # prepare for snapshot
        # TODO: should distinguish between <string> and <stdin> ?
        key = msg.get("filename", STRING_PSEUDO_FILENAME)
        self._current_snapshot = {
            "timestamp": datetime.datetime.now().isoformat()[:19],
            "main_file_path": key,
        }
        self._snapshots_per_main_file.setdefault(key, [])
        self._snapshots_per_main_file[key].append(self._current_snapshot)

        if msg.get("filename") and os.path.exists(msg["filename"]):
            self.main_file_path = msg["filename"]
            source = read_source(msg["filename"])
            self._start_program_analyses(
                msg["filename"], source, _get_imported_user_files(msg["filename"], source)
            )
        else:
            self.main_file_path = None
            self._present_conclusion(None, [])

    def _append_text(self, chars, tags=()):
        self.text.direct_insert("end", chars, tags=tags)

    def _clear(self):
        self._accepted_warning_sets.clear()
        for wp in self._analyzer_instances:
            wp.cancel_analysis()
        self._analyzer_instances = []
        self.text.clear()

    def _start_program_analyses(self, main_file_path, main_file_source, imported_file_paths):
        for cls in _program_analyzer_classes:
            analyzer = cls(self._accept_warnings)
            if analyzer.is_enabled():
                self._analyzer_instances.append(analyzer)

        if not self._analyzer_instances:
            return

        self._append_text("\nAnalyzing your code ...", ("em",))

        # save snapshot of current source
        self._current_snapshot["main_file_path"] = main_file_path
        self._current_snapshot["main_file_source"] = main_file_source
        self._current_snapshot["imported_files"] = {
            name: read_source(name) for name in imported_file_paths
        }

        # start the analysis
        for analyzer in self._analyzer_instances:
            analyzer.start_analysis(main_file_path, imported_file_paths)

        if get_workbench().get_option("edulint.open_edulint_on_warnings"):
            get_workbench().show_view("EduLintView")

    def _accept_warnings(self, analyzer, warnings, config):
        if analyzer.cancelled:
            return

        self._accepted_warning_sets.append(warnings)
        if len(self._accepted_warning_sets) == len(self._analyzer_instances):
            warnings = [w for ws in self._accepted_warning_sets for w in ws]
            self._present_warnings(warnings)
            self._present_conclusion(config, warnings)

    def _present_summary(self, warnings):
        self._append_text("\n")
        rst = "Summary: "
        if len(warnings) == 0:
            return rst + "no problems detected"

        enabler_counts = {
            enabler: len([w for w in warnings if w["enabled_by"] == enabler])
            for enabler in sorted(set(
                w["enabled_by"] for w in warnings
            ))
        }
        rst += ", ".join(
            f"{enabler if enabler is not None else 'undetermined origin'}: {count}"
            for enabler, count in enabler_counts.items()
        )
        rst += "\n\n"
        return rst

    def _present_conclusion(self, config, warnings):
        if self.main_file_path is not None and os.path.exists(self.main_file_path):
            self.text.append_rst(self._present_summary(warnings))

            if config is not None:
                self.text.append_rst(f"used configuration: {config}", ("em",))

            if len(warnings) == 0:
                self.text.append_rst(
                    "If the code is not working as it should, "
                    + "then consider using some general "
                    + "`debugging techniques <debugging.rst>`__.\n\n",
                )

        if ASK_FEEDBACK and len(warnings) > 0:
            self._append_feedback_link()

    def _present_warnings(self, warnings):
        self.text.direct_delete("end-2l linestart", "end-1c lineend")

        if not warnings:
            return

        rst = (
            self._get_rst_prelude()
            + rst_utils.create_title("What to improve")
            + ":remark:`%s`\n\n" % "Addressing these suggestions can fix some bugs and makes your code more readable."
        )

        by_file = {}
        for warning in warnings:
            if warning["filename"] not in by_file:
                by_file[warning["filename"]] = []
            if warning not in by_file[warning["filename"]]:
                # Pylint may give double warnings (eg. when module imports itself)
                by_file[warning["filename"]].append(warning)

        for filename in by_file:
            if len(by_file) > 1:
                rst += "`%s <%s>`__\n\n" % (
                    os.path.basename(filename),
                    self._format_file_url(dict(filename=filename)),
                )
            file_warnings = sorted(
                by_file[filename], key=lambda x: (x.get("lineno", 0), -x.get("relevance", 1))
            )

            for i, warning in enumerate(file_warnings):
                rst += self._format_warning(warning, i == len(file_warnings) - 1) + "\n"

            rst += "\n"

        self.text.append_rst(rst)

        # save snapshot
        self._current_snapshot["warnings_rst"] = rst
        self._current_snapshot["warnings"] = warnings

        if get_workbench().get_option("edulint.open_edulint_on_warnings"):
            get_workbench().show_view("EduLintView")

    def _format_warning(self, warning, last):
        prepared_enabler = f"[{warning['enabled_by']}] " if warning["enabled_by"] is not None else ""
        prepared_msg = warning["msg"].splitlines()[0]
        title = rst_utils.escape(prepared_enabler + prepared_msg)
        if warning.get("lineno") is not None:
            url = self._format_file_url(warning)
            if warning.get("lineno"):
                title = "`Line %d <%s>`__ : %s" % (warning["lineno"], url, title)

        if warning.get("explanation_rst"):
            explanation_rst = warning["explanation_rst"]
        elif warning.get("explanation"):
            explanation_rst = rst_utils.escape(warning["explanation"])
        else:
            explanation_rst = ""

        if warning.get("more_info_url"):
            explanation_rst += "\n\n`More info online <%s>`__" % warning["more_info_url"]

        explanation_rst = explanation_rst.strip()
        topic_class = "toggle" if explanation_rst else "empty"
        if not explanation_rst:
            explanation_rst = "n/a"

        return (
            ".. topic:: %s\n" % title
            + "    :class: "
            + topic_class
            + ("" if last else ", tight")
            + "\n"
            + "    \n"
            + textwrap.indent(explanation_rst, "    ")
            + "\n\n"
        )

    def _append_feedback_link(self):
        self._append_text("Was it helpful or confusing?\n", ("a", "feedback_link"))

    def _format_file_url(self, atts):
        return format_file_url(atts["filename"], atts.get("lineno"), atts.get("col_offset"))

    def _ask_feedback(self, event=None):
        all_snapshots = self._snapshots_per_main_file[self._current_snapshot["main_file_path"]]

        # TODO: select only snapshots which are not sent yet
        snapshots = all_snapshots

        ui_utils.show_dialog(FeedbackDialog(get_workbench(), self.main_file_path, snapshots))

    def _get_rst_prelude(self):
        return ".. default-role:: code\n\n" + ".. role:: light\n\n" + ".. role:: remark\n\n"


class EduLintRstText(rst_utils.RstText):
    def configure_tags(self):
        super().configure_tags()

        main_font = tk.font.nametofont("TkDefaultFont")

        italic_font = main_font.copy()
        italic_font.configure(slant="italic", size=main_font.cget("size"))

        h1_font = main_font.copy()
        h1_font.configure(weight="bold", size=main_font.cget("size"))

        self.tag_configure("h1", font=h1_font, spacing3=0, spacing1=10)
        self.tag_configure("topic_title", font="TkDefaultFont")

        self.tag_configure("topic_body", font=italic_font, spacing1=10, lmargin1=25, lmargin2=25)

        self.tag_raise("sel")


class ProgramAnalyzer:
    def __init__(self, on_completion):
        self.completion_handler = on_completion
        self.cancelled = False

    def is_enabled(self):
        return True

    def start_analysis(self, main_file_path, imported_file_paths):
        raise NotImplementedError()

    def cancel_analysis(self):
        pass


class SubprocessProgramAnalyzer(ProgramAnalyzer):
    def __init__(self, on_completion):
        super().__init__(on_completion)
        self._proc = None

    def cancel_analysis(self):
        self.cancelled = True
        if self._proc is not None:
            self._proc.kill()


def _get_imported_user_files(main_file, source=None):
    assert os.path.isabs(main_file)

    if source is None:
        source = read_source(main_file)

    try:
        root = ast.parse(source, main_file)
    except SyntaxError:
        return set()

    main_dir = os.path.dirname(main_file)
    module_names = set()
    # TODO: at the moment only considers non-package modules
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for item in node.names:
                module_names.add(item.name)
        elif isinstance(node, ast.ImportFrom):
            module_names.add(node.module)

    imported_files = set()

    for file in {name + ext for ext in [".py", ".pyw"] for name in module_names}:
        possible_path = os.path.join(main_dir, file)
        if os.path.exists(possible_path):
            imported_files.add(possible_path)

    return imported_files
    # TODO: add recursion


def add_program_analyzer(cls):
    _program_analyzer_classes.append(cls)


def format_file_url(filename, lineno, col_offset):
    s = "thonny-editor://" + rst_utils.escape(filename).replace(" ", "%20")
    if lineno is not None:
        s += "#" + str(lineno)
        if col_offset is not None:
            s += ":" + str(col_offset)

    return s
