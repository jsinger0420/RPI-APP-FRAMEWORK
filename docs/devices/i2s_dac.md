# I2SDACDeviceManager — `i2s_dac.py`

- **Status:** current (v0.2.0 contract, Step 5; module was `I2SDACdevice_manager.py`)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ (ALSA) · Pi 5 verified ✗
- **pip extra:** `audio` (pyalsaaudio ≥ 0.9) on Raspberry Pi OS
- **Last hardware test:** none yet (simulated Pico 2 W and Raspberry Pi OS only)

## Hardware
MAX98357A I2S class-D amplifier breakout (Adafruit 3006 and clones): takes digital I2S
audio and drives a 4–8 Ω speaker directly (up to ~3 W at 5 V).

- VIN 2.5–5.5 V (5 V for full volume); logic pins accept 3.3 V.
- GAIN pin sets 3/6/9/12/15 dB (unconnected = 9 dB).
- SD (shutdown/channel select): unconnected = mono mix of left+right, which is what this
  class sends (mono).
- Audio format used here: **16-bit signed mono PCM**, one of 8000–48000 Hz.

## Wiring
| Board pin | Pico pin (example) | Pi header pin (BCM) | Notes |
|---|---|---|---|
| VIN | VBUS (pin 40) or 3V3 | 5V (pin 2) | 5 V = louder |
| GND | GND | GND (pin 6) | |
| BCLK | GP10 (`sck_pin`) | GPIO18 / PCM_CLK (pin 12) | Pi pins are fixed |
| LRC | GP11 (`ws_pin`) | GPIO19 / PCM_FS (pin 35) | **Pico: must be BCLK + 1** |
| DIN | GP12 (`sd_pin`) | GPIO21 / PCM_DOUT (pin 40) | |
| speaker + / − | — | — | 4–8 Ω |

Raspberry Pi OS: add `dtoverlay=max98357a` to `/boot/firmware/config.txt` (older images:
`/boot/config.txt`), reboot, check `aplay -l` lists the card. Install the extra:
`sudo apt install python3-dev libasound2-dev` then `pip install rpi-app-framework[audio]`.

## API
```python
dac = I2SDACDeviceManager("speaker", sck_pin=10, ws_pin=11, sd_pin=12, app=self)  # Pico
dac = I2SDACDeviceManager("speaker", alsa_device="default", app=self)            # Pi
```

| Member | Description |
|---|---|
| `I2SDACDeviceManager(name=None, sck_pin=None, ws_pin=None, sd_pin=None, sample_rate=22050, i2s_id=0, ibuf=8192, alsa_device="default", log_func=None, app=None)` | Opens the DAC. Pico: three pins required, `ws_pin == sck_pin + 1`. Linux: ALSA device (`OSError` if it can't be opened). |
| `write(samples)` | Play `array("h")` or bytes of 16-bit samples; blocks while the DAC buffer is full. Returns bytes written. |
| `play(source, buffer_size=None)` | Blocking: play a `SoundStream` or `SoundMixer` until it finishes; returns samples played. |
| `periodsize` | ALSA period in samples (Linux) — a good mixer `buffer_size`; None on the Pico. |
| `sample_rate`, `sck_pin`, `ws_pin`, `sd_pin`, `alsa_device` | Configuration. |
| `close()` | Stops the I2S clock / closes ALSA (amp goes silent). Idempotent. |

## Playing while the app runs
Feed one mixer buffer per `loop()` tick; the buffer must cover the tick:

```python
self.mixer = SoundMixer("mix", dac=self.dac, buffer_size=2205)   # 0.1 s at 22050 Hz
...
def loop(self):            # loop_interval=0.1
    self.dac.write(self.mixer.mix())
```

`write()` blocks when the DAC is full, so audio paces the loop. Gaps (a slow `loop()`)
make clicks; a larger `ibuf` (Pico) hides short gaps.

## Platform differences
- Pico: `machine.I2S` TX, 16-bit mono, pins of your choice (WS = SCK + 1).
- Raspberry Pi OS: ALSA playback, fixed PCM pins, overlay required; other ALSA devices
  (USB sound cards, HDMI) work too via `alsa_device`.

## Safe state
`close()` (app stop, Ctrl-C, crash with `app=self`) stops the clock or closes the ALSA
device; the MAX98357A outputs silence without a clock. (Cutting power fully needs the
SD pin pulled low — not handled.)

## Known issues / TODO
- Mono 16-bit only; no volume control on the DAC itself (use `SoundStream.volume`).
- Pure-Python mixing on the Pico is CPU-heavy; measure in the hardware test.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.i2s_dac import I2SDACDeviceManager
from rpi_app_framework.sound_mixer import SoundMixer
from rpi_app_framework.sound_stream import SoundStream


class Doorbell(RPIApp):
    def setup(self):
        self.dac = I2SDACDeviceManager("speaker", sck_pin=10, ws_pin=11, sd_pin=12,
                                       sample_rate=16000, app=self)
        self.ding = SoundStream("ding", path="ding.wav", app=self)   # 16 kHz mono
        self.mixer = SoundMixer("mix", dac=self.dac, buffer_size=1600, app=self)
        self.mixer.add_stream(self.ding)

    def loop(self):
        self.dac.write(self.mixer.mix())   # silence once the ding has finished


Doorbell(app_name="Doorbell", loop_interval=0.1).start()
```
