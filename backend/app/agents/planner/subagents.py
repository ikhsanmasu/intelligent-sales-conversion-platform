import json
import re
from dataclasses import dataclass

from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig


_SUBAGENT_CONFIG = GenerateConfig(temperature=0.2, max_tokens=420)
_REFLECTION_CONFIG = GenerateConfig(temperature=0.1, max_tokens=520)


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def _normalize_usage(raw_usage: dict | None, prompt_text: str, output_text: str) -> dict:
    usage = raw_usage or {}
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or _estimate_tokens(prompt_text)
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or _estimate_tokens(output_text)

    try:
        prompt_tokens = int(prompt_tokens)
    except Exception:
        prompt_tokens = _estimate_tokens(prompt_text)

    try:
        completion_tokens = int(completion_tokens)
    except Exception:
        completion_tokens = _estimate_tokens(output_text)

    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "input_tokens": int(prompt_tokens),
        "output_tokens": int(completion_tokens),
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(total_tokens),
    }


def _extract_json_object(text: str) -> dict:
    content = (text or "").strip()
    if not content:
        return {}

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if fenced:
        content = fenced.group(1).strip()
    else:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            content = content[start : end + 1]

    try:
        return json.loads(content)
    except Exception:
        repaired = re.sub(r",\s*([}\]])", r"\1", content)
        try:
            return json.loads(repaired)
        except Exception:
            return {}


def _normalize_list(value: object, fallback: list[str] | None = None, max_items: int = 8) -> list[str]:
    if isinstance(value, list):
        out = [str(item).strip() for item in value if str(item).strip()]
        return out[:max_items] if out else (fallback or [])
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return fallback or []


def _format_previous_notes(previous_notes: list["SubAgentResult"]) -> str:
    if not previous_notes:
        return "(no previous notes)"

    rows = []
    for note in previous_notes:
        rows.append(f"[{note.agent}] summary: {note.summary}")
        if note.facts:
            rows.append(f"[{note.agent}] facts: {', '.join(note.facts)}")
        if note.talking_points:
            rows.append(f"[{note.agent}] points: {', '.join(note.talking_points)}")
        if note.question_hint:
            rows.append(f"[{note.agent}] question_hint: {note.question_hint}")
    return "\n".join(rows)


@dataclass
class SubAgentResult:
    agent: str
    summary: str
    must_include: list[str]
    must_avoid: list[str]
    question_hint: str
    talking_points: list[str]
    facts: list[str]
    usage: dict
    raw_output: str = ""


@dataclass
class ReflectionResult:
    approved: bool
    critique: list[str]
    revised_response: str
    usage: dict
    raw_output: str = ""


class PlannerSubAgent:
    agent_key = "generic"
    system_prompt = ""

    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def _default_payload(self) -> dict:
        return {
            "summary": "No specific recommendation.",
            "must_include": [],
            "must_avoid": [],
            "question_hint": "",
            "talking_points": [],
            "facts": [],
        }

    def _normalize_payload(self, payload: dict) -> dict:
        default = self._default_payload()
        return {
            "summary": str(payload.get("summary") or default["summary"]).strip(),
            "must_include": _normalize_list(payload.get("must_include"), fallback=default["must_include"]),
            "must_avoid": _normalize_list(payload.get("must_avoid"), fallback=default["must_avoid"]),
            "question_hint": str(payload.get("question_hint") or default["question_hint"]).strip(),
            "talking_points": _normalize_list(payload.get("talking_points"), fallback=default["talking_points"]),
            "facts": _normalize_list(payload.get("facts"), fallback=default["facts"]),
        }

    def _build_user_prompt(
        self,
        input_text: str,
        history_text: str,
        plan: dict,
        previous_notes: list[SubAgentResult],
        context: dict | None = None,
    ) -> str:
        context = context or {}
        memory_summary = str(context.get("memory_summary") or "")[:700]
        database_context = str(context.get("database_context") or "")[:900]
        vector_context = str(context.get("vector_context") or "")[:900]
        previous = _format_previous_notes(previous_notes)

        return (
            f"Plan planner utama (JSON):\n{json.dumps(plan, ensure_ascii=True)}\n\n"
            f"Pesan user terbaru:\n{input_text}\n\n"
            f"Riwayat ringkas:\n{history_text}\n\n"
            f"Memory summary:\n{memory_summary or '(none)'}\n\n"
            f"Database context:\n{database_context or '(none)'}\n\n"
            f"Vector context:\n{vector_context or '(none)'}\n\n"
            f"Catatan agent sebelumnya:\n{previous}\n\n"
            "Keluarkan rekomendasi untuk planner utama."
        )

    def run(
        self,
        input_text: str,
        history_text: str,
        plan: dict,
        previous_notes: list[SubAgentResult],
        context: dict | None = None,
    ) -> SubAgentResult:
        prompt = self._build_user_prompt(
            input_text=input_text,
            history_text=history_text,
            plan=plan,
            previous_notes=previous_notes,
            context=context,
        )
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        prompt_text = "\n".join(str(item.get("content", "")) for item in messages)

        try:
            response = self.llm.generate(messages=messages, config=_SUBAGENT_CONFIG)
            raw_text = _strip_think_tags(response.text)
            payload = self._normalize_payload(_extract_json_object(raw_text))
            usage = _normalize_usage(response.usage, prompt_text=prompt_text, output_text=raw_text)
        except Exception:
            payload = self._default_payload()
            raw_text = json.dumps(payload, ensure_ascii=True)
            usage = _normalize_usage({}, prompt_text=prompt_text, output_text=raw_text)

        return SubAgentResult(
            agent=self.agent_key,
            summary=payload["summary"],
            must_include=payload["must_include"],
            must_avoid=payload["must_avoid"],
            question_hint=payload["question_hint"],
            talking_points=payload["talking_points"],
            facts=payload["facts"],
            usage=usage,
            raw_output=raw_text,
        )


