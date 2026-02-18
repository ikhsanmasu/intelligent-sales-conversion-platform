"""Safe sandbox for executing LLM-generated Python/pandas code."""

import io
import math
import datetime
import statistics
import threading
from typing import Any

import numpy as np
import pandas as pd

ALLOWED_MODULES = {
    "pd": pd,
    "np": np,
    "math": math,
    "datetime": datetime,
    "statistics": statistics,
}

# Builtins whitelist — safe subset, no file/network/os access.
_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hasattr": hasattr,
    "hash": hash,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}

EXECUTION_TIMEOUT = 5  # seconds


def _check_forbidden(code: str) -> str | None:
    """Return an error message if code contains forbidden patterns."""
    forbidden = ["import ", "__import__", "exec(", "eval(", "compile(", "open(", "globals(", "locals("]
    for pattern in forbidden:
        if pattern in code:
            return f"Forbidden pattern detected: '{pattern}'"
    return None


def execute_code(code: str, dataframes: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Execute generated code in a sandboxed environment.

    Args:
        code: Python source code to execute. Must set a `result` variable.
        dataframes: Dict of name -> DataFrame to inject into the namespace.

    Returns:
        On success: {"result": <value>, "stdout": <captured print output>}
        On failure: {"error": <error message>}
    """
    # Check for forbidden patterns
    violation = _check_forbidden(code)
    if violation:
        return {"error": violation}

    # Build sandboxed namespace
    sandbox_globals: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    sandbox_globals.update(ALLOWED_MODULES)
    sandbox_globals.update(dataframes)

    # Capture stdout
    stdout_capture = io.StringIO()
    sandbox_globals["print"] = lambda *args, **kwargs: print(*args, file=stdout_capture, **kwargs)

    # Execute with timeout using a thread
    exec_error: list[str] = []
    exec_result: list[dict[str, Any]] = []

    def _run() -> None:
        try:
            exec(code, sandbox_globals)  # noqa: S102
            result_val = sandbox_globals.get("result")
            if result_val is None:
                exec_error.append("Code did not set a 'result' variable.")
                return
            exec_result.append({
                "result": result_val,
                "stdout": stdout_capture.getvalue(),
            })
        except Exception as e:
            exec_error.append(f"{type(e).__name__}: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=EXECUTION_TIMEOUT)

    if thread.is_alive():
        return {"error": f"Execution timed out after {EXECUTION_TIMEOUT} seconds."}

    if exec_error:
        return {"error": exec_error[0]}

    if exec_result:
        return exec_result[0]

    return {"error": "Unknown execution error."}
