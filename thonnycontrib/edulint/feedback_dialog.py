import datetime
import os.path
import subprocess
import sys
import tkinter as tk
from logging import getLogger
from tkinter import messagebox, ttk
from typing import Dict

import thonny
from thonny import get_workbench, tktextext, ui_utils
from thonny.common import REPL_PSEUDO_FILENAME
from thonny.misc_utils import running_on_mac_os
from thonny.ui_utils import CommonDialog, get_hyperlink_cursor, scrollbar_style


logger = getLogger(__name__)
_last_feedback_timestamps: Dict[str, str] = {}


class FeedbackDialog(CommonDialog):
    def __init__(self, master, main_file_path, all_snapshots):
        super().__init__(master=master)
        main_frame = ttk.Frame(self)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.main_file_path = main_file_path
        self.snapshots = self._select_unsent_snapshots(all_snapshots)

        self.title("Send feedback for EduLint")

        padx = 15

        intro_label = ttk.Label(
            main_frame,
            text="Below are the messages EduLint gave you in response to "
            + (
                "using the shell"
                if self._happened_in_shell()
                else "testing '" + os.path.basename(main_file_path) + "'"
            )
            + " since "
            + self._get_since_str()
            + ".\n\n"
            + "In order to improve this feature, EduLint developers would love to know how "
            + "useful or confusing these messages were. We will only collect version "
            + "information and the data you enter or approve on this form.",
            wraplength=550,
        )
        intro_label.grid(row=1, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 15))

        tree_label = ttk.Label(
            main_frame,
            text="Which messages were helpful (H) or confusing (C)?       Click on  [  ]  to mark!",
        )
        tree_label.grid(row=2, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 0))
        tree_frame = ui_utils.TreeFrame(
            main_frame,
            columns=["helpful", "confusing", "title", "group", "code"],
            displaycolumns=["helpful", "confusing", "title"],
            height=10,
            borderwidth=1,
            relief="groove",
        )
        tree_frame.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=padx)
        self.tree = tree_frame.tree
        self.tree.column("helpful", width=35, anchor=tk.CENTER, stretch=False)
        self.tree.column("confusing", width=35, anchor=tk.CENTER, stretch=False)
        self.tree.column("title", width=350, anchor=tk.W, stretch=True)

        self.tree.heading("helpful", text="H", anchor=tk.CENTER)
        self.tree.heading("confusing", text="C", anchor=tk.CENTER)
        self.tree.heading("title", text="Group / Message", anchor=tk.W)
        self.tree["show"] = ("headings",)
        self.tree.bind("<1>", self._on_tree_click, True)
        main_font = tk.font.nametofont("TkDefaultFont")
        bold_font = main_font.copy()
        bold_font.configure(weight="bold", size=main_font.cget("size"))
        self.tree.tag_configure("group", font=bold_font)

        self.include_thonny_id_var = tk.IntVar(value=1)
        include_thonny_id_check = ttk.Checkbutton(
            main_frame,
            variable=self.include_thonny_id_var,
            onvalue=1,
            offvalue=0,
            text="Include Thonny's installation time (allows us to group your submissions)",
        )
        include_thonny_id_check.grid(
            row=4, column=0, columnspan=3, sticky="nw", padx=padx, pady=(5, 0)
        )

        self.include_snapshots_var = tk.IntVar(value=1)
        include_snapshots_check = ttk.Checkbutton(
            main_frame,
            variable=self.include_snapshots_var,
            onvalue=1,
            offvalue=0,
            text="Include snapshots of the code and EduLint responses at each run",
        )
        include_snapshots_check.grid(
            row=5, column=0, columnspan=3, sticky="nw", padx=padx, pady=(0, 0)
        )

        comments_label = ttk.Label(main_frame, text="Any comments? Enhancement ideas?")
        comments_label.grid(row=6, column=0, columnspan=3, sticky="nw", padx=padx, pady=(15, 0))
        self.comments_text_frame = tktextext.TextFrame(
            main_frame,
            vertical_scrollbar_style=scrollbar_style("Vertical"),
            horizontal_scrollbar_style=scrollbar_style("Horizontal"),
            horizontal_scrollbar_class=ui_utils.AutoScrollbar,
            wrap="word",
            font="TkDefaultFont",
            # cursor="arrow",
            padx=5,
            pady=5,
            height=4,
            borderwidth=1,
            relief="groove",
        )
        self.comments_text_frame.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=padx)

        url_font = tk.font.nametofont("TkDefaultFont").copy()
        url_font.configure(underline=1, size=url_font.cget("size"))
        preview_link = ttk.Label(
            main_frame,
            text="(Preview the data to be sent)",
            style="Url.TLabel",
            cursor=get_hyperlink_cursor(),
            font=url_font,
        )
        preview_link.bind("<1>", self._preview_submission_data, True)
        preview_link.grid(row=8, column=0, sticky="nw", padx=15, pady=15)

        submit_button = ttk.Button(main_frame, text="Submit", width=10, command=self._submit_data)
        submit_button.grid(row=8, column=0, sticky="ne", padx=0, pady=15)

        cancel_button = ttk.Button(main_frame, text="Cancel", width=7, command=self._close)
        cancel_button.grid(row=8, column=1, sticky="ne", padx=(10, 15), pady=15)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", self._close, True)

        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=3)
        main_frame.rowconfigure(6, weight=2)

        self._empty_box = "[  ]"
        self._checked_box = "[X]"
        self._populate_tree()

    def _happened_in_shell(self):
        return self.main_file_path is None or self.main_file_path == REPL_PSEUDO_FILENAME

    def _populate_tree(self):
        groups = {}

        for snap in self.snapshots:
            # warnings group
            if snap.get("warnings"):
                group = "Improvement suggestions"
                groups.setdefault(group, set())
                for w in snap["warnings"]:
                    groups[group].add((w["code"], w["msg"]))

        for group in sorted(groups.keys(), key=lambda x: x.replace("Improvement suggestions", "z")):
            group_id = self.tree.insert("", "end", open=True, tags=("group",))
            self.tree.set(group_id, "title", group)

            for code, title in sorted(groups[group], key=lambda m: m[1]):
                item_id = self.tree.insert("", "end")
                self.tree.set(item_id, "helpful", self._empty_box)
                self.tree.set(item_id, "confusing", self._empty_box)
                self.tree.set(item_id, "title", title)
                self.tree.set(item_id, "code", code)
                self.tree.set(item_id, "group", group)

        self.tree.see("")

    def _on_tree_click(self, event):
        item_id = self.tree.identify("item", event.x, event.y)
        column = self.tree.identify_column(event.x)

        if not item_id or not column:
            return

        value_index = int(column[1:]) - 1
        values = list(self.tree.item(item_id, "values"))

        if values[value_index] == self._empty_box:
            values[value_index] = self._checked_box
        elif values[value_index] == self._checked_box:
            values[value_index] = self._empty_box
        else:
            return

        # update values
        self.tree.item(item_id, values=tuple(values))

    def _preview_submission_data(self, event=None):
        import tempfile

        temp_path = os.path.join(
            tempfile.mkdtemp(dir=get_workbench().get_temp_dir()),
            "ThonnyEduLintFeedback_"
            + datetime.datetime.now().isoformat().replace(":", ".")[:19]
            + ".txt",
        )
        data = self._collect_submission_data()
        with open(temp_path, "w", encoding="ascii") as fp:
            fp.write(data)

        if running_on_mac_os():
            subprocess.Popen(["open", "-e", temp_path])
        else:
            import webbrowser

            webbrowser.open(temp_path)

    def _collect_submission_data(self):
        import json

        tree_data = []

        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            tree_data.append(
                {
                    "helpful": values[0] == self._checked_box,
                    "confusing": values[1] == self._checked_box,
                    "message": values[2],
                    "group": values[3],
                    "code": values[4],
                }
            )

        submission = {
            "feedback_format_version": 1,
            "thonny_version": thonny.get_version(),
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "message_feedback": tree_data,
            "comments": self.comments_text_frame.text.get("1.0", "end"),
        }

        try:
            import mypy.version

            submission["mypy_version"] = str(mypy.version.__version__)
        except ImportError:
            logger.exception("Could not get MyPy version")

        try:
            import pylint

            submission["pylint_version"] = str(pylint.__version__)
        except ImportError:
            logger.exception("Could not get Pylint version")

        try:
            import flake8
            submission["flake8_version"] = str(flake8.__version__)
        except ImportError:
            logger.exception("Could not get Flake8 version")

        try:
            import edulint
            submission["edulint_version"] = str(edulint.__version__)
        except ImportError:
            logger.exception("Could not get EduLint version")

        if self.include_snapshots_var.get():
            submission["snapshots"] = self.snapshots

        if self.include_thonny_id_var.get():
            submission["thonny_timestamp"] = get_workbench().get_option(
                "general.configuration_creation_timestamp"
            )

        return json.dumps(submission, indent=2)

    def _submit_data(self):
        import gzip
        import urllib.request

        json_data = self._collect_submission_data()
        compressed_data = gzip.compress(json_data.encode("ascii"))

        def do_work():
            try:
                handle = urllib.request.urlopen(
                    "https://edulint.com/store_feedback",
                    data=compressed_data,
                    timeout=10,
                )
                return handle.read()
            except Exception as e:
                return str(e)

        result = ui_utils.run_with_waiting_dialog(self, do_work, description="Uploading")
        if result == b"OK":
            if self.snapshots:
                last_timestamp = self.snapshots[-1]["timestamp"]
                _last_feedback_timestamps[self.main_file_path] = last_timestamp
            messagebox.showinfo(
                "Done!",
                "Thank you for the feedback!\n\nLet us know again when EduLint\nhelps or confuses you!",
                master=self.master,
            )
            self._close()
        else:
            messagebox.showerror(
                "Problem",
                "Something went wrong:\n%s\n\nIf you don't mind, then try again later!"
                % result[:1000],
                master=self,
            )

    def _select_unsent_snapshots(self, all_snapshots):
        if self.main_file_path not in _last_feedback_timestamps:
            return all_snapshots
        else:
            return [
                s
                for s in all_snapshots
                if s["timestamp"] > _last_feedback_timestamps[self.main_file_path]
            ]

    def _close(self, event=None):
        self.destroy()

    def _get_since_str(self):
        if not self.snapshots:
            assert self.main_file_path in _last_feedback_timestamps
            since = datetime.datetime.strptime(
                _last_feedback_timestamps[self.main_file_path], "%Y-%m-%dT%H:%M:%S"
            )
        else:
            since = datetime.datetime.strptime(self.snapshots[0]["timestamp"], "%Y-%m-%dT%H:%M:%S")

        if since.date() == datetime.date.today() or (
            datetime.datetime.now() - since
        ) <= datetime.timedelta(hours=5):
            since_str = since.strftime("%X")
        else:
            # date and time without yer
            since_str = since.strftime("%c").replace(str(datetime.date.today().year), "")

        # remove seconds
        if since_str.count(":") == 2:
            i = since_str.rfind(":")
            if (
                i > 0
                and len(since_str[i + 1 : i + 3]) == 2
                and since_str[i + 1 : i + 3].isnumeric()
            ):
                since_str = since_str[:i] + since_str[i + 3 :]

        return since_str.strip()
