import os
import subprocess
import asyncio
import sys
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
import signal
from io import StringIO
from typing import List, Optional
from langchain_community.tools import DuckDuckGoSearchRun, DuckDuckGoSearchResults

search = DuckDuckGoSearchRun()
 


import tempfile
 
from mcp.server.fastmcp import FastMCP

mcp= FastMCP("mcp")
DEFAULT_WORKSPACE=os.path.expanduser("~/mcp/workspace")

# Track current workspace directory separately
current_workspace_dir = DEFAULT_WORKSPACE


@mcp.tool()
async def run_command(command:str)->str:
    """
    Run a terminal command inside the workspace directory.
    
    Args:
        command: The shell command to run.
    
    Returns:
         The commad output or error message.   

    """

    try:
        result=subprocess.run(command,shell=True,cwd=DEFAULT_WORKSPACE,capture_output=True,text=True)
        return result.stdout or result.stderr
    except Exception as e:
        return str(e)
    
    
@mcp.tool()
async def list_files()->str:
    """
    List files in the workspace directory.
    
    Returns:
        A string listing the files and directories in the workspace.
    """
    try:
        files=os.listdir(current_workspace_dir)
        return "\n".join(files)
    except Exception as e:
        return str(e)


 
@mcp.tool()
def write_file(filename: str, content: str) -> str:
    """
    Write plain text content into a file in the workspace.
    Overwrites the file if it exists.
    """
    # If path is absolute, use it as-is. Otherwise, join with workspace root
    filepath = os.path.join(current_workspace_dir, filename)
    
    try:
        # Create any parent directories if missing
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File {filepath} created with provided content."
    except Exception as e:
        return f"Error writing file {filename}: {e}"



