"""
Script:         progress_tracker.py
Author:         AutoForge Team

Description:
    Auxiliary module which defines the ProgressTracker class, a utility designed for terminal-based status
    and progress reporting. It facilitates real-time updates of task statuses with dynamic text
    formatting, colorization, and cursor manipulations to enhance readability and user interaction
    during long-running operations.

Features:
    - Dynamic in-place update of status messages in the terminal.
    - Customizable text formatting including color support via Colorama.
    - Time prefixing for entries to track the progression of tasks chronologically.

Note:
    This module depends on the 'colorama' and 'ANSIGuru' (hypothetical) packages for its
    color handling and cursor control capabilities.
"""

import shutil
import sys
import time
from datetime import datetime
from enum import Enum
from typing import Optional

# Third-party
from colorama import Fore, Style

# AutoForge imports
from auto_forge import TerminalAnsiGuru, ToolBox

AUTO_FORGE_MODULE_NAME = "ProgressTracker"
AUTO_FORGE_MODULE_DESCRIPTION = "Terminal-based status and progress reporting helper"


class _TrackerState(Enum):
    """
    Enum to specify the types of text display for status messages within the ProgressTracker.

    Attributes:
        PRE (int): Represents the initial state for setting up preliminary text, typically used for
                   displaying the initial part of a status message, padded with dots to align the text.
                   This state is used to prepare and format the status message that appears before any actual
                   progress or result is displayed. E.g., "Loading configurations ................."

        BODY (int): Represents the state for displaying ongoing updates or body content. It is used
                    after the preliminary text to update the status dynamically without changing the
                    initial setup. This state is ideal for providing continuous feedback during a process,
                    such as "Loading configurations ................. 50% complete"

    Example:
        PRE - Used to initialize and display the start of a message with formatting.
        BODY - Used to provide real-time updates to the ongoing process or task within the same line.
    """
    UN_INITIALIZES = 0
    PRE = 1
    BODY = 2


