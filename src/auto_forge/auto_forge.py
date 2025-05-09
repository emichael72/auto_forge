#!/usr/bin/env python3
"""
Script:         auto_forge.py
Author:         AutoForge Team

Description:
    This module serves as the core of the AutoForge system.
    Here we initialize all core libraries, parse and load the various configuration files,
    dynamically load CLI commands and start the build system shell.
"""

import argparse
import builtins
import contextlib
import io
import logging
import os
import sys
from typing import Optional

# Colorama
from colorama import Fore, Style

# Internal AutoForge imports
from auto_forge import (ToolBox, CoreModuleInterface, CoreProcessor, CoreVariables, CoreGUI,
                        CoreSolution, CoreEnvironment, CoreLoader, CorePrompt, Registry, AutoLogger,
                        AddressInfoType, LogHandlersTypes, TerminalAnsiCodes,
                        ExceptionGuru, PROJECT_VERSION, PROJECT_NAME, PROJECT_COMMANDS_PATH)


class AutoForge(CoreModuleInterface):
    """
    This module serves as the core of the AutoForge system, initialized ising the basd 'CoreModuleInterface' which
    ensures a singleton pattern.
    """

    def __init__(self, *args, **kwargs):
        """
        Extra initialization required for assigning runtime values to attributes declared earlier in `__init__()`
        See 'CoreModuleInterface' usage.
        """
        self._solution: Optional[CoreSolution] = None
        self._solution_file: Optional[str] = None
        self._solution_name: Optional[str] = None
        self._variables: Optional[CoreVariables] = None
        self._gui: Optional[CoreGUI] = None
        self._prompt: Optional[CorePrompt] = None

        # Startup argumnets
        self._automated_mode: bool = False
        self._workspace_path: Optional[str] = None
        self._automation_macro: Optional[str] = None
        self._solution_package_path: Optional[str] = None
        self._solution_package_file: Optional[str] = None
        self._solution_url: Optional[str] = None
        self._git_token: Optional[str] = None
        self._remote_debugging: Optional[AddressInfoType] = None
        self._proxy_server: Optional[AddressInfoType] = None
        self._create_workspace: bool = False

        # Save the original print
        self._original_print = builtins.print
        self._original_write = sys.stdout.write

        super().__init__(*args, **kwargs)

    def _initialize(self, *args, **kwargs) -> None:
        """
        Initialize the AutoForge core system and prepare the workspace environment.
        Depending on the context, this may involve:
        - Creating a new workspace, or loading an existing one.
        - Load the solution file from either a local path, local file or a git URL.
        - Run in non-interactive (automation) mode and execute automation macro.
        Args:
            kwargs: Arguments passed from the command line, validated and analyzed internally.
        """

        # Pass all received arguments down to _validate_arguments
        self._validate_arguments(*args, **kwargs)

        # Start remote debugging ASAP if enabled.
        if self._remote_debugging is not None:
            self._attach_debugger(host=self._remote_debugging.host, port=self._remote_debugging.port)

        # Initializes the logger
        self._auto_logger: AutoLogger = AutoLogger(log_level=logging.DEBUG)
        self._auto_logger.set_log_file_name("auto_forge.log")
        self._auto_logger.set_handlers(LogHandlersTypes.FILE_HANDLER | LogHandlersTypes.CONSOLE_HANDLER)
        self._logger: logging.Logger = self._auto_logger.get_logger(output_console_state=self._automated_mode)

        self._logger.debug(f"Workspace path: {self._workspace_path}")

        # Initialize core modules, registry must come first.
        self._registry: Registry = Registry()
        self._toolbox: Optional[ToolBox] = ToolBox()
        self._processor: Optional[CoreProcessor] = CoreProcessor()

        # Load all the builtin commands
        self._loader: Optional[CoreLoader] = CoreLoader()
        self._loader.probe(path=PROJECT_COMMANDS_PATH)
        self._environment: CoreEnvironment = CoreEnvironment(workspace_path=self._workspace_path,
                                                             automated_mode=self._automated_mode)

    def _validate_arguments(self, *_args, **kwargs) -> None:
        """
        Validate command-line arguments and set the AutoForge session execution mode.
        Depending on the inputs, AutoForge will either:
        - Start an interactive user shell, or
        - Enter automated mode and execute the provided automation script.
        - Any validation error will immediately raise an exception and consequently terminate AutoForge.
        Args:
            kwargs: Arguments passed from the command line, validated and analyzed internally.
        Note:
            The logger is likely not yet initialized at this stage, so all errors must be raised directly
            (no logging or print statements should be used here).
        """

        # Get all argumnets from kwargs
        self._workspace_path = kwargs.get("workspace_path")
        self._automation_macro = kwargs.get("automation_macro")
        self._solution_url = kwargs.get("solution_url")
        self._git_token = kwargs.get("git_token")
        self._create_workspace = kwargs.get("create_workspace", False)
        solution_package = kwargs.get("solution_package")
        remote_debugging: Optional[str] = kwargs.get("remote_debugging")
        proxy_server: Optional[str] = kwargs.get("proxy_server")

        # Defensive check: workspace_path should always be set since it is marked as 'required' in argparse.
        # This condition should never occur under normal usage.
        if self._workspace_path is None:
            raise ValueError("Workspace path must be provided.")

        # Expand paths and variables
        self._workspace_path = ToolBox.get_expanded_path(self._workspace_path)
        if self._automation_macro is not None:
            self._automation_macro = ToolBox.get_expanded_path(self._automation_macro)

        if not ToolBox.looks_like_unix_path(self._workspace_path):
            raise ValueError(f"The specified path '{self._workspace_path}' does not look like a valid Unix path.")

        # Workspace creation behavior:
        # - If the workspace path does not exist and creation is enabled (default), AutoForge will create it
        #   based on the solution package instructions.
        # - If the workspace exists and creation is disabled, AutoForge will load the existing workspace.
        # - If the workspace does not exist and creation is disabled, an exception will be raised.

        if not self._create_workspace and not os.path.exists(self._workspace_path):
            raise RuntimeError(f"Workspace path '{self._workspace_path}' does not exist and creation is disabled.")

        # If we ware requested to create a workspace, the destination path must be empty
        if (self._create_workspace
                and os.path.exists(self._workspace_path)
                and not ToolBox.is_directory_empty(self._workspace_path)):
            raise RuntimeError(f"Path '{self._workspace_path}' is not empty while workspace creation is enabled.")

        # Solution package validation:
        # AutoForge allows flexible input for the 'solution_package' argument:
        # - The user can specify a path to a solution archive (.zip file), or
        # - A path to an existing directory containing the solution files.
        # - A Github URL pointing to git path which contains the solution files.
        # Validation ensures that the provided path exists and matches one of the accepted formats.

        if solution_package is not None:

            if ToolBox.is_url(solution_package):
                self._solution_url = solution_package
            else:
                # Path expansion
                solution_package = ToolBox.get_expanded_path(solution_package)

                if ToolBox.looks_like_unix_path(solution_package):
                    # Looks like a UNIX path?
                    if os.path.isdir(solution_package):
                        # It's a valid directory
                        self._solution_package_path = solution_package
                        self._solution_package_file = None

                    elif os.path.isfile(solution_package) and solution_package.lower().endswith(".zip"):
                        # An exiting file with .zip extension
                        self._solution_package_file = solution_package
                        self._solution_package_path = None
                    else:
                        raise ValueError(f"Package '{solution_package}' must be an existing directory or a .zip file.")
                else:
                    # Doesn't look like a UNIX path — treat it as a possible file
                    if os.path.isfile(solution_package) and solution_package.lower().endswith(".zip"):
                        self._solution_package_file = solution_package
                        self._solution_package_path = None

                    else:
                        raise ValueError(f"Package '{solution_package}' is an existing directory or a .zip file.")

        # Solution URL validation:
        # AutoForge allows optionally specifying a Git URL, which will later be used to retrieve solution files.
        # The URL must have a valid structure and must point to a path (not to a single file).

        if self._solution_url:
            is_url_path: Optional[bool] = ToolBox.is_url_path(self._solution_url)
            if is_url_path is None:
                raise RuntimeError(f"The specified URL '{self._solution_url}' is not a valid Git URL.")
            if not is_url_path:
                raise RuntimeError(f"The specified URL '{self._solution_url}' does not point to a valid path.")

        if self._automation_macro:
            if not os.path.isfile(self._automation_macro):
                raise ValueError(f"Automation macro path '{self._automation_macro}' does not exist or is not a file.")
            self._automated_mode = True

        # Optional arguments with specific expected format (IP:port)
        if remote_debugging:
            # Attempt to parse user input into an (address, port) tuple
            self._remote_debugging = ToolBox.get_address_and_port(remote_debugging)
            if self._remote_debugging is None:
                raise ValueError(
                    f"The specified remote debugging address '{remote_debugging}' is invalid. "
                    f"Expected format: <ip-address>:<port> (e.g., 127.0.0.1:5678)."
                )

        if proxy_server:
            # Attempt to parse user input into an (address, port) tuple
            self._proxy_server = ToolBox.get_address_and_port(proxy_server)
            if self._proxy_server is None:
                raise ValueError(
                    f"The specified proxy server address '{proxy_server}' is invalid. "
                    f"Expected format: <ip-address>:<port> (e.g., 127.0.0.1:5678)."
                )

    @staticmethod
    def _attach_debugger(host: str = '127.0.0.1', port: int = 5678, abort_execution: bool = False) -> None:
        """
        Attempt to attach to a remote PyCharm debugger.
        Args:
            host (str, optional): The debugger host to connect to. Defaults to '127.0.0.1'.
            port (int, optional): The debugger port to connect to. Defaults to 5678.
            abort_execution (bool, optional): If True, raise the exception on failure. If False, log and continue.
        """
        try:

            import pydevd_pycharm
            # Redirect stderr temporarily to suppress pydevd's traceback
            with contextlib.redirect_stderr(io.StringIO()):
                pydevd_pycharm.settrace(host=host, port=port, stdoutToServer=False, stderrToServer=False, suspend=False)

        except Exception as exception:
            if abort_execution:
                raise exception

    def forge(self) -> Optional[int]:
        """
        Load a solution and fire the AutoForge shell.
        """
        try:
            # Remove anny previously generated autoforge temporary files.
            ToolBox.clear_residual_files()

            if self._solution_url:
                # Download all files in a given remote git path to a local zip file
                self._solution_package_file = (
                    self._environment.git_get_path_from_url(url=self._solution_url, delete_if_exisit=True,
                                                            proxy=self._proxy_server.endpoint,
                                                            token=self._git_token))

            if self._solution_package_file is not None and self._solution_package_path is None:
                self._solution_package_path = ToolBox.unzip_file(self._solution_package_file)

            self._logger.debug(f"Solution files path: '{self._solution_package_path}'")

            # At this point we expect that self._solution_package_path sill point to valid path
            # where all the solution files could be found
            if self._solution_package_path is None:
                raise RuntimeError(f"Package path is invalid or could not be created")

            solution_file = os.path.join(self._solution_package_path, "solution.jsonc")
            if not os.path.isfile(solution_file):
                raise RuntimeError(f"The main solution file '{solution_file}' was not found")

            # Loads the solution file with multiple parsing passes and comprehensive structural validation.
            # Also initializes the core variables module as part of the process.

            self._solution = CoreSolution(solution_config_file_name=solution_file,
                                          workspace_path=self._workspace_path,
                                          workspace_creation_mode=self._create_workspace)

            self._variables = CoreVariables.get_instance()  # Get an instanced of the singleton variables class

            # Store the primary solution name
            self._solution_name = self._solution.get_primary_solution_name()
            self._logger.debug(f"Primary solution: '{self._solution_name}'")

            if not self._create_workspace:

                # ==============================================================
                # User interactive shell.
                # Indefinite loop until user exits the shell using 'quit'
                # ==============================================================

                # Greetings earthlings, we're here!
                self._toolbox.print_logo(clear_screen=True, terminal_title=f"AutoForge: {self._solution_name}")

                # Start blocking build system user mode shell
                self._gui: CoreGUI = CoreGUI()
                self._prompt = CorePrompt(history_file="~/.auto_forge_history")
                return self._prompt.cmdloop()
            else:

                # ==============================================================
                # Execute workspace creation script
                # Follow workspace setup steps as defined by the solution.
                # ==============================================================
                env_steps_file: Optional[str] = self._solution.get_included_file('environment')
                if env_steps_file is None:
                    raise RuntimeError(f"an environment steps file was not specified in the solution")

                # Execute suction creation steps
                ret_val = self._environment.follow_steps(steps_file=env_steps_file)

                # Lastly store the solution in the newly created workspace
                scripts_path = self._variables.get(variable_name="PROJ_SCRIPTS")
                if scripts_path is not None:
                    solution_destination_path = os.path.join(scripts_path, 'solution')
                    self._toolbox.cp(pattern=f'{self._solution_package_path}/*.*',
                                     dest_dir=f'{solution_destination_path}')
                    self._toolbox.cp(pattern=f'{solution_destination_path}/auto_go.sh',
                                     dest_dir=f'{self._workspace_path}')

                return ret_val


        except Exception:  # Propagate
            raise