@mcp.tool()
def read_file(filename: str) -> str:
    """
    Read and return the content of a file in the workspace.
    """
    filepath = os.path.join(current_workspace_dir, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {filename}: {e}"



@mcp.tool()
def current_working_directory() -> str:
    """ 
    Get the current logical working directory (inside the workspace).
    """
    return current_workspace_dir


 


@mcp.tool()
def change_directory(path: str) -> str:
    """Change the current logical working directory (restricted inside workspace)."""
    global current_workspace_dir
    try:
        new_path = os.path.abspath(os.path.join(current_workspace_dir, path))

        # Windows-safe check: ensure new_path stays inside DEFAULT_WORKSPACE
        if os.path.commonpath([DEFAULT_WORKSPACE, new_path]) != os.path.abspath(DEFAULT_WORKSPACE):
            return f"Error: Cannot leave the workspace directory."

        if not os.path.isdir(new_path):
            return f"Error: Directory does not exist: {new_path}"

        current_workspace_dir = new_path
        return f"Changed directory to {current_workspace_dir}"
    except Exception as e:
        return f"Error changing directory: {e}"
    

 



@mcp.tool()
def os_name()->str:
    ''' 
    Get the name of the operating system.'''
    
    return os.name
    
 
# Keep track of running processes (for long-lived apps like FastAPI)
running_processes = {}

@mcp.tool()
def run_python(filename: str, mode: str = "auto", timeout: int = 15) -> dict:
    """
    Run a Python file in different modes.

    Args:
        filename (str): The Python file to run (relative to DEFAULT_WORKSPACE).
        mode (str): "auto", "exec", or "subprocess"
            - auto: chooses best mode automatically
            - exec: runs via exec (good for small scripts)
            - subprocess: runs via subprocess.Popen (good for apps like FastAPI)
        timeout (int): Max seconds for exec mode. Ignored for subprocess.
    """
    filepath = os.path.join(DEFAULT_WORKSPACE, filename)
    result = {"success": False, "output": "", "error": "", "pid": None}

    if not os.path.exists(filepath):
        result["error"] = f"File not found: {filepath}"
        return result

    try:
        # Detect mode automatically
        if mode == "auto":
            with open(filepath, "r") as f:
                code_preview = f.read(300).lower()
            if "uvicorn.run" in code_preview or "fastapi" in code_preview:
                mode = "subprocess"
            else:
                mode = "exec"

        # -------- exec mode (fast, short scripts) --------
        if mode == "exec":
            stdout_buffer = StringIO()
            old_stdout = sys.stdout
            sys.stdout = stdout_buffer
            try:
                with open(filepath, "r") as f:
                    code = f.read()
                exec_globals = {"__name__": "__main__", "__file__": filepath}
                exec(code, exec_globals)
                result["success"] = True
                result["output"] = stdout_buffer.getvalue()
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {str(e)}"
            finally:
                sys.stdout = old_stdout

        # -------- subprocess mode (for apps, servers) --------
        elif mode == "subprocess":
            process = subprocess.Popen(
                [sys.executable, filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=DEFAULT_WORKSPACE,
            )
            running_processes[process.pid] = process
            result.update({
                "success": True,
                "mode": mode,
                "output": f"Started process PID={process.pid}",
                "pid": process.pid,
            })

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


@mcp.tool()
def stop_process(pid: int) -> dict:
    """
    Stop a running Python process by PID.
    """
    result = {"success": False, "message": ""}
    process = running_processes.pop(pid, None)

    if process:
        try:
            process.terminate()
            result.update({"success": True, "message": f"Process {pid} terminated."})
        except Exception as e:
            result["message"] = f"Error stopping process {pid}: {e}"
    else:
        result["message"] = f"No running process with PID {pid}"

    return result

  
@mcp.tool()
def check_process_logs(pid: int) -> str:
    try:
        import psutil
        proc = psutil.Process(pid)
        if proc.is_running():
            return f"Process {pid} is running ({proc.status()})"
        return f"Process {pid} finished. Exit code: {getattr(proc, 'returncode', 'unknown')}"
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return f"No accessible process found with PID {pid}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"


@mcp.tool()
def create_react_app_vite(app_name: str, template: str = "react") -> dict:
    """
    Creates a Vite app using `npm create vite@latest` in the background. 
    so once the tool runs it instantly returns and 
    also creates log_file which updates the execution later you can open it and see the result.
    """
    global current_workspace_dir
    app_path = os.path.join(current_workspace_dir, app_name)
    log_file = os.path.join(DEFAULT_WORKSPACE, f"{app_name}_vite_logs.txt")
    
    if os.path.exists(app_path):
        return {"success": False, "message": f"Folder {app_name} already exists."}
    
    try:
        with open(log_file, "w") as f:
            process = subprocess.Popen(
                ["npm", "create", "vite@latest", app_name, "--", "--template", template],
                cwd=DEFAULT_WORKSPACE,
                stdout=f,
                stderr=f,
                text=True,
                shell=(os.name == "nt")
            )
        return {
            "success": True,
            "pid": process.pid,
            "message": f"Started Vite app creation for {app_name}. Logs at {log_file}",
        }
    except Exception as e:
        return {"success": False, "message": f"Error starting Vite app: {e}"}

@mcp.tool()
def install_npm_packages(packages: str = "") -> dict:
    """
    Install npm packages in the workspace.
    - If `packages` is empty, runs `npm install` from package.json.
    - Otherwise, installs the given packages.
    """
    try:
        base_cmd = "npm.cmd" if os.name == "nt" else "npm"  # Windows uses npm.cmd

        cmd = [base_cmd, "install"]
        if packages.strip():
            cmd += packages.split()

        process = subprocess.Popen(
            cmd,
            cwd=current_workspace_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        return {
            "success": True,
            "pid": process.pid,
            "message": f"Started: {' '.join(cmd)} in background. Use PID with check_process_logs to see logs."
        }
    except Exception as e:
        return {"success": False, "message": f"Error running npm install: {e}"}


@mcp.tool()
def create_changelog(version: str, changes: str) -> str:
    """
    Create or append to a CHANGELOG.md file in the workspace.
    """
    changelog_path = os.path.join(current_workspace_dir, "CHANGELOG.md")
    try:
        with open(changelog_path, "a", encoding="utf-8") as f:
            f.write(f"## Version {version}\n")
            f.write(f"{changes}\n\n")
        return f"Changelog updated at {changelog_path}"
    except Exception as e:
        
        return f"Error updating changelog: {e}"


@mcp.tool()
async def insert_file_content(
    filename: str, 
    content: str, 
    row: Optional[int] = None, 
    rows: Optional[List[int]] = None
) -> str:
    """
    Insert content at specific row(s) in a file inside the workspace.

    Args:
        filename: Path to the file (relative to workspace).
        content: Content to insert (string or JSON object).
        row: Row number to insert at (0-based, optional).
        rows: List of row numbers to insert at (0-based, optional).
    """
    filepath = os.path.join(current_workspace_dir, filename)

    try:
        # Handle non-string content (dict, list, etc.)
        if not isinstance(content, str):
            import json
            content = json.dumps(content, indent=4, ensure_ascii=False, default=str)

        if content and not content.endswith('\n'):
            content += '\n'

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        if not os.path.exists(filepath):
            open(filepath, 'w').close()

        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        for i in range(len(lines)):
            if lines[i] and not lines[i].endswith('\n'):
                lines[i] += '\n'

        content_lines = content.splitlines(True)

        if rows is not None:
            rows = sorted(rows, reverse=True)
            for r in rows:
                if r > len(lines):
                    lines.extend(['\n'] * (r - len(lines)))
                for line in reversed(content_lines):
                    lines.insert(r, line)
        elif row is not None:
            if row > len(lines):
                lines.extend(['\n'] * (row - len(lines)))
            for line in reversed(content_lines):
                lines.insert(row, line)
        else:
            lines.extend(content_lines)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return f"Inserted content into '{filepath}'."

    except Exception as e:
        return f"Error inserting content into {filename}: {e}"


@mcp.tool()
async def delete_file_content(
    filename: str, 
    row: Optional[int] = None, 
    rows: Optional[List[int]] = None, 
    substring: Optional[str] = None
) -> str:
    """
    Delete content from a file inside the workspace.
     
    Args:
        filename: Path to the file (relative to workspace).
        row: Row number to delete (0-based).
        rows: List of row numbers to delete (0-based).
        substring: If set, remove only this substring instead of whole row(s).
    """
    filepath = os.path.join(current_workspace_dir, filename)

    try:
        if not os.path.isfile(filepath):
            return f"Error: File '{filepath}' does not exist."

        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        modified = False

        if substring is not None:
            targets = rows if rows is not None else ([row] if row is not None else range(total_lines))
            for r in targets:
                if isinstance(r, int) and 0 <= r < total_lines and substring in lines[r]:
                    lines[r] = lines[r].replace(substring, '')
                    if not lines[r].endswith('\n'):
                        lines[r] += '\n'
                    modified = True
        elif rows is not None:
            for r in sorted(rows, reverse=True):
                if 0 <= r < total_lines:
                    lines.pop(r)
                    modified = True
        elif row is not None:
            if 0 <= row < total_lines:
                lines.pop(row)
                modified = True
        else:
            lines = []
            modified = True

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return f"Updated file '{filepath}' successfully."
        else:
            return f"No matching rows or substrings found in '{filepath}'."

    except Exception as e:
        return f"Error deleting content from {filename}: {e}"


 
@mcp.tool()
async def update_file_content(
    filename: str, 
    content: str, 
    row: Optional[int] = None, 
    rows: Optional[List[int]] = None, 
    substring: Optional[str] = None
) -> str:
    """
    Update content at specific row(s) in a file inside the workspace.
   
    Args:
        filename: Path to the file (relative to workspace).
        content: New content to place.
        row: Row number to update (0-based).
        rows: List of row numbers to update (0-based).
        substring: If set, replace only this substring in the row(s).
    """
    filepath = os.path.join(current_workspace_dir, filename)

    try:
        if not os.path.isfile(filepath):
            return f"Error: File '{filepath}' does not exist."

        if not isinstance(content, str):
            import json
            content = json.dumps(content, indent=4, ensure_ascii=False, default=str)

        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        modified = False

        if substring is not None:
            targets = rows if rows is not None else ([row] if row is not None else range(total_lines))
            for r in targets:
                if isinstance(r, int) and 0 <= r < total_lines and substring in lines[r]:
                    lines[r] = lines[r].replace(substring, content)
                    if not lines[r].endswith('\n'):
                        lines[r] += '\n'
                    modified = True
        elif rows is not None:
            for r in rows:
                if 0 <= r < total_lines:
                    lines[r] = (content if content.endswith('\n') else content + '\n')
                    modified = True
        elif row is not None:
            if 0 <= row < total_lines:
                lines[row] = (content if content.endswith('\n') else content + '\n')
                modified = True
        else:
            lines = [content if content.endswith('\n') else content + '\n']
            modified = True

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return f"Updated file '{filepath}' successfully."
        else:
            return f"No updates applied to '{filepath}'."

    except Exception as e:
        return f"Error updating content in {filename}: {e}"




@mcp.tool()
def web_search(query: str) -> str:
    """
    Perform a web search using DuckDuckGo and return the top results.
    
    Args:
        query: The search query string.
         returns: A string containing the top search results.
        """
    result=search.invoke(query)
    return result


@mcp.tool()
async def ask_user_question(agent_question: str) -> str:
    """
    MCP tool that displays Agent 1's question to the user if the agent wants to understand the requiments or any doubts,
    waits for the user's input (max 60 seconds), 
    and returns the user's answer.
    """
    print(" Agent asks:", agent_question)

    try:
        # Wait up to 60 seconds for user input
        user_answer = await asyncio.wait_for(
            asyncio.to_thread(input, "\nYou: "),
            timeout=60
        )
    except asyncio.TimeoutError:
        print("⌛ No response for 1 minute. Exiting...")
        return ""

    return user_answer

if __name__ == "__main__":
    print("Starting Terminal Server on stdio...")
    mcp.run(transport="stdio")
 

# try:
#     ans=subprocess.check_output(["cmd /c","dir"],text=True)
#     print(ans)
    
    
# except subprocess.CalledProcessError as e:
#     print(f"Command failed with return code {e.returncode}")