import re
from collections.abc import Generator
from dataclasses import dataclass, field

from app.agents.base import AgentResult, BaseAgent
from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_config, resolve_prompt

# ---------------------------------------------------------------------------
# Product Knowledge — full version (injected conditionally by stage)
# ---------------------------------------------------------------------------
PRODUCT_KNOWLEDGE_FULL = """Produk yang kamu jual:
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
- Mencegah bakteri penyebab jerawat
- Membantu mengurangi minyak berlebih
- Membantu membersihkan hingga ke pori
- Membantu mengangkat sel kulit mati
- Scrub lembut biodegradable
- Terbukti secara klinis mengontrol sebum hingga 8 jam
- Menjaga kelembapan kulit
- Tidak menimbulkan iritasi

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
   "Oke banget sih buat perawatan jerawat! Awalnya aku cuma pake obat totol jerawatnya cocok banget akhirnya nyoba si facial washnya. Cocok, calming dan ngebantu redain jerawat yang lagi meradang."
2) Silmi (silmisyauz):
   "Udah pake ini dari tahun 2023, selalu repurchase karena cocok banget sama kulitku yang acne-prone, bikin kulit jarang jerawat dan sehat, teksturnya kayak ada scrub kecil tapi ga sakit sama sekali, busa nya ada tapi gak to much."
"""

PRODUCT_KNOWLEDGE_BRIEF = (
    "Produk: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP) — "
    "sabun pembersih wajah untuk kulit berjerawat/berminyak, Rp110.900/60g."
)

# ---------------------------------------------------------------------------
# Base System Prompt — streamlined
# ---------------------------------------------------------------------------
BASE_SYSTEM_PROMPT = """Kamu adalah Lia, sales consultant dari tim Mengantar.
Kamu HANYA menjual satu produk: ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP).
Semua pertanyaan tentang produk = tentang ERHA ACSBP. Kamu SUDAH TAU produknya.

ATURAN KETAT:
- JANGAN PERNAH minta user kirim foto produk, nama produk, atau kode produk.
- JANGAN PERNAH bertanya "produk yang mana?" — kamu hanya jual SATU produk.
- Jika ditanya "aman ga?" → jawab dengan data BPOM dan Halal MUI.
- Jika ditanya "ini siapa?" / "kak siapa?" → jawab "Aku Lia dari tim Mengantar".
- JAWAB SINGKAT. Maksimal 2-3 kalimat per respons.
- Bahasa Indonesia santai-sopan, seperti chat teman.
- Setiap respons ada ajakan halus ke pembelian (soft CTA).
- Pola: Cerita/Empati → Manfaat → Ajakan beli.
- Jangan mengarang data, jangan klaim medis berlebihan.
"""

