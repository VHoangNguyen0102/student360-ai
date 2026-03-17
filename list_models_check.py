import os
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
print(f"Using API Key: {api_key[:10]}...") 

if not api_key:
    print("No API Key found")
    exit(1)

client = genai.Client(api_key=api_key)

try:
    print("Available models:")
    for m in client.models.list():
        print(f" - {m.name}")
except Exception as e:
    print(f"Error listing models: {e}")
