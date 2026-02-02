from pathlib import Path

IMAGE_DIR = Path("app/static/diseases")

def get_disease_image_url(disease_id: str) -> str:
    filename = f"{disease_id}.png"

    if (IMAGE_DIR / filename).exists():
        return f"/static/diseases/{filename}"

    return "/static/diseases/default.png"
