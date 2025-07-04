"""
Script:         builder_interface.py
Author:         AutoForge Team

Description:
    Core abstract base class that defines a standardized interface for implementing a builder instance.
    Each builder implementation is registered at startup with a unique name, and can be invoked as needed based on the
    solution branch configuration, which specifies the registered name of the builder.
"""
import glob
import inspect
import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple, Union, Any, TYPE_CHECKING

# Third-party
from colorama import Fore, Style

# AutoForge imports
from auto_forge import (AutoForgeModuleType, ModuleInfoType, BuildProfileType, CoreContext,
                        CommandResultType, SDKType, VersionCompare)

# Lasy import SDK class instance
if TYPE_CHECKING:
    from auto_forge import SDKType

# Module identification
AUTO_FORGE_MODULE_NAME = "BuilderInterface"
AUTO_FORGE_MODULE_DESCRIPTION = "Dynamic loadable builder interface"


class BuilderArtifactsValidator:
    """
    Handles validation and resolution of build artifact descriptors.

    Each artifact descriptor must include:
        - 'name': Arbitrary identifier for the artifact group.
        - 'path': Absolute or relative path (can include wildcards).
        - Optional 'recursive': bool (default True for wildcards) — controls glob recursion.

    After validation, exposes a mapping of 'name' to a list of resolved file paths.
    """

    def __init__(self, artifact_list: list[dict]):
        self._artifact_list = artifact_list
        self._resolved: dict[str, list[Path]] = {}
        self._validate_and_resolve()

    def _validate_and_resolve(self):
        for i, artifact in enumerate(self._artifact_list):
            if not isinstance(artifact, dict):
                raise TypeError(f"Artifact entry at index {i} must be a dictionary.")

            name = artifact.get("name")
            path_str = artifact.get("path")
            recursive = artifact.get("recursive", True)
            copy_to_path = artifact.get("copy_to")

            if not name or not path_str:
                raise ValueError(f"Artifact entry {artifact} must include 'name' and 'path'.")

            path_obj = Path(path_str)

            if "*" in path_str or "?" in path_str or "[" in path_str:
                matched_files = [
                    Path(p).resolve() for p in glob.glob(path_str, recursive=recursive)
                ]
                if not matched_files:
                    raise FileNotFoundError(f"No files matched wildcard path: {path_str}")
                self._resolved[name] = matched_files
            else:
                resolved_file = path_obj.resolve()
                if not resolved_file.exists():
                    raise FileNotFoundError(f"Expected file not found: {resolved_file}")
                self._resolved[name] = [resolved_file]

            # If copy_to is specified, perform immediate copy
            if copy_to_path:
                self._copy_to(name, copy_to_path)

    def _copy_to(self, group_name: str, destination: str, preserve_structure: bool = True):
        """
        Copy all files from the specified group to the destination directory.
        Args:
            group_name (str): The artifact group name.
            destination (str): Destination directory path.
            preserve_structure (bool): If True, recreate folder structure from the
                                       common root down. If False, flatten all files.
        """
        if group_name not in self._resolved:
            raise KeyError(f"Group '{group_name}' not found in resolved artifacts.")

        files = self._resolved[group_name]
        if not files:
            raise ValueError(f"No files found in group '{group_name}'.")

        destination_path = Path(destination).resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        common_base_path: Optional[Path] = None

        if preserve_structure:
            try:
                # Extract common parent of all file *directories*
                common_base = os.path.commonpath([str(p.parent) for p in files])
                common_base_path = Path(common_base).resolve()
            except Exception as e:
                raise RuntimeError(f"Failed to compute common base path: {e}")
        for src in files:
            if preserve_structure:
                try:
                    relative_subpath = src.parent.relative_to(common_base_path)
                except ValueError:
                    raise ValueError(f"File {src} is not under common base path {common_base_path}")
                dest_dir = destination_path / relative_subpath
            else:
                dest_dir = destination_path

            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / src.name)

    def get_resolved_artifacts(self) -> dict[str, list[Path]]:
        """
        Returns:
            dict[str, list[Path]]: Mapping of artifact name to resolved file paths.
        """
        return self._resolved


