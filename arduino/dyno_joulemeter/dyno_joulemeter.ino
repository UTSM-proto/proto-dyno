#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_ADS1X15.h>

// Prototype dyno joulemeter:
// - ADS1115 AIN2: voltage sense input
// - ADS1115 AIN1: ACS712 current sensor output
// - OLED: live V/I/P/time and paused run summary

Adafruit_ADS1115 ads;

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

const int startButtonPin = 4;
const int stopButtonPin = 5;

const int I2C_SDA_PIN = 8;
const int I2C_SCL_PIN = 9;
const int ADS1115_ADDR = 0x48;
const int OLED_ADDR = 0x3C;

const int VOLTAGE_ADC_CHANNEL = 2;
const int CURRENT_ADC_CHANNEL = 1;

const float CURRENT_SENSOR_ZERO_V = 2.582f;
const float CURRENT_SENSOR_V_PER_A = 0.066f;
const float VOLTAGE_SCALE = 1.0f;

enum TimerState {
  IDLE,
  RUNNING,
  PAUSED
};

TimerState timerState = IDLE;

unsigned long startTime = 0;
unsigned long elapsedTime = 0;
unsigned long lastSampleTime = 0;
unsigned long lastAverageTime = 0;

double voltageTotal = 0.0;
double currentTotal = 0.0;
double energyJ = 0.0;
int averageCount = 0;

struct JoulemeterReading {
  float voltage;
  float current;
  float power;
  float currentSensorVoltage;
};

void setup() {
  Serial.begin(115200);
  Serial.println("millis,elapsed_ms,voltage_v,current_a,power_w,energy_j,state");

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("SSD1306 allocation failed");
    for (;;) {
    }
  }

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 10);
  display.println("Dyno Joulemeter");
  display.println("Press Start");
  display.display();

  pinMode(startButtonPin, INPUT_PULLUP);
  pinMode(stopButtonPin, INPUT_PULLUP);

  if (!ads.begin(ADS1115_ADDR)) {
    Serial.println("ADS1115 not found");
    while (1) {
    }
  }

  ads.setGain(GAIN_TWOTHIRDS);
}

void loop() {
  JoulemeterReading reading = readJoulemeter();

  switch (timerState) {
    case IDLE:
      showIdle(reading);
      logReading(reading, "idle");

      if (buttonPressed(startButtonPin)) {
        startRun();
      }
      break;

    case RUNNING:
      elapsedTime = millis() - startTime;
      integrateEnergy(reading);
      updateAverages(reading);
      displayRun(elapsedTime, reading, true);
      logReading(reading, "running");

      if (buttonPressed(stopButtonPin)) {
        elapsedTime = millis() - startTime;
        timerState = PAUSED;
      }
      break;

    case PAUSED:
      showPaused(elapsedTime, reading);
      logReading(reading, "paused");

      if (buttonPressed(startButtonPin)) {
        startTime = millis() - elapsedTime;
        lastSampleTime = millis();
        timerState = RUNNING;
      } else if (buttonPressed(stopButtonPin)) {
        timerState = IDLE;
      }
      break;
  }

  delay(100);
}

JoulemeterReading readJoulemeter() {
  int16_t rawBattery = ads.readADC_SingleEnded(VOLTAGE_ADC_CHANNEL);
  float voltage = ads.computeVolts(rawBattery) * VOLTAGE_SCALE;

  int16_t rawCurrentSensor = ads.readADC_SingleEnded(CURRENT_ADC_CHANNEL);
  float currentSensorVoltage = ads.computeVolts(rawCurrentSensor);
  float current = (currentSensorVoltage - CURRENT_SENSOR_ZERO_V) / CURRENT_SENSOR_V_PER_A;

  JoulemeterReading reading;
  reading.voltage = voltage;
  reading.current = current;
  reading.power = voltage * current;
  reading.currentSensorVoltage = currentSensorVoltage;
  return reading;
}

void startRun() {
  startTime = millis();
  elapsedTime = 0;
  lastSampleTime = millis();
  lastAverageTime = 0;
  voltageTotal = 0.0;
  currentTotal = 0.0;
  energyJ = 0.0;
  averageCount = 0;
  timerState = RUNNING;
}

void integrateEnergy(JoulemeterReading reading) {
  unsigned long now = millis();
  if (lastSampleTime == 0) {
    lastSampleTime = now;
    return;
  }

  float dtSeconds = (now - lastSampleTime) / 1000.0f;
  energyJ += reading.power * dtSeconds;
  lastSampleTime = now;
}

void updateAverages(JoulemeterReading reading) {
  if (elapsedTime - lastAverageTime >= 1000) {
    lastAverageTime = elapsedTime;
    voltageTotal += reading.voltage;
    currentTotal += reading.current;
    averageCount++;
  }
}

bool buttonPressed(int pin) {
  if (digitalRead(pin) != LOW) {
    return false;
  }

  delay(50);
  while (digitalRead(pin) == LOW) {
    delay(10);
  }
  return true;
}

void showIdle(JoulemeterReading reading) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Dyno Joulemeter");
  display.print("V: ");
  display.println(reading.voltage, 3);
  display.print("I: ");
  display.println(reading.current, 3);
  display.print("P: ");
  display.println(reading.power, 2);
  display.print("Sense V: ");
  display.println(reading.currentSensorVoltage, 4);
  display.println("Press Start");
  display.display();
}

void displayRun(unsigned long timeInMillis, JoulemeterReading reading, bool clear) {
  unsigned int minutes = timeInMillis / 60000;
  unsigned int seconds = (timeInMillis % 60000) / 1000;
  unsigned int milliseconds = timeInMillis % 1000;

  char timeStr[12];
  sprintf(timeStr, "%02u:%02u:%03u", minutes, seconds, milliseconds);

  if (clear) {
    display.clearDisplay();
  }

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("V: ");
  display.println(reading.voltage, 3);
  display.print("I: ");
  display.println(reading.current, 3);
  display.print("P: ");
  display.println(reading.power, 2);
  display.print("J: ");
  display.println(energyJ, 1);
  display.println(timeStr);

  if (clear) {
    display.display();
  }
}

void showPaused(unsigned long timeInMillis, JoulemeterReading reading) {
  display.clearDisplay();
  displayRun(timeInMillis, reading, false);

  display.print("Avg V: ");
  if (averageCount > 0) {
    display.println((float)voltageTotal / averageCount, 3);
  } else {
    display.println("N/A");
  }

  display.print("Avg I: ");
  if (averageCount > 0) {
    display.println((float)currentTotal / averageCount, 3);
  } else {
    display.println("N/A");
  }

  display.print("Avg P: ");
  if (averageCount > 0) {
    display.println((float)((currentTotal * voltageTotal) / (averageCount * averageCount)), 2);
  } else {
    display.println("N/A");
  }

  display.display();
}

void logReading(JoulemeterReading reading, const char *state) {
  Serial.print(millis());
  Serial.print(",");
  Serial.print(elapsedTime);
  Serial.print(",");
  Serial.print(reading.voltage, 4);
  Serial.print(",");
  Serial.print(reading.current, 4);
  Serial.print(",");
  Serial.print(reading.power, 4);
  Serial.print(",");
  Serial.print(energyJ, 4);
  Serial.print(",");
  Serial.println(state);
}
