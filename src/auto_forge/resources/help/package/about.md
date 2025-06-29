# 🛠️ Welcome to AutoForge

<!--suppress HtmlDeprecatedAttribute -->

**AutoForge** is an extensible, Python-based framework designed to streamline complex build and validation workflows
across embedded and software systems. Built with automation, clarity, and scalability in mind,
it enables developers to define, run, and manage sophisticated build pipelines with minimal
friction and maximum control.

### In A Nutshell

At its core, **AutoForge** transforms JSON-based declarative definitions into fully automated build flows.
It handles everything from environment setup and configuration validation to build orchestration,
structured logging, error recovery, and post-build analytics.
Whether you're compiling a single RTOS image or coordinating cross-platform
toolchains, this tool offers a unified interface to get the job done efficiently.

### Key Features

- **Declarative Build Recipes**  
  Define and reuse build flows using structured, human-readable JSONC files with support for dynamic variable
  resolution and dependency injection.

- **Modular CLI Framework**  
  Add and extend functionality via self-registering Python modules that conform to a common `CLICommandInterface`. The
  system includes a user-friendly interactive shell with support for tab-completion, history-based suggestions, and
  contextual
  help.

- **Integrated Help System**  
  Discover commands, arguments, and usage examples via a built-in help interface accessible from the terminal without
  leaving your workflow.

- **Robust Logging and Telemetry**  
  Structured, colorized logs and build-time telemetry for auditability and debugging across local and CI environments.

- **Environment Virtualization & Probing**  
  Automated setup and teardown of environment variables, toolchains, and paths including native detection of SDKs, tool
  versions, and platform capabilities.

- **Plugin-Based Extensibility**  
  Dynamically discoverable plugins let teams introduce new command types, validators, and tool integrations without
  altering the core.

### AI-Friendly by Design

**AutoForge's** predictable structure, rich metadata, and standardized error handling make it ideal for AI-assisted
development **and debugging. Its JSON-based configuration, uniform logging,
and consistent directory layout allow AI tools to:

- Understand project state quickly
- Locate build artifacts and failures reliably
- Offer actionable suggestions with minimal context

This makes this tool particularly suitable for advanced workflows involving intelligent
assistants and automated analysis tools.

---

## 🧩 Runtime Dependencies

| Package             | Description                                                                                  | License (Model)    |
|---------------------|----------------------------------------------------------------------------------------------|--------------------|
| `packaging`         | Parse and compare package versions and requirements.                                         | Apache License 2.0 |
| `wheel`             | Build standard Python wheel distribution packages.                                           | MIT                |
| `opentelemetry-api` | Core telemetry API for tracing and metrics instrumentation.                                  | Apache License 2.0 |
| `opentelemetry-sdk` | SDK implementation for OpenTelemetry API (exporters, processors).                            | Apache License 2.0 |
| `colorama`          | Cross-platform colored terminal text (Windows ANSI compatibility).                           | BSD 3-Clause       |
| `rich`              | Modern terminal formatting library for text, tables, trees, progress bars, etc.              | MIT                |
| `tabulate`          | Pretty-print tabular data in various formats (plain, HTML, grid, etc.).                      | MIT                |
| `pyfiglet`          | Render text as ASCII art using FIGlet fonts.                                                 | MIT                |
| `psutil`            | Access system and process info (CPU, memory, disks, network).                                | BSD 3-Clause       |
| `toml`              | Parser for TOML configuration files.                                                         | MIT                |
| `gitpython`         | Git repository access and automation via Python interface.                                   | BSD 3-Clause       |
| `jsonpath-ng`       | Extract values from nested JSON structures using JSONPath expressions.                       | Apache License 2.0 |
| `json5`             | Parser for relaxed JSON (comments, trailing commas, etc.).                                   | MIT                |
| `jsonschema`        | Validate JSON data structures against defined schemas (Draft 4+).                            | MIT                |
| `pyaml`             | Thin wrapper around PyYAML for cleaner YAML serialization.                                   | MIT                |
| `ruamel.yaml`       | YAML parser/emitter that preserves comments and formatting.                                  | MIT                |
| `prompt_toolkit`    | Powerful interactive command-line interface (CLI) toolkit.                                   | BSD 3-Clause       |
| `jmespath`          | Query language for filtering JSON data (used by AWS tools).                                  | MIT                |
| `textual`           | Terminal UI framework for building rich text user interfaces with layout, mouse, async, etc. | MIT                |
| `whoosh`            | Pure-Python search engine library for indexing and querying text.                            | BSD                |
| `watchdog`          | Monitor filesystem changes across platforms (used in hot reload, file triggers).             | Apache License 2.0 |
| `pynput`            | Control and monitor keyboard/mouse input, used for productivity tracking.                    | GPLv3 (copyleft)   |
| `cmd2`              | Enhances standard cmd module with features like auto-completion, history, and scripting.     | MIT                |

---

## Awesome! What's In It For Me?

If you're tired of scattered shell scripts, fragile CI jobs, and inconsistent build behaviors **AutoForge** gives you a
single, maintainable system for reproducible builds, insightful logs, and a consistent developer experience across the
board.

## The Demo Project

The following link installs the `userspace` demo solution.
Rather than replacing your existing `userspace` build flow, this demo is designed to overlay an
already cloned repository. This approach lets you explore the tool in a realistic environment
without disrupting your current working setup.

### 🛠 Prerequisites

Before we continue, make sure the following tools are installed:

- `dt` Developer Tool:  
  Intel-internal command-line tool used to link your private GitHub account with your Intel SSO, allowing access to
  Intel’s private repositories.

- Usually preinstalled — if not, just add them manually:
  > 📦 Install via package manager:  
  `sudo dnf install cmake ninja-build`

### Setup Instructions

Copy and paste the following into your terminal.

```bash

# The following command does quite a bit. Here's a breakdown:
#
# 1. Uses the 'dt' tool to retrieve a GitHub token for accessing Intel private repositories.
# 2. Downloads the 'bootstrap' script from the package Git repo using 'curl' and executes it.
#
# The 'bootstrap' script then:
#
# 3. Installs the latest AutoForge package into the user scope (via pip).
# 4. Loads the built-in 'userspace' sample.
# 5. Uses the solution also named 'userspace' from that sample.
# 6. Creates a new workspace in a local folder named 'ws'.
# 7. Runs the 'create_environment_sequence' defined by the solution, which:
#    - Verifies required tools are installed,
#    - Creates a dedicated Python virtual environment,
#    - Installs required Python packages,
#    - Performs any additional setup defined by the solution.
#
# ⚠ No 'sudo' is required, and no files are deleted without consent.

GITHUB_REPO="intel-innersource/firmware.ethernet.devops.auto_forge"
GITHUB_TOKEN=$(dt github print-token https://github.com/${GITHUB_REPO})

curl -sSL \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Cache-Control: no-store" \
  "https://raw.githubusercontent.com/${GITHUB_REPO}/main/src/auto_forge/resources/shared/bootstrap.sh" \
  | bash -s -- \
      -n userspace \
      -w ws \
      -s create_environment_sequence \
      -p "<samples>/userspace"
```

Got ideas or improvements?<br>Jump in and help make **AutoForge** even better - contributions are always welcome!

## License

This project is licensed under the MIT License—see the LICENSE file for details.
