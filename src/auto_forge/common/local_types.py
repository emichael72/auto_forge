"""
Script:         local_types,py
Author:         AutoForge Team

Description:
    Single point module defining many common types, enumerations, and simple classes
    shared across multiple components of the project.
"""
import asyncio
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field, asdict, is_dataclass
from enum import Enum, auto, IntFlag
from itertools import cycle
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple, Optional, TextIO, Union, ClassVar, TypeVar, Type

AUTO_FORGE_MODULE_NAME: str = "LocalTypes"
AUTO_FORGE_MODULE_DESCRIPTION: str = "Project shared types"


class AutoForgeWorkModeType(Enum):
    """ Enumeration of known AutoForge run modes. """
    UNKNOWN = 0
    INTERACTIVE = 1  # Normal interactive shell
    NON_INTERACTIVE_SEQUENCE = 3  # Executing sequence non interactively
    NON_INTERACTIVE_AUTOMATION = 4  # Executing single command, used in automation mode


class AutoForgeModuleType(Enum):
    """
    Enumeration of known AutoForge module types.
    """
    UNKNOWN = 0
    CORE = 1
    COMMON = 2
    COMMAND = 3
    BUILDER = 4
    ANALYZER = 5
    PROMPT = 6  # Reserved for cmd2 implemented commands ("do_<command>")


# noinspection DuplicatedCode
class AutoForgCommandType(Enum):
    """ Enumeration of known AutoForge command types. """
    UNKNOWN = 0
    BUILD = 1
    NAVIGATE = 2
    EMULATION = 3
    AUTOMATION = 4
    GIT = 5
    UTILITY = 6
    SYSTEM = 7
    INSTALLER = 8
    MISCELLANEOUS = 9
    SHELL = 10
    ALIASES = 11
    BUILTIN = 12
    HELP = 13
    AI = 14

    @classmethod
    def from_str(cls, value: str, default: Union[str, 'AutoForgCommandType'] = None) -> 'AutoForgCommandType':
        """
        Safely convert a string to an AutoForgCommandType enum value.
        Args:
            value (str): The string to convert (case-insensitive).
            default (Union[str, AutoForgCommandType]): The fallback value if conversion fails.
                Can be a string or an enum member. If omitted, defaults to AutoForgCommandType.UNKNOWN.
        Returns:
            AutoForgCommandType: Matching enum member or fallback.
        """
        # Normalize default first
        if default is None:
            default_enum = cls.UNKNOWN
        elif isinstance(default, str):
            default_enum = cls.__members__.get(default.strip().upper(), cls.UNKNOWN)
        elif isinstance(default, cls):
            default_enum = default
        else:
            default_enum = cls.UNKNOWN

        if not isinstance(value, str):
            return default_enum

        return cls.__members__.get(value.strip().upper(), default_enum)


class LogHandlersType(IntFlag):
    """
    Bitwise-capable enumeration of supported log handler types.
    Allows combining multiple handlers using bitwise OR.
    """
    NO_HANDLERS = 0
    CONSOLE_HANDLER = auto()
    FILE_HANDLER = auto()
    MEMORY_HANDLER = auto()


# noinspection DuplicatedCode
class AutoForgFolderType(Enum):
    """ Enumeration of known AutoForge folder types. """
    UNKNOWN = 0
    BUILD = 1
    SOURCES = 2
    DOCUMENTS = 3
    SCRIPTS = 4
    RESOURCES = 5
    EXTERNALS = 6
    IMAGES = 7
    INDEX = 8
    LOGS = 9
    AUTOMATION = 10
    HELP = 11
    COMMANDS = 12
    BUILDERS = 13
    MISFITS = 14

    @classmethod
    def from_str(cls, value: Optional[str],
                 default: Optional[Union[str, 'AutoForgFolderType']] = None) -> 'AutoForgFolderType':
        """
        Safely convert a string to an AutoForgFolderType enum value.
        Args:
            value (str): The string to convert (case-insensitive).
            default (Union[str, AutoForgFolderType]): The fallback value if conversion fails.
                Can be a string or an enum member. If omitted, defaults to AutoForgFolderType.UNKNOWN.
        Returns:
            AutoForgFolderType: Matching enum member or fallback.
        """
        # Normalize default first
        if default is None:
            default_enum = cls.UNKNOWN
        elif isinstance(default, str):
            default_enum = cls.__members__.get(default.strip().upper(), cls.UNKNOWN)
        elif isinstance(default, cls):
            default_enum = default
        else:
            default_enum = cls.UNKNOWN

        if not isinstance(value, str):
            return default_enum

        return cls.__members__.get(value.strip().upper(), default_enum)