class ProgressTracker:
    def __init__(self, title_length: int = 80, add_time_prefix: bool = False, min_update_interval_ms: int = 250,
                 hide_cursor: bool = True, linger_interval_ms: int = 0, default_new_line: bool = True) -> None:
        """
        Initializes the ProgressTracker instance.

        Args:
            title_length (int): Maximum length of the status message title.
            add_time_prefix (bool): Whether to prefix messages with the current time.
            min_update_interval_ms (int): Minimum interval in milliseconds between updates to prevent flickering.
            linger_interval_ms (int): Time to wait between consecutive lines update.
            default_new_line (bool): Default behaviour for new message.
        """
        self._state = _TrackerState.UN_INITIALIZES
        self._add_time_prefix: bool = add_time_prefix
        self._title_length: int = title_length
        self._terminal_width: int = shutil.get_terminal_size().columns
        self._ansi_term = TerminalAnsiGuru()
        self._pre_text: Optional[str] = None
        self._linger_interval_ms: int = linger_interval_ms
        self._min_update_interval_ms = min_update_interval_ms
        self._last_update_time = 0  # Epoch time of the last update
        self._default_new_line: bool = default_new_line
        self._state = _TrackerState.PRE

        # Hide the cursor
        if hide_cursor:
            self._ansi_term.set_cursor_visibility(False)

    @staticmethod
    def _normalize_text(text: Optional[str], allow_empty: bool = False) -> str:
        """
        Normalize the input string by stripping leading and trailing whitespace.

        Args:
            text (Optional[str]): The string to be normalized.
            allow_empty (bool): No exception if the output is an empty string.

        Returns:
            str: A normalized string with no leading or trailing whitespace.
        """
        if text is None or not isinstance(text, str):
            raise ValueError("input must be a non-empty string.")

        normalized_string = text.strip()
        if not allow_empty and not normalized_string:
            raise ValueError("input string cannot be empty after stripping")

        return normalized_string

    def _pre_format(self, text: str) -> str:
        """
        Formats the preliminary status message to include a time prefix (if enabled) and ensures
        it fits within the defined title length by truncating if necessary and padding with dots.
        Args:
            text (str): The preliminary status message to display.

        Returns:
            str: The formatted string ready for display.
        """

        input_len = len(ToolBox.strip_ansi(text).strip())

        time_string = datetime.now().strftime("%H:%M:%S ") if self._add_time_prefix else ""
        title_usable_length = self._title_length - len(time_string)
        if input_len > title_usable_length:
            text = text[-max(0, title_usable_length - 4):]  # Truncate from the left
            input_len = len(ToolBox.strip_ansi(text).strip())

        text_length = len(time_string) + input_len
        dots_count = self._title_length - text_length - 2
        dots = "." * max(0, dots_count)  # Ensure non-negative count of dots

        if text_length > self._title_length:
            truncate_length = self._title_length - len(time_string) - 4  # space for dots and spacing
            text = text[:max(0, truncate_length)]  # Truncate text if necessary

        if self._add_time_prefix:
            formatted_text = f"{Fore.LIGHTBLUE_EX}{time_string}{Style.RESET_ALL}{text} {dots} "
        else:
            formatted_text = f"{text} {dots} "

        return formatted_text

    def set_pre(self, text: str, new_line: Optional[bool] = None) -> bool:
        """
        Sets the preliminary message, preparing the display format in the console.
        Args:
            text (str): The preliminary status message to display.
            new_line (Optional[bool]): Whether or star the message in a new line.
        """

        if self._state != _TrackerState.PRE:
            return False

        # Set default new line behaviour when not specified explicitly
        if new_line is None:
            new_line = self._default_new_line

        text = self._normalize_text(text, allow_empty=True)
        formatted_text = self._pre_format(text)
        if len(formatted_text) >= self._terminal_width:
            return False  # formatted text is too wide for the terminal

        self._ansi_term.erase_line_to_end()
        sys.stdout.write(('\n' if new_line else '\r') + formatted_text)

        self._ansi_term.save_cursor_position()
        self._pre_text = text
        self._state = _TrackerState.BODY
        return True

    def set_body_in_place(self, text: str, pre_text: Optional[str] = None, update_clock: bool = True) -> bool:
        """
        Updates the message body in place, optionally updating the timestamp (clock)
        to reflect the current time when the update occurs.

        Args:
            text (str): The message body to display.
            pre_text (str, optional): Adjust the preliminary status message to display.
            update_clock (bool): Whether to update the message clock.
        """
        if self._state != _TrackerState.BODY:
            return False

        current_time = time.time() * 1000  # Get current time in milliseconds
        if current_time - self._last_update_time < self._min_update_interval_ms:
            return False  # Exit if the minimum interval has not passed

        # Move the cursor to the beginning of the line to potentially update the whole line
        self._ansi_term.restore_cursor_position()

        # Optionally update the ptr-text section
        if pre_text is not None:
            self._pre_text = pre_text

        # Update the clock and text if specified
        if update_clock and self._pre_text is not None:
            # Format the preliminary text with the updated clock
            formatted_pre_text = self._pre_format(self._pre_text)
            sys.stdout.write('\r' + formatted_pre_text)  # Use carriage return to overwrite the line
            # After updating the prefix and clock, adjust cursor position to after the prefix
            self._ansi_term.save_cursor_position()

        # Write the new body text ensuring it does not overflow the terminal width
        body_start_pos = len(
            self._pre_format(self._pre_text).strip())  # Calculate end position of the formatted pre text
        max_body_length = self._terminal_width - body_start_pos

        sys.stdout.write(text[:max_body_length])
        self._ansi_term.erase_line_to_end()
        sys.stdout.flush()

        # Update the last update time
        self._last_update_time = current_time
        return True

    def set_result(self, text: str, status_code: Optional[int] = None) -> bool:
        """
        Sets the result message with an optional status code and decides whether to add a new line.
        Args:
            text (str): The result message to display.
            status_code (Optional[int]): The status code to determine message color.
        """
        if self._state != _TrackerState.BODY:
            return False

        self._ansi_term.restore_cursor_position()
        color = Fore.GREEN if status_code == 0 else Fore.RED
        text = f"{color}{text}{Style.RESET_ALL}" if status_code is not None else text

        sys.stdout.write(text)
        sys.stdout.flush()
        self._ansi_term.erase_line_to_end()
        self._pre_text = None
        self._state = _TrackerState.PRE

        if self._linger_interval_ms:
            time.sleep(self._linger_interval_ms / 1000.0)

        return True

    def set_complete_line(self, pre_text: str, result_text: str, status_code: Optional[int] = None) -> bool:
        """
        Sets a complete line in a single call by printing the preliminary text with a timestamp,
        followed by the result text.

        Args:
            pre_text (str): Preliminary message text.
            result_text (str): Result message text.
            status_code (Optional[int]): Optional status code used to determine message color.
        """
        ret_val = False

        if self.set_pre(text=pre_text, new_line=True):
            ret_val = self.set_result(text=result_text, status_code=status_code)
            if ret_val:
                sys.stdout.write('\n')

        return ret_val

    def set_end(self):
        """ Flush stdout buffers and restore the curser """
        sys.stdout.write('\r')
        self._ansi_term.erase_line_to_end()
        sys.stdout.write('\r\n')
        sys.stdout.flush()
        self._ansi_term.set_cursor_visibility(True)

    def __del__(self):
        """
        Class destructor.
        """
        self.set_end()
        self._state = _TrackerState.UN_INITIALIZES
