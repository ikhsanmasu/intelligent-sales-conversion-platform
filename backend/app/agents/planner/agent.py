import re
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_config, resolve_prompt

PRODUCT_KNOWLEDGE = """Produk yang kamu jual:
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
- Membantu mengurangi minyak berlebih
- Membantu membersihkan hingga ke pori
- Membantu mengangkat sel kulit mati
- Scrub lembut biodegradable

Kandungan utama:
- BHA
- Sulphur
- Biodegradable Sphere Scrub

Cara pakai:
- Basahi wajah
- Aplikasikan dan pijat lembut
- Bilas hingga bersih
- Gunakan 2-3 kali sehari

Ketentuan pengiriman dan komplain:
- Wajib isi alamat lengkap
- Komplain wajib dengan video unboxing tanpa putus
- Tanpa video unboxing, komplain tidak diproses

Testimoni:
1) Amanda (amandabilla98):
   "Oke banget sih buat perawatan jerawat... calming dan ngebantu redain jerawat meradang."
2) Silmi (silmisyauz):
   "Udah pake ini dari tahun 2023, repurchase terus karena cocok untuk acne-prone..."
"""

BASE_SYSTEM_PROMPT = """Kamu adalah chatbot sales Mengantar yang fokus high-conversion tapi tetap natural, empatik,
dan tidak memaksa.

Karakter dan aturan:
- Bahasa Indonesia santai, ramah, kekinian, tetap sopan.
- Fokus menyelesaikan masalah user dulu, baru ajakan beli secara halus.
- Gunakan struktur persuasi: empati/cerita singkat -> manfaat relevan -> ajakan lembut.
- Jangan mengarang data di luar informasi produk yang tersedia.
- Jika data tidak ada, jujur dan arahkan dengan pertanyaan klarifikasi.
- Jangan memberi klaim medis berlebihan atau janji pasti sembuh.
- Buat jawaban ringkas, praktis, dan enak dibaca.
- Setiap jawaban sebaiknya diakhiri pertanyaan lanjutan/CTA halus.

Tahap percakapan yang harus kamu ikuti:
1. Sapa pembeli
2. Pembukaan
3. Konsultasi (gali kebutuhan/masalah)
4. Testimoni (bukti sosial natural)
5. Promo (dorongan beli relevan tanpa klaim promo palsu)
6. Closing (ajak transaksi secara soft-selling)
7. Kalimat penutup yang hangat

Untuk tahap promo:
- Jika tidak ada info promo nominal, jangan membuat angka diskon fiktif.
- Boleh dorong aksi seperti cek promo ongkir/benefit berdasarkan lokasi.

Target psikologis user:
- Remaja/dewasa dengan kulit berjerawat atau berminyak
- Trigger: ingin lebih percaya diri, lelah coba produk yang tidak cocok

"""

STAGE_GUIDANCE = {
    "greeting": "Sapa user dengan hangat dan personal. Bangun koneksi awal.",
    "opening": "Kenalkan produk secara singkat dan bangkitkan minat tanpa hard-sell.",
    "consultation": "Gali masalah kulit user dan hubungkan manfaat produk yang relevan.",
    "testimony": "Sisipkan testimoni paling relevan secara natural sebagai bukti sosial.",
    "promo": (
        "Berikan dorongan beli yang relevan (misalnya cek benefit kirim/promo sesuai lokasi), "
        "tanpa membuat klaim promo palsu."
    ),
    "closing": "Arahkan ke transaksi dengan ajakan lembut dan langkah yang jelas.",
    "farewell": "Tutup percakapan dengan hangat, positif, dan tetap membuka bantuan lanjutan.",
}

ORDER_INTENT_KEYWORDS = {
    "beli",
    "checkout",
    "co",
    "ambil",
    "pesan",
    "order",
    "gas",
    "lanjut",
}

PROMO_KEYWORDS = {
    "promo",
    "diskon",
    "ongkir",
    "gratis ongkir",
    "voucher",
    "harga",
    "murah",
}

TESTIMONY_KEYWORDS = {
    "testimoni",
    "review",
    "bukti",
    "cocok gak",
    "aman gak",
    "yakin",
}

CONSULTATION_KEYWORDS = {
    "jerawat",
    "berminyak",
    "bruntusan",
    "kusam",
    "iritasi",
    "komedo",
    "sensitif",
}

