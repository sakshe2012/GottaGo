
#include <WiFi.h>
#include <HTTPClient.h>
#include "config.h"

// ==========================================
// GOTTAGO THREE-SENSOR FIRMWARE
// PIR + IR1 + IR2
// ==========================================

// ESP32 GPIO pins
#define IR1_PIN 26
#define IR2_PIN 25
#define PIR_PIN 27

// Sensor settings
#define IR_DEBOUNCE_MS 40
#define PIR_DEBOUNCE_MS 80

// Timing settings
#define CROSSING_TIMEOUT_MS 2500
#define PIR_VALIDATION_MS 5000

// Backend settings
// Read from your existing config.h

// ==========================================
// VARIABLES
// ==========================================

int peopleCount = 0;

bool ir1State = false;
bool ir2State = false;
bool pirMotion = false;

bool lastIR1Raw = HIGH;
bool lastIR2Raw = HIGH;
bool lastPIRRaw = LOW;

bool stableIR1 = HIGH;
bool stableIR2 = HIGH;
bool stablePIR = LOW;

unsigned long ir1ChangeTime = 0;
unsigned long ir2ChangeTime = 0;
unsigned long pirChangeTime = 0;

unsigned long lastPIRMotionTime = 0;
unsigned long lastHeartbeat = 0;

bool pendingPIRConfirmation = false;
bool pendingTelemetry = false;

unsigned long crossingStartTime = 0;
unsigned long pendingCrossingTime = 0;

// Crossing directions
enum CrossingState {
  WAITING,
  IR1_FIRST,
  IR2_FIRST
};

enum CrossingDirection {
  NO_DIRECTION,
  ENTRY,
  EXIT
};

CrossingState crossingState = WAITING;
CrossingDirection pendingDirection = NO_DIRECTION;

// ==========================================
// WIFI CONNECTION
// ==========================================

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("[WiFi] Connecting...");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED &&
         millis() - start < WIFI_RETRY_MS) {
    delay(250);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] Connected!");
    Serial.print("[WiFi] ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WiFi] Connection failed. Will retry.");
  }
}

// ==========================================
// BACKEND COMMUNICATION
// ==========================================

void sendSensorDataToBackend() {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] WiFi unavailable. Data not sent.");
    return;
  }

  HTTPClient http;

  String url = String("http://") +
               BACKEND_HOST + ":" +
               String(BACKEND_PORT) +
               BACKEND_PATH;

  http.begin(url);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");

  String occupancyStatus =
      (peopleCount > 0) ? "OCCUPIED" : "VACANT";

  String json = "{";
  json += "\"ir1_state\":" + String(ir1State ? "true" : "false") + ",";
  json += "\"ir2_state\":" + String(ir2State ? "true" : "false") + ",";
  json += "\"pir_state\":" + String(pirMotion ? "true" : "false") + ",";
  json += "\"people_count\":" + String(peopleCount) + ",";
  json += "\"occupancy_status\":\"" + occupancyStatus + "\"";
  json += "}";

  Serial.println("[HTTP] Sending telemetry:");
  Serial.println(json);

  int responseCode = http.POST(json);

  if (responseCode > 0) {
    Serial.print("[HTTP] Response ");
    Serial.print(responseCode);
    Serial.print(": ");
    Serial.println(http.getString());
  } else {
    Serial.print("[HTTP] Error: ");
    Serial.println(http.errorToString(responseCode));
  }

  http.end();
}

// ==========================================
// OCCUPANCY UPDATE
// ==========================================

void updateOccupancy(CrossingDirection direction) {

  if (direction == ENTRY) {

    peopleCount++;

    Serial.println();
    Serial.println("========== ENTRY CONFIRMED ==========");
    Serial.print("People Inside: ");
    Serial.println(peopleCount);

  } else if (direction == EXIT) {

    if (peopleCount > 0) {
      peopleCount--;

      Serial.println();
      Serial.println("========== EXIT CONFIRMED ==========");
      Serial.print("People Inside: ");
      Serial.println(peopleCount);

    } else {
      Serial.println("[COUNT] Exit ignored. Count is already zero.");
    }
  }

  Serial.print("[STATUS] ");
  Serial.println(peopleCount > 0 ? "OCCUPIED" : "VACANT");

  pendingTelemetry = true;
}

// ==========================================
// PIR SENSOR
// ==========================================

void readPIR() {

  bool raw = digitalRead(PIR_PIN);

  if (raw != lastPIRRaw) {
    lastPIRRaw = raw;
    pirChangeTime = millis();
  }

  if (millis() - pirChangeTime >= PIR_DEBOUNCE_MS) {

    if (raw != stablePIR) {

      stablePIR = raw;
      pirMotion = (stablePIR == HIGH);

      if (pirMotion) {

        lastPIRMotionTime = millis();

        Serial.println("[PIR] MOTION DETECTED");

      } else {

        Serial.println("[PIR] CLEAR");

      }
    }
  }
}

// ==========================================
// IR SENSOR READING
// ==========================================

bool detectIR1Event() {

  bool raw = digitalRead(IR1_PIN);

  if (raw != lastIR1Raw) {
    lastIR1Raw = raw;
    ir1ChangeTime = millis();
  }

  if (millis() - ir1ChangeTime >= IR_DEBOUNCE_MS) {

    if (raw != stableIR1) {

      stableIR1 = raw;
      ir1State = (stableIR1 == LOW);

      if (ir1State) {
        Serial.println("[IR] IR1 triggered");
        return true;
      }
    }
  }

  return false;
}