class BuilderToolChain:
    """
    Tool chaim validation auxiliary cass.
    """

    def __init__(self, toolchain: dict[str, object], builder_instance: Optional["BuilderRunnerInterface"]) -> None:
        """
        Checks that the specified tool chin exists and that its different components,has the correct version.
        Args:
            toolchain (dict[str, object]): The toolchain to check.
            builder_instance (Optional[BuilderRunnerInterface]): The parent builder instance.

        """
        self._toolchain = toolchain
        self._resolved_tools: dict[str, str] = {}
        self._builder_instance = builder_instance
        self._registry = self._builder_instance.sdk.registry
        self._tool_box = self._builder_instance.sdk.tool_box

        if self._tool_box is None:
            raise RuntimeError("unable to instantiate dependent core module")

    def validate(self, show_help_on_error: bool = False) -> Optional[bool]:
        """
        Validates the toolchain structure and required tools specified by the solution.
        For each tool:
          - Attempts to resolve the binary using the defined path.
          - Confirms the version requirement is met.
          - Optionally shows help (Markdown-rendered) if validation fails.
        Args:
            show_help_on_error (bool): Show help message if validation fails.
        Return:
            bool: True if validation passes, otherwise an exception is raised.
        """
        required_keys = {"name", "platform", "architecture", "build_system", "required_tools"}
        missing = required_keys - self._toolchain.keys()
        if missing:
            raise ValueError(f"missing top-level toolchain keys: {missing}")

        tools = self._toolchain["required_tools"]
        if not isinstance(tools, dict) or not tools:
            raise ValueError("'required_tools' must be a non-empty dictionary")

        for name, definition in tools.items():
            if not isinstance(definition, dict):
                raise ValueError(f"Tool '{name}' definition must be a dictionary")

            tool_path = definition.get("path")
            version_expr = definition.get("version")
            help_path = definition.get("help")

            if not tool_path or not version_expr:
                raise ValueError(f"toolchain element '{tool_path}' must define 'path' and 'version' fields")

            resolved_t_tool_path = self._resolve_tool([tool_path], version_expr)
            if not resolved_t_tool_path:
                # If we have to auto show help
                if show_help_on_error:
                    if help_path:
                        if self._tool_box.show_help_file(help_path) != 0:
                            self._builder_instance.print_message(
                                message=f"Error displaying help file '{help_path}' see log for details",
                                log_level=logging.WARNING)
                # Break the build
                raise RuntimeError(f"missing toolchain component: {name}")

            self._resolved_tools[name] = resolved_t_tool_path

        return True

    def get_tool(self, tool_name: str) -> Optional[str]:
        """
        Returns the resolved absolute path of the specified tool name,
        or None if not found.
        """
        return self._resolved_tools.get(tool_name)

    def get_value(self, key_name: str) -> Optional[str]:
        """
        Returns the value of a top-level key in the toolchain dictionary,
        only if it is a string. Returns None otherwise.
        """
        value = self._toolchain.get(key_name)
        return value if isinstance(value, str) else None

    def _resolve_tool(self, candidates: list[str], version_expr: str) -> Optional[str]:
        """
        Attempts to locate a binary from the provided list of candidates that satisfies the required version expression.
        Args:
            candidates: A list of binary names or absolute paths to check.
            version_expr: A version requirement string (e.g., ">=3.2").
        Returns:
            The resolved binary path if found and version is valid, otherwise None.
        """
        for binary in candidates:
            path = binary if os.path.isabs(binary) else shutil.which(binary)

            if not path:
                self._builder_instance.print_message(message=f"Toolchain item '{binary}' not found.",
                                                     log_level=logging.ERROR)
                continue

            version_ok, detected_version = self._version_ok(path, version_expr)
            if not version_ok:
                base_name = os.path.basename(path)
                if detected_version:
                    msg = (f"Toolchain item '{base_name}' version {detected_version} "
                           f"does not satisfy required {version_expr}.")
                else:
                    msg = f"Toolchain item '{base_name}' version could not be determined."
                self._builder_instance.print_message(message=msg, log_level=logging.ERROR)
                continue
            return path
        return None

    @staticmethod
    def _version_ok(binary_path: str, version_expr: str) -> Optional[tuple[bool, Optional[str]]]:
        """
        Checks whether the binary at binary_path satisfies the version constraint (e.g., ">=10.0").
        Args:
            binary_path (str): Path to the binary.
            version_expr (str): Version constraint expression (e.g., ">=10.0", "==1.2.3").
        Returns:
            Tuple[bool, Optional[str]]: A tuple of (is_satisfied, detected_version_str).
        """
        try:
            # Run the binary with --version and capture output
            binary_output = subprocess.check_output(args=[binary_path, "--version"], stderr=subprocess.STDOUT,
                                                    text=True)

            compare_results = VersionCompare().compare(detected=binary_output, expected=version_expr)
            return compare_results

        except Exception as version_verify_error:
            raise version_verify_error from version_verify_error