class XRayStateType(Enum):
    """ XRay SQLite management class status types"""
    UNKNOWN = 0
    INITIALIZED = auto()  # Class is initialized
    DB_READY = auto()  # SQLite DB is initialized
    DB_INDEXING = auto()  # SQLite DB is indexing files
    IDLE = auto()  # Module is running and ready to serve requests
    DB_QUERY = auto()  # Executing SQL query
    ERROR = auto()  # Module is in error state


class PromptStatusType(Enum):
    """ Type of prompt status stripes """
    INFO = "info"
    DEBUG = "debug"
    ERROR = "error"


class SequenceErrorActionType(Enum):
    """ Enum for error actions, storing both int value and string label. """
    DEFAULT = (0, "default")
    BREAK = (1, "break")
    RESUME = (2, "resume")

    def __new__(cls, value, label):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.label = label
        return obj

    def __str__(self):
        return self.label

    @classmethod
    def from_label(cls, label: Optional[str] = None) -> "SequenceErrorActionType":
        """ Convert string label to enum; return DEFAULT if label is None or invalid. """
        if not label:
            return cls.DEFAULT

        label = label.strip().lower()
        for member in cls:
            if member.label == label:
                return member
        return cls.DEFAULT


class ModuleInfoType(NamedTuple):
    """ Define a named tuple type for AutoForge registered modules. """
    name: str
    description: Optional[str] = None
    class_name: Optional[str] = None
    class_instance: Optional[Any] = None
    class_interface_name: Optional[str] = None
    auto_forge_module_type: AutoForgeModuleType = AutoForgeModuleType.UNKNOWN
    python_module_type: Optional[ModuleType] = None
    file_name: Optional[str] = None
    version: Optional[str] = None
    hidden: bool = False  # Applicable for commands
    command_type: AutoForgCommandType = AutoForgCommandType.UNKNOWN
    metadata: Optional[dict[str, Any]] = None


class ValidationMethodType(Enum):
    """
    Enumeration for supported validation methods.
    Attributes:
        EXECUTE_PROCESS (int): Run a shell command and validate based on its return code and/or output.
        READ_FILE (int): Read specific lines from a file and validate expected content.
        SYS_PACKAGE (int): Checks if a specific package ('apt', 'dnf' is installed)
    """
    EXECUTE_PROCESS = 1
    READ_FILE = 2
    SYS_PACKAGE = 3


class ExecutionModeType(Enum):
    """
    Defines how a command should be executed.
    Attributes:
        SHELL: Execute using a shell subprocess (e.g., bash, cmd).
        PYTHON: Execute as a direct Python callable.
    """
    SHELL = "shell"
    PYTHON = "python"


class ExpectedVersionInfoType(NamedTuple):
    """ Generic type for splitting version and operator (e.g.'>= 3.16') into 2 parts """
    operator: str  # e.g. '>=' ,'<' act.
    version: str  # Version identifier, e.g. '4.6'


@dataclass
class CommandResultType:
    """ Generic type for executed command results """
    response: Optional[str] = None  # Command output
    return_code: int = 1  # Command returned integer value, initialized to error.
    message: Optional[str] = None
    command: Optional[str] = "unknown"
    extra_value: Optional[
        int] = None  # Optional additional return value, for ex. HTTP status from a method that handles downloads.
    extra_data: Optional[Any] = None  # Optional additional return data, could be anything.


@dataclass
class ProxyServerType:
    """Generic type for storing proxy server configuration."""
    scheme: Optional[str] = "http"  # 'http', 'https', 'socks5', etc.
    host: Optional[str] = None  # e.g., 'proxy.company.com'
    port: Optional[int] = None  # e.g., 8080
    username: Optional[str] = None  # Optional authentication username
    password: Optional[str] = None  # Optional authentication password
    bypass: Optional[list[str]] = None  # List of hosts or domains to exclude (no_proxy)
    enabled: bool = True  # Enable/disable without removing config
    notes: Optional[str] = None  # Human-readable notes or source of proxy

    def url(self) -> Optional[str]:
        """Constructs the full proxy URL."""
        if not self.host or not self.port:
            return None
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"


@dataclass
class AIKeyType:
    """Generic type for storing a single credential key for an AI provider."""
    name: Optional[str] = None  # e.g., 'api_key', 'access_token'
    data: Optional[str] = None  # The actual secret/key content
    id: Optional[str] = None  # Optional: used for key rotation, identification, etc.


