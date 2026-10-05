"""
AutoMovie Pro - Voice Cues Generator
Synthesizes and saves actual, high-quality audio wave files (.wav) to disk
for all pre-determined Jarvis commentary stages, greetings, and chimes.
"""

import os
import sys
import math
import wave
import struct
from pathlib import Path

AUDIO_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio" / "voice_cues"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def generate_synthesized_cue(filename: str, frequencies: list, durations: list, sample_rate: int = 22050):
    """
    Generates a crisp, futuristic harmonic audio chime for Jarvis cues.
    Guaranteed zero-dependency native audio synthesis.
    """
    out_path = AUDIO_DIR / filename
    n_channels = 1
    sampwidth = 2
    total_frames = int(sample_rate * sum(durations))

    with wave.open(str(out_path), "w") as wav_file:
        wav_file.setparams((n_channels, sampwidth, sample_rate, total_frames, "NONE", "not compressed"))
        
        for freq, duration in zip(frequencies, durations):
            num_samples = int(sample_rate * duration)
            for i in range(num_samples):
                # Envelope: smooth attack & decay
                t = i / sample_rate
                envelope = math.sin(math.pi * (i / num_samples))
                # Primary harmonic tone + upper futuristic overtone
                sample = envelope * (
                    0.7 * math.sin(2.0 * math.pi * freq * t) +
                    0.3 * math.sin(2.0 * math.pi * (freq * 2.02) * t)
                )
                clamped = int(max(-32767, min(32767, sample * 32767)))
                wav_file.writeframes(struct.pack("<h", clamped))

    print(f"Generated audio cue: {filename} ({os.path.getsize(out_path)} bytes)")


def generate_speech_file_via_sapi(filename: str, text: str):
    """
    Attempts to use Windows native SAPI to render natural spoken voice directly to file.
    """
    out_path = str(AUDIO_DIR / filename)
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        filestream = win32com.client.Dispatch("SAPI.SpFileStream")
        # 3 = SSFMCreateForWrite
        filestream.Open(out_path, 3, False)
        speaker.AudioOutputStream = filestream
        speaker.Speak(text)
        filestream.Close()
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            print(f"SAPI voice generated: {filename} ({os.path.getsize(out_path)} bytes)")
            return True
    except Exception:
        pass
    return False