def auto_forge_main() -> Optional[int]:
    """
    Console entry point for the AutoForge build suite.
    This function handles user arguments and launches AutoForge to execute the required test.
    Returns:
        int: Exit code of the function.
    """
    result: int = 1  # Default to internal error

    try:
        # Check early for the version flag before constructing the parser
        if len(sys.argv) == 2 and sys.argv[1] in ("-v", "--version"):
            print(f"\n{PROJECT_NAME} Version: {PROJECT_VERSION}\n")
            sys.exit(0)

        # Normal arguments handling
        parser = argparse.ArgumentParser(prog="autoforge",
                                         description=f"\033c{AutoForge.who_we_are()} BuildSystem Argumnets:")

        # Required argument specifying the workspace path. This can point to an existing workspace
        # or a new one to be created by AutoForge, depending on the solution definition.
        parser.add_argument(
            "-w", "--workspace-path", required=True,
            help="Path to an existing or new workspace to be used by AutoForge"
        )

        # AutoForge requires a solution to operate. This can be provided either as a pre-existing local ZIP archive,
        # or as a Git URL pointing to a directory containing the necessary solution JSON files.
        group = parser.add_mutually_exclusive_group(required=True)

        group.add_argument(
            "-p", "--solution-package", required=False,
            help=(
                "Path to a local AutoForge solution. This can be either:\n"
                "- A path to an existing .zip archive file.\n"
                "- A path to an existing directory containing solution files.\n"
                "- A Github URL pointing to git path which contains the solution files.\n"
                "The provided path will be validated at runtime."
            )
        )

        # Optional arguments and flags
        parser.add_argument(
            "--create-workspace", dest="create_workspace", action="store_true", default=True,
            help="Create the workspace if it does not exist (default: True)."
        )
        parser.add_argument(
            "--no-create-workspace", dest="create_workspace", action="store_false",
            help="Do not create the workspace if it does not exist (raises an error instead)."
        )

        parser.add_argument(
            "--automation-macro", type=str, required=False,
            help="Path to a JSON file defining an automatic flow to execute after loading the workspace."
        )

        parser.add_argument(
            "--remote-debugging", type=str, required=False,
            help="Remote debugging endpoint in the format <ip-address>:<port> (e.g., 127.0.0.1:5678)"
        )

        parser.add_argument(
            "--proxy-server", type=str, required=False,
            help="Optional proxy server endpoint in the format <ip-address>:<port> (e.g., 192.168.1.1:8080)."
        )

        parser.add_argument(
            "--git-token", type=str, required=False,
            help="Optional GitHub token to use for authenticating HTTP requests."
        )

        args = parser.parse_args()

        # Spread the news
        print(f"{TerminalAnsiCodes.CLS_SB}{AutoForge.who_we_are()} v{PROJECT_VERSION} starting...\n")

        # Instantiate AutoForge, pass all argumnets
        auto_forge: AutoForge = AutoForge(**vars(args))
        return auto_forge.forge()

    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Interrupted by user, shutting down.{Style.RESET_ALL}\n")

    except Exception as runtime_error:
        # Retrieve information about the original exception that triggered this handler.
        file_name, line_number = ExceptionGuru().get_context()
        # If we can get a logger, use it to log the error.
        logger_instance = AutoLogger.get_base_logger()
        if logger_instance is not None:
            logger_instance.error(f"Exception: {runtime_error}.File: {file_name}, Line: {line_number}")
        print(f"\n\n{Fore.RED}Exception:{Style.RESET_ALL} {runtime_error}.\nFile: {file_name}\nLine: {line_number}\n")

    return result
