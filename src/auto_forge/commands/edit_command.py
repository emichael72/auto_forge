"""
Module: edit_command.py
Author: AutoForge Team

Description:
    Provides functionality for launching text editors to open files or directories
Features:
    - Editor discovery and listing.
    - Wildcard and numeric selection of editor.
    - Safe invocation of terminal and GUI editors.
    - Automatic trust registration for Visual Studio Code workspace.
"""

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import threading
from contextlib import suppress
from nturl2path import pathname2url
from pathlib import Path
from typing import Optional, Any, Iterable

from rich import box
from rich.console import Console
from rich.table import Table

# AutoForge imports
from auto_forge import (CommandInterface)

AUTO_FORGE_MODULE_NAME = "edit"
AUTO_FORGE_MODULE_DESCRIPTION = "Invokes the preferred editor to open files or directories"
AUTO_FORGE_MODULE_VERSION = "1.0"


class EditCommand(CommandInterface):
    """
    Implements a command cross-platform command similar to Windows 'start'.
    """

    def __init__(self, **_kwargs: Any):
        """
        Initializes the EditCommand class.
        Args:
            **_kwargs (Any): Optional keyword arguments, such as:
        """

        self._detected_editors: Optional[list[dict[str, Any]]] = []
        self._selected_editor_index: Optional[int] = None
        self._max_fallback_search_paths: int = 10

        # Base class initialization
        super().__init__(command_name=AUTO_FORGE_MODULE_NAME, hidden=True)

    def initialize(self, **_kwargs: Any) -> bool:
        """
        Command specific initialization, will be executed lastly by the interface class after all other initializers.
        """
        # Add few WSL specific variables to the project environment
        self._inject_wsl_environment()

        # Detect installed editors
        if self._configuration is None:
            raise RuntimeError("Package configuration was missing during initialization")

        searched_editors_data = self._configuration.get("searched_editors", [])
        fallback_search_path = self._configuration.get("editors_fallback_search_paths", [])

        # Clean bad or missing paths
        fallback_search_path = self._purify_paths(paths=fallback_search_path,
                                                  max_items=self._max_fallback_search_paths)

        if not len(searched_editors_data):
            self._logger.warning(
                "Missing 'searched_editors' list in configuration — editor detection feature disabled.")
            return True

        # Scan the system for known editors in a background thread.
        # This prevents UI or CLI slowdown during potentially slow filesystem operations.
        self._logger.debug(f"Searching for {len(searched_editors_data)} specified editors")
        threading.Thread(
            target=self._detect_installed_editors_thread,
            args=(searched_editors_data, fallback_search_path, 0),
            name="EditorScanThread",
            daemon=True
        ).start()

        return True

    def _inject_wsl_environment(self) -> None:
        """
        Injects relevant WSL environment variables into the package runtime,
        such as the user's home path and the Windows C: drive mount path.
        """
        wsl_home = self.sdk.system_info.wsl_home
        if isinstance(wsl_home, str):
            # noinspection SpellCheckingInspection
            self.sdk.variables.add(key='WSL_HOMEPATH', value=wsl_home, is_path=True, path_must_exist=True,
                                   description='WSL user home path')

        wsl_c_mount = self.sdk.system_info.wsl_c_mount
        if isinstance(wsl_c_mount, str):
            # noinspection SpellCheckingInspection
            self.sdk.variables.add(key='WSL_C_MOUNT', value=wsl_c_mount, is_path=True, path_must_exist=True,
                                   description='WSL C mount path')

    def _search_in_fallback_dirs(self, aliases: list, fallback_search_path: list, max_depth: int) -> Optional[str]:
        """
        Search for an executable matching one of the aliases inside fallback search paths.
        - Optional WSL-specific search path entries (skipped if not in WSL or not targeting .exe).
        - Automatic appending of `.exe` for Windows paths when missing.
        - Case-insensitive match for Windows (.exe) paths.
        - Use of os.scandir() for efficient shallow scans (max_depth == 0).
        - Variable expansion via self._variables.expand(key=...).
        Args:
            aliases (list): List of potential executable names.
            fallback_search_path (list): List of dicts with "path" and optional "wsl_path".
            max_depth (int): How deep to search sub-directories (0 = top level only).

        Returns:
            str | None: Absolute path of the first found executable, or None.
        """
        is_windows_target = any(alias.lower().endswith(".exe") for alias in aliases)
        search_dirs = []

        for entry in fallback_search_path:
            raw_path = entry.get("path")
            is_wsl_path = entry.get("wsl_path", False)
            if not raw_path:
                continue

            # Expand variables and normalize slashes
            path = self.sdk.variables.expand(key=raw_path, quiet=True).replace("\\", "/").rstrip("/")

            # Skip Windows paths if we're not in WSL or not targeting .exe
            if is_wsl_path and (not self.sdk.system_info.is_wsl or not is_windows_target):
                continue

            if os.path.isdir(path):
                search_dirs.append((path, is_wsl_path))

        for root, is_windows_path in search_dirs:
            # Adjust candidate names: append .exe if needed for WSL paths
            candidate_names = [
                alias if not (is_windows_path and not alias.lower().endswith(".exe"))
                else alias + ".exe"
                for alias in aliases
            ]
            candidate_names_lc = [name.lower() for name in candidate_names] if is_windows_path else None

            if max_depth <= 0:
                try:
                    for entry in os.scandir(root):
                        if not entry.is_file():
                            continue
                        name = entry.name
                        if is_windows_path:
                            if name.lower() in candidate_names_lc and os.access(entry.path, os.X_OK):
                                return entry.path
                        else:
                            if name in candidate_names and os.access(entry.path, os.X_OK):
                                return entry.path
                except PermissionError:
                    continue

            else:
                for dirpath, _, filenames in os.walk(root):
                    depth = dirpath[len(root):].count(os.sep)
                    if depth >= max_depth:
                        continue

                    if is_windows_path:
                        filenames_lc = {f.lower() for f in filenames}
                        for name_lc in candidate_names_lc:
                            if name_lc in filenames_lc:
                                match_name = next(f for f in filenames if f.lower() == name_lc)
                                full_path = os.path.join(dirpath, match_name)
                                if os.access(full_path, os.X_OK):
                                    return str(full_path)
                    else:
                        for name in candidate_names:
                            if name in filenames:
                                full_path = os.path.join(dirpath, name)
                                if os.access(full_path, os.X_OK):
                                    return str(full_path)

        return None

    def _detect_installed_editors_thread(self, editors: list, fallback_search_path: list, max_depth: int = 3) -> None:
        """
        Detects which editors from the given list are available on the system.
        Args:
            editors (list): List of editor descriptors, each containing 'name', 'type', and 'aliases'.
            fallback_search_path (list): Paths to use for fallback recursive search.
            max_depth (int): Maximum recursion depth for fallback search.
        Returns:
            List[dict]: A list of detected editors with name, type, and absolute path.
        """
        detected = []

        for editor in editors:
            aliases = editor.get("aliases", [])
            editor_name = editor.get("name")
            editor_type = editor.get("type")
            editor_args = editor.get("args")

            found_path: Optional[str] = None

            # Try PATH-based search
            for alias in aliases:
                path = shutil.which(alias)
                if path and not path.startswith("/mnt/"):
                    found_path = str(path)
                    break

            # Fallback directory scan
            if not found_path:
                found_path = self._search_in_fallback_dirs(
                    aliases=aliases,
                    fallback_search_path=fallback_search_path,
                    max_depth=max_depth
                )

            if found_path:
                detected.append({
                    "name": editor_name,
                    "type": editor_type,
                    "path": str(found_path),
                    "args": editor_args,
                })

        self._detected_editors = detected
        self._logger.debug(f"Found {len(self._detected_editors)} editors, use 'edit -l' to list them")

    def _print_detected_editors(self, editor_index: Optional[int] = None) -> None:
        """
        Pretty-prints the detected editors using a Rich table.
        Uses self._detected_editors, which should be a list of dicts
        containing 'name', 'type', and 'path'.
        Args:
            editor_index (Optional[int]): Index of selected editor (0-based).
        """
        console = Console(force_terminal=True)

        if not len(self._detected_editors):
            console.print("[bold red]No editors detected.[/bold red]")
            return None

        # Invalidate editor_index if we can't use it
        if not isinstance(editor_index, int) or (editor_index > len(self._detected_editors)):
            editor_index = None

        table = Table(title="Detected Editors", box=box.ROUNDED)

        table.add_column("#", style="bold yellow", justify="right", width=4)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta", justify="center")
        table.add_column("Path", style="white", overflow="fold")

        for idx, editor in enumerate(self._detected_editors, start=1):
            is_selected = (editor_index is not None and editor_index == idx - 1)
            ordinal = f"[bold cyan]* {idx}[/bold cyan]" if is_selected else str(idx)
            name = str(editor.get("name", "-"))
            typ = str(editor.get("type", "-"))
            path = str(editor.get("path", "-"))

            table.add_row(ordinal, name, typ, path)

        console.print('\n', table, '\n')
        return None

    def _resolve_editor_identifier(self, editor_identifier: Optional[str] = None) -> Optional[int]:
        """
        Resolves the index of the selected editor based on an identifier.
        The identifier may be:
            - None: defaults to the first detected editor.
            - A digit (e.g., "2"): interpreted as a 1-based index.
            - A wildcard string (e.g., "*code*"): matched case-insensitively against editor names.
        Returns:
            int: The index of the resolved editor in self._detected_editors.
            None: If no editors are detected.
        """
        self._logger.debug(f"Resolving editor using '{editor_identifier}'")

        if not self._detected_editors:
            self._logger.warning("No editors detected.")
            return None

        # Numeric selection (1-based index)
        if editor_identifier and editor_identifier.isdigit():
            idx = int(editor_identifier) - 1
            if 0 <= idx < len(self._detected_editors):
                return idx
            self._logger.warning(f"Editor index '{editor_identifier}' is out of range, falling back to default.")
            return 0

        # Wildcard + case-insensitive name match
        elif isinstance(editor_identifier, str):
            pattern = editor_identifier.lower()
            for idx, editor in enumerate(self._detected_editors):
                name = editor.get("name", "").lower()
                if fnmatch.fnmatch(name, pattern):
                    return idx

            self._logger.warning(f"Editor was not resolved using '{editor_identifier}', falling back to default.")
            return 0

        # Fallback to default
        return None

    def _purify_paths(self, paths: Iterable[dict[str, Any]], max_items: Optional[int] = None) -> list[dict[str, Any]]:
        """
        Filters and normalizes a list of dictionaries containing file or directory paths.
        For each dictionary that has a 'path' key:
          - Expands the path to an absolute path.
          - Validates that the path exists.
          - If valid, includes the updated dictionary in the result.
          - If missing or invalid, the item is excluded.
        Args:
            paths: Iterable of dictionaries. Each dict may contain a 'path' key.
            max_items: Maximum number of items to allow in the returned list.
        Returns:
            A new list of dictionaries where 'path' values are absolute and exist on disk.
        """
        purified = []
        for entry in paths:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if isinstance(path, str):
                abs_path = self.sdk.variables.expand(key=path, quiet=True)
                if os.path.exists(abs_path):
                    new_entry = dict(entry)  # shallow copy
                    new_entry["path"] = abs_path
                    purified.append(new_entry)

        # Truncate the list of specified
        if isinstance(max_items, int) and len(purified) > max_items:
            purified[:] = purified[:purified]

        return purified

    def _vscode_trust_workspace_path(self, path: str):
        """
        Best-effort method to mark a workspace as trusted in Visual Studio Code,
        suppressing the "Restricted Mode" popup, accepts either a file path or a directory path.

        Note: On WSL, it automatically finds the Windows-side trust file.
        On native Linux, it uses the standard config path.
        """
        with suppress(Exception):
            abs_path = os.path.abspath(path)
            trusted_path = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
            folder_uri = "file://" + pathname2url(trusted_path)

            # Detect WSL environment
            is_wsl = self.sdk.system_info.is_wsl

            if is_wsl:
                # noinspection SpellCheckingInspection
                user = (
                        os.environ.get("WINUSER")
                        or os.environ.get("USERNAME")
                        or os.environ.get("USER")
                )
                config_path = f"/mnt/c/Users/{user}/AppData/Roaming/Code/User/workspaceTrustState.json"
                if not os.path.exists(config_path):
                    # Try VS Code Insiders
                    config_path = f"/mnt/c/Users/{user}/AppData/Roaming/Code - Insiders/User/workspaceTrustState.json"
            else:
                config_path = os.path.expanduser("~/.config/Code/User/workspaceTrustState.json")

            # Load or initialize trust data
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    trust_data = json.load(f)
            else:
                trust_data = {"trustedFolders": [], "trustedFiles": []}

            trusted = trust_data.setdefault("trustedFolders", [])
            if folder_uri not in trusted:
                trusted.append(folder_uri)
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(trust_data, f, indent=4)

    def _summarize_error_context(self) -> Optional[list[tuple[str, int]]]:
        """
        If there is an error context file left by a log analyzer after a build operation,
        open it and extract (file_path, line_number) tuples for unique files only,
        so we can allow opening the default editor once per file at its first error.

        Returns:
            A list of unique (file_path, line_number) tuples, or None if no errors were found.
        """

        build_logs_path = self._tool_box.get_valid_path(self.sdk.variables.get("BUILD_LOGS"))
        context_path: Optional[str] = self._configuration.get("build_error_context_file")

        if not build_logs_path or not context_path:
            return None

        context_file = build_logs_path / context_path
        if not context_file.is_file():
            return None

        try:
            with context_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._logger.warning(f"Failed to load error context file: {e}")
            return None

        events = data.get("events", [])
        if not isinstance(events, list):
            return None

        seen_files = {}
        for event in reversed(events):
            file = event.get("file")
            line = event.get("line")
            if isinstance(file, str) and isinstance(line, int) and file not in seen_files:
                seen_files[file] = line

        if not seen_files:
            return None

        return list(seen_files.items())

    def _edit_file(self, path: str, editor_index: Optional[int] = None) -> Optional[int]:
        """
        Launch the selected editor to open a file or directory.
        Args:
            path (str): The target file or directory to open.
            editor_index (int): The index of the editor to use.
                - A number (e.g., "2"): treated as 1-based index into self._detected_editors.
                - A wildcard string (e.g., "*code*"): matched case-insensitively against editor names.
        Returns:
            Execution return code.
        """
        if not len(self._detected_editors):
            raise RuntimeError("no editors detected")

        if not isinstance(editor_index, int) or (editor_index > len(self._detected_editors)):
            raise RuntimeError("invalid editor index specified, run 'edit -l' to list available editors")

        path = self.sdk.variables.expand(key=path, quiet=True)
        if os.path.basename(path) == path:
            # Note: When it's just a base name (e.g., "foo.txt"), prepend current working directory
            path = os.path.abspath(os.path.join(os.getcwd(), path))

        if not os.path.exists(path):
            raise FileNotFoundError(f"path does not exist: {path}")

        selected_editor = self._detected_editors[editor_index]
        editor_path = selected_editor.get("path")
        editor_type = selected_editor.get("type", "terminal")
        editor_args = selected_editor.get("args")

        if os.path.isdir(path):
            if editor_type != "gui":
                raise RuntimeError(f"cannot open directory with terminal editor: '{path}'")
        try:
            # VSCode specific: automatically add the path to the trusted paths
            self._vscode_trust_workspace_path(path)

            self._logger.debug(f"Opening '{path}' in '{editor_path} {editor_args}'")
            if selected_editor.get("type") == "terminal":
                results = subprocess.run([editor_path, *editor_args, os.path.abspath(path)])
            else:
                results = subprocess.Popen(
                    [editor_path, *editor_args, os.path.abspath(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True
                )
            return results.returncode

        except Exception as execution_error:
            raise execution_error from execution_error

    def _edit_error_context_summary(self, editor_index: Optional[int] = 0) -> bool:
        """
        Open all files and lines reported in the last analyzed error context using the selected editor.
        If the editor supports line numbers, they'll be passed as arguments.
        Args:
            editor_index (Optional[int]): Index of editor to use (default is first editor).

        Returns:
            True if at least one file was successfully opened, False otherwise.
        """
        error_context_summary: Optional[list[tuple[str, int]]] = self._summarize_error_context()
        if not isinstance(error_context_summary, list):
            print("No analyzed 🪲 error context data found or failed to load.")
            return False

        if not self._detected_editors:
            raise RuntimeError("No editors detected")

        if not isinstance(editor_index, int) or editor_index >= len(self._detected_editors):
            raise RuntimeError("Invalid editor index specified; use 'edit -l' to list editors")

        selected_editor = self._detected_editors[editor_index]
        editor_path = selected_editor.get("path")
        editor_args = selected_editor.get("args", [])
        editor_name = selected_editor.get("name", "").lower()

        opened_any = False

        for file_path, line in error_context_summary:
            full_path = self.sdk.variables.expand(key=file_path, quiet=True)

            if not os.path.isfile(full_path):
                self._logger.warning(f"Skipping missing file: {full_path}")
                continue

            args = [editor_path] + editor_args
            abs_path = os.path.abspath(full_path)

            # Add line number argument if editor supports it
            # noinspection SpellCheckingInspection
            if editor_name in ("vscode", "code"):
                args += [f"--goto", f"{abs_path}:{line}"]
            elif editor_name in ("sublime_text", "subl", "sublime"):
                args += [f"{abs_path}:{line}"]
            elif editor_name in ("gedit", "pluma", "xed", "mousepad", "kate", "notepad++"):
                args += [f"+{line}", abs_path]
            elif editor_name in ("vim", "vi", "nano", "micro", "emacs"):
                args += [f"+{line}", abs_path]
            else:
                args += [abs_path]  # fallback, no line support

            try:
                self._logger.debug(f"Opening file: {file_path}:{line}")
                subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True
                )
                opened_any = True
            except Exception as e:
                self._logger.warning(f"Failed to open {full_path}: {e}")

        return opened_any

    def _refresh_identifier(self, editor_identifier: Optional[str] = None):
        """
        Resolve the editor identifier (from arguments or config) to an index in the detected editors list
        and update class locals.
        """

        if self._selected_editor_index is None:
            if editor_identifier is not None:
                self._selected_editor_index = self._resolve_editor_identifier(editor_identifier)
            else:
                # Get the identifier from the solution
                editor_identifier = self.sdk.solution.get_arbitrary_item(key="default_editor")
                if isinstance(editor_identifier, str):
                    self._selected_editor_index = self._resolve_editor_identifier(editor_identifier)

    def get_editor_path(self) -> Optional[Path]:
        """
        Gets the currently selected editor as a Path object, if valid.
        Returns:
            Path: Path to the selected editor, or None if not set or invalid.
        """
        self._refresh_identifier()

        if (
                not self._detected_editors
                or not isinstance(self._selected_editor_index, int)
                or self._selected_editor_index < 0
                or self._selected_editor_index >= len(self._detected_editors)
        ):
            return None

        editor_data = self._detected_editors[self._selected_editor_index]
        editor_path_str = editor_data.get("path")

        if not editor_path_str:
            return None

        editor_path = Path(editor_path_str)
        return editor_path if editor_path.is_file() else None

    def create_parser(self, parser: argparse.ArgumentParser) -> None:
        """
        Adds command-line arguments.
        Args:
            parser (argparse.ArgumentParser): The argument parser to extend.
        """
        parser.add_argument("-p", "--path", type=str, help="File name or path to open")
        parser.add_argument("-l", "--list-editors", action="store_true", help="Show the list of detected editors")
        parser.add_argument("-id", "--editor-identifier", type=str,
                            help="Editor identifying text, could be index or string")

        parser.add_argument(
            "-e", "--error-context",
            action="store_true",
            help="Open all files listed in the most recent error context summary"
        )

    def run(self, args: argparse.Namespace) -> int:
        """
        Executes 'edit' command based on parsed arguments.
        Args:
            args (argparse.Namespace): Parsed command-line arguments.
        Returns:
            int: 0 on success, non-zero on failure.
        """

        return_code = 0

        # Refresh class locals based on specified identifier 
        self._refresh_identifier(args.editor_identifier)

        # Handle arguments
        if args.path is not None:
            # Execute the selected editor to edit a specified file
            return_code = self._edit_file(path=args.path, editor_index=self._selected_editor_index)

        elif args.error_context:
            # Open all files listed in the most recent error context summary
            return_code = self._edit_error_context_summary(editor_index=self._selected_editor_index)

        elif args.list_editors:
            # List all detected editors.
            self._print_detected_editors(editor_index=self._selected_editor_index)

        elif args.editor_identifier is not None:
            # Set the session editor
            editor_index = self._resolve_editor_identifier(args.editor_identifier)
            if editor_index is not None:
                self._selected_editor_index = editor_index
                print(f"Editor index changed to '{editor_index + 1}'\n")
            else:
                raise RuntimeError(f"Could not set editor index for '{args.editor_identifier}'")

        else:
            # Error: no arguments
            return_code = CommandInterface.COMMAND_ERROR_NO_ARGUMENTS

        return return_code
