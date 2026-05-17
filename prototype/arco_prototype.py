import sys
import threading
import time

import numpy as np
import sounddevice as sd
from pynput import keyboard, mouse

SAMPLE_RATE = 44100
BLOCK_SIZE = 256

NOTE_FREQS = {
    "a": 293.66,  # D4
    "s": 349.23,  # F4
    "d": 392.00,  # G4
    "f": 440.00,  # A4
    "g": 523.25,  # C5
}

NOTE_NAMES = {
    "a": "D4",
    "s": "F4",
    "d": "G4",
    "f": "A4",
    "g": "C5",
}

lock = threading.Lock()
curr_freq = NOTE_FREQS["a"]
bow_intensity = 0.0
preset_idx = 0

PRESETS = [
    {
        "name": "Staccato",
        "decay": 0.9960,
        "brightness": 0.40,
        "reverb": 0.08,
        "excite_amount": 0.60,
    },
    {
        "name": "Sustained",
        "decay": 0.9998,
        "brightness": 0.30,
        "reverb": 0.35,
        "excite_amount": 0.20,
    },
]


class WaveguideVoice:
    """Karplus-Strong digital waveguide.
    
    Ref: https://ccrma.stanford.edu/~jos/pasp/Karplus_Strong_Algorithm.html
    Circular buffer of samples: each sample travels around the loop, losing energy each cycle through the loop filter. Loop length sets the pitch.
    """

    def __init__(self, freq: float, sample_rate: int) -> None:
        self.sr = sample_rate
        self.delay_len = max(2, int(round(sample_rate / freq)))
        self.delay = np.zeros(self.delay_len, dtype=np.float32)
        self.pos = 0
        self.freq = freq
    
    def retune(self, freq: float) -> None:
        """Change pitch. Resets the delay line."""
        self.freq = freq
        self.delay_len = max(2, int(round(self.sr / freq)))
        self.delay = np.zeros(self.delay_len, dtype=np.float32)
        self.pos = 0
    
    def excite(self, amount: float) -> None:
        """Inject a noise burst into the delay line."""
        burst_len = min(self.delay_len, max(4, int(self.delay_len * 0.15)))
        noise = np.random.uniform(-amount, amount, burst_len).astype(np.float32)
        for i in range(burst_len):
            idx = (self.pos + i) % self.delay_len
            self.delay[idx] = noise[i]

    def process(self, num_samples: int, preset: dict, bow: float) -> np.ndarray:
        """Generate num_samples of audio.

        - Read current value from delay line
        - Apply loop filter
        - Apply decay
        - Optionally add soft distortion
        - Add tiny noise if bowing
        - Write back into delay line
        - Output
        """
        out = np.zeros(num_samples, dtype=np.float32)
        decay = preset["decay"]
        bright = preset["brightness"]

        for i in range(num_samples):
            cur = self.delay[self.pos]
            nxt = self.delay[(self.pos + 1) % self.delay_len]
            
            # Blend between lowpass and current
            filtered = (1.0 - bright) * 0.5 * (cur + nxt) + bright * cur
            # Simple one-pole high shelf cut
            # Ref: https://ccrma.stanford.edu/~jos/filters/One_Pole.html
            filtered *= 0.98
            
            # Multiply by just-under-1.0 each sample to add decay
            filtered *= decay

            # Trickle noise while bowing
            if bow > 0.05:
                filtered += np.random.uniform(-bow * 0.06, bow * 0.06)
            
            self.delay[self.pos] = filtered
            out[i] = filtered
            self.pos = (self.pos + 1) % self.delay_len

        return out


class SimpleReverb:
    """Single feedback comb filter reverb, adds space and tail.

    Ref: Schroeder (1962) comb filter
    https://ccrma.stanford.edu/~jos/pasp/Feedback_Comb_Filters.html
    """

    def __init__(self, sample_rate: int) -> None:
        # Delay length sets the room size
        comb_len = int(sample_rate * 0.043)
        self.comb = np.zeros(comb_len, dtype=np.float32)
        self.cpos = 0  # Current position of circular buffer
        self.fb = 0.82  # How much of the delay signal feeds back
    
    def process(self, signal: np.ndarray) -> np.ndarray:
        """Apply reverb to a block of samples."""
        out = np.zeros_like(signal)
        for i, s in enumerate(signal):
            delayed = self.comb[self.cpos]
            self.comb[self.cpos] = s + delayed * self.fb
            self.cpos = (self.cpos + 1) % len(self.comb)
            out[i] = delayed
        return out


