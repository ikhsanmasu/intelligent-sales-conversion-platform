import json
import re
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.agents.planner.subagents import (
    ConsultationSubAgent,
    EmpathySubAgent,
    ProductKnowledgeSubAgent,
    ReflectionSubAgent,
    SubAgentResult,
    render_notes_for_prompt,
)
from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_config, resolve_prompt


PRODUCT_KNOWLEDGE_FULL = """Produk yang dijual:
- Nama: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP)
- Harga: Rp110.900
- Kemasan: 60 g
- EXP: 30 Januari 2028
- BPOM: NA18201202832
- Halal MUI: 00150086800118

Deskripsi:
Sabun pembersih wajah berbentuk krim berbusa dengan scrub lembut untuk membantu
mengangkat sebum berlebih, kotoran, dan sel kulit mati.

Manfaat utama:
- Membantu menghambat bakteri penyebab jerawat (uji in-vitro)
- Membantu mencegah jerawat baru
- Membantu mengurangi minyak berlebih
- Membantu membersihkan hingga ke pori
- Membantu mengangkat sel kulit mati
- Scrub lembut biodegradable
- Terbukti secara klinis membantu kontrol sebum hingga 8 jam
- Menjaga kelembapan kulit
- Tidak menimbulkan iritasi

Kandungan utama:
- BHA
- Sulphur
- Biodegradable Sphere Scrub

Cara pakai:
- Basahi wajah
- Aplikasikan lalu pijat lembut
- Bilas hingga bersih
- Gunakan 2-3 kali sehari

Ketentuan pengiriman dan komplain:
- Wajib isi alamat lengkap
- Komplain wajib dengan video unboxing tanpa putus
- Tanpa video unboxing, komplain tidak diproses

Testimoni:
1) @amandabilla98 (Amanda):
"Oke banget sih buat perawatan jerawat! Awalnya aku cuma pake obat totol jerawatnya cocok banget akhirnya nyoba si facial washnya. Cocok, calming dan ngebantu redain jerawat yang lagi meradang."
2) @silmisyauz (Silmi):
"Udah pake ini dari tahun 2023, selalu repurchase karena cocok banget sama kulitku yang acne-prone, bikin kulit jarang jerawat dan sehat, teksturnya kayak ada scrub kecil tapi ga sakit sama sekali, busa nya ada tapi gak to much."
"""

PRODUCT_KNOWLEDGE_BRIEF = (
    "Produk tunggal yang dijual: ERHA Acneact Acne Cleanser Scrub Beta Plus "
    "(ACSBP), untuk kulit berjerawat dan berminyak, harga Rp110.900 per 60 g."
)

BASE_SYSTEM_PROMPT = """Kamu adalah Ira Acneact Care Assistant.
Kamu hanya menjual satu produk: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP).

Aturan wajib:
1) Bahasa ramah, santai, natural seperti manusia.
2) Soft-selling empatik: validasi user dulu, lalu bantu dengan solusi.
3) Struktur persuasi: Story -> Benefit -> Ajakan lembut.
4) Jangan memaksa beli.
5) Jangan mengarang data.
6) Maksimal 1 pertanyaan follow-up per balasan.
7) Fokus user merasa dipahami, bukan merasa dijuali.
"""

_STAGE_ORDER = [
    "greeting",
    "opening",
    "consultation",
    "testimony",
    "promo",
    "closing",
    "farewell",
]
_VALID_STAGES = set(_STAGE_ORDER)
_KNOWLEDGE_BRIEF_STAGES = {"greeting", "farewell"}
_MAX_HISTORY_MESSAGES = 15
_MAX_PLAN_HISTORY_MESSAGES = 12

_DEFAULT_STAGE_OBJECTIVES = {
    "greeting": "Bangun koneksi awal yang hangat.",
    "opening": "Gali masalah utama user dengan natural.",
    "consultation": "Hubungkan masalah user dengan solusi produk secara empatik.",
    "testimony": "Bangun trust dengan bukti sosial yang relevan.",
    "promo": "Jelaskan value produk dengan ajakan lembut.",
    "closing": "Dorong transaksi dengan langkah jelas tanpa tekanan.",
    "farewell": "Akhiri percakapan secara hangat dan suportif.",
}

