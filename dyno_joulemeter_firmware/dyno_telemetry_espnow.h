#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>

#include "dyno_telemetry_packet.h"

static const uint8_t DYNO_TELEMETRY_BROADCAST_MAC[6] = {
  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
};
static const uint8_t DYNO_TELEMETRY_ESPNOW_CHANNEL = 1;
static const uint32_t DYNO_TELEMETRY_SEND_INTERVAL_MS = 500;

class DynoTelemetryEspNowSender
{
public:
  bool begin()
  {
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    esp_wifi_set_channel(DYNO_TELEMETRY_ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    Serial.print("Dyno ESP-NOW sender MAC: ");
    Serial.println(WiFi.macAddress());

    if (esp_now_init() != ESP_OK) {
      Serial.println("Dyno ESP-NOW init failed; local joulemeter will continue");
      return false;
    }

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, DYNO_TELEMETRY_BROADCAST_MAC, sizeof(peer.peer_addr));
    peer.channel = DYNO_TELEMETRY_ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_err_t result = esp_now_add_peer(&peer);
    if (result != ESP_OK && result != ESP_ERR_ESPNOW_EXIST) {
      Serial.printf("Dyno ESP-NOW peer setup failed: %d\n", result);
      return false;
    }

    _bootId = esp_random();
    _ready = true;
    Serial.printf("Dyno ESP-NOW ready (broadcast, channel %u, every %lu ms)\n",
                  DYNO_TELEMETRY_ESPNOW_CHANNEL,
                  static_cast<unsigned long>(DYNO_TELEMETRY_SEND_INTERVAL_MS));
    return true;
  }

  bool send(uint32_t timestampMs,
            int32_t voltageMv,
            int32_t currentMa,
            int32_t powerMw,
            uint64_t energyMj,
            DynoRunState state)
  {
    if (!_ready) return false;
    if (_hasSent && timestampMs - _lastSendMs < DYNO_TELEMETRY_SEND_INTERVAL_MS) {
      return true;
    }

    DynoTelemetryPacket packet = {};
    packet.magic = DYNO_TELEMETRY_MAGIC;
    packet.version = DYNO_TELEMETRY_VERSION;
    packet.state = state;
    packet.packet_size = sizeof(packet);
    packet.boot_id = _bootId;
    packet.sequence = _sequence++;
    packet.timestamp_ms = timestampMs;
    packet.voltage_mV = voltageMv;
    packet.current_mA = currentMa;
    packet.power_mW = powerMw;
    packet.energy_mJ = energyMj;

    esp_err_t result = esp_now_send(
      DYNO_TELEMETRY_BROADCAST_MAC,
      reinterpret_cast<const uint8_t *>(&packet),
      sizeof(packet)
    );
    if (result != ESP_OK) {
      Serial.printf("Dyno ESP-NOW queue failed: %d\n", result);
      return false;
    }

    _lastSendMs = timestampMs;
    _hasSent = true;
    Serial.printf("Dyno ESP-NOW queued seq=%lu P=%.3f W\n",
                  static_cast<unsigned long>(packet.sequence),
                  packet.power_mW / 1000.0f);
    return true;
  }

private:
  bool _ready = false;
  bool _hasSent = false;
  uint32_t _bootId = 0;
  uint32_t _sequence = 0;
  uint32_t _lastSendMs = 0;
};