FAREWELL_KEYWORDS = {
    "makasih",
    "terima kasih",
    "thanks",
    "oke sip",
    "dadah",
    "bye",
}


class PlannerAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        # Rough fallback: ~1 token per 4 chars for Latin text.
        return max(1, round(len(text) / 4))

    def _normalize_usage(self, raw_usage: dict, prompt_text: str, output_text: str) -> dict:
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

    def _detect_stage(self, input_text: str, history: list[dict] | None = None) -> str:
        message = input_text.lower()
        history = history or []
        user_turns = [m for m in history if m.get("role") == "user"]

        if any(keyword in message for keyword in FAREWELL_KEYWORDS):
            return "farewell"

        if any(keyword in message for keyword in ORDER_INTENT_KEYWORDS):
            return "closing"

        if any(keyword in message for keyword in PROMO_KEYWORDS):
            return "promo"

        if any(keyword in message for keyword in TESTIMONY_KEYWORDS):
            return "testimony"

        if any(keyword in message for keyword in CONSULTATION_KEYWORDS):
            return "consultation"

        if not user_turns:
            return "greeting"

        if len(user_turns) == 1:
            return "opening"

        if len(user_turns) == 2:
            return "consultation"

        if len(user_turns) == 3:
            return "testimony"

        if len(user_turns) == 4:
            return "promo"

        return "closing"

    def _build_messages(
        self,
        input_text: str,
        stage: str,
        history: list[dict] | None = None,
        context: dict | None = None,
    ) -> list[dict[str, str]]:
        context = context or {}
        memory_summary = context.get("memory_summary")
        database_context = context.get("database_context")
        vector_context = context.get("vector_context")

        stage_instruction = STAGE_GUIDANCE.get(stage, STAGE_GUIDANCE["consultation"])
        sales_prompt_template = resolve_prompt("sales_system") or BASE_SYSTEM_PROMPT
        try:
            sales_prompt = sales_prompt_template.format(
                stage=stage,
                stage_instruction=stage_instruction,
            )
        except Exception:
            sales_prompt = sales_prompt_template
        system_prompt = (
            f"{sales_prompt}\n\n"
            f"Tahap aktif saat ini: {stage}\n"
            f"Instruksi tahap: {stage_instruction}\n\n"
            f"{PRODUCT_KNOWLEDGE}"
        )

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        if memory_summary:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Ringkasan preferensi/fakta user dari percakapan sebelumnya:\n"
                        f"{memory_summary}"
                    ),
                }
            )

        if database_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Fakta terstruktur dari Database Agent (prioritaskan jika relevan):\n"
                        f"{database_context}"
                    ),
                }
            )

        if vector_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Konteks retrieval dari Vector Agent (gunakan untuk memperkaya jawaban):\n"
                        f"{vector_context}"
                    ),
                }
            )

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": input_text})
        return messages

    def execute(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> AgentResult:
        stage = self._detect_stage(input_text, history=history)
        messages = self._build_messages(
            input_text=input_text,
            stage=stage,
            history=history,
            context=context,
        )

        response = self.llm.generate(
            messages=messages,
            config=GenerateConfig(temperature=0.6),
        )

        output_text = self._strip_think_tags(response.text)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        usage = self._normalize_usage(response.usage, prompt_text=prompt_text, output_text=output_text)

        provider, model = self._resolve_llm_identity()

        return AgentResult(
            output=output_text,
            metadata={
                "agent": "sales",
                "stage": stage,
                "model": {
                    "provider": provider,
                    "name": model,
                },
                "usage": usage,
            },
        )

    def execute_stream(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> Generator[dict, None, None]:
        result = self.execute(input_text=input_text, context=context, history=history)

        stage = result.metadata.get("stage", "consultation")
        yield {"type": "thinking", "content": f"Tahap percakapan: {stage}\n"}

        text = result.output or ""
        if not text:
            yield {"type": "content", "content": "Maaf, belum ada jawaban. Bisa diulang dengan detail kebutuhan kamu?"}
        else:
            chunk_size = 180
            for idx in range(0, len(text), chunk_size):
                yield {"type": "content", "content": text[idx : idx + chunk_size]}

        yield {"type": "meta", "metadata": result.metadata}