@dataclass
class AIProviderType:
    """Generic type for storing AI provider configuration."""
    name: str  # Required: 'openai', 'azure_openai', 'anthropic', etc.
    pretty_name: Optional[str] = None  # Formated provider name e.g 'OpenAI'
    keys: list[AIKeyType] = field(default_factory=list)  # Required: one or more keys
    endpoint: Optional[str] = None  # Required for most APIs
    organization: Optional[str] = None  # OpenAI-style org ID
    deployment: Optional[str] = None  # Azure-specific deployment ID
    api_version: Optional[str] = None  # Azure-specific or versioned APIs
    model: Optional[str] = None  # Optional: default model to use (e.g., 'gpt-4')
    extra_field_1: Optional[str] = None  # Additional optional general purpose field
    extra_field_2: Optional[str] = None  # Additional optional general purpose field
    extra_field_3: Optional[str] = None  # Additional optional general purpose field
    extra_field_4: Optional[str] = None  # Additional optional general purpose field
    notes: Optional[str] = None  # Optional: free-text field for human-readable description
    request_time_out: int = 30  # Default request timeout in seconds
    max_tokens: Optional[int] = None  # Optional default value for max tokens to use
    proxy_server: Optional[
        ProxyServerType] = None  # Optional proxy server which will be used when proxy_allowed is true
    proxy_allowed: bool = False  # Allow the use of the configured proxy server when connecting to the AI
    registration_date: Optional[str] = None  # Date (ISO format) when this AI was added

    def get_key(self, name: str) -> Optional[str]:
        """Return the key data for the given key name, or None if not found."""
        for key in self.keys:
            if key.name == name:
                return key.data
        return None


T = TypeVar("T", bound="AIProvidersType")


@dataclass
class AIProvidersType:
    """Container for AI provider configurations and associated metadata."""
    version: str = "0.1"
    last_updated: Optional[str] = None
    description: Optional[str] = None
    providers: list[AIProviderType] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Recursively convert dataclass object (including nested) to dict."""

        def convert(obj):
            if isinstance(obj, list):
                return [convert(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif is_dataclass(obj):
                return {k: convert(v) for k, v in asdict(obj).items()}
            else:
                return obj

        return convert(self)

    def to_json(self, path: Union[str, Path]) -> None:
        """Serialize AIProvidersType to a JSON file."""
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        """Recursively create AIProvidersType from a dictionary."""

        def build_ai_key(d):
            return AIKeyType(**d)

        def build_proxy(d):
            return ProxyServerType(**d)

        def build_provider(d):
            d['keys'] = [build_ai_key(k) for k in d.get('keys', [])]
            if 'proxy_server' in d and d['proxy_server'] is not None:
                d['proxy_server'] = build_proxy(d['proxy_server'])
            return AIProviderType(**d)

        providers = [build_provider(p) for p in data.get('providers', [])]
        return cls(
            version=data.get('version', "0.1"),
            last_updated=data.get('last_updated'),
            description=data.get('description'),
            providers=providers
        )

    @classmethod
    def from_json(cls: Type[T], path: Union[str, Path]) -> T:
        """Load AIProvidersType from a JSON file."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_provider(self, name: str) -> Optional[AIProviderType]:
        """Return the AI provider by name, or None if not found."""
        name = name.strip().lower()
        for provider in self.providers:
            if provider.name.strip().lower() == name:
                return provider
        return None


class CommandFailedException(Exception):
    """
    Custom exception that carries a 'CommandResultType' instance,
    which can be raised when a command fails.
    """

    def __init__(self, results: Optional[CommandResultType] = None):
        super().__init__()
        self.results: Optional[CommandResultType] = results


class MessageBoxType(Enum):
    """
    Enum representing supported message box types.
    These types define the set of buttons and dialog styles used
    when displaying a message box to the user.
    """
    MB_OK = 1  # OK button only
    MB_OKCANCEL = 2  # OK and Cancel buttons
    MB_RETRYCANCEL = 3  # Retry and Cancel buttons
    MB_YESNO = 4  # Yes and No buttons
    MB_YESNOCANCEL = 5  # Yes, No, and Cancel buttons
    MB_ERROR = 6  # Error message style
    MB_WARNING = 7  # Warning message style


class InputBoxTextType(Enum):
    """
    Defines the type of text input for an input box.
    Options:
        INPUT_TEXT: Plain visible text.
        INPUT_PASSWORD: Hidden text input (e.g., for passwords).
    """
    INPUT_TEXT = auto()
    INPUT_PASSWORD = auto()


