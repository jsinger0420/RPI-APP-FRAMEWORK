# SoundMixer — `sound_mixer.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ (pure Python)
- **pip extra:** none
- **Last hardware test:** none yet

## Hardware
None: sums `SoundStream`s into buffers for `I2SDACDeviceManager` (see `i2s_dac.md`).

## Wiring
None.

## API
| Member | Description |
|---|---|
| `SoundMixer(name=None, buffer_size=None, sample_rate=22050, dac=None, drop_finished=True, log_func=None, app=None)` | `dac=` supplies the rate and (Linux) the ALSA period as defaults; otherwise 512 samples. |
| `add_stream(s)` / `remove_stream(s)` | Streams must have the mixer's sample rate; adding a finished stream rewinds it. |
| `mix()` | Next `buffer_size` samples (`array("h")`, reused by the next call): sum of active streams, clipped to ±32767. |
| `is_active`, `streams`, `buffer_size`, `sample_rate`, `drop_finished` | State. |
| `close()` | Forget the streams. |

Logs only when a stream finishes (not per buffer).

## Platform differences
None. On the Pico, mixing is pure Python: about `buffer_size × streams` additions per
call — measure with the hardware test before using many streams at 22 kHz.

## Safe state
Not applicable.

## Known issues / TODO
- A `@micropython.viper` inner loop would speed up mixing on the Pico.

## Example
See `i2s_dac.md` § Example.
