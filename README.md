# proto-dyno

Simple Python dyno load controller for ATORCH DL24/DL24P-style USB serial electronic loads.

The app treats the load bank as a variable road load / hill resistance for a motor-generator dyno. It presents a watts slider, reads live telemetry, and uses conservative software safety clamps.

## Safety Defaults

This software intentionally defaults far below advertised DL24 ratings:

- max power: 50 W
- max current: 3 A
- max voltage: 36 V
- minimum voltage: 2.5 V
- max temperature: 70 C
- update rate: 2 Hz
- telemetry timeout: 2 seconds

Cheap DL24-style loads are often advertised around 150 W / 180 W, but those ratings are not safe continuous dyno limits. Start low, keep airflow on the load, and validate with external meters.

The app immediately attempts to stop the load if:

- voltage rises above the configured maximum
- voltage falls below the configured minimum while load is enabled
- temperature exceeds the configured maximum
- serial telemetry is lost for more than 2 seconds

## Protocol Status

The known public DL24/PX100-style serial protocol supports:

- output on/off
- current setpoint
- voltage cutoff setpoint
- voltage telemetry
- current telemetry
- temperature telemetry

Native constant-power mode control is not exposed by the simple working Python examples inspected for this repo. `proto-dyno` therefore defaults to constant-power emulation:

```text
I_target = P_target / V_measured
```

The computed current is clamped to the configured current and power limits before being sent to the load.

## Install

Python 3.10+ is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Tkinter ships with normal python.org Windows installers. If your Python build lacks Tkinter, install a standard CPython build.

## Run

```powershell
python -m proto_dyno.app
```

For a specific port:

```powershell
python -m proto_dyno.app --port COM7
```

To list likely devices:

```powershell
python -m proto_dyno.cli list
```

## Notes

- Plug in the DL24 before launching the app.
- The app looks for likely USB serial adapters such as CH340, USB-SERIAL, CP210x, and FTDI devices.
- The load starts disabled. Move the slider, then press `Enable Load`.
- Press `Stop Load` before changing wiring.
- Keep hardware current limits, fuses, and external meters in the setup. Software clamps are a backup, not the primary protection.

## Dyno Joulemeter Firmware

This repo also includes Arduino firmware for the prototype dyno joulemeter:

```text
dyno_joulemeter_firmware/dyno_joulemeter.ino
```

That sketch reads voltage and ACS712 current through an ADS1115, displays live V/I/P/J on an SSD1306 OLED, and logs CSV-style serial rows for dyno runs. See `dyno_joulemeter_firmware/README.md` for wiring, calibration constants, and library requirements.
