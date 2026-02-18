from dataclasses import dataclass, field


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    sql: str