bool detectIR2Event() {

  bool raw = digitalRead(IR2_PIN);

  if (raw != lastIR2Raw) {
    lastIR2Raw = raw;
    ir2ChangeTime = millis();
  }

  if (millis() - ir2ChangeTime >= IR_DEBOUNCE_MS) {

    if (raw != stableIR2) {

      stableIR2 = raw;
      ir2State = (stableIR2 == LOW);

      if (ir2State) {
        Serial.println("[IR] IR2 triggered");
        return true;
      }
    }
  }

  return false;
}

// ==========================================
// CROSSING DETECTION
// ==========================================

void processIRCrossing(bool ir1Event, bool ir2Event) {

  unsigned long now = millis();

  // Reset incomplete crossing after timeout
  if (crossingState != WAITING &&
      now - crossingStartTime > CROSSING_TIMEOUT_MS) {

    Serial.println("[IR] Crossing timeout. Sequence reset.");

    crossingState = WAITING;
  }

  if (ir1Event) {

    if (crossingState == WAITING) {

      crossingState = IR1_FIRST;
      crossingStartTime = now;

      Serial.println("[IR] IR1 first. Possible entry.");

    } else if (crossingState == IR2_FIRST &&
               now - crossingStartTime <= CROSSING_TIMEOUT_MS) {

      Serial.println("[IR] IR2 -> IR1 sequence detected.");

      pendingDirection = EXIT;
      pendingCrossingTime = now;
      pendingPIRConfirmation = true;

      crossingState = WAITING;
    }
  }

  if (ir2Event) {

    if (crossingState == WAITING) {

      crossingState = IR2_FIRST;
      crossingStartTime = now;

      Serial.println("[IR] IR2 first. Possible exit.");

    } else if (crossingState == IR1_FIRST &&
               now - crossingStartTime <= CROSSING_TIMEOUT_MS) {

      Serial.println("[IR] IR1 -> IR2 sequence detected.");

      pendingDirection = ENTRY;
      pendingCrossingTime = now;
      pendingPIRConfirmation = true;

      crossingState = WAITING;
    }
  }
}

// ==========================================
// PIR + IR VALIDATION
// ==========================================


void validateCrossing() {

  if (!pendingPIRConfirmation) return;

  unsigned long now = millis();

  // Accept PIR if it is currently detecting motion
  // OR if it detected motion recently.
  bool recentPIR =
      (lastPIRMotionTime != 0 &&
       now - lastPIRMotionTime <= PIR_VALIDATION_MS);

  bool pirConfirmed = pirMotion || recentPIR;

  if (pirConfirmed) {

    Serial.println("[VALIDATION] PIR + IR confirmed!");

    updateOccupancy(pendingDirection);

    pendingPIRConfirmation = false;
    pendingDirection = NO_DIRECTION;

    return;
  }

  if (now - pendingCrossingTime > PIR_VALIDATION_MS) {

    Serial.println("[VALIDATION] No PIR confirmation.");
    Serial.println("[VALIDATION] Crossing ignored.");

    pendingPIRConfirmation = false;
    pendingDirection = NO_DIRECTION;
  }
}


// ==========================================
// SETUP
// ==========================================

void setup() {

  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("======================================");
  Serial.println(" GOT TAGO THREE-SENSOR FIRMWARE");
  Serial.println(" PIR + IR1 + IR2");
  Serial.println("======================================");

  pinMode(IR1_PIN, INPUT_PULLUP);
  pinMode(IR2_PIN, INPUT_PULLUP);
  pinMode(PIR_PIN, INPUT);

  // Capture initial sensor states
  stableIR1 = digitalRead(IR1_PIN);
  stableIR2 = digitalRead(IR2_PIN);
  stablePIR = digitalRead(PIR_PIN);

  lastIR1Raw = stableIR1;
  lastIR2Raw = stableIR2;
  lastPIRRaw = stablePIR;

  ir1State = (stableIR1 == LOW);
  ir2State = (stableIR2 == LOW);
  pirMotion = (stablePIR == HIGH);

  Serial.println("[SYSTEM] Sensors initialized.");

  connectWiFi();

  Serial.println("[SYSTEM] GottaGo ready.");
}

// ==========================================
// MAIN LOOP
// ==========================================

void loop() {

  // Reconnect WiFi when necessary
  static unsigned long lastWiFiAttempt = 0;

  if (WiFi.status() != WL_CONNECTED &&
      millis() - lastWiFiAttempt >= WIFI_RETRY_MS) {

    lastWiFiAttempt = millis();
    connectWiFi();
  }

  // Read all three sensors
  readPIR();

  bool ir1Event = detectIR1Event();
  bool ir2Event = detectIR2Event();

  // Process directional IR crossing
  processIRCrossing(ir1Event, ir2Event);

  // Confirm crossing with PIR
  validateCrossing();

  // Send occupancy changes immediately
  if (pendingTelemetry) {

    sendSensorDataToBackend();

    pendingTelemetry = false;
  }

  // Send heartbeat periodically
  if (millis() - lastHeartbeat >= HEARTBEAT_INTERVAL) {

    lastHeartbeat = millis();

    sendSensorDataToBackend();
  }

  delay(2);
}
