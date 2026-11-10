import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/nearby_washroom.dart';
import '../utils/constants.dart';

/// Custom exception for GottaGo API errors.
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final dynamic cause;

  ApiException(this.message, {this.statusCode, this.cause});

  @override
  String toString() => 'ApiException: $message (status: $statusCode)';
}

class BackendOfflineException extends ApiException {
  BackendOfflineException(super.message, {super.cause});
}

/// DTO for GET /health response
class HealthStatus {
  final String status;
  final String backend;
  final DateTime timestamp;

  const HealthStatus({
    required this.status,
    required this.backend,
    required this.timestamp,
  });

  factory HealthStatus.fromJson(Map<String, dynamic> json) {
    return HealthStatus(
      status: json['status'] as String? ?? 'unknown',
      backend: json['backend'] as String? ?? 'GottaGo Backend',
      timestamp: DateTime.tryParse(json['timestamp'] as String? ?? '') ??
          DateTime.now(),
    );
  }
}

/// DTO for GET /api/status response
class LiveWashroomStatus {
  final String occupancyStatus; // "VACANT" or "OCCUPIED"
  final int peopleCount;
  final bool esp32Connected;
  final DateTime? lastUpdated;

  const LiveWashroomStatus({
    required this.occupancyStatus,
    required this.peopleCount,
    required this.esp32Connected,
    this.lastUpdated,
  });

  factory LiveWashroomStatus.fromJson(Map<String, dynamic> json) {
    return LiveWashroomStatus(
      occupancyStatus: (json['occupancy_status'] as String? ?? 'VACANT').toUpperCase(),
      peopleCount: (json['people_count'] as num? ?? 0).toInt(),
      esp32Connected: json['esp32_connected'] as bool? ?? false,
      lastUpdated: json['last_updated'] != null
          ? DateTime.tryParse(json['last_updated'] as String)
          : null,
    );
  }
}

/// DTO for GET /api/prediction response
class RushPredictionData {
  final String predictedRush; // "LOW", "MEDIUM", "HIGH", "UNAVAILABLE"
  final String predictedRushLevel;
  final String predictionStatus; // "SUCCESS", "UNAVAILABLE", "ERROR"
  final DateTime predictionTimestamp;
  final int? currentOccupancy;
  final double? occupancyPercent;
  final int? capacity;
  final Map<String, double>? probabilities;
  final Map<String, dynamic>? featuresUsed;
  final String modelStatus;
  final String? note;

  const RushPredictionData({
    required this.predictedRush,
    required this.predictedRushLevel,
    required this.predictionStatus,
    required this.predictionTimestamp,
    this.currentOccupancy,
    this.occupancyPercent,
    this.capacity,
    this.probabilities,
    this.featuresUsed,
    required this.modelStatus,
    this.note,
  });

  bool get isAvailable =>
      predictionStatus.toUpperCase() == 'SUCCESS' &&
      predictedRush.toUpperCase() != 'UNAVAILABLE';

  double? get lowProbability => probabilities?['LOW'];
  double? get mediumProbability => probabilities?['MEDIUM'];
  double? get highProbability => probabilities?['HIGH'];

