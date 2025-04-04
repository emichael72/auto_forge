#!/usr/bin/env python3
"""
Script:         __init__.py
Author:         Intel AutoForge team

Description:
    This module serves as the centralized import hub for the AutoForge application, managing the import of essential
    modules and configurations. It is critical not to reorganize the import order
    automatically (e.g., by IDE tools like PyCharm) as the sequence may impact application behavior due to
    dependencies and initialization order required by certain components.
"""

# Main module imports must not be optimized by PyCharm, order  does matter here.
# noinspection PyUnresolvedReferences
from auto_forge.logger import logger, logger_setup, logger_counter, logger_get_filename, logger_close
from auto_forge.core.json_processor import JSONProcessorLib
from auto_forge.core.variables import VariablesLib
from auto_forge.core.binary_signatures import (SignaturesLib, SignatureFileHandler, Signature,
                                               SignatureField, SignatureSchema)
from auto_forge.core.solution_processor import SolutionProcessorLib

# Globals provided by the project setting module
from .settings import PROJECT_BASE_PATH, PROJECT_CONFIG_PATH, PROJECT_VERSION, PROJECT_NAME, PROJECT_REPO, PROJECT_PACKAGE
from auto_forge.auto_forge import AutoForge, auto_forge_main as main

# Exported symbols
__all__ = [
    "JSONProcessorLib",
    "VariablesLib",
    "SignaturesLib",
    "SolutionProcessorLib",
    "SignatureFileHandler",
    "Signature",
    "SignatureSchema",
    "PROJECT_BASE_PATH",
    "PROJECT_CONFIG_PATH",
    "PROJECT_VERSION",
    "PROJECT_NAME",
    "PROJECT_REPO",
    "PROJECT_PACKAGE",
    "logger",
    "logger_setup",
    "logger_close",
    "logger_get_filename",
    "logger_counter",
    "main"
]