class InputBoxButtonType(Enum):
    """
    Defines the types of buttons used in an input box dialog.
    Options:
        INPUT_MB_OK: OK/Confirm button.
        INPUT_CANCEL: Cancel/Close button.
    """
    INPUT_MB_OK = auto()
    INPUT_CANCEL = auto()


@dataclass
class InputBoxLineType:
    """
    Represents a single input line in a multi-line input box dialog.
    Attributes:
        label (str): The label displayed next to the input field.
        input_text (str): Default or pre-filled input value.
        text_type (InputBoxTextType): Type of input (e.g., plain, password).
        length (int): Desired input field width; 0 means auto-sized.
    """
    label: str
    input_text: str = ""
    text_type: InputBoxTextType = InputBoxTextType.INPUT_TEXT
    length: int = 0  # 0 = auto width


class AddressInfoType(NamedTuple):
    """
    Defines a TCP endpoint consisting of:
    - host (str): Either an IP address (IPv4) or a hostname.
    - port (int): TCP port number.
    - endpoint (str): a string formated as host:port
    - is_host_name (bool): True if 'host' is a hostname, False if it's an IP address.
    """
    host: str
    port: int
    endpoint: str
    url: str
    is_host_name: bool


@dataclass
class SignatureSchemaType:
    """ A data class to facilitate handling signature schema data. """
    name: Optional[str] = None
    description: Optional[str] = None
    dictionary: dict[str, Any] = field(default_factory=dict)
    size: Optional[int] = None
    search_pattern: Optional[re.Pattern] = None
    format_string: Optional[str] = None
    is_default: bool = False


@dataclass
class SignatureFieldType:
    """
    A data class to facilitate reading and writing specific fields from
    signature binary data.
    """
    name: Optional[str] = None
    type: Optional[str] = None
    size: Optional[int] = None
    data: Optional[Any] = None
    read_only: Optional[bool] = False  # If True, modifying the field raises an error
    is_integrity: Optional[bool] = None  # True if this field holds a CRC or integrity value
    offset: Optional[int] = None  # Offset relative to the signature start address
    type_info: Optional[dict[str, Any]] = None  # Type definition metadata for this field


class MethodLocationType(NamedTuple):
    """ A data type to describe a method location. """
    class_name: Optional[str]
    method_name: Optional[str]
    module_path: Optional[str]


class VariableType(Enum):
    """
    Represents the different types of variables that can be automatically detected
    based on their value format.
    """
    UNKNOWN = auto()  # Type could not be determined
    PATH = auto()  # Unix-style directory path (e.g., /usr/bin)
    FILE = auto()  # Unix-style file path (e.g., /usr/bin/ls)
    WIN_PATH = auto()  # Windows-style directory path (e.g., C:\Windows)
    WIN_FILE = auto()  # Windows-style file path (e.g., C:\Windows\notepad.exe)
    URL = auto()  # Web URL (e.g., https://example.com)
    BOOL = auto()  # Boolean value (True, False, "yes", "no", etc.)
    INT = auto()  # Integer value (e.g., 42, -7)
    FLOAT = auto()  # Floating-point value (e.g., 3.14, -0.001)
    VERSION = auto()  # Version-like string (e.g., "1.2.3", "v2.0-beta")
    STRING = auto()  # Generic string not matching any of the above types


@dataclass
class VariableFieldType:
    """ A data class to manage a single managed variable. """
    key: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    is_path: Optional[bool] = None
    path_must_exist: Optional[bool] = None
    create_path_if_not_exist: Optional[bool] = None
    folder_type: Optional[AutoForgFolderType] = AutoForgFolderType.UNKNOWN
    type: Optional[VariableType] = VariableType.UNKNOWN,
    kwargs: Optional[dict[str, Any]] = field(default_factory=dict)


class SysInfoPackageManagerType(str, Enum):
    """ Enum representing common system package managers, based on their command names. """
    APT = "apt"
    DNF = "dnf"
    YUM = "yum"
    PACMAN = "pacman"
    ZYPPER = "zypper"
    APK = "apk"
    BREW = "brew"
    CHOCO = "choco"


# noinspection SpellCheckingInspection
class SysInfoLinuxDistroType(str, Enum):
    """ Enum representing major Linux distributions, normalized by ID values found in /etc/os-release. """
    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    FEDORA = "fedora"
    CENTOS = "centos"
    RHEL = "rhel"
    ROCKY = "rocky"
    ALMA = "almalinux"
    ARCH = "arch"
    MANJARO = "manjaro"
    SUSE = "opensuse"
    ALPINE = "alpine"
    AMAZON = "amzn"
    UNKNOWN = "unknown"

    @classmethod
    def from_id(cls, distro_id: str) -> "SysInfoLinuxDistroType":
        """
        Map a raw distro ID string to a LinuxDistroType enum value.
        Defaults to UNKNOWN if not recognized.
        """
        try:
            return cls(distro_id.lower())
        except ValueError:
            return cls.UNKNOWN