# ---------------------------------------------------------------------------
# Rich Stage Prompts
# ---------------------------------------------------------------------------
STAGE_PROMPTS = {
    "greeting": {
        "instruction": (
            "- Perkenalkan diri: 'Hai kak! Aku Lia dari Mengantar.'\n"
            "- Tanyakan nama user.\n"
            "- JANGAN langsung menyebut produk atau jualan."
        ),
        "tone": "Hangat, bersahabat, seperti teman yang baru kenalan.",
        "emotional_hook": "Buat user merasa disambut dan nyaman untuk curhat.",
        "do_not": "Jangan sebut nama produk, harga, atau manfaat apapun di tahap ini.",
        "example_pattern": (
            "Hai kak! Aku Lia dari Mengantar~ "
            "Boleh tau nama kamu siapa? Biar ngobrolnya lebih asik~"
        ),
        "transition_trigger": "User merespons sapaan / menyebut nama / menyebut masalah kulit.",
        "response_length": "1-2 kalimat saja. Singkat dan hangat.",
    },
    "opening": {
        "instruction": (
            "- Kenalkan dirimu sebagai beauty advisor yang bisa bantu soal skincare.\n"
            "- Tanyakan masalah kulit user secara empatik.\n"
            "- Boleh menyebut bahwa kamu punya rekomendasi produk, tapi jangan detail dulu."
        ),
        "tone": "Antusias tapi tidak agresif, penuh perhatian.",
        "emotional_hook": "Validasi bahwa masalah kulit itu wajar dan bisa diatasi.",
        "do_not": "Jangan langsung sebut nama produk atau harga.",
        "example_pattern": (
            "Wah, seneng kenalan sama kamu! Aku di sini bisa bantu soal skincare lho. "
            "Btw, ada keluhan kulit yang lagi ganggu nggak? Cerita aja, siapa tau aku bisa bantu~"
        ),
        "transition_trigger": "User menceritakan masalah kulit / bertanya soal produk.",
        "response_length": "2-3 kalimat. Perkenalan singkat + 1 pertanyaan.",
    },
    "consultation": {
        "instruction": (
            "- Gali masalah kulit user lebih dalam: tipe kulit, sudah coba apa, hasilnya bagaimana.\n"
            "- Tunjukkan empati: validasi perasaan user soal masalah kulitnya.\n"
            "- Hubungkan masalah user dengan manfaat produk yang RELEVAN.\n"
            "- Jelaskan kandungan (BHA, Sulphur, Scrub biodegradable) dan cara kerjanya.\n"
            "- Jangan overselling — fokus edukasi."
        ),
        "tone": "Seperti konsultan kecantikan yang sabar dan berpengetahuan.",
        "emotional_hook": "Buat user merasa masalahnya dipahami dan ada solusinya.",
        "do_not": "Jangan buat klaim medis pasti ('pasti sembuh', 'dijamin hilang'). Gunakan 'membantu', 'bisa bantu'.",
        "example_pattern": (
            "Hmm, jerawat meradang emang bikin nggak nyaman ya :( Aku paham banget. "
            "Nah, biasanya jerawat kayak gitu butuh pembersih yang bisa kontrol minyak sekaligus antibakteri. "
            "Kebetulan ERHA ACSBP ini ada kandungan BHA dan Sulphur yang membantu banget buat itu..."
        ),
        "transition_trigger": "User sudah paham manfaat produk / tertarik / minta bukti.",
        "response_length": "3-5 kalimat. Empati + edukasi produk, jangan terlalu panjang.",
    },
    "testimony": {
        "instruction": (
            "- KUTIP PERSIS KATA PER KATA testimoni di bawah. JANGAN UBAH, JANGAN PARAFRASE, JANGAN SINGKAT.\n"
            "- Hubungkan testimoni dengan masalah spesifik user.\n"
            "- Gunakan format @username untuk kredibilitas.\n"
            "- Boleh tambahkan konteks singkat sebelum/sesudah kutipan.\n\n"
            "TESTIMONI VERBATIM (wajib dikutip persis):\n\n"
            "1) @amandabilla98 (Amanda):\n"
            "\"Oke banget sih buat perawatan jerawat! Awalnya aku cuma pake obat totol "
            "jerawatnya cocok banget akhirnya nyoba si facial washnya. Cocok, calming "
            "dan ngebantu redain jerawat yang lagi meradang.\"\n\n"
            "2) @silmisyauz (Silmi):\n"
            "\"Udah pake ini dari tahun 2023, selalu repurchase karena cocok banget "
            "sama kulitku yang acne-prone, bikin kulit jarang jerawat dan sehat, "
            "teksturnya kayak ada scrub kecil tapi ga sakit sama sekali, busa nya "
            "ada tapi gak to much.\""
        ),
        "tone": "Antusias berbagi cerita sukses, seperti kasih rekomendasi ke teman.",
        "emotional_hook": "Social proof — orang lain dengan masalah serupa sudah terbantu.",
        "do_not": "DILARANG mengubah, menyingkat, atau memparafrase testimoni. Kutip PERSIS.",
        "example_pattern": (
            "Oh iya, ada yang ceritanya mirip kayak kamu nih!\n\n"
            "@amandabilla98 (Amanda) bilang:\n"
            "\"Oke banget sih buat perawatan jerawat! Awalnya aku cuma pake obat totol "
            "jerawatnya cocok banget akhirnya nyoba si facial washnya. Cocok, calming "
            "dan ngebantu redain jerawat yang lagi meradang.\"\n\n"
            "Terus @silmisyauz (Silmi) juga bilang:\n"
            "\"Udah pake ini dari tahun 2023, selalu repurchase karena cocok banget "
            "sama kulitku yang acne-prone, bikin kulit jarang jerawat dan sehat, "
            "teksturnya kayak ada scrub kecil tapi ga sakit sama sekali, busa nya "
            "ada tapi gak to much.\"\n\n"
            "Relatable kan?"
        ),
        "transition_trigger": "User tertarik / mau tau harga / mau beli.",
        "response_length": "Kutip KEDUA testimoni LENGKAP + 1-2 kalimat konteks. Jangan potong.",
    },
    "promo": {
        "instruction": (
            "- Sampaikan harga produk: Rp110.900 untuk 60g.\n"
            "- Berikan dorongan beli yang relevan tanpa klaim promo palsu.\n"
            "- Boleh suggest: cek promo ongkir, benefit berdasarkan lokasi.\n"
            "- Tekankan value: harga terjangkau untuk produk BPOM + Halal.\n"
            "- Frame sebagai investasi untuk kulit, bukan pengeluaran."
        ),
        "tone": "Excited tapi jujur, seperti kasih info deal bagus ke teman.",
        "emotional_hook": "FOMO halus — 'sayang kalau nggak dicoba' tanpa tekanan.",
        "do_not": "Jangan buat angka diskon fiktif atau promo yang tidak ada.",
        "example_pattern": (
            "Nah, kabar baiknya harganya cuma Rp110.900 aja lho untuk 60g! "
            "Udah BPOM dan Halal MUI juga. Worth it banget sih buat investasi kulit sehat. "
            "Mau aku bantu proses pesanannya?"
        ),
        "transition_trigger": "User bilang mau beli / minta cara order.",
        "response_length": "3-4 kalimat. Harga + value proposition + CTA.",
    },
    "closing": {
        "instruction": (
            "- Berikan instruksi order yang JELAS dan langkah-langkah konkret.\n"
            "- Minta alamat lengkap untuk pengiriman.\n"
            "- Infokan kebijakan komplain: wajib video unboxing tanpa putus.\n"
            "- Buat user merasa keputusannya tepat (reinforcement positif).\n"
            "- Jika user ragu, handle objection dengan empati."
        ),
        "tone": "Supportive dan clear, seperti bantu teman checkout.",
        "emotional_hook": "Reinforcement — 'pilihan bagus, kulit kamu pasti seneng!'",
        "do_not": "Jangan skip info kebijakan komplain.",
        "example_pattern": (
            "Yay, pilihan bagus! Biar aku bantu ya. Untuk prosesnya:\n"
            "1. Kirim alamat lengkap kamu\n"
            "2. Nanti aku info total + ongkirnya\n"
            "Oh iya, satu hal penting: kalau nanti ada kendala, pastikan rekam video unboxing "
            "tanpa putus ya, karena itu syarat untuk proses komplain."
        ),
        "transition_trigger": "User konfirmasi order / kirim alamat.",
        "response_length": "4-6 kalimat. Langkah order + kebijakan komplain.",
    },
    "farewell": {
        "instruction": (
            "- Tutup percakapan dengan hangat dan PERSONAL.\n"
            "- Sebutkan kembali masalah/kekhawatiran spesifik user dari percakapan (misal: jerawat meradang, kulit berminyak).\n"
            "- Referensikan perjalanan percakapan (misal: 'seneng bisa bantu kamu soal jerawat tadi').\n"
            "- Ucapkan terima kasih.\n"
            "- Buka pintu untuk konsultasi lanjutan di masa depan.\n"
            "- Jika sudah order: ingatkan soal video unboxing."
        ),
        "tone": "Hangat dan caring, seperti pamitan sama teman yang udah curhat.",
        "emotional_hook": "Buat user merasa dihargai secara personal, bukan template.",
        "do_not": "Jangan hard-sell di tahap ini. Jangan pakai template generik tanpa referensi percakapan.",
        "example_pattern": (
            "Makasih ya udah cerita soal masalah jerawatnya! Semoga ERHA ACSBP-nya bisa bantu "
            "redain jerawat kamu yang lagi meradang itu. Kalau nanti ada pertanyaan lagi soal "
            "skincare, jangan sungkan chat aku ya~ Semangat!"
        ),
        "transition_trigger": "",
        "response_length": "2-3 kalimat. Personal, singkat, dan hangat.",
    },
}