class BuildLogAnalyzerInterface(ABC):
    """
    Abstract base class defining the interface for log analysis.
    Any specific log analyzer (e.g., GCC, Clang, Java) should
    inherit from this interface and implement the 'analyze' method.
    """

    def __init__(self):
        # Keep track of last analysis
        self._last_analysis: Optional[list[dict[str, Union[str, int, None, list[str]]]]] = None
        self._logger: Optional[logging.Logger] = None

    @abstractmethod
    def analyze(self, log_source: Union[Path, str], json_name: Optional[str] = None) -> Optional[list[dict[str, Any]]]:
        """
        Analyzes a log source, which can be a file path or a string,
        and extracts structured information.
        Args:
            log_source: The source of the log data, either a Path object
                        to a log file or a string containing the log content.
            json_name: Optional JSON export file path.
        Returns:
            A list of dictionaries, where each dictionary represents a parsed entry,
            or None if no relevant entries are found.
        """
        raise NotImplementedError("Subclasses must implement the 'analyze' method.")


class BuilderRunnerInterface(ABC):
    """
    Abstract base class for builder instances that can be dynamically registered and executed by AutoForge.
    """

    def __init__(self, build_system: Optional[str] = None, build_label: Optional[str] = None):
        """
        Initializes the builder and registers it with the AutoForge registry.

        Args:
            build_system (str, optional): The unique name of the builder instance build system to use, for ex.
                make, cmake and so on. If not provided, the value of the
                class field 'AUTO_FORGE_MODULE_NAME' will be used.
            build_label (str, optional): The unique name of the builder instance build label to use.
        """

        self._registry = self.sdk.registry
        self._build_context_file: Optional[Path] = None
        self.build_logs_path: Optional[Path] = None

        # Probe caller globals for command description and name
        caller_frame = inspect.stack()[1].frame
        caller_globals = caller_frame.f_globals
        caller_module_name = caller_globals.get("AUTO_FORGE_MODULE_NAME", None)
        caller_module_description = caller_globals.get("AUTO_FORGE_MODULE_DESCRIPTION", "Description not provided")
        caller_module_version = caller_globals.get("AUTO_FORGE_MODULE_VERSION", "0.0.0")

        self._build_system: str = build_system if build_system is not None else caller_module_name
        if self._build_system is None:
            raise RuntimeError("build_system properties cannot be None")

        # Set optional build label
        self._build_label: str = build_label if build_label is not None else "AutoForge"

        # Register this builder instance in the global registry for centralized access
        self._module_info: ModuleInfoType = (
            self._registry.register_module(name=self._build_system, description=caller_module_description,
                                           version=caller_module_version,
                                           auto_forge_module_type=AutoForgeModuleType.BUILDER))

        # Get configuration from the root auto_forge class through context provider
        self._configuration = CoreContext.get_config_provider().configuration
        self._core_logger = self.sdk.logger
        self._logger = self.sdk.logger.get_logger(name=self._build_system.capitalize())
        self._tool_box = self.sdk.tool_box

        # Dependencies check
        if None in (self._logger, self._tool_box):
            raise RuntimeError("unable to instantiate dependent core")

        try:
            # Create the logs path if fits missing
            self.build_logs_path = self._tool_box.get_valid_path(self.sdk.variables.get("BUILD_LOGS"),
                                                                 create_if_missing=False)
            context_file: str = self._configuration.get("build_context_file", "build_context.json")
            self._build_context_file = self.build_logs_path / context_file
            self._build_context_file.unlink(missing_ok=True)

        except Exception as path_prep_error:
            raise RuntimeError(f"failed to prepare build paths {path_prep_error}")

    @abstractmethod
    def build(self, build_profile: BuildProfileType) -> Optional[int]:
        """
        Validates the provided build configuration and executes the corresponding build flow.
        Args:
            build_profile (BuildProfileType): The build profile containing solution, project, configuration,
                and toolchain information required for the build process.
        Returns:
            Optional[int]: The return code from the build process, or None if not applicable.
        """
        raise NotImplementedError("must implement 'build'")

    def get_info(self) -> ModuleInfoType:
        """
        Retrievers information about the implemented builder.
        Note: Implementation class must call _set_info().
        Returns:
            ModuleInfoType: a named tuple containing the implemented command id
        """
        if self._module_info is None:
            raise RuntimeError('command info not initialized, make sure call set_info() first')

        return self._module_info

    def print_build_results(self, results: Optional[CommandResultType], raise_exception: bool = True) -> Optional[int]:
        """
        Handle and report the result of a build command.
        Args:
            results: The command result object containing return code and optional response.
            raise_exception: Whether to raise an exception if the build failed.
        Returns:
            The return code if results are provided; otherwise, None.
        """
        if results is None:
            return 1  # Error

        if results.return_code != 0:
            self.print_message(message=f"Build failed with error code: {results.return_code}", log_level=logging.ERROR)
            if results.response:
                self.print_message(message=f"Build response: {results.response}", log_level=logging.ERROR)

            if raise_exception:
                raise RuntimeError(f"Build failed with return code: {results.return_code}")

        return results.return_code

    def analyze_so_exports(self, path: str, nm_tool_name: str = "nm", max_libs: int = 50) -> dict[str, list[str]]:
        """
        Analyze exported symbols from .so files in the given directory.
        Args:
            path (str): Root path to search.
            nm_tool_name (str): Tool to extract symbols ('nm', 'readelf', etc.).
            max_libs (int): Maximum number of .so files to process.
        Returns:
            Dict[str, List[str]]: Mapping from .so file path to list of exported function names.
        """
        so_exports = {}
        seen_symbols = defaultdict(list)
        processed = 0

        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".so"):
                    full_path = os.path.join(root, file)
                    try:
                        result = subprocess.run(
                            [nm_tool_name, '-D', '--defined-only', full_path],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            text=True,
                            check=True,
                        )
                        symbols = []
                        for line in result.stdout.splitlines():
                            parts = line.strip().split()
                            if len(parts) >= 3 and parts[-2] in ('T', 't'):  # 'T' = text (function)
                                symbol = parts[-1]
                                symbols.append(symbol)
                                seen_symbols[symbol].append(full_path)

                        so_exports[full_path] = symbols
                        processed += 1
                        if processed >= max_libs:
                            break
                    except subprocess.CalledProcessError:
                        self.print_message(message=f"Warning: Failed to analyze {full_path}", log_level=logging.WARNING)
            if processed >= max_libs:
                break

        # Conflict report
        conflicts = {sym: paths for sym, paths in seen_symbols.items() if len(paths) > 1}
        if conflicts:
            for sym, libs in conflicts.items():
                self.print_message(message=f"Symbol '{sym}' found in:")
                for lib in libs:
                    self.print_message(message=f"  - {lib}", bare_text=True)
        else:
            self.print_message(message=f"No duplicate symbols found across {processed} libraries.",
                               log_level=logging.INFO)

        return so_exports

    def print_message(self, message: str, bare_text: bool = False, log_level: Optional[int] = logging.DEBUG) -> None:
        """
        Prints a build-time message prefixed with an AutoForge label.
        Args:
            message (str): The text to print.
            bare_text (bool, optional): If True, prints without ANSI color formatting.
            log_level (int, optional): Logging level to use (e.g., logging.INFO).
                                       If None, the message is not logged.
        """
        if not bare_text:
            # Map log levels to distinct label colors
            level_color_map = {logging.CRITICAL: Fore.LIGHTRED_EX, logging.ERROR: Fore.RED,
                               logging.WARNING: Fore.YELLOW, logging.INFO: Fore.CYAN,
                               logging.DEBUG: Fore.LIGHTGREEN_EX, }
            color = level_color_map.get(log_level, Fore.WHITE)
            leading_text = f"{color}-- {self._build_label}:{Style.RESET_ALL} "

        else:
            leading_text = f"-- {self._build_label}: "
            message = self._tool_box.strip_ansi(text=message, bare_text=True)

        # Optionally log the message
        if log_level is not None:
            self._logger.log(log_level, message)

        print(leading_text + message)

    def update_info(self, command_info: ModuleInfoType):
        """
        Updates information about the implemented builder.
        """
        self._module_info = command_info

    @property
    def sdk(self) -> SDKType:
        """
        Returns the global SDK singleton instance, which holds references
        to all registered core module instances.
        This property provides convenient access to the centralized SDKType
        container, after all core modules have registered themselves during
        initialization.
        """
        return SDKType.get_instance()
