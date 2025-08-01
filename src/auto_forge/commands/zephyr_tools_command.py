"""
Script:         zephyr_tools_command.py
Author:         AutoForge Team

Description:
    Utility module for tools related to the Zephyr build system.
    Currently includes:
    - SDK detection: Locates the Zephyr SDK installation and returns its path and version.

    Note: This command is currently inactive and may serve as a placeholder for future tools.
"""

import argparse
from pathlib import Path
from typing import Any, Optional, cast

# AutoForge imports
from auto_forge import (CommandInterface)

AUTO_FORGE_MODULE_NAME = "zt"
AUTO_FORGE_MODULE_DESCRIPTION = "Zephyr Tools"
AUTO_FORGE_MODULE_VERSION = "1.0"

# Default CMake user package registry path where the Zephyr SDK is expected to be registered
CMAKE_PACKAGE_PATH: Path = Path.home() / ".cmake/packages/Zephyr-sdk"


class ZephyrToolsCommand(CommandInterface):

    def __init__(self, **kwargs: Any):
        """
        Initializes the ZephyrSDKCommand class.

        Initializes internal state and allows for optional overrides such as custom CMake
        package registry path and error handling behavior.

        Args:
            **kwargs (Any): Optional keyword arguments:
                - cmake_pkg_dir (Path or str): Custom path to the CMake package registry directory.
        """
        self._path: Optional[str] = None  # Detected Zephyr SDK path
        self._version: Optional[str] = None  # Detected SDK version
        self._detected: bool = False

        # Extract optional parameters from kwargs
        self._cmake_pkg_dir: Optional[Path] = Path(kwargs.get('cmake_pkg_dir', CMAKE_PACKAGE_PATH))

        # Base class initialization
        super().__init__(command_name=AUTO_FORGE_MODULE_NAME, hidden=True)

    def _locate_sdk(self, **_kwargs: Any) -> bool:
        """
        Detect the installed Zephyr SDK by examining the CMake user package registry.
        Note: Assumes standard SDK install with 'zephyr-sdk-setup.sh' registration.

        Args:
            **_kwargs (Any): Optional keyword arguments:
        Returns:
            bool: True if initialization succeeded, False otherwise.
        """

        if self._detected:
            return True  # SDK Already found

        if not self._cmake_pkg_dir or not self._cmake_pkg_dir.is_dir():
            return False  # CMake package registry path does not exist

        # Workaround PyCharm's static analyzer quirks
        cmake_pkg_dir: Path = cast(Path, self._cmake_pkg_dir)

        for pkg_file in cmake_pkg_dir.iterdir():
            _file = Path(pkg_file)
            if not _file.is_file():
                continue

            try:
                _file = Path(pkg_file)
                with _file.open("r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
            except (OSError, UnicodeDecodeError):
                continue

            if first_line.startswith("%"):
                first_line = first_line[1:]

            cmake_dir = Path(first_line)
            sdk_path = cmake_dir.parent

            # Validate existence of expected toolchain binary
            if not (sdk_path / "arm-zephyr-eabi" / "bin" / "arm-zephyr-eabi-gcc").exists():
                continue

            # Extract version
            version = (
                sdk_path.name.replace("zephyr-sdk-", "").upper() if sdk_path.name.startswith("zephyr-sdk-") else None)

            self._path = sdk_path.__str__()
            self._version = version
            self._detected = True
            return True

        return False

    def create_parser(self, parser: argparse.ArgumentParser) -> None:
        """
        Adds the command-line arguments supported by this command.
        Args:
            parser (argparse.ArgumentParser): The parser to extend.
        """
        parser.add_argument('-p', '--get-zephyr-path', action='store_true',
                            help='Prints the detected Zephyrs SDK installation path.')
        parser.add_argument('-z', '--get-zephyr-version', action='store_true',
                            help='Prints the detected Zephyrs SDK version.')

    def run(self, args: argparse.Namespace) -> int:
        """
        Executes the command based on parsed arguments.
        Args:
            args (argparse.Namespace): The parsed arguments.
        Returns:
            int: Exit status (0 for success, non-zero for failure).
        """
        return_value: int = 0
        self._locate_sdk()  # Attempt to locate the SDK

        # The SDK path should have been discovered when this class was created.
        if not self._path:
            print("Error: Zephyr SDK not found.")
            return 1

        # Handle arguments
        if args.get_zephyr_path:
            print(self._path)
        elif args.get_zephyr_version:
            print(self._version)
        else:
            return_value = CommandInterface.COMMAND_ERROR_NO_ARGUMENTS

        return return_value
