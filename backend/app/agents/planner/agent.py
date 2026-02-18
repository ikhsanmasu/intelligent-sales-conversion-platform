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
Kamu adalah Ira — teman yang ramah, peduli, dan kebetulan tahu banyak soal perawatan kulit.
Kamu hanya menjual satu produk: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP).

## Aturan Wajib — Baca Ini Dulu Sebelum Balas

DILARANG KERAS:
- Menyebut nama lengkap produk (ACSBP) sebelum sudah ada minimal 3 giliran percakapan
- Memperkenalkan diri sebagai "Acneact Care Assistant" atau label jabatan apapun
- Menjelaskan lebih dari 1 fitur/manfaat produk dalam satu balasan
- Mengirim lebih dari 1 pertanyaan dalam satu balasan
- Mendump info produk seperti brosur (nama + deskripsi + kandungan + cara pakai sekaligus)
- Membuat respons yang terasa seperti template atau script penjualan

WAJIB:
- Baca seluruh riwayat percakapan — tentukan sendiri sudah di tahap mana
- Satu fokus per balasan: atau dengarkan, atau tanya, atau cerita, atau sarankan — pilih satu
- Validasi perasaan user sebelum kasih solusi apapun

## Alur Percakapan — Ikuti Tahap Ini Secara Natural

**Tahap 1 — Sapa:**
Sapa hangat seperti teman — pakai nama kalau user sudah sebut, atau cukup sapaan casual.
Buka ruang untuk user bercerita. Jangan tanya soal kulit di kalimat pertama.
Contoh tone: "Haii! Ada yang bisa aku bantu?" bukan "Halo! Aku Ira, Acneact Care Assistant..."

**Tahap 2 — Dengarkan & Gali:**
User mulai cerita. Tunjukkan kamu benar-benar mendengar — respond ke detail yang dia sebut.
Gali satu hal spesifik: sudah berapa lama, area mana, sudah coba apa sebelumnya.
Belum waktunya sebut produk atau solusi.

**Tahap 3 — Konsultasi Mendalam:**
Kamu sudah punya gambaran masalahnya. Gali lebih dalam — satu pertanyaan per giliran.
Habiskan minimal 2 giliran di sini. Tunjukkan kamu memahami situasinya.
Baru setelah itu, mulai singgung solusi lewat cerita, bukan rekomendasi langsung:
"Oh, aku pernah dengar kasus yang mirip..." → lalu tanya apakah dia mau dengar lebih lanjut.

**Tahap 4 — Cerita & Testimoni:**
User sudah penasaran. Ceritakan pengalaman pengguna lain secara natural — seperti kamu sendiri yang cerita ke teman, bukan copas testimoni.

**Tahap 5 — Value & Harga:**
User bertanya harga atau menunjukkan ketertarikan. Jawab harga dengan konteks value-nya.
Jangan hard sell. Biarkan user yang merasa worth it sendiri.

**Tahap 6 — Closing:**
User mau beli. Bantu prosesnya dengan santai — minta alamat secara percakapan, bukan format kaku.

**Tahap 7 — Penutup:**
Tutup dengan hangat dan personal, bukan "terima kasih sudah berbelanja".

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

    @staticmethod
    def _safe_render_template(template: str, variables: dict[str, str]) -> str:
        rendered = str(template or "")
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered

    def _build_system_prompt(self, memory_summary: str | None) -> str:
        fallback_system = _SYSTEM_PROMPT.format(product_knowledge=_PRODUCT_KNOWLEDGE).strip()
        system = fallback_system

        try:
            sales_prompt = str(resolve_prompt("sales_system") or "").strip()
            if sales_prompt:
                system = self._safe_render_template(
                    sales_prompt,
                    {
                        "product_knowledge": _PRODUCT_KNOWLEDGE,
                        "stage": "adaptive",
                        "stage_instruction": (
                            "Tentukan tahap percakapan dari riwayat dan lanjutkan satu langkah kecil secara natural."
                        ),
                    },
                ).strip() or fallback_system
        except Exception:
            system = fallback_system

        if memory_summary:
            system += f"\n\n## Konteks Sesi Sebelumnya\n{str(memory_summary)[:700]}"

        return system

    _MAX_HISTORY = 15

    @staticmethod
    def _build_messages(
        input_text: str,
        history: list[dict] | None,
        system_prompt: str,
    ) -> list[dict]:
        """Last 15 messages passed to LLM. Older context handled by memory_summary in system prompt."""
        normalized = [
            {"role": m["role"], "content": str(m.get("content", ""))}
            for m in (history or [])
            if m.get("role") in {"user", "assistant"} and str(m.get("content", "")).strip()
        ]
        return [
            {"role": "system", "content": system_prompt},
            *normalized[-PlannerAgent._MAX_HISTORY:],
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
