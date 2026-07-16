#include <Adafruit_GFX.h>
#include <Adafruit_GrayOLED.h>
#include <Adafruit_SPITFT.h>
#include <Adafruit_SPITFT_Macros.h>
#include <gfxfont.h>

#include <Adafruit_SSD1306.h>
#include <splash.h>

/*
-----------------------------------------
 DYNAMOMETER FLAG SPEED SENSOR WIRING
-----------------------------------------
Sensor: LM393 IR Slotted Speed Sensor Module
Pins on sensor module:
    VCC  → Arduino 5V
    GND  → Arduino GND
    DO   → Arduino DIGITAL PIN 2   (sensorPin)
           (This pin outputs 0/1 depending on whether a flag blocks the IR beam)
-----------------------------------------
*/

#include <Arduino.h>

// -------------------------------------------------
// CONFIGURATION
// -------------------------------------------------

// Number of reflective/mechanical flags on the pulley wheel
#define FLAG_COUNT 8        //Change this depending on actual amounto f flags; I forget how many mech team had

// LM393 digital output pin (DO)
const int sensorPin = 2;     // MUST be a digital pin; this code assumes Arduino UNO D2

// OLED stuff
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_SLEEP_TIME 3000

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

unsigned long lastChangeTime = 0;
bool displaySleeping = false;

// SPEED Stuff
#define GEAR_RATIO 3.33333333 // 3:1
#define CONVERT_TO_KM_H 0.06 // 60/1000
#define CIRCUM_SMALL 0.2 // Circumference of small gear is ~20cm

// -------------------------------------------------
// FILTERING / HISTORY BUFFERS
// -------------------------------------------------
long rpmHistory[5]   = {0,0,0,0,0};
long speedHistory[5] = {0,0,0,0,0};

long rpmFiltered = 0;
long speedFiltered = 0;

void updateHistoryArrays(long rpmVal, long speedVal) {
    for (int i = 0; i < 4; i++) {
        rpmHistory[i]   = rpmHistory[i+1];
        speedHistory[i] = speedHistory[i+1];
    }
    rpmHistory[4]   = rpmVal;
    speedHistory[4] = speedVal;

    long rpmSum = 0;
    long speedSum = 0;
    for (int i = 0; i < 5; i++) {
        rpmSum   += rpmHistory[i];
        speedSum += speedHistory[i];
    }

    rpmFiltered   = rpmSum / 5;
    speedFiltered = speedSum / 5;
}

// -------------------------------------------------
// INTERRUPT SYSTEM
// -------------------------------------------------
volatile unsigned long lastPulseMicros = 0;
volatile unsigned long pulseIntervalMicros = 0;
volatile bool newPulse = false;

void pulseISR() {
    unsigned long now = micros();
    unsigned long dt = now - lastPulseMicros;

    // Reject impossible pulses / chatter
    if (dt < 500) return;   // tune this threshold

    pulseIntervalMicros = dt;
    lastPulseMicros = now;
    newPulse = true;
}

// -------------------------------------------------
// SENSOR EDGE DETECTION
// -------------------------------------------------

bool previousFlagState = false;   // previous state of DO pin
bool flagState         = false;   // current state of DO pin

// Detect a flag passing through the slotted sensor
// One pulse per flag: output only on LOW to HIGH transistion,
// then require it to go back LOW before rearming
/*
bool detectFlag() {
    static bool armed = true;  // ready to detect next flag entry

    int raw = digitalRead(sensorPin);      // DO pin
    bool flagPresent = (raw == HIGH);      // something obstructing sensor

    if (armed && flagPresent) {
        armed = false;                    // lock out until flag leaves
        Serial.println("FLAG DETECTED");  // debug output - worked as of Jan 28
        Serial.println(""); 
        Serial.println("PIN STATE:");
        Serial.println(raw);
        return true;                      // only one pulse per flag
    }

    if (!flagPresent) {
        armed = true;                     // rearm once flag is gone
    }

    return false;
}*/
// revised detection function: require N (can change and tune) lows before rearming (ignore bounces)
bool detectFlag() {
    static bool armed = true;
    static uint8_t lowCount = 0;
    static int N_num = 10; 

    int raw = digitalRead(sensorPin);
    bool flagPresent = (raw == HIGH);

    // Detection: only once per flag
    if (armed && flagPresent) {
        armed = false;
        lowCount = 0;          // reset any pending rearm low counts
        return true;
    }

    // Rearm logic: require N consecutive LOW samples
    if (!flagPresent) {
        if (lowCount < N_num) lowCount++;
        if (lowCount >= N_num) armed = true;
    } else {
        // Any HIGH breaks the "consecutive LOW" streak
        lowCount = 0;
    }

    return false;
}


