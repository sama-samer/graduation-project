import sounddevice as sd
from scipy.io.wavfile import write
import whisper



def record_audio(filename="recorded_audio.wav", duration=5, fs=16000):
    print("Recording started...")
    
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
    sd.wait()  # Wait until recording is finished
    
    write(filename, fs, recording)
    
    print(f"Recording saved as {filename}")
    return filename


def transcribe_audio(audio_path):
    print("Loading Whisper model...")
    model = whisper.load_model("base")   
    
    print("Transcribing...")
    result = model.transcribe(audio_path)
    
    return result["text"]

if __name__ == "__main__":
    
    audio_file = record_audio(duration=5)
    
    text = transcribe_audio(audio_file)
    
    print("\n===== TRANSCRIPT =====")
    print(text)