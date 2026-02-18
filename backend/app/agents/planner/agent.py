import re
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_config, resolve_prompt


_PRODUCT_KNOWLEDGE = """Nama: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP)
Harga: Rp110.900 | Kemasan: 60 g | EXP: 30 Jan 2028
BPOM: NA18201202832 | Halal MUI: 00150086800118

Deskripsi:
Sabun muka krim berbusa dengan scrub lembut. Terbukti klinis mengontrol sebum hingga 8 jam,
menjaga kelembapan kulit, dan tidak menimbulkan iritasi.

Manfaat:
- Menghambat bakteri penyebab jerawat (uji in-vitro)
- Mengurangi minyak berlebih & membersihkan hingga ke pori
- Mengangkat sel kulit mati dengan scrub biodegradable yang lembut

Kandungan utama: BHA, Sulphur, Biodegradable Sphere Scrub

Cara pakai:
Basahi wajah → aplikasikan & pijat lembut → bilas hingga bersih → gunakan 2–3x sehari

Ketentuan komplain:
Isi alamat lengkap saat order. Komplain wajib disertai video unboxing tanpa putus —
tanpa video, komplain tidak dapat diproses.

Testimoni:
• @amandabilla98 (Amanda):
  "Oke banget sih buat perawatan jerawat! Awalnya aku cuma pake obat totol jerawatnya,
   cocok banget akhirnya nyoba si facial washnya. Cocok, calming dan ngebantu redain
   jerawat yang lagi meradang."
• @silmisyauz (Silmi):
  "Udah pake ini dari tahun 2023, selalu repurchase karena cocok banget sama kulitku yang
   acne-prone. Bikin kulit jarang jerawat dan sehat. Teksturnya kayak ada scrub kecil tapi
   ga sakit sama sekali, busanya ada tapi gak too much."
"""

_SYSTEM_PROMPT = """\
Kamu adalah Ira, Acneact Care Assistant yang ramah dan empatik.
Kamu hanya menjual satu produk: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP).

## Tugas Utama
Setiap giliran, baca seluruh riwayat percakapan dari awal, tentukan sendiri tahap percakapan
saat ini, lalu berikan respons yang paling tepat untuk tahap tersebut.

## Alur Percakapan (7 Tahap)
Ikuti alur ini secara natural — jangan lompat terlalu jauh, tapi jangan terlalu lambat:

1. **Greeting** – Sapa hangat & personal. Bangun koneksi awal yang menyenangkan.
2. **Opening** – Kenalkan topik kulit/jerawat, bangkitkan minat, mulai gali masalah user.
3. **Consultation** – Gali masalah lebih dalam, validasi, lalu hubungkan ke solusi produk
   dengan pola: Story → Manfaat → Ajakan lembut.
4. **Testimony** – Perkuat kepercayaan dengan bukti sosial (testimoni pengguna nyata)
   secara natural — bukan sekadar copy-paste.
5. **Promo** – Tekankan value produk, manfaat yang didapat, bukan hanya harga.
6. **Closing** – Dorong user untuk order dengan langkah jelas, ramah, tidak memaksa.
7. **Farewell** – Tutup percakapan dengan nada hangat dan positif.

Cara menentukan tahap saat ini:
- Baca semua pesan dari awal percakapan.
- Perhatikan sudah sejauh mana percakapan berjalan dan apa yang sudah dibahas.
- Pilih tahap yang paling masuk akal untuk dilanjutkan sekarang.
- Jika user bertanya hal spesifik di luar alur, jawab dulu lalu kembali ke alur secara natural.

## Karakter & Gaya Bahasa
- Bahasa Indonesia santai, kekinian, hangat — seperti ngobrol dengan teman yang peduli.
- Empati dulu, solusi kemudian — user harus merasa dipahami sebelum ditawarkan produk.
- Soft-selling: fokus pada manfaat dan solusi, bukan "beli sekarang".
- Satu pertanyaan follow-up per balasan — jangan bertanya beruntun.
- Respons pendek & padat — hindari paragraf panjang yang terkesan template atau robotik.
- Jangan mengarang data produk yang tidak ada di product knowledge.

## Product Knowledge
{product_knowledge}
"""