# ---------------------------------------------------------------------------
# Intent keywords
# ---------------------------------------------------------------------------
ORDER_INTENT_KEYWORDS = {
    "beli", "checkout", "co", "ambil", "pesan", "order", "gas", "lanjut",
}
PROMO_KEYWORDS = {
    "promo", "diskon", "ongkir", "gratis ongkir", "voucher", "harga", "murah",
    "berapa", "harganya",
}
TESTIMONY_KEYWORDS = {
    "testimoni", "review", "bukti", "cocok gak", "yakin",
    "pengalaman", "real",
}
CONSULTATION_KEYWORDS = {
    "jerawat", "berminyak", "bruntusan", "kusam", "iritasi", "komedo", "sensitif",
    "aman",
}
FAREWELL_KEYWORDS = {
    "makasih", "terima kasih", "thanks", "oke sip", "dadah", "bye",
}

# Short keywords (≤3 chars) that need word-boundary matching to avoid false positives
_SHORT_KEYWORDS = {"co", "gas", "bye"}

# Knowledge tiers: brief for greeting/farewell, full for everything else
_KNOWLEDGE_BRIEF_STAGES = {"greeting", "farewell"}
# All other stages get full knowledge

# Ordered stages for progression
_STAGE_ORDER = ["greeting", "opening", "consultation", "testimony", "promo", "closing", "farewell"]

