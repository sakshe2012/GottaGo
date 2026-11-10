#pragma once

// GottaGo ESP32 - Public Example Configuration
// Copy this file as config.h and replace placeholders.

// Wi-Fi credentials
#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// Backend configuration
#define BACKEND_HOST "YOUR_BACKEND_HOST"
#define BACKEND_PORT 0
#define BACKEND_PATH "/api/sensor-data"

// Timing parameters (example values only)
#define HTTP_TIMEOUT_MS 10000UL
#define WIFI_RETRY_MS 5000UL
#define HEARTBEAT_INTERVAL 10000UL