class LinuxShellType(Enum):
    """ Enumeration of Linux shells that this class can handle. """
    UNKNOWN = 0
    BASH = 1
    ZSH = 2
    FISH = 3


class TerminalEchoType(Enum):
    """
    Defines how data is being echoed to the terminal from a forked process.
        NONE: No echo.
        BYTE: echo one byte at a time.
        LINE: accumulate complete line before echoing.
    """
    NONE = auto()
    BYTE = auto()
    LINE = auto()
    CLEAR_LINE = auto()
    SINGLE_LINE = auto()


class TerminalTeeStream:
    """ A simple output stream duplicator that writes data to multiple target streams. """

    def __init__(self, *targets: TextIO):
        """
        Initialize the _TeeStream with one or more target streams.
        Args:
            *targets (TextIO): Output streams to write to (e.g., sys.stdout, StringIO).
        """
        self._targets = targets

    def write(self, data: str) -> int:
        """
        Write data to all registered target streams.
        Args:
            data (str): The string data to write.
        Returns:
            int: The number of characters written (equal to len(data)).
        """
        for target in self._targets:
            target.write(data)
        return len(data)

    def flush(self) -> None:
        """
        Flush all target streams that support flushing.
        """
        for target in self._targets:
            if hasattr(target, "flush"):
                target.flush()


class TerminalAnsiGuru:
    """
    A utility class for managing terminal output through ANSI escape codes. The class provides methods to
    manipulate the cursor's visibility and position, allowing for dynamic updates to the terminal content
    without disrupting the user's view. This class is particularly useful for applications that require
    fine control over the terminal interface, such as text-based user interfaces, progress bars, and
    interactive command-line tools.
    """

    def __init__(self):
        pass

    @staticmethod
    def set_cursor_visibility(visible: bool):
        """Shows or hides the cursor based on the 'visible' parameter."""
        sys.stdout.write('\033[?25h' if visible else '\033[?25l')
        sys.stdout.flush()

    @staticmethod
    def save_cursor_position():
        """Saves the current cursor position."""
        sys.stdout.write("\033[s")
        sys.stdout.flush()

    @staticmethod
    def restore_cursor_position():
        """Restores the cursor to the last saved position."""
        sys.stdout.write("\033[u")
        sys.stdout.flush()

    @staticmethod
    def restore_cursor_position_and_erase_line_to_end():
        """
        Restores the cursor to the last saved position,
        erases from the cursor to the end of the line,
        and restores the cursor back to the same position again.
        """
        sys.stdout.write("\033[u")
        sys.stdout.write("\033[K")
        sys.stdout.write("\033[u")
        sys.stdout.flush()

    def move_cursor(self, row: Optional[int] = None, col: Optional[int] = None):
        """
        Moves the cursor to the specified (row, col). Handles partial parameters by moving
        to the specific row or column while keeping the other coordinate unchanged.
        """
        # Attempt to get the current cursor position
        current_pos = self.get_cursor_position()
        if current_pos is None:
            return  # If the position is unknown, exit early

        row = row or current_pos[0]  # Use current row if not specified
        col = col or current_pos[1]  # Use current column if not specified
        sys.stdout.write(f"\033[{row + 1};{col + 1}H")
        sys.stdout.flush()

    @staticmethod
    def erase_line_to_end():
        """Erases from the current cursor position to the end of the line."""
        sys.stdout.write("\033[K")
        sys.stdout.flush()

    @staticmethod
    def get_cursor_position() -> Optional[tuple[int, int]]:
        """
        Attempts to query the terminal for the current cursor position. Requires terminal support.
        Returns the cursor position as zero-based indices or None if undetermined.
        """
        sys.stdout.write("\033[6n")
        sys.stdout.flush()
        response = sys.stdin.read(20)  # Read enough characters for typical response
        match = re.search(r"\033\[(\d+);(\d+)R", response)
        return (int(match.group(1)) - 1, int(match.group(2)) - 1) if match else None