_MAX_HISTORY_MESSAGES = 10

_STAGE_COMPACT_GUIDANCE = {
    "greeting": "Perkenalkan diri: 'Hai kak! Aku Lia dari Mengantar.' Tanyakan nama. MAX 2 kalimat.",
    "opening": "Validasi masalah user, ajak cerita. MAX 2-3 kalimat.",
    "consultation": "Empati + manfaat ERHA ACSBP yang relevan + ajakan coba. MAX 2-3 kalimat.",
    "testimony": "Berikan 1 testimoni paling relevan. Berikan kedua jika diminta. MAX 2-3 kalimat + kutipan.",
    "promo": "Sebut harga Rp110.900, BPOM + Halal, ajak beli. MAX 2-3 kalimat.",
    "closing": "Langkah order jelas, minta alamat, ingatkan video unboxing. MAX 3 kalimat.",
    "farewell": "Tutup hangat dan personal, tanpa hard-selling. MAX 2 kalimat.",
}

_TESTIMONIAL_QUOTES = [
    (
        "@amandabilla98 (Amanda): "
        "\"Oke banget sih buat perawatan jerawat! Awalnya aku cuma pake obat totol "
        "jerawatnya cocok banget akhirnya nyoba si facial washnya. Cocok, calming "
        "dan ngebantu redain jerawat yang lagi meradang.\""
    ),
    (
        "@silmisyauz (Silmi): "
        "\"Udah pake ini dari tahun 2023, selalu repurchase karena cocok banget "
        "sama kulitku yang acne-prone, bikin kulit jarang jerawat dan sehat, "
        "teksturnya kayak ada scrub kecil tapi ga sakit sama sekali, busa nya "
        "ada tapi gak to much.\""
    ),
]


