# SoundStream — `sound_stream.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ (pure Python)
- **pip extra:** none
- **Last hardware test:** none yet

## Hardware
None: a sound held in memory, played through `SoundMixer` / `I2SDACDeviceManager`
(see `i2s_dac.md`).

Files must be **WAV, 16-bit PCM, mono**. Convert with
`ffmpeg -i in.mp3 -ac 1 -ar 16000 -sample_fmt s16 out.wav` (or Audacity: Tracks → Mix
to mono, Export as WAV "Signed 16-bit PCM"). The whole file is loaded: 1 s at 16 kHz is
32 KB, so keep sounds short on the Pico.

## Wiring
None.

## API
| Member | Description |
|---|---|
| `SoundStream(name=None, path=None, samples=None, sample_rate=22050, volume=1.0, loop=False, log_func=None, app=None)` | Load `path` (rate taken from the file) or wrap an `array("h")`. |
| `volume` | 0.0–1.0, settable while playing. |
| `loop` | Repeat at the end. |
| `rewind()` / `stop()` | Restart / stop playing. |
| `active`, `position`, `duration_s`, `sample_rate`, `samples`, `path` | State. |
| `add_into(acc, n)` | Used by the mixer: add the next `n` scaled samples into an int array. |
| `close()` | Stop and free the samples. |

## Platform differences
None. The WAV reader is built in (MicroPython has no `wave` module).

## Safe state
Not applicable.

## Known issues / TODO
- No streaming from flash for long sounds; no stereo or 8-bit files.

## Example
See `i2s_dac.md` § Example.