class TerminalSpinner:
    """
    A colorful animated terminal spinner for asynchronous operations.
    """
    SPINNER_FRAMES = [
        "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
    ]
    COLORS = [
        "\033[91m",  # Red
        "\033[93m",  # Yellow
        "\033[92m",  # Green
        "\033[96m",  # Cyan
        "\033[94m",  # Blue
        "\033[95m",  # Magenta
    ]
    COLOR_END = "\033[0m"
    CURSOR_HIDE = "\033[?25l"
    CURSOR_SHOW = "\033[?25h"

    @staticmethod
    async def run(message="Thinking..."):
        color_cycle = cycle(TerminalSpinner.COLORS)
        frame_cycle = cycle(TerminalSpinner.SPINNER_FRAMES)

        print(TerminalSpinner.CURSOR_HIDE, end='', flush=True)

        try:
            while True:
                color = next(color_cycle)
                frame = next(frame_cycle)
                print(f"\r{color}{frame}{TerminalSpinner.COLOR_END} {message}", end='', flush=True)
                await asyncio.sleep(0.1)
        finally:
            print(f"\r{TerminalSpinner.CURSOR_SHOW}", end='', flush=True)


class FieldColorType(NamedTuple):
    """  Maps arbitrary filed text to a desired color """
    field_name: str
    color: str


class ExceptionGuru:
    """
    A singleton utility class for capturing and exposing the origin (filename and line number)
    of the innermost frame where the most recent exception occurred bty ensuring the exception context
    is captured only once.
    """

    _instance: Optional["ExceptionGuru"] = None
    _context_stored: bool = False

    def __new__(cls) -> "ExceptionGuru":
        """
        Overrides object instantiation to implement the singleton pattern.
        Returns:
            ExceptionGuru: The singleton instance of the class.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initializes the exception context (filename and line number).
        The context is captured only once during the lifetime of the singleton instance.
        """
        if not self.__class__._context_stored:
            self._file_name: Optional[str] = "<unknown>"
            self._line_number: Optional[int] = -1
            self._store_context()
            self.__class__._context_stored = True

    def get_context(self) -> tuple[str, int]:
        """
        Retrieves the exception origin information.
        Returns:
            Tuple[str, int]: A tuple containing the base filename and the line number
                             where the exception originally occurred.
        """
        return self._file_name, self._line_number

    def _store_context(self) -> None:
        """
        Captures the filename and line number of the innermost frame where the most recent
        exception occurred. If no exception context is found, defaults to '<unknown>' and -1.
        """
        exc_type, exc_obj, exc_tb = sys.exc_info()

        if exc_tb is None:
            return

        # Traverse to the innermost (deepest) frame
        tb = exc_tb
        while tb.tb_next:
            tb = tb.tb_next

        self._file_name = os.path.basename(tb.tb_frame.f_code.co_filename)
        self._line_number = tb.tb_lineno


@dataclass
class BuildProfileType:
    """
    A data class to facilitate reading and writing specific fields from
    signature binary data.
    """
    build_system: Optional[str] = None  # 'make', 'ninja' and others must be unique across all builders
    solution_name: Optional[str] = None
    project_name: Optional[str] = None
    config_name: Optional[str] = None
    terminal_leading_text: Optional[str] = None
    extra_args: Optional[list[str]] = None
    build_dot_notation: Optional[str] = None
    config_data: Optional[dict[str, Any]] = None
    tool_chain_data: Optional[dict[str, Any]] = None


@dataclass
class BuildAnalyzedEventType:
    """
    Represents a normalized build event captured by any registered build analyzer.
    Designed to support a wide range of tools including GCC, Python, CMake, and others.
    A sequence of such events can be compressed and optionally sent to an AI for analysis.
    """
    file: Optional[str] = None  # File where the issue (error/warning/etc.) occurred
    derived_file: Optional[str] = None  # File that was built while the error happened
    line: Optional[int] = None  # Line number in the file where the issue was reported
    column: Optional[int] = None  # Column number within the line, if available
    type: Optional[str] = None  # Event type (e.g., 'error', 'warning', 'note')
    message: Optional[str] = None  # Diagnostic message or explanation
    function: Optional[str] = None  # Function or method name, if applicable
    snippet: Optional[str] = None  # Code snippet relevant to the issue (full function or surrounding lines)
    snippet_line: int = 0  # Line offset of the 'line' field relative to the snippet (0-based)