// -------------------------------------------------
// OLED Functions
// -------------------------------------------------

void updateDisplay(long rpm_current, long rpmFiltered, long speed_current) {

    display.clearDisplay();
    display.setTextSize(2);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 0);
    display.print("RPM:");
    display.println(rpm_current);

    display.setCursor(0, 20);
    display.print("FRPM:"); // Filtered RPM
    display.println(rpmFiltered);

    display.setCursor(0, 40);
    display.print("SPD:");
    display.println(speed_current);

    display.display();
}



// -------------------------------------------------
// MAIN SETUP
// -------------------------------------------------
void setup() {
    
    pinMode(sensorPin, INPUT); // LM393 module already has pull-up
    attachInterrupt(digitalPinToInterrupt(sensorPin), pulseISR, RISING); // Using interrupts

    Serial.begin(115200);

    // OLED Display
    if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        for(;;); // OLED not found
    }

    display.clearDisplay();
    // display.println("Hello");
    // display.display();
}



// -------------------------------------------------
// MAIN LOOP
// (period measurement using micros() for high resolution)
// -------------------------------------------------

void loop() {
  // Quick debugging: just printing pin state to check flag levels. 
  /*
    Serial.print("TEST ____ TEST"); 
    int state = digitalRead(sensorPin);
    Serial.println(state);
    delay(100);
    */
  
    
    // wait for first flag transition start (ignore interval of first one)
    unsigned long pulseStartTime_us = micros();
    while (!detectFlag()) {}

    // time of next flag event
    unsigned long pulseEndTime_us = micros();

    // time between two consecutive flags
    unsigned long pulseInterval_us = pulseEndTime_us - pulseStartTime_us;


    // -----------------------------------------------
    // RPM COMPUTATION (using microsecond precision)
    //
    // time per pulse = pulseInterval_us
    // time per revolution = pulseInterval_us * FLAG_COUNT
    //
    // RPM = 60 sec/min * (1 rev / (FLAG_COUNT * Δt_sec))
    //     = 60e6 / (FLAG_COUNT * Δt_us)
    // -----------------------------------------------

    // long rpm_current = 0;
    // if (pulseInterval_us > 0) {
    //     rpm_current = (60000000UL / FLAG_COUNT) / pulseInterval_us;
    // }

    long rpm_current = 0;

    noInterrupts();
    unsigned long interval = pulseIntervalMicros;
    bool pulseSeen = newPulse;
    newPulse = false;
    interrupts();

    if (pulseSeen && interval > 0) {
        rpm_current = (60000000UL / FLAG_COUNT) / interval;
    }


    // speed calculation (your formula) CAM's CODE
    //long speed_current = 3 * 3.14 * 0.6 * rpm_current / 25;

    // Calculate speed GRACE's CODE
    long speed_current = CIRCUM_SMALL * rpm_current * CONVERT_TO_KM_H * GEAR_RATIO;

    // apply smoothing
    updateHistoryArrays(rpm_current, speed_current);


    // serial debugging
    // Serial.print("RPM: ");
    // Serial.print(rpm_current);
    // Serial.print(" | Filtered RPM: ");
    // Serial.println(rpmFiltered);

    updateDisplay(rpm_current, rpmFiltered, speed_current);
    
    //delay(200);
}