class PlannerAgent(BaseAgent):
    """Sales agent — full LLM driven, no hardcoded stage logic."""

    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()

    @staticmethod
    def _normalize_usage(raw: dict | None, prompt: str = "", output: str = "") -> dict:
        raw = raw or {}
        inp = int(raw.get("prompt_tokens") or raw.get("input_tokens") or max(1, len(prompt) // 4))
        out = int(raw.get("completion_tokens") or raw.get("output_tokens") or max(1, len(output) // 4))
        return {
            "input_tokens": inp,
            "output_tokens": out,
            "prompt_tokens": inp,
            "completion_tokens": out,
            "total_tokens": inp + out,
        }

    @staticmethod
    def _resolve_llm_identity() -> tuple[str, str]:
        provider, model = settings.CHATBOT_DEFAULT_LLM, settings.CHATBOT_DEFAULT_MODEL
        try:
            provider = (
                resolve_config("llm_planner", "provider")
                or resolve_config("llm", "default_provider")
                or provider
            )
            model = (
                resolve_config("llm_planner", "model")
                or resolve_config("llm", "default_model")
                or model
            )
        except Exception:
            pass
        return str(provider), str(model)

    # ── Prompt & Message Building ──────────────────────────────────────────────

    def _build_system_prompt(self, memory_summary: str | None) -> str:
        system = _SYSTEM_PROMPT.format(product_knowledge=_PRODUCT_KNOWLEDGE).strip()

        try:
            sales_prompt = resolve_prompt("sales_system") or ""
            if sales_prompt:
                system += f"\n\n{str(sales_prompt).strip()[:600]}"
        except Exception:
            pass

        if memory_summary:
            system += f"\n\n## Konteks Sesi Sebelumnya\n{str(memory_summary)[:700]}"

        return system

    @staticmethod
    def _build_messages(
        input_text: str,
        history: list[dict] | None,
        system_prompt: str,
    ) -> list[dict]:
        """Pass full history so the LLM can track stage progression itself."""
        normalized = [
            {"role": m["role"], "content": str(m.get("content", ""))}
            for m in (history or [])
            if m.get("role") in {"user", "assistant"} and str(m.get("content", "")).strip()
        ]
        return [
            {"role": "system", "content": system_prompt},
            *normalized,
            {"role": "user", "content": input_text},
        ]

    @staticmethod
    def _llm_config() -> GenerateConfig:
        return GenerateConfig(temperature=0.4, max_tokens=300)

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 70) -> list[str]:
        return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)] if text else []

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> AgentResult:
        context = context or {}
        system = self._build_system_prompt(context.get("memory_summary"))
        messages = self._build_messages(input_text, history, system)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)

        try:
            response = self.llm.generate(messages=messages, config=self._llm_config())
            output = self._strip_think_tags(response.text).strip()
            usage = self._normalize_usage(response.usage, prompt=prompt_text, output=output)
        except Exception:
            output = "Makasih udah cerita. Biar aku bantu lebih tepat, boleh aku tahu kondisi kulitmu sekarang?"
            usage = self._normalize_usage({}, prompt=prompt_text, output=output)

        provider, model = self._resolve_llm_identity()
        return AgentResult(
            output=output,
            metadata={
                "agent": "sales",
                "model": {"provider": provider, "name": model},
                "usage": usage,
            },
        )

    def execute_stream(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> Generator[dict, None, None]:
        context = context or {}
        system = self._build_system_prompt(context.get("memory_summary"))
        messages = self._build_messages(input_text, history, system)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)

        try:
            response = self.llm.generate(messages=messages, config=self._llm_config())
            output = self._strip_think_tags(response.text).strip()
            usage = self._normalize_usage(response.usage, prompt=prompt_text, output=output)
        except Exception:
            output = "Maaf, bisa cerita ulang sedikit masalah kulitmu biar aku bantu lebih tepat?"
            usage = self._normalize_usage({}, prompt=prompt_text, output=output)

        for chunk in self._chunk_text(output):
            yield {"type": "content", "content": chunk}

        provider, model = self._resolve_llm_identity()
        yield {
            "type": "meta",
            "metadata": {
                "agent": "sales",
                "model": {"provider": provider, "name": model},
                "usage": usage,
            },
        }
