import requests

def ask_mistral(prompt: str) -> str:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }
    )
    result = response.json()
    return result.get("response", "").strip()