# ---------------------------------------------------------------------------
# Conversation State
# ---------------------------------------------------------------------------
@dataclass
class ConversationState:
    """Tracks which stages have been covered in conversation history."""
    covered_stages: set[str] = field(default_factory=set)
    current_intent: str = "general"
    resolved_stage: str = "greeting"


# ---------------------------------------------------------------------------
# ThinkFilter — streaming state machine for <think> tags
# ---------------------------------------------------------------------------
class ThinkFilter:
    """Filters out <think>...</think> blocks from a token stream."""

    def __init__(self):
        self._inside_think = False
        self._buffer = ""

    def feed(self, token: str) -> str:
        """Feed a token, return filtered output (may be empty)."""
        self._buffer += token
        output = []

        while self._buffer:
            if self._inside_think:
                end_idx = self._buffer.find("</think>")
                if end_idx != -1:
                    self._buffer = self._buffer[end_idx + len("</think>"):]
                    self._inside_think = False
                else:
                    # Could be partial tag — keep buffering
                    if len(self._buffer) > 500:
                        self._buffer = self._buffer[-20:]
                    break
            else:
                start_idx = self._buffer.find("<think>")
                if start_idx != -1:
                    output.append(self._buffer[:start_idx])
                    self._buffer = self._buffer[start_idx + len("<think>"):]
                    self._inside_think = True
                elif "<" in self._buffer and not self._buffer.endswith(">"):
                    # Possible partial <think> tag — flush safe part
                    last_lt = self._buffer.rfind("<")
                    tail = self._buffer[last_lt:]
                    if "<think>"[:len(tail)] == tail:
                        output.append(self._buffer[:last_lt])
                        self._buffer = tail
                        break
                    else:
                        output.append(self._buffer)
                        self._buffer = ""
                else:
                    output.append(self._buffer)
                    self._buffer = ""

        return "".join(output)

    def flush(self) -> str:
        """Flush remaining buffer."""
        if self._inside_think:
            self._buffer = ""
            return ""
        out = self._buffer
        self._buffer = ""
        return out


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------
class PlannerAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    # -- Utility ----------------------------------------------------------

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
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

    # -- Stage Detection (hybrid) -----------------------------------------

    @staticmethod
    def _match_keywords(message: str, keywords: set[str]) -> bool:
        """Match keywords against message. Short keywords (≤3 chars) use
        word-boundary regex to prevent substring false-positives
        (e.g. 'co' must not match 'cocok')."""
        for kw in keywords:
            if kw in _SHORT_KEYWORDS:
                if re.search(rf"\b{re.escape(kw)}\b", message):
                    return True
            else:
                if kw in message:
                    return True
        return False

    @staticmethod
    def _detect_intent(input_text: str) -> str:
        """Detect the user's current intent from their message."""
        message = input_text.lower()

        if PlannerAgent._match_keywords(message, FAREWELL_KEYWORDS):
            return "farewell"
        if PlannerAgent._match_keywords(message, ORDER_INTENT_KEYWORDS):
            return "order"
        if PlannerAgent._match_keywords(message, PROMO_KEYWORDS):
            return "price"
        if PlannerAgent._match_keywords(message, TESTIMONY_KEYWORDS):
            return "testimony"
        if PlannerAgent._match_keywords(message, CONSULTATION_KEYWORDS):
            return "skin_concern"
        return "general"

    @staticmethod
    def _build_state(history: list[dict] | None) -> ConversationState:
        """Scan conversation history to determine which stages have been covered."""
        state = ConversationState()
        history = history or []

        assistant_messages = [
            m.get("content", "").lower()
            for m in history
            if m.get("role") == "assistant"
        ]
        all_text = " ".join(assistant_messages)

        if not assistant_messages:
            return state

        # Check covered stages by content analysis
        # Greeting: assistant has greeted (require greeting-specific phrases)
        greet_signals = ["selamat datang", "seneng banget kamu mampir", "kenalan dulu", "boleh tau nama"]
        if any(s in all_text for s in greet_signals):
            state.covered_stages.add("greeting")

        # Opening: assistant introduced self as advisor / asked about skin
        opening_signals = ["beauty advisor", "bantu soal skincare", "ada keluhan kulit", "masalah kulit"]
        if any(s in all_text for s in opening_signals):
            state.covered_stages.add("opening")

        # Consultation: discussed product ingredients with product context
        _product_terms = {"erha", "acsbp", "acneact", "produk"}
        _ingredient_terms = {"bha", "sulphur", "scrub biodegradable"}
        has_product = any(t in all_text for t in _product_terms)
        has_ingredient = any(t in all_text for t in _ingredient_terms)
        consult_signals = ["membersihkan pori", "minyak berlebih", "menghambat bakteri"]
        if (has_product and has_ingredient) or any(s in all_text for s in consult_signals):
            state.covered_stages.add("consultation")

        # Testimony: shared actual testimonials (require username mentions)
        testi_signals = ["amandabilla98", "silmisyauz", "@amandabilla", "@silmisyauz"]
        if any(s in all_text for s in testi_signals):
            state.covered_stages.add("testimony")

        # Promo: mentioned specific price
        promo_signals = ["110.900", "110900", "rp110"]
        if any(s in all_text for s in promo_signals):
            state.covered_stages.add("promo")

        # Closing: gave order instructions
        closing_signals = ["alamat lengkap", "proses pesanan", "video unboxing"]
        if any(s in all_text for s in closing_signals):
            state.covered_stages.add("closing")

        return state

    @staticmethod
    def _resolve_stage(intent: str, state: ConversationState) -> str:
        """Combine intent + state — honor user intent directly, no rigid prerequisites."""
        if intent == "farewell":
            return "farewell"
        if intent == "order":
            return "closing"
        if intent == "price":
            return "promo"
        if intent == "testimony":
            return "testimony"
        if intent == "skin_concern":
            return "consultation"

        # General intent: progress through stages naturally
        for stage in _STAGE_ORDER:
            if stage not in state.covered_stages:
                return stage

        return "closing"

    def _analyze_conversation(
        self, input_text: str, history: list[dict] | None
    ) -> tuple[str, ConversationState]:
        """Full conversation analysis: returns (stage, state)."""
        intent = self._detect_intent(input_text)
        state = self._build_state(history)
        state.current_intent = intent
        stage = self._resolve_stage(intent, state)
        state.resolved_stage = stage
        return stage, state

    # -- Message Building -------------------------------------------------

    @staticmethod
    def _trim_history(history: list[dict] | None, max_messages: int = _MAX_HISTORY_MESSAGES) -> list[dict]:
        if not history:
            return []
        normalized = [
            {"role": h.get("role", ""), "content": str(h.get("content", ""))}
            for h in history
            if h.get("role") in {"user", "assistant"} and str(h.get("content", "")).strip()
        ]
        if len(normalized) <= max_messages:
            return normalized
        return normalized[-max_messages:]

    @staticmethod
    def _build_compact_stage_block(stage: str, input_text: str) -> str:
        guidance = _STAGE_COMPACT_GUIDANCE.get(stage, _STAGE_COMPACT_GUIDANCE["consultation"])
        lines = [
            f"TAHAP_AKTIF={stage}",
            f"ATURAN_TAHAP={guidance}",
            "FORMAT=Maksimal 2-3 kalimat, bahasa Indonesia santai sopan.",
            "WAJIB=Selalu tutup dengan pertanyaan lanjutan atau CTA halus.",
        ]

        if stage == "testimony":
            message = input_text.lower()
            ask_for_many = any(token in message for token in {"dua", "2", "lebih banyak", "lainnya", "lagi"})
            selected_quotes = _TESTIMONIAL_QUOTES[:2] if ask_for_many else _TESTIMONIAL_QUOTES[:1]
            lines.append("TESTIMONI_VERBATIM:")
            lines.extend(f"- {quote}" for quote in selected_quotes)

        return "\n".join(lines)

    @staticmethod
    def _generation_config_for_stage(stage: str) -> GenerateConfig:
        return GenerateConfig(
            temperature=0.45,
        )

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

        stage_block = self._build_compact_stage_block(stage=stage, input_text=input_text)
        sales_prompt_template = resolve_prompt("sales_system") or ""
        sales_prompt = ""
        if sales_prompt_template:
            try:
                sales_prompt = sales_prompt_template.format(
                    stage=stage,
                    stage_instruction=_STAGE_COMPACT_GUIDANCE.get(stage, ""),
                )
                # Admin prompt override can be very long; clamp to keep token budget healthy.
                sales_prompt = " ".join(str(sales_prompt).split())[:500]
            except Exception:
                sales_prompt = ""

        if stage in _KNOWLEDGE_BRIEF_STAGES:
            product_block = PRODUCT_KNOWLEDGE_BRIEF
        else:
            product_block = PRODUCT_KNOWLEDGE_FULL

        parts = [BASE_SYSTEM_PROMPT]
        if sales_prompt:
            parts.append(sales_prompt)
        parts.append(stage_block)
        if product_block:
            parts.append(product_block)
        system_prompt = "\n\n".join(parts)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        if memory_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Ringkasan user sebelumnya:\n{str(memory_summary)[:500]}",
                }
            )

        if database_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Konteks database relevan:\n{str(database_context)[:700]}",
                }
            )

        if vector_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Konteks retrieval relevan:\n{str(vector_context)[:700]}",
                }
            )

        messages.extend(self._trim_history(history))
        messages.append({"role": "user", "content": input_text})
        return messages

    # -- Execute (blocking) -----------------------------------------------

    def execute(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> AgentResult:
        stage, _state = self._analyze_conversation(input_text, history=history)
        messages = self._build_messages(
            input_text=input_text,
            stage=stage,
            history=history,
            context=context,
        )

        response = self.llm.generate(
            messages=messages,
            config=self._generation_config_for_stage(stage),
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

    # -- Execute Stream (true streaming) ----------------------------------

    def execute_stream(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> Generator[dict, None, None]:
        stage, _state = self._analyze_conversation(input_text, history=history)
        messages = self._build_messages(
            input_text=input_text,
            stage=stage,
            history=history,
            context=context,
        )

        yield {"type": "thinking", "content": f"Tahap percakapan: {stage}\n"}

        think_filter = ThinkFilter()
        full_output = []
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        has_content = False

        try:
            for token in self.llm.generate_stream(
                messages=messages,
                config=self._generation_config_for_stage(stage),
            ):
                filtered = think_filter.feed(token)
                if filtered:
                    has_content = True
                    full_output.append(filtered)
                    yield {"type": "content", "content": filtered}

            # Flush any remaining buffer
            remaining = think_filter.flush()
            if remaining:
                has_content = True
                full_output.append(remaining)
                yield {"type": "content", "content": remaining}

        except Exception:
            if not has_content:
                yield {
                    "type": "content",
                    "content": "Maaf, belum ada jawaban. Bisa diulang dengan detail kebutuhan kamu?",
                }

        if not has_content:
            yield {
                "type": "content",
                "content": "Maaf, belum ada jawaban. Bisa diulang dengan detail kebutuhan kamu?",
            }

        output_text = "".join(full_output)
        usage = self._normalize_usage({}, prompt_text=prompt_text, output_text=output_text)
        provider, model = self._resolve_llm_identity()

        yield {
            "type": "meta",
            "metadata": {
                "agent": "sales",
                "stage": stage,
                "model": {"provider": provider, "name": model},
                "usage": usage,
            },
        }

