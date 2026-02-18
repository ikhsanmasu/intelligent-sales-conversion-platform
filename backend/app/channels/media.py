import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelImage:
    title: str
    image_url: str
    source_url: str


_TESTIMONIAL_CELEBRITY_IMAGES: list[ChannelImage] = [
    ChannelImage(
        title="Taylor Swift",
        image_url="https://upload.wikimedia.org/wikipedia/commons/b/b1/Taylor_Swift_at_the_2023_MTV_Video_Music_Awards_%283%29.png",
        source_url="https://en.wikipedia.org/wiki/Taylor_Swift",
    ),
    ChannelImage(
        title="Emma Watson",
        image_url="https://upload.wikimedia.org/wikipedia/commons/7/7f/Emma_Watson_2013.jpg",
        source_url="https://en.wikipedia.org/wiki/Emma_Watson",
    ),
    ChannelImage(
        title="Chris Hemsworth",
        image_url="https://upload.wikimedia.org/wikipedia/commons/8/86/Chris_Hemsworth_-_Crime_101.jpg",
        source_url="https://en.wikipedia.org/wiki/Chris_Hemsworth",
    ),
    ChannelImage(
        title="Tom Cruise",
        image_url="https://upload.wikimedia.org/wikipedia/commons/b/b5/Tom_Cruise-2428.jpg",
        source_url="https://en.wikipedia.org/wiki/Tom_Cruise",
    ),
    ChannelImage(
        title="Selena Gomez",
        image_url="https://upload.wikimedia.org/wikipedia/commons/8/81/Selena_Gomez_at_the_2024_Toronto_International_Film_Festival_10_%28cropped%29.jpg",
        source_url="https://en.wikipedia.org/wiki/Selena_Gomez",
    ),
    ChannelImage(
        title="Ariana Grande",
        image_url="https://upload.wikimedia.org/wikipedia/commons/7/7c/Ariana_Grande_promoting_Wicked_%282024%29.jpg",
        source_url="https://en.wikipedia.org/wiki/Ariana_Grande",
    ),
]


def pick_random_testimonial_image() -> ChannelImage:
    return random.choice(_TESTIMONIAL_CELEBRITY_IMAGES)


def format_testimony_reply_text(base_text: str) -> str:
    clean = str(base_text or "").strip()
    if not clean:
        return ""
    return (
        "✨ Testimoni Real Pengguna\n\n"
        f"{clean}\n\n"
        "Kalau mau, aku bantu lanjut ke cara pakai paling aman buat kondisi kulit kamu."
    )
