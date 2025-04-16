"""
Script:         imcv2_sig_tool.py
Author:         AutoForge Team

Description:
    Utility for binary signing operations, leveraging the internal `Signatures` class for implementation.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Any

from git import Commit, Repo

# AutoForge imports
from auto_forge import (CLICommandInterface, CLICommandInfo, Signatures, ToolBox)

AUTO_FORGE_COMMAND_NAME = "sig_tool"
AUTO_FORGE_COMMAND_DESCRIPTION = "Binary file signing tool"
AUTO_FORGE_COMMAND_VERSION = "1.0"


class SigToolCommand(CLICommandInterface):

    def __init__(self, **kwargs: Any):
        """
        Constructor for SigToolCommand.
        """

        self._toolbox = ToolBox()  # AutoForge swissknife handy class

        self._sig_tool: Optional[Signatures] = None
        self._descriptor_file: Optional[str] = None
        self._signature_id: int = -1
        self._git_repo_path: Optional[str] = None
        self._git_repo: Optional[Repo] = None
        self._git_commit: Optional[Commit] = None
        self._git_commit_hash: Optional[str] = None

        # Set logger instance
        self._logger = logging.getLogger(AUTO_FORGE_COMMAND_NAME)

        # Extract optional parameters
        raise_exceptions: bool = kwargs.get('raise_exceptions', False)

        # Base class initialization
        super().__init__(raise_exceptions=raise_exceptions)

    def _create_sig_tool(self, **kwargs: Any) -> bool:
        """
        Validate reqwired arguments and initialize the signature tool
        """

        # Already created?
        if self._sig_tool:
            return True

        try:

            self._descriptor_file = kwargs.get("descriptor_file")
            self._git_repo_path = kwargs.get("git_repo_path")
            self._signature_id = kwargs.get("signature_id", self._signature_id)

            # Validate required string paths
            for name in ("descriptor_file", "git_repo_path"):
                value = getattr(self, f"_{name}")
                if not isinstance(value, str) or not value.strip():
                    raise RuntimeError(f"missing or invalid required argument: '{name}'")
                # Expand the value and validate we have it
                value = self._toolbox.get_expanded_path(value)
                if not Path(value).exists():
                    raise RuntimeError(f"path does not exist: {value}")

            # Validate integer signature ID
            if not isinstance(self._signature_id, int) or self._signature_id < 0:
                raise RuntimeError("missing or invalid required argument: 'signature_id'")

            # Retrieve git properties which we use later to update an image
            self._git_repo = Repo(self._git_repo_path)
            self._git_commit = self._git_repo.head.commit
            self._git_commit_hash = self._git_commit.hexsha

            # Create Signatures instance using the provided schema and the signature id.
            self._sig_tool = Signatures(descriptor_file=self._descriptor_file,
                                        signature_id=self._signature_id)

            return True

        except Exception:
            raise  # Propagate

    def _update_crc(self, source_binary_file: str, validate_only: Optional[bool] = True,
                    destination_path: Optional[str] = None, pad_to_size: Optional[int] = None) -> Optional[int]:
        """
        Update or validate the CRC of a binary file with a signature.

        Args:
            source_binary_file (str): Path to a binary file that contains a single signature.
            validate_only (bool, optional): If True, only validate the CRC without modifying the file. Defaults to True.
            destination_path (str, optional): Path where the modified file will be saved. If not specified, the
                source file will be updated in place.
            pad_to_size(Optional[int], optional): Resize the file to the specified size. Defaults to None.

        Returns:
            int: 0 if the CRC check or update succeeded, non zero otherwise.
        """

        try:
            if self._sig_tool is None:
                raise RuntimeError("signature tool not initialized")

            # Expand and validate the source file path
            source_binary_file = self._toolbox.get_expanded_path(path=source_binary_file)
            source_binary_file_base_name = os.path.basename(source_binary_file)
            padding_bytes: int = 0

            if not os.path.exists(source_binary_file):
                raise RuntimeError(f"source binary file '{source_binary_file}' not found")

            # Ensure the file is not empty
            source_file_size: int = os.path.getsize(source_binary_file)
            if source_file_size == 0:
                raise RuntimeError(f"source file '{source_binary_file_base_name}' is empty")

            # Do we have to resize the file?
            if pad_to_size is not None:
                if source_file_size >= pad_to_size:
                    self._logger.warning(
                        f"source size '{source_file_size}' >= padded size '{pad_to_size}', padding ignored")
                else:
                    pad_results = self._pad_file(source_binary_file=source_binary_file, required_size=pad_to_size)
                    if pad_results:
                        # Update the new file size and the bytes that ware added
                        padding_bytes = pad_to_size - source_file_size
                    else:
                        raise RuntimeError(f"error padding '{source_binary_file}'")

            # Load the file
            file_handler = self._sig_tool.deserialize(source_binary_file)
            if not file_handler:
                raise RuntimeError(f"error deserializing source file '{source_binary_file_base_name}'")

            # Check the number of signatures
            if len(file_handler.signatures) != 1:
                raise RuntimeError("CRC validation is not supported on files with multiple signatures")

            # Handle the single signature scenario
            signature = file_handler.signatures[0]
            if not signature.verified:
                self._logger.warning(f"binary CRC is invalid")

            # Only validate the CRC without updating
            if validate_only:
                if not signature.verified:
                    raise RuntimeError(f"CRC verification for '{source_binary_file_base_name}' failed")
            else:
                # Update the git hash and image size in the signature
                git_field = signature.find_first_field('git_commit')
                image_size_field = signature.find_first_field('image_size')

                if git_field is None or image_size_field is None:
                    raise RuntimeError("required fields are missing")

                signature.set_field_data(git_field, self._git_commit_hash)
                signature.set_field_data(image_size_field, source_file_size)

                # Update the 'padding_bytes' field in the signature
                if padding_bytes > 0:
                    padding_bytes_field = signature.find_first_field('padding_bytes')
                    if padding_bytes_field is not None:
                        signature.set_field_data(padding_bytes_field, padding_bytes)

                # Recalculate the CRC, update the signature, and save the file
                return int(signature.save(ignore_bad_integrity=True, file_name=destination_path))

        except Exception as exception:
            raise RuntimeError(f"cannot apply CRC on '{source_binary_file}' {exception}")

    def _pad_file(self, source_binary_file: str, required_size: int, pad_byte: Optional[int] = 0xFF) -> bool:
        """
        Resize a file by appending bytes to its end until it reaches the required size.

        Args:
            source_binary_file (str): Path to the file.
            required_size (int): The desired final size in bytes.
            pad_byte (int, optional): Byte to use for padding, defaults to 0xFF.

        Returns:
            bool: True on success, or False if the target size is less than the current file size.
        """
        try:
            # Expand as needed
            source_binary_file = self._toolbox.get_expanded_path(path=source_binary_file)

            if not os.path.exists(source_binary_file):
                raise RuntimeError(f"source binary file '{source_binary_file}' not found")

            # Get the current size of the file
            source_file_size = os.path.getsize(source_binary_file)

            # Check if resizing is necessary or possible
            if source_file_size >= required_size:
                self._logger.error(
                    f"Cannot pad file '{source_binary_file}' to {required_size} "
                    f"bytes as it is already {source_file_size} bytes or larger.")
                return False

            self._logger.debug(
                f"padding '{os.path.basename(source_binary_file)}' to {required_size} bytes, "
                f"current size {source_file_size} bytes.")

            # Calculate the number of bytes to add
            bytes_to_add = required_size - source_file_size

            # Open the file in append-binary mode and pad it
            with open(source_binary_file, 'ab') as file:
                file.write(bytes([pad_byte] * bytes_to_add))

            self._logger.debug(f"File '{os.path.basename(source_binary_file)}' "
                               f"resized to {required_size} bytes.")
            return True

        except Exception as exception:
            raise RuntimeError(
                f"can't resize '{os.path.basename(source_binary_file)}' "
                f"to {required_size} bytes: {exception}")

    def get_info(self) -> CLICommandInfo:
        """
        Returns:
            CLICommandInfo: a named tuple containing the implemented command id
        """
        # Populate and return the command info type
        if self._command_info is None:
            self._command_info = CLICommandInfo(name=AUTO_FORGE_COMMAND_NAME,
                                                description=AUTO_FORGE_COMMAND_DESCRIPTION,
                                                version=AUTO_FORGE_COMMAND_VERSION,
                                                class_name=self.__class__.__name__,
                                                class_instance=self)

        return self._command_info

    def create_parser(self, parser: argparse.ArgumentParser) -> None:
        """
        Adds the command-line arguments supported by this command.
        Args:
            parser (argparse.ArgumentParser): The parser to extend.
        """

        parser.add_argument("-p", "--path", type=str, required=True, help="Path to the binary file.")
        parser.add_argument("--verify-crc", action="store_true", help="Verify the CRC32 of the binary.")
        parser.add_argument("--update-crc", action="store_true", help="Update the CRC32 in the binary file.")
        parser.add_argument("-g", "--grow", type=lambda x: int(x, 0), nargs="?", const=0, default=0,
                            help="Resize file prior to signing.")
        parser.add_argument("-git", "--git_path", type=str, required=True,
                            help="Path where we can retrieve git related info.")
        parser.add_argument("-r", "--replace", type=str,
                            help="Search and replace a signed section with the one created.")
        parser.add_argument("-m", "--mini_loader", action="store_true",
                            help="Updates NVM mini-loader CRC value.")
        parser.add_argument("-s", "--show", action="store_true", help="Show signature content.")
        parser.add_argument("-i", "--signature_id", type=lambda x: int(x) if int(x) > 0
        else argparse.ArgumentTypeError(f"{x} is not a positive integer"), default=42,
                            help="Signature Id to use")
        parser.add_argument('-d', '--descriptor_file', required=True,
                            help="The path to the signature descriptor file")
        parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
        parser.add_argument("-ver", "--version", action="store_true", help="Only show binary version")

    def run(self, args: argparse.Namespace) -> int:
        """
        Executes the command based on parsed arguments.
        Args:
            args (argparse.Namespace): The parsed CLI arguments.

        Returns:
            int: Exit status (0 for success, non-zero for failure).
        """

        return_value: int = 0

        # Create a signature tool instance if we don't have it
        if self._sig_tool is None:
            self._create_sig_tool(descriptor_file=args.descriptor_file,
                                  signature_id=args.signature_id, git_repo_path=args.git_path)
        # Handle arguments
        if args.update_crc:
            return_value = self._update_crc(source_binary_file=args.path, validate_only=False, pad_to_size=args.grow)
        elif args.version:
            print(f"{AUTO_FORGE_COMMAND_NAME} version {AUTO_FORGE_COMMAND_VERSION}")
        else:
            # No arguments provided, show command usage
            sys.stdout.write("No arguments provided.\n")
            self._parser.print_usage()
            return_value = 1

        return return_value