CUE_DEFINITIONS = [
    # 1. Startup & Welcome
    {
        "file": "startup_chime.wav",
        "freqs": [523.25, 659.25, 783.99, 1046.50],
        "durs": [0.12, 0.12, 0.15, 0.40],
        "speech": "AutoMovie Pro Jarvis online. Systems ready."
    },
    {
        "file": "welcome_bn.wav",
        "freqs": [440.0, 554.37, 659.25, 880.0],
        "durs": [0.15, 0.15, 0.18, 0.45],
        "speech": "Assalamu Alaikum. AutoMovie Pro is ready."
    },
    {
        "file": "welcome_en.wav",
        "freqs": [440.0, 554.37, 659.25, 880.0],
        "durs": [0.15, 0.15, 0.18, 0.45],
        "speech": "Welcome to AutoMovie Pro. All systems are operational."
    },
    # 2. 15 Specific Requirements Progress Commentary Cues (Lines 213-229)
    {
        "file": "cue_topic_research.wav",
        "freqs": [587.33, 739.99, 880.0],
        "durs": [0.12, 0.14, 0.35],
        "speech": "Starting topic research for short video production."
    },
    {
        "file": "cue_topic_found.wav",
        "freqs": [659.25, 880.0, 1108.73],
        "durs": [0.10, 0.12, 0.30],
        "speech": "A high CTR viral topic has been successfully discovered."
    },
    {
        "file": "cue_title_script.wav",
        "freqs": [493.88, 659.25, 987.77],
        "durs": [0.12, 0.14, 0.35],
        "speech": "Generating SEO friendly title and high retention script."
    },
    {
        "file": "cue_script_ready.wav",
        "freqs": [659.25, 783.99, 1046.50],
        "durs": [0.10, 0.12, 0.30],
        "speech": "Script generated successfully. Total scenes 15, duration 78 seconds."
    },
    {
        "file": "cue_localize_start.wav",
        "freqs": [523.25, 659.25, 783.99],
        "durs": [0.12, 0.12, 0.30],
        "speech": "Initiating script localization pipeline."
    },
    {
        "file": "cue_localize_bn_progress.wav",
        "freqs": [587.33, 698.46, 880.0],
        "durs": [0.12, 0.14, 0.35],
        "speech": "Bengali language localization is actively processing."
    },
    {
        "file": "cue_localize_bn_done.wav",
        "freqs": [659.25, 880.0, 1046.50],
        "durs": [0.10, 0.12, 0.30],
        "speech": "Bengali localization completed successfully."
    },
    {
        "file": "cue_localize_hi_progress.wav",
        "freqs": [587.33, 739.99, 880.0],
        "durs": [0.12, 0.14, 0.35],
        "speech": "Hindi language localization is in progress."
    },
    {
        "file": "cue_localize_hi_done.wav",
        "freqs": [659.25, 880.0, 1174.66],
        "durs": [0.10, 0.12, 0.30],
        "speech": "Hindi localization completed successfully."
    },
    {
        "file": "cue_audio_gen_start.wav",
        "freqs": [440.0, 554.37, 659.25, 880.0],
        "durs": [0.14, 0.14, 0.18, 0.40],
        "speech": "Starting master audio synthesis. High fidelity voice generation active."
    },
    {
        "file": "cue_agnes_generating.wav",
        "freqs": [523.25, 698.46, 880.0],
        "durs": [0.14, 0.16, 0.40],
        "speech": "Generating visual video clip for scene one through Agnes engine."
    },
    {
        "file": "cue_agnes_fallback_google.wav",
        "freqs": [880.0, 783.99, 659.25, 523.25],
        "durs": [0.12, 0.12, 0.15, 0.35],
        "speech": "Agnes returned 450 error. Switching to Google fallback circuit."
    },
    {
        "file": "cue_scene1_done.wav",
        "freqs": [587.33, 880.0, 1174.66],
        "durs": [0.12, 0.15, 0.45],
        "speech": "Scene one video rendering and timing synchronized."
    },
    {
        "file": "cue_pollinations_image.wav",
        "freqs": [493.88, 659.25, 880.0, 987.77],
        "durs": [0.10, 0.12, 0.14, 0.30],
        "speech": "Generating high quality cinematic image via Pollinations for scene two."
    },
    {
        "file": "cue_upload_starting.wav",
        "freqs": [523.25, 659.25, 783.99, 1046.50, 1318.51],
        "durs": [0.10, 0.10, 0.12, 0.15, 0.50],
        "speech": "Starting automated multi-platform short video upload."
    },
    # 3. Notification & Captcha
    {
        "file": "captcha_alert.wav",
        "freqs": [880.0, 440.0, 880.0, 440.0],
        "durs": [0.15, 0.15, 0.15, 0.35],
        "speech": "Attention. Captcha challenge detected."
    },
    {
        "file": "notification_chime.wav",
        "freqs": [783.99, 1046.50],
        "durs": [0.10, 0.25],
        "speech": "Notice."
    }
]


def main():
    print(f"Targeting audio directory: {AUDIO_DIR}")
    for item in CUE_DEFINITIONS:
        fname = item["file"]
        # Try Windows SAPI first
        created_speech = generate_speech_file_via_sapi(fname, item["speech"])
        if not created_speech:
            # Fallback to harmonic audio synthesizer
            generate_synthesized_cue(fname, item["freqs"], item["durs"])

    print("\nAll audio cues successfully created on disk!")


if __name__ == "__main__":
    main()
