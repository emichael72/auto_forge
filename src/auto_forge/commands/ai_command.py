"""
Module: ai_command.py
Author: AutoForge Team

Description:
    This command defines miscellaneous AI-related commands for e.g:
    - Chat: Enables free-form user interaction with the system's registered AI model and engine.
    - Providers: Allows importing and exporting stored AI provider information.
"""

import argparse
import asyncio
import re
from typing import Any, Optional

# Third-party
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

# AutoForge imports
from auto_forge import (CommandInterface, TerminalSpinner, AutoForgCommandType)

AUTO_FORGE_MODULE_NAME = "ai"
AUTO_FORGE_MODULE_DESCRIPTION = "AI Playground"
AUTO_FORGE_MODULE_VERSION = "1.0"


class AICommand(CommandInterface):
    """
    Implements a command to allow interacting with an AI.
    """

    def __init__(self, **_kwargs: Any):
        """
        Initializes the EditCommand class.
        Args:
            **_kwargs (Any): Optional keyword arguments, such as:
        """

        self._console = Console(force_terminal=True)
        self._system_info_data = self.sdk.system_info.get_data

        # Base class initialization
        super().__init__(command_name=AUTO_FORGE_MODULE_NAME, hidden=False, command_type=AutoForgCommandType.AI)

    @staticmethod
    def _sanitize_prompt(text: str) -> str:
        # Replace smart quotes with regular quotes
        text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

        # Normalize white-spaces
        text = re.sub(r'\s+', ' ', text)

        # Escape backslashes and quotes to avoid breaking string parsing if needed downstream
        text = text.replace('\\', '\\\\').replace('"', '\\"')
        return text.strip()

    async def _async_query_from_nl(self, user_prompt: str):
        """
        Uses the AI assistant to generate a SQL query based on a natural language prompt,
        and prints the resulting SQL to the terminal.

        Args:
            user_prompt (str): The user's natural language query description.
        """

        def _clean_sql_query(_query: str) -> str:
            """
            Cleans up an AI-generated SQL query string by:
            - Removing Markdown code block markers (```sql, ```).
            - Stripping leading/trailing whitespace.
            - Normalizing indentation and removing aligned padding.
            - Collapsing excessive internal whitespace to a single space.
            """
            # Remove markdown code fences
            _query = re.sub(r"```sql\s*|```", "", _query.strip(), flags=re.IGNORECASE)

            # Remove extra indentation/padding from each line
            lines = _query.splitlines()
            stripped_lines = [line.strip() for line in lines if line.strip()]

            # Rejoin and normalize internal spaces for alignment artifacts
            normalized_sql = "\n".join(
                re.sub(r"\s{2,}", " ", line) for line in stripped_lines
            )

            return normalized_sql

        ai_prompt = f"""
        Generate a safe and complete SQL SELECT query based on the user's request.

        Database schema:
        - files(path TEXT, content TEXT)                   -- content is full file source
        - file_meta(path TEXT PRIMARY KEY, modified REAL, checksum TEXT, ext TEXT, base TEXT)
        - meta(key TEXT PRIMARY KEY, value TEXT)

        Important:
        - File extensions are stored in the 'ext' field **without the dot**, e.g., '.py' is stored as 'py'.
        - Do not select the 'content' column unless the user explicitly asks to see file contents.
        - Prefer returning only the 'path' field unless the user clearly asks for more detail.
        - Always fully qualify column names (e.g., files.path, file_meta.ext) when selecting or filtering from multiple tables.
        - Always group OR conditions in parentheses when combined with AND.
        
        Content Search Rules:
        - You may use SQL LIKE or MATCH, but only for literal substring searches.
        - If a user says "uses X", and X is a known package or symbol, match it as code, e.g.:
            - "uses rich" → look for 'import rich' or 'from rich import'
            - "uses numpy" → 'import numpy'
        - Do not match vague terms like 'rich' unless no better keyword is implied.
        - All code content searches (e.g., #define, macros, functions) must be case-sensitive.
        - Use COLLATE BINARY with LIKE, or GLOB for accurate results.
        - Example:
          -- LIKE '%#define MIN%' COLLATE BINARY
          -- GLOB '*#define MIN*'

        Limitations:
        - You cannot match code structure, similarity, or syntax trees.
        - If the request cannot be fulfilled with literal substring matching, return:
        -- UNSUPPORTED REQUEST: Cannot be translated to SQL with available schema.

        Only output a valid SQL SELECT or the unsupported message. No comments or explanation.

        User request: {user_prompt}
        """
        print()
        sql_query: Optional[str] = None
        spin_task = asyncio.create_task(TerminalSpinner.run("Thinking..."))

        try:
            sql_query = await  self.sdk.ai_bridge.query(
                prompt=ai_prompt, context="You are an assistant for querying a SQLite database.")
        finally:
            spin_task.cancel()
            try:
                await spin_task
            except asyncio.CancelledError:
                pass
            print("\r", end='', flush=True)

        if not sql_query or "select" not in sql_query.lower():
            self._logger.warning("AI response does not look like a valid SQL query")
            return

        sql_query = _clean_sql_query(sql_query)

        sql_syntax = Syntax(sql_query, "sql", theme="monokai", line_numbers=False, code_width=80)
        self._console.print(sql_syntax)
        print()

        self.sdk.xray_db.query_raw(query=sql_query, print_table=True)

    async def _async_ask_ai(self, user_prompt: str, response_width: int = 100):
        """
        Asynchronously sends the provided prompt to the AI service and prints the response,
        wrapping regular text and formatting detected code blocks with syntax highlighting.
        Args:
            user_prompt (str): The user's input prompt to be analyzed.
            response_width (int, optional): The width of the response line length.
        """
        print()
        response: Optional[str] = None
        spin_task = asyncio.create_task(TerminalSpinner.run("Thinking..."))

        try:
            response = await  self.sdk.ai_bridge.query(
                prompt=user_prompt)
        finally:
            spin_task.cancel()
            try:
                await spin_task
            except asyncio.CancelledError:
                pass
            print("\r", end='', flush=True)

        if not response:
            self._console.print("[bold red]No response received.[/bold red]")
            print()
            return

        # Detect and format code blocks
        pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
        last_end = 0

        for match in pattern.finditer(response):
            lang = match.group(1) or "text"
            code = match.group(2)
            start, end = match.span()

            # Append wrapped plain text before the code block
            if start > last_end:
                plain_text = response[last_end:start].strip()
                if plain_text:
                    text = Text(plain_text, style="white")
                    wrapped_lines = text.wrap(self._console, width=response_width)
                    wrapped_text = Text()
                    for line in wrapped_lines:
                        wrapped_text.append(line)
                        wrapped_text.append("\n")
                    self._console.print(wrapped_text)

            # Append syntax-highlighted code
            syntax = Syntax(code, lang, word_wrap=True, line_numbers=False)
            self._console.print(Panel(syntax, border_style="cyan", expand=False))
            last_end = end

        # Append wrapped trailing plain text after last code block
        if last_end < len(response):
            trailing_text = response[last_end:].strip()
            if trailing_text:
                text = Text(trailing_text, style="white")
                wrapped_lines = text.wrap(self._console, width=response_width)
                wrapped_text = Text()
                for line in wrapped_lines:
                    wrapped_text.append(line)
                    wrapped_text.append("\n")
                self._console.print(wrapped_text)

    def create_parser(self, parser: argparse.ArgumentParser) -> None:
        """
        Adds command-line arguments for the hello command.
        Args:
            parser (argparse.ArgumentParser): The argument parser to extend.
        """

        # AI providers export and import
        parser.add_argument('-pe', '--providers-export', help='Export AI providers to a JSON file.')
        parser.add_argument('-pi', '--providers-import', help='Import AI providers from a JSON file.')

        parser.add_argument("--db", action="store_true", help="Interpret message as a database search")
        parser.add_argument("message", nargs=argparse.REMAINDER, help="The message or query in natural language")

    def run(self, args: argparse.Namespace) -> int:
        """
        Executes the command based on parsed arguments.
        Args:q
            args (argparse.Namespace): The parsed arguments.
        Returns:
            int: Exit status (0 for success, non-zero for failure).
        """

        if args.message:
            row_message = " ".join(args.message).strip()
            message = self._sanitize_prompt(row_message)

            if args.db:
                asyncio.run(self._async_query_from_nl(user_prompt=message))
            else:
                asyncio.run(self._async_ask_ai(user_prompt=message))
            return 0

        # Export import providers stored information
        elif args.providers_export:
            exit_code = self.sdk.ai_bridge.export_providers(file_name=args.providers_export)
            if exit_code == 0:
                print(f"Successfully exported AI providers to '{args.providers_export}'\n")
            return exit_code

        elif args.providers_import:
            exit_code = self.sdk.ai_bridge.import_providers(file_name=args.providers_import)
            if exit_code == 0:
                print(f"Successfully imported AI providers from '{args.providers_import}'\n")
            return exit_code

        else:
            return CommandInterface.COMMAND_ERROR_NO_ARGUMENTS
