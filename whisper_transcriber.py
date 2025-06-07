import whisper

model = whisper.load_model("base")  # можно заменить на "small" или "medium"

def transcribe(audio_path: str) -> str:
    result = model.transcribe(audio_path)
    return result["text"]
