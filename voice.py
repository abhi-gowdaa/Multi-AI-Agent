import sounddevice as sd
import tempfile
from scipy.io.wavfile import write
import google.generativeai as genai
import os

import tempfile
from groq import Groq
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()


client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

 

# Record mic
def record_audio(duration=7, fs=16000):
    print("🎤 Listening...")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="int16")
    sd.wait()
    temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    write(temp_wav.name, fs, recording)
    return temp_wav.name


def transcribe(file_path):
# Open the audio file
    with open(file_path, "rb") as file:
        # Create a translation of the audio file
        translation = client.audio.translations.create(
        file=(file_path, file.read()), # Required audio file
        model="whisper-large-v3", # Required model to use for translation
        prompt="Specify context or spelling",  # Optional
        response_format="json",  # Optional
        temperature=0.0  # Optional
        )
        # Print the translation text
        print(translation.text)
        
        return translation.text


 