class EmpathySubAgent(PlannerSubAgent):
    agent_key = "empathy"
    system_prompt = """Kamu adalah Empathy Agent untuk sales skincare.
Tugasmu: baca kondisi user, validasi emosi user, lalu beri arahan gaya bahasa supaya jawaban terasa natural.

Balas JSON valid saja:
{
  "summary": "ringkasan emosi user dan pendekatan empatik",
  "must_include": ["frasa empatik 1", "frasa empatik 2"],
  "must_avoid": ["gaya yang harus dihindari"],
  "question_hint": "maksimal satu pertanyaan jika perlu",
  "talking_points": ["poin percakapan penting"],
  "facts": []
}

Aturan:
- Bahasa Indonesia santai, ramah, tidak kaku.
- Jangan hard-selling.
- Jangan memberi janji berlebihan.
"""

    def _default_payload(self) -> dict:
        return {
            "summary": "User butuh respon yang menenangkan dan tidak menghakimi.",
            "must_include": ["validasi perasaan user", "nada hangat"],
            "must_avoid": ["menggurui", "menekan user untuk beli"],
            "question_hint": "",
            "talking_points": ["mulai dari empati sebelum solusi"],
            "facts": [],
        }


class ProductKnowledgeSubAgent(PlannerSubAgent):
    agent_key = "product_knowledge"
    system_prompt = """Kamu adalah Product Knowledge Agent.
Tugasmu: pilih fakta produk yang paling relevan untuk pesan user dan cek potensi halusinasi.

Balas JSON valid saja:
{
  "summary": "fakta produk paling relevan untuk turn ini",
  "must_include": ["fakta yang wajib disebut jika relevan"],
  "must_avoid": ["klaim yang tidak boleh disebut"],
  "question_hint": "",
  "talking_points": ["cara menyampaikan fakta agar natural"],
  "facts": ["fakta ringkas 1", "fakta ringkas 2"]
}

Aturan:
- Hanya gunakan data yang tersedia.
- Jika data tidak ada, sarankan klarifikasi dan jangan mengarang.
- Prioritaskan akurasi BPOM, Halal, harga, cara pakai jika relevan.
"""

    def _default_payload(self) -> dict:
        return {
            "summary": "Gunakan fakta inti produk tanpa menambah klaim baru.",
            "must_include": [],
            "must_avoid": ["mengarang data", "klaim medis berlebihan"],
            "question_hint": "",
            "talking_points": ["pilih fakta yang relevan dengan masalah user"],
            "facts": [],
        }


