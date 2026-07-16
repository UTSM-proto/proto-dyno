# Dyno Joulemeter Firmware

Arduino sketch for the prototype dyno joulemeter board. It measures voltage and current through an ADS1115, estimates live power, integrates run energy in joules, and shows values on a small SSD1306 OLED.

## Hardware Role

Use this alongside the Python DL24 load slider when the dyno needs an independent meter for generator output:

- voltage sense into ADS1115 `AIN2`
- ACS712 current sensor output into ADS1115 `AIN1`
- SSD1306 OLED on I2C address `0x3C`
- ADS1115 on I2C address `0x48`
- start/resume button on GPIO `4`, active low
- stop/pause/reset button on GPIO `5`, active low
- ESP32 I2C pins: SDA `8`, SCL `9`

## Arduino Libraries

Install these through Arduino IDE Library Manager:

- `Adafruit SSD1306`
- `Adafruit GFX Library`
- `Adafruit ADS1X15`

The old temporary sketch also included `ADS1X58.h`; this checked-in version uses the Adafruit ADS1115 API that the code actually calls.

## Calibration Constants

The important constants live near the top of `dyno_joulemeter.ino`:

```cpp
const float CURRENT_SENSOR_ZERO_V = 2.582f;
const float CURRENT_SENSOR_V_PER_A = 0.066f;
const float VOLTAGE_SCALE = 1.0f;
```

`CURRENT_SENSOR_ZERO_V` is the no-current ACS712 output voltage. Re-measure this with no load connected.

`CURRENT_SENSOR_V_PER_A` is `0.066 V/A`, matching a common ACS712 30 A module. Change it if the installed sensor is a 5 A or 20 A version.

`VOLTAGE_SCALE` must match the voltage divider. It is currently `1.0`, meaning the displayed voltage is the ADS1115 input voltage. Do not connect dyno voltage directly unless the divider keeps the ADS1115 input within range. Set this to the divider ratio before measuring higher voltages.

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
