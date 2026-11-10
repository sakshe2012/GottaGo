import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:latlong2/latlong.dart';
import 'package:gottago/models/nearby_washroom.dart';
import 'package:gottago/screens/nearby_screen.dart';
import 'package:gottago/screens/washroom_detail_screen.dart';
import 'package:gottago/services/api_service.dart';
import 'package:gottago/services/location_service.dart';

void main() {
  group('Milestone 3A DTO & Parsing Tests', () {
    test('NearbyDiscoveryResult parses valid JSON response correctly', () {
      final jsonSample = {
        'user_location': {'latitude': 18.5204, 'longitude': 73.8567},
        'search_radius_km': 5.0,
        'total_found': 1,
        'washrooms': [
          {
            'washroom_id': 101,
            'slug': 'central-washroom',
            'name': 'Central Washroom',
            'building': 'Main Hall',
            'floor': '1st Floor',
            'room_number': '102',
            'latitude': 18.5240,
            'longitude': 73.8570,
            'distance_km': 0.41,
            'gender_type': 'UNISEX',
            'is_accessible': true,
            'capacity': 5,
            'has_hardware': true,
            'is_active': true,
            'occupancy_status': 'VACANT',
            'people_count': 0,
            'esp32_connected': true,
            'last_updated': '2026-11-07T10:00:00Z',
            'predicted_rush': 'LOW',
            'predicted_rush_level': 'LOW',
            'prediction_status': 'SUCCESS',
            'rush_probabilities': {'LOW': 0.9, 'MEDIUM': 0.08, 'HIGH': 0.02},
            'cleanliness': {'rating': 4.5, 'review_count': 10, 'status_label': '4.5/5.0'},
            'recommendation_score': 0.41,
            'recommendation_rank': 1,
          }
        ]
      };

      final result = NearbyDiscoveryResult.fromJson(jsonSample);
      expect(result.userLatitude, 18.5204);
      expect(result.userLongitude, 73.8567);
      expect(result.searchRadiusKm, 5.0);
      expect(result.totalFound, 1);
      expect(result.washrooms.length, 1);

      final w = result.washrooms.first;
      expect(w.washroomId, 101);
      expect(w.name, 'Central Washroom');
      expect(w.isVacant, true);
      expect(w.isOccupied, false);
      expect(w.distanceKm, 0.41);
      expect(w.isAccessible, true);
      expect(w.cleanliness.rating, 4.5);
      expect(w.rushProbabilities?.low, 0.9);
    });

    test('WashroomDetail parses hardware-less facility without crashing', () {
      final jsonSample = {
        'washroom_id': 102,
        'slug': 'manual-washroom',
        'name': 'Manual Washroom',
        'latitude': 18.5300,
        'longitude': 73.8600,
        'distance_km': 1.25,
        'gender_type': 'FEMALE',
        'is_accessible': null,
        'capacity': 4,
        'operating_status': 'OPEN',
        'has_hardware': false,
        'is_active': true,
        'occupancy_status': 'VACANT',
        'people_count': 0,
        'esp32_connected': false,
        'predicted_rush': 'UNAVAILABLE',
        'predicted_rush_level': 'UNAVAILABLE',
        'prediction_status': 'UNAVAILABLE',
        'cleanliness': {'rating': null, 'review_count': 0, 'status_label': 'Not yet rated'},
      };

      final detail = WashroomDetail.fromJson(jsonSample);
      expect(detail.washroomId, 102);
      expect(detail.hasHardware, false);
      expect(detail.esp32Connected, false);
      expect(detail.predictedRush, 'UNAVAILABLE');
      expect(detail.cleanliness.rating, isNull);
      expect(detail.cleanliness.statusLabel, 'Not yet rated');
      expect(detail.distanceKm, 1.25);
    });
  });

  group('LocationResult Model Tests', () {
    test('serviceDisabled returns proper state and error message', () {
      final res = LocationResult.serviceDisabled();
      expect(res.isSuccess, false);
      expect(res.isServiceEnabled, false);
      expect(res.errorMessage, contains('Location services are disabled'));
    });

    test('permissionDenied distinguishes permanent vs standard denial', () {
      final resStandard = LocationResult.permissionDenied(permanently: false);
      expect(resStandard.isSuccess, false);
      expect(resStandard.isPermissionDenied, true);

      final resPermanent = LocationResult.permissionDenied(permanently: true);
      expect(resPermanent.isSuccess, false);
      expect(resPermanent.isPermissionDenied, true);
      expect(resPermanent.errorMessage, contains('permanently denied'));
    });
  });

  group('ApiService Nearby & Detail HTTP Tests', () {
    test('getNearbyWashrooms encodes query parameters and parses result', () async {
      final mockClient = MockClient((request) async {
        expect(request.url.path, '/api/washrooms/nearby');
        expect(request.url.queryParameters['latitude'], '18.5204');
        expect(request.url.queryParameters['longitude'], '73.8567');
        expect(request.url.queryParameters['radius_km'], '5.0');
        expect(request.url.queryParameters['gender'], 'FEMALE');

        return http.Response(
          jsonEncode({
            'user_location': {'latitude': 18.5204, 'longitude': 73.8567},
            'search_radius_km': 5.0,
            'total_found': 0,
            'washrooms': []
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final api = ApiService(baseUrl: 'http://testserver', client: mockClient);
      final res = await api.getNearbyWashrooms(
        latitude: 18.5204,
        longitude: 73.8567,
        radiusKm: 5.0,
        gender: 'FEMALE',
      );

      expect(res.totalFound, 0);
      expect(res.washrooms, isEmpty);
    });

    test('getWashroomDetails encodes user_lat/lng query params', () async {
      final mockClient = MockClient((request) async {
        expect(request.url.path, '/api/washrooms/1');
        expect(request.url.queryParameters['user_lat'], '18.5204');
        expect(request.url.queryParameters['user_lng'], '73.8567');

        return http.Response(
          jsonEncode({
            'washroom_id': 1,
            'slug': 'primary-washroom',
            'name': 'Primary Washroom',
            'latitude': 18.5220,
            'longitude': 73.8580,
            'distance_km': 0.22,
            'gender_type': 'UNISEX',
            'has_hardware': true,
            'is_active': true,
            'occupancy_status': 'VACANT',
            'people_count': 0,
            'esp32_connected': true,
            'predicted_rush': 'LOW',
            'predicted_rush_level': 'LOW',
            'prediction_status': 'SUCCESS',
            'cleanliness': {'rating': null, 'review_count': 0, 'status_label': 'Not yet rated'},
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final api = ApiService(baseUrl: 'http://testserver', client: mockClient);
      final detail = await api.getWashroomDetails(1, userLat: 18.5204, userLng: 73.8567);

      expect(detail.washroomId, 1);
      expect(detail.distanceKm, 0.22);
      expect(detail.name, 'Primary Washroom');
    });
  });

  group('NearbyScreen & WashroomDetailScreen Widget Tests', () {
    testWidgets('NearbyScreen renders filter chips and map', (tester) async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'user_location': {'latitude': 18.5204, 'longitude': 73.8567},
            'search_radius_km': 5.0,
            'total_found': 0,
            'washrooms': []
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final api = ApiService(baseUrl: 'http://testserver', client: mockClient);

      await tester.pumpWidget(
        MaterialApp(
          home: NearbyScreen(
            apiService: api,
            initialLocation: const LatLng(18.5204, 73.8567),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Nearby Washrooms'), findsOneWidget);
      expect(find.text('5.0 km'), findsOneWidget);
      expect(find.text('All'), findsOneWidget);
      expect(find.text('Female'), findsOneWidget);
      expect(find.text('Male'), findsOneWidget);
      expect(find.text('Wheelchair'), findsOneWidget);
    });

    testWidgets('NearbyScreen renders location required state and banner when userLocation is null (no fabricated coordinates)', (tester) async {
      bool apiWasCalled = false;
      final mockClient = MockClient((request) async {
        apiWasCalled = true;
        return http.Response('{"washrooms": []}', 200, headers: {'content-type': 'application/json'});
      });

      final api = ApiService(baseUrl: 'http://testserver', client: mockClient);

      // Instantiate NearbyScreen without any initial location
      await tester.pumpWidget(
        MaterialApp(
          home: NearbyScreen(
            apiService: api,
            initialLocation: null,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify that no fabricated API call was executed
      expect(apiWasCalled, false);

      // Verify permission banner is visible
      expect(find.text('Location services are unavailable in automated test environment.'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      // Verify center state informs user that location access is required
      expect(find.text('Location Access Required'), findsOneWidget);
      expect(find.text('Detect Current Location'), findsOneWidget);
    });

    testWidgets('WashroomDetailScreen renders occupancy and AI rush status', (tester) async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'washroom_id': 42,
            'slug': 'test-facility',
            'name': 'Science Center Washroom',
            'building': 'Physics Building',
            'floor': '2nd Floor',
            'latitude': 18.5220,
            'longitude': 73.8580,
            'distance_km': 0.35,
            'gender_type': 'UNISEX',
            'is_accessible': true,
            'capacity': 5,
            'operating_status': 'OPEN',
            'has_hardware': true,
            'is_active': true,
            'occupancy_status': 'OCCUPIED',
            'people_count': 3,
            'esp32_connected': true,
            'predicted_rush': 'HIGH',
            'predicted_rush_level': 'HIGH',
            'prediction_status': 'SUCCESS',
            'rush_probabilities': {'LOW': 0.1, 'MEDIUM': 0.2, 'HIGH': 0.7},
            'cleanliness': {'rating': null, 'review_count': 0, 'status_label': 'Not yet rated'},
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final api = ApiService(baseUrl: 'http://testserver', client: mockClient);

      await tester.pumpWidget(
        MaterialApp(
          home: WashroomDetailScreen(
            washroomId: 42,
            userLat: 18.5204,
            userLng: 73.8567,
            apiService: api,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Science Center Washroom'), findsWidgets);
      expect(find.text('OCCUPIED'), findsOneWidget);
      expect(find.text('Directions (0.35 km away)'), findsOneWidget);
      expect(find.text('HIGH'), findsOneWidget);
      expect(find.text('LIVE'), findsOneWidget);
      expect(find.text('Not yet rated'), findsOneWidget);
    });
  });
}
