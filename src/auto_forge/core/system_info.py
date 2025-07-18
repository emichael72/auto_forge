"""
Script:         system_info.py
Author:         AutoForge Team

Description:
    Provides the SystemInfo class and supporting enums for collecting detailed system
    information such as OS type, distribution, architecture, user environment, package
    manager, virtualization/container status, and system uptime.
"""

import getpass
import grp
import os
import platform
import pwd
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Optional, Tuple

import psutil
from git import GitConfigParser

# AutoForge imports
from auto_forge import (
    AutoForgeModuleType, CoreModuleInterface, CoreRegistry, CoreTelemetry, CoreLogger, DataSizeFormatter,
    SysInfoLinuxDistroType, SysInfoPackageManagerType)

AUTO_FORGE_MODULE_NAME = "SystemInfo"
AUTO_FORGE_MODULE_DESCRIPTION = "System information collector"


class CoreSystemInfo(CoreModuleInterface):

    def __init__(self, *args, **kwargs):
        """
        Extra initialization required for assigning runtime values to attributes declared
        earlier in `__init__()` See 'CoreModuleInterface' usage.
        """
        super().__init__(*args, **kwargs)

    def _initialize(self) -> None:
        """
        Initialize CoreSystemInfo and collect system metadata. This includes platform type,
        virtualization/container status, user and host info, package manager, memory,
        and (on Linux) distribution details.
        """
        self._core_logger = CoreLogger.get_instance()
        self._logger = self._core_logger.get_logger(name=AUTO_FORGE_MODULE_NAME)
        self._telemetry: CoreTelemetry = CoreTelemetry.get_instance()
        self._registry = CoreRegistry.get_instance()

        # Dependencies check
        if None in (self._core_logger, self._logger, self._telemetry, self._registry):
            raise RuntimeError("failed to instantiate critical dependencies")

        self._system_type: str = platform.system().lower()
        self._is_wsl: bool = "wsl" in platform.release().lower()
        self._wsl_home: Optional[str] = self._get_windows_home_from_wsl() if self._is_wsl else None
        self._wsl_c_mount: Optional[str] = self._resolve_wsl_c_mount() if self._is_wsl else None
        self._is_docker: bool = self._detect_docker()
        self._architecture: str = platform.machine()
        self._python_version: str = platform.python_version()
        self._python_venv: Optional[str] = self._get_py_venv()
        self._hostname: str = socket.gethostname()
        self._ip_address: Optional[str] = self._get_ip_address()
        self._is_admin: bool = self._is_admin()
        self._uptime: Optional[float] = self._get_uptime()
        self._cpu_count: Optional[int] = self._get_cpu_count()
        self._username: str = getpass.getuser()
        self._package_manager: Optional[SysInfoPackageManagerType] = self._detect_package_manager()
        self._linux_distro: Optional[SysInfoLinuxDistroType] = None
        self._linux_version: Optional[str] = None
        self._linux_shell: Optional[str] = self._detect_login_shell()
        self._linux_kernel_version: Optional[str] = self._get_linux_kernel_version()
        self._virtualization: Optional[str] = self._detect_virtualization()
        self._git_name: Optional[str] = None
        self._git_email: Optional[str] = None
        self._gfx: str = self._get_desktop_and_gfx()
        self._launch_arguments = ' '.join(shlex.quote(arg) for arg in sys.argv[1:])
        self._info_data: Optional[dict] = None
        self._total_memory_mb: Optional[DataSizeFormatter] = None
        self._available_memory_mb: Optional[DataSizeFormatter] = None

        # Try to fish the email and the fill name from git
        self._git_name, self._git_email = self._get_git_user_info()

        if self._system_type == "linux":
            self._linux_distro, self._linux_version = self._get_linux_distro()

        system_ram = self._get_total_and_available_memory()
        if system_ram:
            total_kb, available_kb = system_ram
            self._total_memory = DataSizeFormatter(total_kb * 1024)
            self._available_memory = DataSizeFormatter(available_kb * 1024)

        # Pack into a dictionary
        self._info_data = {"system_type": self._system_type.title(), "is_wsl": self._is_wsl,
                           "cpu_count": self._cpu_count or -1,
                           "wsl_home": self._wsl_home if self._wsl_home else None,
                           "wsl_c_mount": self._wsl_c_mount if self._wsl_c_mount else None,
                           "is_docker": self._is_docker,
                           "work_path": os.getcwd(), "pid": os.getpid(),
                           "disk_usage": self._get_disk_usage(),
                           "architecture": self._architecture, "python_version": self._python_version,
                           "python_venv": self._python_venv if self._python_venv else None, "hostname": self._hostname,
                           "ip_address": self._ip_address if self._ip_address else None, "is_admin": self._is_admin,
                           "username": self._username,
                           "package_manager": self._package_manager.name if self._package_manager else None,
                           "linux_distro": self._linux_distro.name.title() if self._linux_distro else None,
                           "distro_version": self._linux_version,
                           "total_memory_mb": self._total_memory if self._total_memory else None,
                           "available_memory_mb": self._available_memory if self._available_memory else None,
                           "linux_kernel_version": self._linux_kernel_version,
                           "linux_shell": self._linux_shell if self._linux_shell else None,
                           "virtualization": self._virtualization or "Unknown",
                           "launch_arguments": self._launch_arguments,
                           "full_name": self._git_name if self._git_name else None,
                           "email_address": self._git_email if self._git_email else None,
                           "gfx": self._gfx, "uptime": self._uptime}

        # Register this module with the package registry
        self._registry.register_module(name=AUTO_FORGE_MODULE_NAME, description=AUTO_FORGE_MODULE_DESCRIPTION,
                                       auto_forge_module_type=AutoForgeModuleType.CORE)

        # Inform telemetry that the module is up & running
        self._telemetry.mark_module_boot(module_name=AUTO_FORGE_MODULE_NAME)

    @staticmethod
    def _get_linux_distro() -> Tuple[SysInfoLinuxDistroType, str]:
        """
        Retrieve the Linux distribution as a standardized enum and version string.
        Returns:
            Tuple[SysInfoLinuxDistroType, str]: (Distro enum, version ID), or (UNKNOWN, "") if not found.
        """
        with suppress(Exception):
            with open("/etc/os-release") as f:
                data = {}
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        data[k] = v.strip('"')
                distro_id = data.get("ID", "").lower()
                version_id = data.get("VERSION_ID", "")
                return SysInfoLinuxDistroType.from_id(distro_id), version_id

        return SysInfoLinuxDistroType.UNKNOWN, ""

    @staticmethod
    def _get_disk_usage() -> str:
        """
        Get Disk space usage summary for the root filesystem.
        Returns:
            str: A human-readable string summarizing total, used, and free disk space in GB.
                 Returns an error message if disk usage can't be retrieved.
        """
        try:
            total_disk, used_disk, free_disk = shutil.disk_usage('/')

            # Convert bytes to Gigabytes for human readability
            total_gb = total_disk / (1024 ** 3)
            used_gb = used_disk / (1024 ** 3)
            free_gb = free_disk / (1024 ** 3)
            return f"Disk: Total {total_gb:.2f} GB, Used {used_gb:.2f} GB, Free {free_gb:.2f} GB"
        except Exception as e:
            return f"Error retrieving disk usage: {e}"

    # noinspection SpellCheckingInspection
    @staticmethod
    def _get_desktop_and_gfx() -> str:
        """Detect the running desktop environment and graphics system (Linux only)."""
        with suppress(Exception):
            # Try to detect desktop environment
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION")

            # Try to detect display server
            if os.environ.get("WAYLAND_DISPLAY"):
                display_server = "Wayland"
            elif os.environ.get("DISPLAY"):
                display_server = "X11"
            else:
                display_server = "Unknown"

            # Try to get GPU info using lspci
            with suppress(Exception):
                lspci_output = subprocess.check_output(["lspci"], text=True)
                gpu_info = next((line for line in lspci_output.splitlines() if "VGA compatible controller" in line),
                                None)
            gpu_desc = gpu_info if gpu_info else "GPU info not found"

            return f"{desktop_env or 'Unknown Desktop'} | {display_server} | {gpu_desc}"

        return "Unknown Desktop/GFX"

    @staticmethod
    def _detect_package_manager() -> Optional[SysInfoPackageManagerType]:
        """
        Detect the available package manager on the system.
        Returns:
            Optional[SysInfoPackageManagerType]: Detected package manager enum value, or None if none found.
        """
        with suppress(Exception):
            for pm in SysInfoPackageManagerType:
                if shutil.which(pm.value):
                    return pm
        return None

    # noinspection SpellCheckingInspection
    def _get_total_and_available_memory(self) -> Optional[Tuple[int, int]]:
        """
        Retrieve the total and free usable system memory in kilobytes.
        Returns:
            Tuple[int, int]: (Total memory in kB, Free usable memory in kB) if successfully determined, else None.
        """
        total_memory_kb = None
        available_memory_kb = None

        with suppress(Exception):
            if self._system_type == "linux":
                with open("/proc/meminfo") as f:
                    meminfo = f.readlines()  # Read all lines once

                # Iterate through meminfo to find the relevant lines
                mem_total_line = None
                mem_available_line = None
                for line in meminfo:
                    if line.startswith("MemTotal:"):
                        mem_total_line = line
                    elif line.startswith("MemAvailable:"):
                        mem_available_line = line
                    # Optimization: if both are found, break early
                    if mem_total_line and mem_available_line:
                        break

                if mem_total_line:
                    # /proc/meminfo values are already in KB
                    total_memory_kb = int(mem_total_line.split()[1])
                if mem_available_line:
                    # /proc/meminfo values are already in KB
                    available_memory_kb = int(mem_available_line.split()[1])

            elif self._system_type == "darwin":
                # Total memory (hw.memsize is in bytes, so divide by 1024 to get KB)
                output_total = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
                total_memory_kb = int(output_total) // 1024

                # Available memory using psutil (psutil.available is in bytes, divide by 1024 for KB)
                vmem = psutil.virtual_memory()
                available_memory_kb = vmem.available // 1024

            elif self._system_type == "windows":
                # psutil.total and psutil.available are in bytes, divide by 1024 for KB
                vmem = psutil.virtual_memory()
                total_memory_kb = int(vmem.total) // 1024
                available_memory_kb = int(vmem.available) // 1024

        if total_memory_kb is not None and available_memory_kb is not None:
            return total_memory_kb, available_memory_kb
        return None

    @staticmethod
    def _get_uptime() -> Optional[str]:
        """
        Retrieve the system uptime in a human-readable format: 'Xd Yh Zm'.
        Returns:
            str: Uptime in a human-readable format, or None if it could not be determined.
        """
        with suppress(Exception):
            seconds = None
            if platform.system().lower() == "linux":
                with open("/proc/uptime") as f:
                    seconds = float(f.readline().split()[0])
            elif platform.system().lower() == "darwin":
                # noinspection SpellCheckingInspection
                output = subprocess.check_output(["sysctl", "-n", "kern.boottime"]).decode()
                match = re.search(r"sec = (\d+)", output)
                if match:
                    boot_time = int(match.group(1))
                    seconds = time.time() - boot_time

            if seconds is not None:
                minutes, _ = divmod(int(seconds), 60)
                hours, minutes = divmod(minutes, 60)
                days, hours = divmod(hours, 24)
                return f"{days}d {hours}h {minutes}m"

        return None

    @staticmethod
    def _detect_login_shell() -> Optional[str]:
        """
        Detects the user's default login shell using the most reliable methods available.
        Tries, in order:
        1. The SHELL environment variable.
        2. The current shell path via /proc/self/exe (Linux-specific).
        3. The user's login shell from /etc/passwd.
        Returns:
            Optional[str]: The absolute path to the shell binary, or None if detection failed.
        """
        # Try SHELL environment variable
        shell_env = os.environ.get("SHELL")
        if shell_env and shutil.which(shell_env):
            return shell_env

        # Try /proc/self/exe (current process executable)
        with suppress(Exception):
            shell_from_proc = os.readlink("/proc/self/exe")
            if shell_from_proc and shutil.which(shell_from_proc):
                return shell_from_proc

        # Try /etc/passwd entry
        with suppress(Exception):
            user_entry = pwd.getpwuid(os.getuid())
            if user_entry and shutil.which(user_entry.pw_shell):
                return user_entry.pw_shell

        return None

    @staticmethod
    def _get_ip_address() -> Optional[str]:
        """ Retrieve host IP address """
        with suppress(Exception):
            # Connect to an external host to determine IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Google's DNS
            ip = s.getsockname()[0]
            s.close()
            return ip

        return None

    @staticmethod
    def _is_admin() -> bool:
        """Check if the user has root privileges or belongs to a Linux admin group."""
        with suppress(Exception):
            if os.geteuid() == 0:
                return True  # Root user
            user = getpass.getuser()
            groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]
            return any(g in ('sudo', 'admin', 'wheel') for g in groups)

        return False

    @staticmethod
    def _get_py_venv() -> Optional[str]:
        """Return the Python version and venv path if in a virtual environment, else None."""
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            return f"{sys.version.split()[0]} (venv: {sys.prefix})"
        elif venv := os.getenv('VIRTUAL_ENV'):
            return f"{sys.version.split()[0]} (venv: {venv})"
        return None

    @staticmethod
    def _get_git_user_info() -> Tuple[Optional[str], Optional[str]]:
        """
        Attempts to retrieve the user's name and email from the global Git configuration.
        Returns:
            Optional[Tuple[str, str]]: A tuple of (name, email) if found, otherwise None.
        """
        config_path = Path.home() / ".gitconfig"
        config = GitConfigParser(config_path, read_only=True)

        with suppress(Exception):
            name = config.get_value('user', 'name')
            email = config.get_value('user', 'email')
            return name, email

        return None, None

    @staticmethod
    def _resolve_wsl_c_mount() -> Optional[str]:
        """
        Returns the path to the WSL-mounted Windows C: drive if available.
        Returns:
            str, optional: '/mnt/c' if it exists and is accessible, otherwise None.
        """
        path = "/mnt/c"
        if os.path.ismount(path) and os.access(path, os.R_OK | os.X_OK):
            return path
        return None

    @staticmethod
    def _get_windows_home_from_wsl() -> Optional[str]:
        """ Best effort to returns the WSL-accessible Windows user home path """
        with suppress(Exception):
            # Try USERPROFILE or HOME from environment
            for env_var in ("USERPROFILE", "HOME"):
                path = os.environ.get(env_var)
                if path and path.startswith("/mnt/c/Users/") and os.path.isdir(path):
                    return path.replace("\\", "/")

            # Try constructing /mnt/c/Users/<username> fallback
            username = os.environ.get("USERNAME") or os.environ.get("USER")
            if username:
                candidate = f"/mnt/c/Users/{username}"
                if os.path.isdir(candidate):
                    return candidate
        return None

    # noinspection SpellCheckingInspection
    @staticmethod
    def _detect_virtualization() -> Optional[str]:
        """
        Detect if the system is running in a virtualized or containerized environment.
        Returns:
            str: Virtualization/container type (e.g., 'kvm', 'vmware', 'lxc', 'docker'), or None if undetectable.
        """
        with suppress(Exception):
            if shutil.which("systemd-detect-virt"):
                result = subprocess.run(["systemd-detect-virt"], capture_output=True, text=True)
                virt_type = result.stdout.strip().title()
                if virt_type and virt_type != "none":
                    return virt_type

        return None

    @staticmethod
    def _detect_docker() -> bool:
        """
        Detect whether the system is running inside a Docker container.
        Returns:
            bool: True if Docker is detected, False otherwise.
        """
        with suppress(Exception):
            with open("/proc/1/cgroup", "rt") as f:
                return any("docker" in line for line in f)
        return False

    @staticmethod
    def _get_cpu_count() -> Optional[int]:
        """
        Return the number of logical CPUs available to the current process.
        This reflects any cgroup restrictions (e.g. in containers) and falls back
        to the total visible CPU count if no limits are in place.

        Returns:
            int: The number of usable logical CPUs, or None if detection fails.
        """
        # Check cgroup v2 cpu.max first
        with suppress(Exception):
            if os.path.exists("/sys/fs/cgroup/cpu.max"):
                quota_str, period_str = open("/sys/fs/cgroup/cpu.max").read().strip().split()
                if quota_str != "max":
                    quota = int(quota_str)
                    period = int(period_str)
                    if quota > 0 and period > 0:
                        return max(1, round(quota / period))

        # Fallback to total logical CPUs
        with suppress(Exception):
            count = psutil.cpu_count(logical=True)
            if isinstance(count, int) and count > 0:
                return count

        return None

    @staticmethod
    def _get_linux_kernel_version() -> Optional[str]:
        # noinspection GrazieInspection
        """
        Retrieves the Linux kernel version using the platform module.
        Returns a string similar to 'uname -a' output (or a subset of it),
        or None if not on Linux or if information cannot be retrieved.
        """
        if platform.system() != "Linux":
            # This method is intended for Linux systems only.
            return None

        with suppress(Exception):
            uname_info = platform.uname()
            kernel_string = (f"{uname_info.system} {uname_info.node} {uname_info.release} "
                             f"{uname_info.version} {uname_info.machine}")
            # Add processor if available
            if uname_info.processor:
                kernel_string += f" {uname_info.processor}"

            return kernel_string.strip()

        # An error occurred while retrieving kernel information
        return None

    def to_markdown(self, as_table: bool = True, heading_level: int = 2) -> str:
        """
        Return system info as a Markdown-formatted string.
        Args:
            as_table (bool): If True, format as a table. If False, format as a bulleted list.
            heading_level (int): Number of '#' characters for headings (1-6 recommended).
        Returns:
            str: Markdown-formatted representation of system info.
        """

        base_level = max(1, min(heading_level, 6))
        heading_prefix = "#" * base_level
        lines = [f"{heading_prefix} System Information", ""]

        for key, value in self._info_data.items():
            # Normalize value
            if value is None or value == "":
                continue
            elif isinstance(value, (list, tuple)):
                value_str = ", ".join(map(str, value))
            elif isinstance(value, dict):
                value_str = ", ".join(f"{k}: {v}" for k, v in value.items())
            else:
                value_str = str(value)

            # Escape pipes and prettify keys
            key_escaped = key.replace("|", "\\|").replace('_', ' ').title()
            value_escaped = value_str.replace("|", "\\|")

            if as_table:
                if len(lines) == 2:
                    lines.append("| Key | Value |")
                    lines.append("|-----|-------|")
                lines.append(f"| `{key_escaped}` | {value_escaped} |")
            else:
                lines.append(f"- {key_escaped}: {value_escaped}\n")

        return "\n".join(lines)

    def __str__(self) -> str:
        """
        Return a human-readable, formatted string of system information.
        Returns:
            str: A multi-line string representing key system details.
        """

        def _beautify_key(key: str) -> str:
            return key.replace('_', ' ').title()

        info_summary = "\n".join(
            f"{_beautify_key(k):20}: {v if v is not None else 'N/A'}" for k, v in self._info_data.items())

        return f"System Information:\n{info_summary}"

    @property
    def get_data(self) -> Optional[dict]:
        """ Return a dictionary containing the collected information """
        return self._info_data

    @property
    def distro(self) -> Optional[str]:
        """ Return the Linux distro name. """
        return self._linux_distro

    @property
    def is_wsl(self) -> Optional[bool]:
        """ Return true if we're running under WSL """
        return self._is_wsl

    @property
    def wsl_home(self) -> Optional[bool]:
        """ Return the user WSL Windows home path when running on WSL """
        return self._wsl_home

    @property
    def wsl_c_mount(self) -> Optional[bool]:
        """  Return the status of the WSL C: drive mount """
        return self._wsl_c_mount

    @property
    def linux_shell(self) -> None:
        """ Returns the detected Linux user default shell """
        return CoreSystemInfo._detect_login_shell()

    @property
    def cpu_count(self) -> Optional[int]:
        """ 
        Returns the detected number of logical CPUs available to this process. 
        This may reflect cgroup restrictions (e.g. in containers or LXC) if applicable. 
        """
        return self._cpu_count