class ConsultationSubAgent(PlannerSubAgent):
    agent_key = "consultation"
    system_prompt = """Kamu adalah Consultation Agent.
Tugasmu: susun alur konsultasi singkat agar user merasa dibantu sebelum diajak closing.

Balas JSON valid saja:
{
  "summary": "strategi konsultasi turn ini",
  "must_include": ["poin konsultasi wajib"],
  "must_avoid": ["hal yang membuat konsultasi terasa robotik"],
  "question_hint": "pertanyaan follow-up tunggal jika diperlukan",
  "talking_points": ["alur cerita", "manfaat", "ajakan lembut"],
  "facts": []
}

Aturan:
- Maksimal 1 pertanyaan follow-up.
- Terapkan Story -> Benefit -> Ajakan lembut.
- Dorong closing tanpa memaksa.
"""

    def _default_payload(self) -> dict:
        return {
            "summary": "Gali kebutuhan inti user lalu arahkan ke manfaat paling relevan.",
            "must_include": ["story -> benefit -> ajakan lembut"],
            "must_avoid": ["pertanyaan bertubi-tubi", "hard close"],
            "question_hint": "",
            "talking_points": ["hubungkan masalah user dengan manfaat produk"],
            "facts": [],
        }


class ReflectionSubAgent:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def review(
        self,
        input_text: str,
        history_text: str,
        plan: dict,
        notes: list[SubAgentResult],
        draft_response: str,
    ) -> ReflectionResult:
        notes_text = render_notes_for_prompt(notes)
        system_prompt = """Kamu adalah Reflection Agent untuk quality control jawaban sales.
Evaluasi draft jawaban lalu berikan versi final yang lebih baik.

Balas JSON valid saja:
{
  "approved": true,
  "critique": ["catatan singkat 1", "catatan singkat 2"],
  "revised_response": "jawaban final untuk user"
}

Checklist:
- Natural, empatik, tidak robotik.
- Akurat terhadap fakta produk.
- Soft-selling, tidak memaksa.
- Struktur Story -> Benefit -> Ajakan lembut.
- Maksimal satu pertanyaan follow-up.
"""
        user_prompt = (
            f"Pesan user: {input_text}\n\n"
            f"Riwayat ringkas:\n{history_text}\n\n"
            f"Plan planner:\n{json.dumps(plan, ensure_ascii=True)}\n\n"
            f"Catatan subagent:\n{notes_text}\n\n"
            f"Draft jawaban:\n{draft_response}\n\n"
            "Tingkatkan draft jika perlu."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prompt_text = "\n".join(str(item.get("content", "")) for item in messages)

        try:
            response = self.llm.generate(messages=messages, config=_REFLECTION_CONFIG)
            raw_text = _strip_think_tags(response.text)
            parsed = _extract_json_object(raw_text)
            approved = bool(parsed.get("approved", True))
            critique = _normalize_list(parsed.get("critique"), fallback=[])
            revised_response = str(parsed.get("revised_response") or "").strip()
            if not revised_response:
                revised_response = draft_response.strip()
            usage = _normalize_usage(response.usage, prompt_text=prompt_text, output_text=raw_text)
        except Exception:
            approved = True
            critique = []
            revised_response = draft_response.strip()
            raw_text = revised_response
            usage = _normalize_usage({}, prompt_text=prompt_text, output_text=raw_text)

        return ReflectionResult(
            approved=approved,
            critique=critique,
            revised_response=revised_response,
            usage=usage,
            raw_output=raw_text,
        )


def render_notes_for_prompt(notes: list[SubAgentResult]) -> str:
    if not notes:
        return "(no notes)"

    rows = []
    for note in notes:
        rows.append(f"[{note.agent}] summary: {note.summary}")
        if note.must_include:
            rows.append(f"[{note.agent}] must_include: {', '.join(note.must_include)}")
        if note.must_avoid:
            rows.append(f"[{note.agent}] must_avoid: {', '.join(note.must_avoid)}")
        if note.talking_points:
            rows.append(f"[{note.agent}] talking_points: {', '.join(note.talking_points)}")
        if note.facts:
            rows.append(f"[{note.agent}] facts: {', '.join(note.facts)}")
        if note.question_hint:
            rows.append(f"[{note.agent}] question_hint: {note.question_hint}")
    return "\n".join(rows)


__all__ = [
    "ConsultationSubAgent",
    "EmpathySubAgent",
    "ProductKnowledgeSubAgent",
    "ReflectionResult",
    "ReflectionSubAgent",
    "SubAgentResult",
    "render_notes_for_prompt",
]