_STAGE_COMPACT_GUIDANCE = {
    "greeting": "Sapa hangat dan personal. Bila perlu tanya satu hal ringan.",
    "opening": "Validasi masalah user, lalu gali inti kebutuhannya.",
    "consultation": "Empati dulu, berikan solusi relevan, lalu ajakan halus.",
    "testimony": "Pakai social proof relevan tanpa terkesan memaksa.",
    "promo": "Tekankan manfaat dan value, bukan sekadar harga.",
    "closing": "Berikan langkah order dengan bahasa ramah.",
    "farewell": "Tutup percakapan dengan nada positif.",
}

_PLANNER_SYSTEM_PROMPT = """Kamu adalah Planner Agent utama untuk sales skincare.
Tugasmu: menentukan rencana SATU bubble balasan berikutnya berbasis konteks percakapan.

Tujuan global:
- Natural, empatik, tidak robotik.
- Soft-selling: fokus solusi, bukan paksaan.
- Struktur: Story -> Benefit -> Ajakan lembut.
- Maksimal satu pertanyaan follow-up.

Balas JSON valid saja (tanpa markdown):
{
  "stage": "consultation",
  "stage_reason": "alasan singkat pemilihan stage",
  "objective": "tujuan bubble ini",
  "tone": "gaya bahasa spesifik",
  "soft_closing_strategy": "cara ajakan lembut",
  "persuasion": {
    "story": "framing masalah user",
    "benefit": "manfaat yang mau ditekankan",
    "gentle_cta": "ajakan halus"
  },
  "ask_follow_up": true,
  "follow_up_question": "pertanyaan follow-up tunggal jika perlu",
  "must_include": ["poin wajib"],
  "must_avoid": ["poin yang harus dihindari"],
  "agent_priorities": ["prioritas untuk subagent"]
}
"""


class PlannerAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)
        self.empathy_agent = EmpathySubAgent(llm=llm)
        self.product_agent = ProductKnowledgeSubAgent(llm=llm)
        self.consultation_agent = ConsultationSubAgent(llm=llm)
        self.reflection_agent = ReflectionSubAgent(llm=llm)

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, round(len(text) / 4))

    def _normalize_usage(self, raw_usage: dict | None, prompt_text: str, output_text: str) -> dict:
        raw_usage = raw_usage or {}
        prompt_tokens = (
            raw_usage.get("prompt_tokens")
            or raw_usage.get("input_tokens")
            or self._estimate_tokens(prompt_text)
        )
        completion_tokens = (
            raw_usage.get("completion_tokens")
            or raw_usage.get("output_tokens")
            or self._estimate_tokens(output_text)
        )

        try:
            prompt_tokens = int(prompt_tokens)
        except Exception:
            prompt_tokens = self._estimate_tokens(prompt_text)

        try:
            completion_tokens = int(completion_tokens)
        except Exception:
            completion_tokens = self._estimate_tokens(output_text)

        total_tokens = raw_usage.get("total_tokens")
        if total_tokens is None:
            total_tokens = prompt_tokens + completion_tokens

        return {
            "input_tokens": int(prompt_tokens),
            "output_tokens": int(completion_tokens),
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
        }

    @staticmethod
    def _merge_usage(*usages: dict) -> dict:
        merged = {
            "input_tokens": 0,
            "output_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for usage in usages:
            if not isinstance(usage, dict):
                continue
            for key in merged:
                try:
                    merged[key] += int(usage.get(key, 0) or 0)
                except Exception:
                    pass
        merged["total_tokens"] = merged["prompt_tokens"] + merged["completion_tokens"]
        merged["input_tokens"] = merged["prompt_tokens"]
        merged["output_tokens"] = merged["completion_tokens"]
        return merged

    @staticmethod
    def _resolve_llm_identity() -> tuple[str, str]:
        provider = settings.CHATBOT_DEFAULT_LLM
        model = settings.CHATBOT_DEFAULT_MODEL
        try:
            planner_provider = resolve_config("llm_planner", "provider")
            planner_model = resolve_config("llm_planner", "model")
            fallback_provider = resolve_config("llm", "default_provider")
            fallback_model = resolve_config("llm", "default_model")
            provider = planner_provider or fallback_provider or provider
            model = planner_model or fallback_model or model
        except Exception:
            pass
        return str(provider), str(model)

    @staticmethod
    def _trim_history(history: list[dict] | None, max_messages: int = _MAX_HISTORY_MESSAGES) -> list[dict]:
        if not history:
            return []
        normalized = [
            {"role": item.get("role", ""), "content": str(item.get("content", ""))}
            for item in history
            if item.get("role") in {"user", "assistant"} and str(item.get("content", "")).strip()
        ]
        if len(normalized) <= max_messages:
            return normalized
        return normalized[-max_messages:]

    def _format_history_for_planner(self, history: list[dict] | None) -> str:
        trimmed = self._trim_history(history, max_messages=_MAX_PLAN_HISTORY_MESSAGES)
        if not trimmed:
            return "(no history)"
        rows = []
        for item in trimmed:
            role = "USER" if item.get("role") == "user" else "ASSISTANT"
            content = " ".join(str(item.get("content", "")).split())
            rows.append(f"{role}: {content[:320]}")
        return "\n".join(rows)

    @staticmethod
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

    @staticmethod
    def _normalize_list(value: object, fallback: list[str] | None = None, max_items: int = 8) -> list[str]:
        if isinstance(value, list):
            out = [str(item).strip() for item in value if str(item).strip()]
            return out[:max_items] if out else (fallback or [])
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return fallback or []

    def _default_plan(self) -> dict:
        return {
            "stage": "consultation",
            "stage_reason": "fallback plan",
            "objective": _DEFAULT_STAGE_OBJECTIVES["consultation"],
            "tone": "ramah, santai, empatik",
            "soft_closing_strategy": "beri solusi dulu lalu ajak lanjut dengan halus",
            "persuasion": {
                "story": "Validasi cerita user tentang masalah kulit.",
                "benefit": "Pilih manfaat produk yang paling relevan.",
                "gentle_cta": "Ajak lanjut tanpa tekanan.",
            },
            "ask_follow_up": True,
            "follow_up_question": "",
            "must_include": [
                "nada empatik",
                "story -> benefit -> ajakan lembut",
            ],
            "must_avoid": [
                "hard-selling",
                "mengarang data",
                "lebih dari satu pertanyaan",
            ],
            "agent_priorities": [
                "empathy first",
                "factual accuracy",
                "consultative closing",
            ],
        }

    def _normalize_plan(self, raw_plan: dict) -> dict:
        plan = raw_plan if isinstance(raw_plan, dict) else {}
        default = self._default_plan()
        persuasion = plan.get("persuasion")
        if not isinstance(persuasion, dict):
            persuasion = {}

        stage = str(plan.get("stage") or default["stage"]).strip().lower()
        if stage not in _VALID_STAGES:
            stage = default["stage"]

        ask_follow_up = bool(plan.get("ask_follow_up", default["ask_follow_up"]))
        follow_up_question = str(plan.get("follow_up_question") or "").strip()
        if not ask_follow_up:
            follow_up_question = ""

        return {
            "stage": stage,
            "stage_reason": str(plan.get("stage_reason") or default["stage_reason"]).strip(),
            "objective": str(
                plan.get("objective") or _DEFAULT_STAGE_OBJECTIVES.get(stage) or default["objective"]
            ).strip(),
            "tone": str(plan.get("tone") or default["tone"]).strip(),
            "soft_closing_strategy": str(
                plan.get("soft_closing_strategy") or default["soft_closing_strategy"]
            ).strip(),
            "persuasion": {
                "story": str(persuasion.get("story") or default["persuasion"]["story"]).strip(),
                "benefit": str(persuasion.get("benefit") or default["persuasion"]["benefit"]).strip(),
                "gentle_cta": str(
                    persuasion.get("gentle_cta") or default["persuasion"]["gentle_cta"]
                ).strip(),
            },
            "ask_follow_up": ask_follow_up,
            "follow_up_question": follow_up_question,
            "must_include": self._normalize_list(plan.get("must_include"), fallback=default["must_include"]),
            "must_avoid": self._normalize_list(plan.get("must_avoid"), fallback=default["must_avoid"]),
            "agent_priorities": self._normalize_list(
                plan.get("agent_priorities"), fallback=default["agent_priorities"]
            ),
        }

    @staticmethod
    def _planning_config() -> GenerateConfig:
        return GenerateConfig(temperature=0.15, max_tokens=560)

    @staticmethod
    def _draft_config(stage: str) -> GenerateConfig:
        temp = 0.45
        if stage in {"promo", "closing"}:
            temp = 0.35
        if stage in {"greeting", "opening"}:
            temp = 0.4
        return GenerateConfig(temperature=temp)

    def _plan_orchestration_with_llm(
        self,
        input_text: str,
        history: list[dict] | None = None,
        context: dict | None = None,
    ) -> tuple[dict, dict]:
        history_text = self._format_history_for_planner(history)
        context = context or {}
        memory_summary = str(context.get("memory_summary") or "")[:700]
        database_context = str(context.get("database_context") or "")[:900]
        vector_context = str(context.get("vector_context") or "")[:900]

        planner_user_prompt = (
            f"Pesan user terbaru:\n{input_text}\n\n"
            f"Riwayat ringkas:\n{history_text}\n\n"
            f"Memory summary:\n{memory_summary or '(none)'}\n\n"
            f"Database context:\n{database_context or '(none)'}\n\n"
            f"Vector context:\n{vector_context or '(none)'}\n\n"
            "Buat rencana untuk satu bubble jawaban berikutnya."
        )
        messages = [
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": planner_user_prompt},
        ]
        prompt_text = "\n".join(str(item.get("content", "")) for item in messages)

        try:
            response = self.llm.generate(messages=messages, config=self._planning_config())
            raw_text = self._strip_think_tags(response.text)
            plan = self._normalize_plan(self._extract_json_object(raw_text))
            usage = self._normalize_usage(response.usage, prompt_text=prompt_text, output_text=raw_text)
            return plan, usage
        except Exception:
            fallback = self._default_plan()
            usage = self._normalize_usage({}, prompt_text=prompt_text, output_text=json.dumps(fallback))
            return fallback, usage

    def _run_subagents(
        self,
        input_text: str,
        history: list[dict] | None,
        plan: dict,
        context: dict | None = None,
    ) -> tuple[list[SubAgentResult], dict]:
        notes: list[SubAgentResult] = []
        usages: list[dict] = []
        history_text = self._format_history_for_planner(history)

        for subagent in (self.empathy_agent, self.product_agent, self.consultation_agent):
            note = subagent.run(
                input_text=input_text,
                history_text=history_text,
                plan=plan,
                previous_notes=notes,
                context=context,
            )
            notes.append(note)
            usages.append(note.usage)

        return notes, self._merge_usage(*usages)

    def _build_stage_block(self, plan: dict, notes: list[SubAgentResult]) -> str:
        stage = str(plan.get("stage") or "consultation")
        persuasion = plan.get("persuasion", {})
        lines = [
            f"TAHAP_AKTIF={stage}",
            f"PANDUAN_TAHAP={_STAGE_COMPACT_GUIDANCE.get(stage, _STAGE_COMPACT_GUIDANCE['consultation'])}",
            f"TUJUAN_BUBBLE={plan.get('objective', '')}",
            f"GAYA_DETAIL={plan.get('tone', '')}",
            f"SOFT_CLOSING={plan.get('soft_closing_strategy', '')}",
            f"STORY_FOCUS={persuasion.get('story', '')}",
            f"BENEFIT_FOCUS={persuasion.get('benefit', '')}",
            f"GENTLE_CTA={persuasion.get('gentle_cta', '')}",
            (
                "FOLLOW_UP_POLICY="
                f"ask={str(bool(plan.get('ask_follow_up', False))).lower()}, "
                f"question={str(plan.get('follow_up_question', '')).strip()}"
            ),
            "FORMAT=2-4 kalimat natural, tidak terdengar template bot.",
        ]
        if plan.get("must_include"):
            lines.append("MUST_INCLUDE:")
            lines.extend(f"- {item}" for item in plan.get("must_include", []))
        if plan.get("must_avoid"):
            lines.append("MUST_AVOID:")
            lines.extend(f"- {item}" for item in plan.get("must_avoid", []))

        notes_text = render_notes_for_prompt(notes)
        if notes_text:
            lines.append("CATATAN_SUBAGENT:")
            lines.append(notes_text)
        return "\n".join(lines)

    def _build_messages(
        self,
        input_text: str,
        history: list[dict] | None,
        plan: dict,
        notes: list[SubAgentResult],
        context: dict | None = None,
    ) -> list[dict[str, str]]:
        context = context or {}
        stage = str(plan.get("stage") or "consultation")
        memory_summary = context.get("memory_summary")
        database_context = context.get("database_context")
        vector_context = context.get("vector_context")

        sales_prompt_template = resolve_prompt("sales_system") or ""
        sales_prompt = ""
        if sales_prompt_template:
            try:
                sales_prompt = sales_prompt_template.format(
                    stage=stage,
                    stage_instruction=_STAGE_COMPACT_GUIDANCE.get(stage, ""),
                )
                sales_prompt = " ".join(str(sales_prompt).split())[:700]
            except Exception:
                sales_prompt = ""

        stage_block = self._build_stage_block(plan, notes)
        product_block = PRODUCT_KNOWLEDGE_BRIEF if stage in _KNOWLEDGE_BRIEF_STAGES else PRODUCT_KNOWLEDGE_FULL

        system_parts = [BASE_SYSTEM_PROMPT]
        if sales_prompt:
            system_parts.append(sales_prompt)
        system_parts.append(stage_block)
        system_parts.append(product_block)
        system_prompt = "\n\n".join(system_parts)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        if memory_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Ringkasan user sebelumnya:\n{str(memory_summary)[:700]}",
                }
            )
        if database_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Konteks database relevan:\n{str(database_context)[:900]}",
                }
            )
        if vector_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Konteks retrieval relevan:\n{str(vector_context)[:900]}",
                }
            )

        messages.extend(self._trim_history(history))
        messages.append({"role": "user", "content": input_text})
        return messages

    def _generate_draft(
        self,
        input_text: str,
        history: list[dict] | None,
        plan: dict,
        notes: list[SubAgentResult],
        context: dict | None = None,
    ) -> tuple[str, dict]:
        stage = str(plan.get("stage") or "consultation")
        messages = self._build_messages(
            input_text=input_text,
            history=history,
            plan=plan,
            notes=notes,
            context=context,
        )
        prompt_text = "\n".join(str(item.get("content", "")) for item in messages)

        try:
            response = self.llm.generate(
                messages=messages,
                config=self._draft_config(stage),
            )
            output_text = self._strip_think_tags(response.text)
            usage = self._normalize_usage(response.usage, prompt_text=prompt_text, output_text=output_text)
            if output_text:
                return output_text, usage
        except Exception:
            pass

        fallback = "Makasih udah cerita. Biar aku bantu paling pas, boleh aku tahu kondisi kulitmu sekarang lagi cenderung berminyak banget atau ada jerawat meradang?"
        usage = self._normalize_usage({}, prompt_text=prompt_text, output_text=fallback)
        return fallback, usage

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 70) -> list[str]:
        clean = str(text or "")
        if not clean:
            return []
        return [clean[idx : idx + chunk_size] for idx in range(0, len(clean), chunk_size)]

    def _build_metadata(
        self,
        plan: dict,
        notes: list[SubAgentResult],
        reflection,
        usage: dict,
    ) -> dict:
        provider, model = self._resolve_llm_identity()
        return {
            "agent": "sales",
            "stage": plan.get("stage", "consultation"),
            "orchestration": {
                "objective": plan.get("objective", ""),
                "tone": plan.get("tone", ""),
                "soft_closing_strategy": plan.get("soft_closing_strategy", ""),
                "stage_reason": plan.get("stage_reason", ""),
            },
            "subagents": [
                {
                    "agent": note.agent,
                    "summary": note.summary,
                    "must_include": note.must_include,
                    "must_avoid": note.must_avoid,
                }
                for note in notes
            ],
            "reflection": {
                "approved": bool(getattr(reflection, "approved", True)),
                "critique": list(getattr(reflection, "critique", []) or []),
            },
            "model": {"provider": provider, "name": model},
            "usage": usage,
        }

    def execute(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> AgentResult:
        plan, planning_usage = self._plan_orchestration_with_llm(
            input_text=input_text,
            history=history,
            context=context,
        )
        notes, subagent_usage = self._run_subagents(
            input_text=input_text,
            history=history,
            plan=plan,
            context=context,
        )
        draft_output, draft_usage = self._generate_draft(
            input_text=input_text,
            history=history,
            plan=plan,
            notes=notes,
            context=context,
        )
        history_text = self._format_history_for_planner(history)
        reflection = self.reflection_agent.review(
            input_text=input_text,
            history_text=history_text,
            plan=plan,
            notes=notes,
            draft_response=draft_output,
        )
        final_output = (reflection.revised_response or draft_output).strip() or draft_output
        usage = self._merge_usage(planning_usage, subagent_usage, draft_usage, reflection.usage)
        metadata = self._build_metadata(plan=plan, notes=notes, reflection=reflection, usage=usage)

        return AgentResult(output=final_output, metadata=metadata)

    def execute_stream(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> Generator[dict, None, None]:
        yield {"type": "thinking", "content": "Planner: menyusun strategi percakapan...\n"}

        try:
            plan, planning_usage = self._plan_orchestration_with_llm(
                input_text=input_text,
                history=history,
                context=context,
            )
            stage = plan.get("stage", "consultation")
            yield {
                "type": "thinking",
                "content": (
                    f"Planner stage: {stage}\n"
                    f"Objective: {plan.get('objective', '')}\n"
                ),
            }

            history_text = self._format_history_for_planner(history)
            notes: list[SubAgentResult] = []
            subagent_usages: list[dict] = []

            for subagent in (self.empathy_agent, self.product_agent, self.consultation_agent):
                note = subagent.run(
                    input_text=input_text,
                    history_text=history_text,
                    plan=plan,
                    previous_notes=notes,
                    context=context,
                )
                notes.append(note)
                subagent_usages.append(note.usage)
                yield {
                    "type": "thinking",
                    "content": (
                        f"Subagent {note.agent}: {note.summary}\n"
                    ),
                }

            draft_output, draft_usage = self._generate_draft(
                input_text=input_text,
                history=history,
                plan=plan,
                notes=notes,
                context=context,
            )
            yield {"type": "thinking", "content": "Reflection: mengecek kualitas jawaban final...\n"}

            reflection = self.reflection_agent.review(
                input_text=input_text,
                history_text=history_text,
                plan=plan,
                notes=notes,
                draft_response=draft_output,
            )
            final_output = (reflection.revised_response or draft_output).strip() or draft_output
            usage = self._merge_usage(
                planning_usage,
                self._merge_usage(*subagent_usages),
                draft_usage,
                reflection.usage,
            )
            metadata = self._build_metadata(plan=plan, notes=notes, reflection=reflection, usage=usage)

            for chunk in self._chunk_text(final_output):
                yield {"type": "content", "content": chunk}

            yield {"type": "meta", "metadata": metadata}
            return
        except Exception:
            fallback = "Maaf, bisa cerita ulang sedikit masalah kulitmu biar aku bantu lebih tepat?"
            usage = self._normalize_usage({}, prompt_text=input_text, output_text=fallback)
            metadata = self._build_metadata(
                plan=self._default_plan(),
                notes=[],
                reflection=type("ReflectionFallback", (), {"approved": True, "critique": []})(),
                usage=usage,
            )
            yield {"type": "content", "content": fallback}
            yield {"type": "meta", "metadata": metadata}