class BuildAnalyzedContextType:
    """
    Container for build events, allowing structured accumulation and export to JSON.
    """

    def __init__(self, toolchain: Optional[dict[str, Any]] = None):
        """
        Initializes a build analyzer context.
        Args:
            toolchain: Optional metadata about the toolchain used (e.g., compiler version, flags).
                      Absolute paths will be truncated to their base-names for clarity.
        """
        self._events: list[BuildAnalyzedEventType] = []

        def _basename_only(val):
            return Path(val).name if isinstance(val, str) and ("/" in val or "\\" in val) else val

        self._toolchain: Optional[dict[str, Any]] = (
            {k: _basename_only(v) for k, v in toolchain.items()} if isinstance(toolchain, dict) else None
        )

    def add_event(self, event: BuildAnalyzedEventType) -> None:
        """Add a parsed build event to the context."""
        self._events.append(event)

    def export_data(self) -> Union[list[dict[str, Any]], dict[str, Any]]:
        """
        Export the collected events as either a raw list or a dictionary containing toolchain info.
        Returns:
            - A list of event dictionaries if no toolchain metadata is present.
            - A dictionary containing:
                {
                    "toolchain": { ... },
                    "events": [ ... ]
                }
        """
        events_data = [asdict(event) for event in self._events]

        if self._toolchain is not None:
            return {
                "toolchain": self._toolchain,
                "events": events_data
            }

        return events_data

    def export_json(self, output_path: Path, indent: int = 2) -> None:
        """
        Export the collected data (events or toolchain + events) to a JSON file.
        Args:
            output_path: Path to the output file.
            indent: Indentation for pretty-printing.
        """
        data = self.export_data()
        output_path.write_text(json.dumps(data, indent=indent), encoding='utf-8')

    @property
    def count(self) -> int:
        """Returns the number of collected events."""
        return len(self._events)


class StatusNotifType(Enum):
    """
    Defines the types of status notifications used by all modules.
    Attributes:
        INIT (int,str): Sent once a modules is initialized and ready to be used
        OPERATION_START (int,str): Sent when an arbitrary operation has started
        OPERATION_END (int,str): Sent when an arbitrary operation has ended
        PERIODIC_TIMER (int, str): Sent when a periodic background tome has expired
        ERROR (int,str): Error notification type
        TERM (int,str): Sent when a module is being terminated
    """
    INIT = (0, "INIT")
    OPERATION_START = (1, "OPERATION_START")
    OPERATION_END = (2, "OPERATION_END")
    PERIODIC_TIMER = (3, "PERIODIC_TIMER")
    ERROR = (4, "ERROR")
    TERM = (5, "TERM")

    def __init__(self, num, name):
        self._num = num
        self._name = name

    @property
    def num(self):
        return self._num

    @property
    def name(self):
        return self._name

    def __int__(self):
        return self.num

    def __str__(self):
        return self.name


class EventManager:
    """
    Manages synchronization events for modules using threading events, facilitating the coordination
    of various plugin notification types. Each event type from a passed Enum is associated with a unique
    threading.Event, with an additional 'any_event_triggered' event that auto-resets to signal any event occurrence.
    """

    def __init__(self, event_enum: type[Enum]):
        self.event_map = {notification: threading.Event() for notification in event_enum}
        self.any_event_triggered = threading.Event()
        self.reset_all()

    def set(self, notification: Enum):
        """
        Set the event associated with a specific notification type, and also signal that any event has been set.
        Args:
            notification (Enum): The specific notification type whose event is to be set.
        """
        event = self.event_map[notification]
        event.set()
        self.any_event_triggered.set()

    def wait(self, notification: Enum, timeout: float = None) -> bool:
        """
        Wait for a specific event to be set and then automatically clear it to reset the state.
        Args:
            notification (Enum): The event type to wait for.
            timeout (float, optional): The maximum time to wait for the event, in seconds.
            If None, wait indefinitely.
        Returns:
            bool: True if the event was set within the timeout, False otherwise.
        """
        event = self.event_map[notification]
        result = event.wait(timeout)
        event.clear()
        return result

    def clear(self, notification: Enum):
        """Clear the event associated with a specific notification type."""
        event = self.event_map[notification]
        event.clear()

    def wait_any(self, timeout: float = None) -> bool:
        """
        Wait until any of the specified events are triggered. The 'any_event_triggered' event
        is automatically reset after the wait to prepare for the next set of events.
        Args:
            timeout (float, optional): The maximum time to wait for any event in seconds.
                                       If None, wait indefinitely.
        Returns:
            bool: True if any event was set within the timeout period, False otherwise.
        """
        result = self.any_event_triggered.wait(timeout)
        self.any_event_triggered.clear()
        return result

    def is_set(self, notification: Optional[Enum] = None) -> bool:
        """
        Check whether specific notification events are 'set' (meaning actions are pending for them).
        If no specific notification is provided, checks if any events are 'set'.
        Args:
            notification (Optional[Enum]): The specific notification to check.
                                           If None, check all notifications.
        Returns:
            bool: True if the specified event or any event is set (actions pending), False otherwise.
        """
        if notification:
            return self.event_map[notification].is_set()
        else:
            return any(event.is_set() for event in self.event_map.values())

    def reset_all(self):
        """Reset all events to the non-set state."""
        for event in self.event_map.values():
            event.clear()
        self.any_event_triggered.clear()