  factory RushPredictionData.fromJson(Map<String, dynamic> json) {
    Map<String, double>? parsedProbabilities;
    if (json['probabilities'] is Map) {
      final rawProbs = json['probabilities'] as Map;
      parsedProbabilities = {
        'LOW': (rawProbs['LOW'] as num?)?.toDouble() ?? 0.0,
        'MEDIUM': (rawProbs['MEDIUM'] as num?)?.toDouble() ?? 0.0,
        'HIGH': (rawProbs['HIGH'] as num?)?.toDouble() ?? 0.0,
      };
    }

    return RushPredictionData(
      predictedRush: (json['predicted_rush'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      predictedRushLevel: (json['predicted_rush_level'] as String? ??
              json['predicted_rush'] as String? ??
              'UNAVAILABLE')
          .toUpperCase(),
      predictionStatus: (json['prediction_status'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      predictionTimestamp: DateTime.tryParse(
              json['prediction_timestamp'] as String? ?? '') ??
          DateTime.now(),
      currentOccupancy: (json['current_occupancy'] as num?)?.toInt(),
      occupancyPercent: (json['occupancy_percent'] as num?)?.toDouble(),
      capacity: (json['capacity'] as num?)?.toInt(),
      probabilities: parsedProbabilities,
      featuresUsed: json['features_used'] as Map<String, dynamic>?,
      modelStatus: json['model_status'] as String? ?? 'UNKNOWN',
      note: json['note'] as String?,
    );
  }

  factory RushPredictionData.unavailable({String? reason}) {
    return RushPredictionData(
      predictedRush: 'UNAVAILABLE',
      predictedRushLevel: 'UNAVAILABLE',
      predictionStatus: 'UNAVAILABLE',
      predictionTimestamp: DateTime.now(),
      modelStatus: 'NOT_CONNECTED',
      note: reason ?? 'Prediction unavailable: backend offline or sensor telemetry disconnected.',
    );
  }
}

/// Service providing typed communication with the GottaGo FastAPI backend.
class ApiService {
  final String baseUrl;
  final http.Client _client;
  final Duration timeout;
  final bool _isCustomClient;

  ApiService({
    this.baseUrl = AppConstants.defaultApiBaseUrl,
    http.Client? client,
    this.timeout = AppConstants.requestTimeout,
  })  : _client = client ?? http.Client(),
        _isCustomClient = client != null;

  /// Check server health
  Future<HealthStatus> getHealth() async {
    final uri = Uri.parse('$baseUrl${AppConstants.healthEndpoint}');
    final json = await _getJson(uri);
    return HealthStatus.fromJson(json);
  }

  /// Get live occupancy, count, and ESP32 heartbeat connection state
  Future<LiveWashroomStatus> getStatus() async {
    final uri = Uri.parse('$baseUrl${AppConstants.statusEndpoint}');
    final json = await _getJson(uri);
    return LiveWashroomStatus.fromJson(json);
  }

  /// Get real ML rush level prediction and probabilities
  Future<RushPredictionData> getPrediction({bool allowStale = false}) async {
    final endpoint = allowStale
        ? '${AppConstants.predictionEndpoint}?allow_stale=true'
        : AppConstants.predictionEndpoint;
    final uri = Uri.parse('$baseUrl$endpoint');
    final json = await _getJson(uri);
    return RushPredictionData.fromJson(json);
  }

  /// Discover nearby washrooms using smartphone coordinates and optional filters
  Future<NearbyDiscoveryResult> getNearbyWashrooms({
    required double latitude,
    required double longitude,
    double radiusKm = 5.0,
    String? gender,
    bool accessibilityRequired = false,
    int limit = 10,
  }) async {
    final queryParams = <String, String>{
      'latitude': latitude.toString(),
      'longitude': longitude.toString(),
      'radius_km': radiusKm.toString(),
      'accessibility_required': accessibilityRequired.toString(),
      'limit': limit.toString(),
    };
    if (gender != null && gender.isNotEmpty) {
      queryParams['gender'] = gender;
    }

    final uri = Uri.parse('$baseUrl${AppConstants.nearbyEndpoint}').replace(
      queryParameters: queryParams,
    );
    final json = await _getJson(uri);
    return NearbyDiscoveryResult.fromJson(json);
  }

  /// Get comprehensive washroom details, live state, and distance
  Future<WashroomDetail> getWashroomDetails(
    int washroomId, {
    double? userLat,
    double? userLng,
  }) async {
    final queryParams = <String, String>{};
    if (userLat != null && userLng != null) {
      queryParams['user_lat'] = userLat.toString();
      queryParams['user_lng'] = userLng.toString();
    }

    final baseUri = Uri.parse('$baseUrl${AppConstants.washroomsEndpoint}/$washroomId');
    final uri = queryParams.isNotEmpty
        ? baseUri.replace(queryParameters: queryParams)
        : baseUri;

    final json = await _getJson(uri);
    return WashroomDetail.fromJson(json);
  }

  /// Internal HTTP GET helper with resilient error handling and timeouts
  Future<Map<String, dynamic>> _getJson(Uri uri) async {
    try {
      final response = await _client.get(
        uri,
        headers: {
          'Accept': 'application/json',
        },
      ).timeout(timeout);

      if (response.statusCode >= 200 && response.statusCode < 300) {
        try {
          final decoded = jsonDecode(response.body);
          if (decoded is Map<String, dynamic>) {
            return decoded;
          }
          throw ApiException('Unexpected JSON response shape: not an object');
        } on FormatException catch (e) {
          throw ApiException('Failed to parse response as JSON: ${e.message}', cause: e);
        }
      } else {
        throw ApiException(
          'HTTP request failed with status ${response.statusCode}: ${response.body}',
          statusCode: response.statusCode,
        );
      }
    } on SocketException catch (e) {
      throw BackendOfflineException(
        'Cannot reach GottaGo backend at $baseUrl. Check host address and network.',
        cause: e,
      );
    } on TimeoutException catch (e) {
      throw BackendOfflineException(
        'Backend request timed out after ${timeout.inSeconds}s.',
        cause: e,
      );
    } on http.ClientException catch (e) {
      throw BackendOfflineException(
        'Client connection error: ${e.message}',
        cause: e,
      );
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('Unexpected error while calling $uri: $e', cause: e);
    }
  }

  /// Disposes HTTP client resources
  void dispose() {
    if (!_isCustomClient) {
      _client.close();
    }
  }
}
