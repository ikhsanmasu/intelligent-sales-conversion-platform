from dataclasses import dataclass


@dataclass
class CodeGenResult:
    code: str
    explanation: str
