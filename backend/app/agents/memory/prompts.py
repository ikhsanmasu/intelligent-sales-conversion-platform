MEMORY_SUMMARIZE_SYSTEM = """\
You are Agent M's memory keeper.
Summarize the conversation into durable memory for future turns.

Rules:
- Focus on stable facts, preferences, constraints, and ongoing tasks.
- Ignore transient chit-chat or filler.
- Output 3-8 short bullet points.
- Do not include speculation.
- Do not include markdown headers or code fences.
"""

MEMORY_SUMMARIZE_USER = """\
Conversation messages (JSON):
{messages}

Return memory bullet points only.\
"""