class DataSizeFormatter:
    """
    FDisplay data sizes in human-readable formats (e.g., KB, MB, GB).
    """

    UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    """Standard units for data size."""

    def __init__(self, bytes_size: int):
        """
        Initializes the DataSizeFormatter with a size in bytes.
        Args:
            bytes_size: The data size in bytes (integer).
        """
        if not isinstance(bytes_size, int) or bytes_size < 0:
            raise ValueError("bytes_size must be a non-negative integer.")
        self._bytes_size = bytes_size

    @property
    def bytes(self) -> int:
        """Returns the data size in bytes."""
        return self._bytes_size

    def to_human_readable(self, decimal_places: int = 2) -> str:
        """
        Converts the data size to a human-readable string with appropriate units.
        Args:
            decimal_places: The number of decimal places for the converted value.
                Defaults to 2.
        Returns:
            A string representing the data size in a human-readable format.
        """
        if self._bytes_size == 0:
            return "0 B"

        if not isinstance(decimal_places, int) or decimal_places < 0:
            raise ValueError("decimal_places must be a non-negative integer.")

        i = 0
        bytes_val = float(self._bytes_size)
        while bytes_val >= 1024 and i < len(self.UNITS) - 1:
            bytes_val /= 1024
            i += 1

        return f"{bytes_val:.{decimal_places}f} {self.UNITS[i]}"

    def __str__(self) -> str:
        """
        Returns the human-readable representation as the default string representation.
        """
        return self.to_human_readable()

    def __repr__(self) -> str:
        """
        Returns a developer-friendly representation of the object.
        """
        return f"DataSizeFormatter(bytes_size={self._bytes_size})"


class SDKType:
    """
    Singleton container for all dynamically registered core modules in the AutoForge SDK.
    This class acts as a runtime service locator, allowing core modules (such as telemetry,
    logging, toolchains, and platform tools) to self-register and expose themselves through
    a centralized global instance.

    Unlike traditional dataclasses, this implementation does **not** declare fixed attributes.
    Instead, it dynamically injects fields based on core module class names, which are converted
    to standardized `snake_case` identifiers (e.g., `CoreXRayDB` → `xray_db`). This avoids static
    annotation boilerplate and keeps the class extensible.

    Registration:
        Each core module should inherit from `CoreModuleInterface`, which invokes `SDKType.get_instance().register(self)`
        automatically during its initialization. This mechanism ensures the module becomes accessible
        via the global SDK instance.
    """

    _instance: ClassVar[Optional["SDKType"]] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __getattr__(self, name: str) -> Any:
        """
        Escape hatch for IDEs to prevent 'Cannot find reference' warnings.
        All dynamically injected core modules go through here if not declared.
        """
        raise AttributeError(f"{name!r} is not defined in SDKType")

    @classmethod
    def get_instance(cls) -> "SDKType":
        return cls()

    def register(self, instance: object) -> None:
        """
        Registers a core module instance into the SDK singleton under a snake_case name
        derived from its class name (e.g., CoreTelemetry → telemetry).
        """

        _ACRONYMS = {"AI", "JSONC", "XRay", "DB", "SDK"}

        def _camel_to_snake(_name: str) -> str:
            """
            Converts CamelCase to snake_case, correctly preserving known acronyms
            and inserting underscores between consecutive acronym groups.
            """
            _name = re.sub(r'^Core', '', _name)
            acr_pattern = '|'.join(sorted(_ACRONYMS, key=len, reverse=True))
            pattern = rf'(?:{acr_pattern})|[A-Z][a-z]*|\d+'
            parts = re.findall(pattern, _name)
            return '_'.join(part.lower() for part in parts)

        # Light check that the class inherits from the core interface abstract class
        if not any(base.__name__ == "CoreModuleInterface" for base in instance.__class__.__mro__):
            raise TypeError(f"{instance.__class__.__name__} must inherit from 'CoreModuleInterface'")

        class_name = instance.__class__.__name__
        stripped = class_name[4:] if class_name.startswith("Core") else class_name
        snake_name = _camel_to_snake(stripped)

        if hasattr(self, snake_name):
            raise ValueError(f"instance named '{snake_name}' already registered")

        setattr(self, snake_name, instance)
