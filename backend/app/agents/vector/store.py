from dataclasses import dataclass


@dataclass
class VectorDocument:
    doc_id: str
    text: str
    metadata: dict
