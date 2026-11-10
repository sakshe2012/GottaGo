import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gottago/main.dart';
import 'package:gottago/services/api_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  group('ApiService Unit Tests', () {
    test('getHealth parses healthy response', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'status': 'healthy',
            'backend': 'GottaGo Backend',
            'timestamp': '2026-11-01T15:00:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = ApiService(baseUrl: 'http://test', client: mockClient);
      final health = await service.getHealth();
      expect(health.status, 'healthy');
      expect(health.backend, 'GottaGo Backend');
    });

    test('getStatus parses live status and ESP32 connection', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'occupancy_status': 'OCCUPIED',
            'people_count': 3,
            'esp32_connected': true,
            'last_updated': '2026-11-01T15:10:00Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = ApiService(baseUrl: 'http://test', client: mockClient);
      final status = await service.getStatus();
      expect(status.occupancyStatus, 'OCCUPIED');
      expect(status.peopleCount, 3);
      expect(status.esp32Connected, true);
      expect(status.lastUpdated, isNotNull);
    });

    test('getPrediction parses real ML inference and probabilities', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'predicted_rush': 'HIGH',
            'predicted_rush_level': 'HIGH',
            'prediction_status': 'SUCCESS',
            'prediction_timestamp': '2026-11-01T15:10:00Z',
            'current_occupancy': 3,
            'occupancy_percent': 60.0,
            'capacity': 5,
            'probabilities': {
              'LOW': 0.10,
              'MEDIUM': 0.25,
              'HIGH': 0.65,
            },
            'model_status': 'LOADED',
            'note': 'Prediction generated from real trained Random Forest model.',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = ApiService(baseUrl: 'http://test', client: mockClient);
      final pred = await service.getPrediction();
      expect(pred.isAvailable, true);
      expect(pred.predictedRush, 'HIGH');
      expect(pred.probabilities?['HIGH'], 0.65);
      expect(pred.probabilities?['LOW'], 0.10);
    });

    test('getPrediction handles UNAVAILABLE state without fabricated values', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'predicted_rush': 'UNAVAILABLE',
            'prediction_status': 'UNAVAILABLE',
            'prediction_timestamp': '2026-11-01T15:10:00Z',
            'probabilities': null,
            'model_status': 'LOADED',
            'note': 'Sensor data is stale.',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final service = ApiService(baseUrl: 'http://test', client: mockClient);
      final pred = await service.getPrediction();
      expect(pred.isAvailable, false);
      expect(pred.predictedRush, 'UNAVAILABLE');
      expect(pred.probabilities, isNull);
    });
  });

  group('HomeScreen Live Mode Integration Tests', () {
    testWidgets('Live mode displays live occupancy, high rush, and probabilities',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      final mockClient = MockClient((request) async {
        if (request.url.path.contains('/status')) {
          return http.Response(
            jsonEncode({
              'occupancy_status': 'OCCUPIED',
              'people_count': 4,
              'esp32_connected': true,
              'last_updated': '2026-11-01T15:30:00Z',
            }),
            200,
          );
        } else if (request.url.path.contains('/prediction')) {
          return http.Response(
            jsonEncode({
              'predicted_rush': 'HIGH',
              'prediction_status': 'SUCCESS',
              'prediction_timestamp': '2026-11-01T15:30:00Z',
              'current_occupancy': 4,
              'occupancy_percent': 80.0,
              'capacity': 5,
              'probabilities': {
                'LOW': 0.05,
                'MEDIUM': 0.15,
                'HIGH': 0.80,
              },
              'model_status': 'LOADED',
            }),
            200,
          );
        }
        return http.Response('{}', 404);
      });

      final mockService = ApiService(baseUrl: 'http://test', client: mockClient);

      await tester.pumpWidget(
        GottaGoApp(
          startInDemoMode: false,
          apiService: mockService,
        ),
      );

      // Allow async HTTP calls to complete and rebuild
      await tester.pumpAndSettle();

      // Verify LIVE MODE badge in AppBar
      expect(find.text('LIVE MODE'), findsOneWidget);

      // Verify live occupancy from backend
      expect(find.text('OCCUPIED'), findsOneWidget);
      expect(find.text('4'), findsOneWidget);

      // Verify ML predicted rush
      expect(find.text('HIGH'), findsOneWidget);

      // Verify calibrated probabilities are rendered: L: 5%, M: 15%, H: 80%
      expect(find.text('L:'), findsOneWidget);
      expect(find.text('5%'), findsOneWidget);
      expect(find.text('M:'), findsOneWidget);
      expect(find.text('15%'), findsOneWidget);
      expect(find.text('H:'), findsOneWidget);
      expect(find.text('80%'), findsOneWidget);

      // Verify ESP32 is CONNECTED and Backend is ONLINE
      expect(find.text('CONNECTED'), findsOneWidget);
      expect(find.text('ONLINE'), findsOneWidget);
    });

    testWidgets('Live mode displays UNAVAILABLE prediction when sensor is stale',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      final mockClient = MockClient((request) async {
        if (request.url.path.contains('/status')) {
          return http.Response(
            jsonEncode({
              'occupancy_status': 'VACANT',
              'people_count': 0,
              'esp32_connected': false,
              'last_updated': '2026-11-01T15:00:00Z',
            }),
            200,
          );
        } else if (request.url.path.contains('/prediction')) {
          return http.Response(
            jsonEncode({
              'predicted_rush': 'UNAVAILABLE',
              'prediction_status': 'UNAVAILABLE',
              'prediction_timestamp': '2026-11-01T15:00:00Z',
              'probabilities': null,
              'model_status': 'LOADED',
              'note': 'Sensor data is stale.',
            }),
            200,
          );
        }
        return http.Response('{}', 404);
      });

      final mockService = ApiService(baseUrl: 'http://test', client: mockClient);

      await tester.pumpWidget(
        GottaGoApp(
          startInDemoMode: false,
          apiService: mockService,
        ),
      );

      await tester.pumpAndSettle();

      // Rush should display UNAVAILABLE
      expect(find.text('UNAVAILABLE'), findsOneWidget);
      expect(find.text('Sensor data is stale.'), findsOneWidget);

      // Status should reflect ESP32 DISCONNECTED
      expect(find.text('DISCONNECTED'), findsOneWidget);
      expect(find.text('ONLINE'), findsOneWidget);
    });

    testWidgets('Live mode handles backend offline gracefully without crashing',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      final mockClient = MockClient((request) async {
        throw http.ClientException('Connection refused');
      });

      final mockService = ApiService(baseUrl: 'http://offline-test', client: mockClient);

      await tester.pumpWidget(
        GottaGoApp(
          startInDemoMode: false,
          apiService: mockService,
        ),
      );

      await tester.pumpAndSettle();

      // App should not crash; backend should be OFFLINE
      expect(find.text('OFFLINE'), findsOneWidget);
      expect(find.text('DISCONNECTED'), findsOneWidget);
      expect(find.text('Backend offline. Reconnecting automatically...'), findsOneWidget);
    });
  });
}
