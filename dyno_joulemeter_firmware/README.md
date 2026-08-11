# Dyno Joulemeter Firmware

Arduino sketch for the prototype dyno joulemeter board. It measures voltage and current through an ADS1115, estimates live power, integrates run energy in joules, shows values on a small SSD1306 OLED, and broadcasts live output measurements to the vehicle WROVER relay over ESP-NOW.

## Hardware Role

Use this alongside the Python DL24 load slider when the dyno needs an independent meter for generator output:

- voltage sense into ADS1115 `AIN2`
- ACS712 current sensor output into ADS1115 `AIN1`
- SSD1306 OLED on I2C address `0x3C`
- ADS1115 on I2C address `0x48`
- red start/resume button on GPIO `4`, active low
- yellow stop/pause/reset button on GPIO `5`, active low
- ESP32 I2C pins: SDA `8`, SCL `9`
- ESP-NOW broadcast on Wi-Fi channel `1`

## Arduino Libraries

Install these through Arduino IDE Library Manager:

- `Adafruit SSD1306`
- `Adafruit GFX Library`
- `Adafruit ADS1X15`

ESP-NOW and Wi-Fi support come from the ESP32 Arduino core.

## Wireless live telemetry

The dyno C3 sends a versioned `DynoTelemetryPacket` every 500 ms. The packet includes voltage, current, output power, accumulated joulemeter energy, run state, boot ID, and sequence number. It is best-effort and has no outage buffer, so local measurement and the OLED continue if the WROVER or LTE connection is unavailable.

Flash the matching `lte_relay` change from `UTSM-proto/utsm-telem-firmware` to the existing WROVER/A7670 board. Both the car C3 and dyno C3 broadcast on channel 1; the relay keeps a separate newest packet for each source.

Expected dyno serial output at 115200 baud:

```text
Dyno ESP-NOW ready (broadcast, channel 1, every 500 ms)
Dyno ESP-NOW queued seq=12 P=84.215 W
```

Flash `dyno_joulemeter_firmware.ino` to the dyno C3 after flashing the WROVER
relay. The existing live-car C3 can remain
on its current compatible live-telemetry firmware. After flashing the dyno C3,
require both the `Dyno ESP-NOW queued` line above and the relay's matching
`DYNO seq=N delivered` line before treating the wireless path as working.

The old temporary sketch also included `ADS1X58.h`; this checked-in version uses the Adafruit ADS1115 API that the code actually calls.

## Calibration Constants

The important constants live near the top of `dyno_joulemeter_firmware.ino`:

```cpp
const float CURRENT_SENSOR_V_PER_A = 0.066f;
const float VOLTAGE_SCALE = 11.0f;
```

At every boot, the OLED displays **Zeroing current** while the firmware waits
two seconds for the ACS712 to settle and then averages its zero-current output
for three seconds. Keep the dyno stopped with no current flowing throughout
this sequence. The measured voltage becomes the run's current zero offset.

Readings within `0.03 A` of calibrated zero and voltage readings within
`0.005 V` of zero are displayed and transmitted as zero to suppress idle noise.

`CURRENT_SENSOR_V_PER_A` is `0.066 V/A`, matching a common ACS712 30 A module. Change it if the installed sensor is a 5 A or 20 A version.

`VOLTAGE_SCALE` matches the installed divider: `10 kOhm` from dyno positive
to ADS1115 AIN2 and `1 kOhm` from AIN2 to ground. The ADC sees
`Vin * 1k / (10k + 1k)`, so the input-voltage multiplier is `11.0`. Keep the
divider installed; do not connect dyno voltage directly to the ADS1115 input.

## Controls

- IDLE: shows live V/I/P and waits for Start.
- RUNNING: starts the timer, accumulates voltage/current averages, and integrates joules.
- PAUSED: shows elapsed time, average voltage, average current, average power, and total joules.
- Start while paused resumes the same run.
- Stop while paused resets back to idle.

Serial output is CSV-style:

```text
millis,elapsed_ms,voltage_v,current_a,power_w,energy_j,state
```

This makes it easy to log the joulemeter output on a laptop while the OLED is used at the dyno.