voice = WaveguideVoice(NOTE_FREQS["a"], SAMPLE_RATE)
reverb = SimpleReverb(SAMPLE_RATE)

needs_excite = False


def audio_callback(
    out_data: np.ndarray,
    frames: int,
    time_info: object,
    status: sd.CallbackFlags
) -> None:
    """Called by sounddevice every BLOCK_SIZE samples."""
    global needs_excite

    # Snapshot shared state under lock so keyboard/mouse threads can't change values mid-block
    with lock:
        preset = PRESETS[preset_idx]
        bow = bow_intensity
        excite = needs_excite
        needs_excite = False
    
    if excite:
        amount = preset.get("excite_amount", 0.3)
        voice.excite(amount)
    
    block = voice.process(frames, preset, bow)

    rev_mix = preset["reverb"]
    if rev_mix > 0.0:
        wet = reverb.process(block)
        block = block * (1.0 - rev_mix) + wet * rev_mix
    
    # Brickwall limiter at 0db
    block = np.tanh(block * 2.0) * 0.5

    # Both stereo channels
    out_data[:, 0] = block
    out_data[:, 1] = block


_last_mouse_y: float = 0.0
_mouse_velocity: float = 0.0


def on_mouse_move(x: float, y: float) -> None:
    """Called by pynput every time the mouse moves.

    Use absolute Y speed as the bow intensity.
    """
    global _last_mouse_y, _mouse_velocity, bow_intensity

    delta = abs(y - _last_mouse_y)
    _last_mouse_y = y

    # Scale delta to 0.0-1.0 intensity range
    _mouse_velocity = min(delta / 30.0, 1.0)

    with lock:
        bow_intensity = _mouse_velocity


def mouse_decay_loop() -> None:
    """Runs in its own thread.

    Mouse still -> bow intensity decays towards zero
    """
    global bow_intensity

    while True:
        time.sleep(0.03)
        with lock:
            bow_intensity = max(0.0, bow_intensity - 0.15)


def print_status() -> None:
    """Print current instrument state to terminal."""
    with lock:
        preset_name = PRESETS[preset_idx]["name"]
        freq = voice.freq
        bow = bow_intensity
    
    note = next(
        (name for key, name in NOTE_NAMES.items() if NOTE_FREQS[key] == freq), "---"
    )

    sys.stdout.write(
        f"\r\033[K"
        f"Preset: [{preset_name:<14}]  "
        f"Note: {note}  "
        f"Bow: {bow:.2f}  "
        f"| ASDFG=pitch  mouse=bow  P=preset  Q=quit"
    )
    sys.stdout.flush()


def handle_key(ch: str) -> bool:
    """Handle a keypress. Returns False if we should quit."""
    global needs_excite, preset_idx

    if ch in NOTE_FREQS:
        with lock:
            freq = NOTE_FREQS[ch]
            if freq != voice.freq:
                voice.retune(freq)
            needs_excite = True
        print_status()

    elif ch == 'p':
        with lock:
            preset_idx = (preset_idx + 1) % len(PRESETS)
            voice.retune(voice.freq)  # reset delay line on preset change
            needs_excite = True
        print_status()

    elif ch == 'q':
        return False

    return True


def main() -> None:
    import tty
    import termios

    decay_thread = threading.Thread(target=mouse_decay_loop, daemon=True)
    decay_thread.start()

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        channels=2,
        dtype="float32",
        callback=audio_callback,
    )

    mouse_listener = mouse.Listener(on_move=on_mouse_move)

    print("Arco - starting...")
    print("Move mouse to bow. ASDFG = pitch. P = preset. Q = quit.\n")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        import tty
        tty.setcbreak(fd)
        with stream, mouse_listener:
            print_status()
            while True:
                ch = sys.stdin.read(1).lower()
                if not handle_key(ch):
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\nArco stopped.")


if __name__ == "__main__":
    main()
