import whisper

model = whisper.load_model("large")  

def transcribe(audio_path: str, lang: str = "en") -> str:
    result = model.transcribe(audio_path, language=lang)
    return result["text"]
