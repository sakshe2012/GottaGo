import 'dart:async';
import 'package:geolocator/geolocator.dart';

/// Encapsulates the outcome of a smartphone location retrieval attempt.
class LocationResult {
  final Position? position;
  final bool isServiceEnabled;
  final LocationPermission permission;
  final String? errorMessage;

  const LocationResult({
    this.position,
    required this.isServiceEnabled,
    required this.permission,
    this.errorMessage,
  });

  bool get isSuccess => position != null;
  bool get isPermissionDenied =>
      permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever;

  factory LocationResult.success(Position position) {
    return LocationResult(
      position: position,
      isServiceEnabled: true,
      permission: LocationPermission.always,
    );
  }

  factory LocationResult.serviceDisabled() {
    return const LocationResult(
      isServiceEnabled: false,
      permission: LocationPermission.unableToDetermine,
      errorMessage: 'Location services are disabled on this device. Please enable GPS in settings.',
    );
  }

  factory LocationResult.permissionDenied({bool permanently = false}) {
    return LocationResult(
      isServiceEnabled: true,
      permission: permanently ? LocationPermission.deniedForever : LocationPermission.denied,
      errorMessage: permanently
          ? 'Location permission is permanently denied. Please grant location access in App Settings.'
          : 'Location permission was denied. Tap to grant permission to find nearby washrooms.',
    );
  }

  factory LocationResult.error(String message) {
    return LocationResult(
      isServiceEnabled: true,
      permission: LocationPermission.unableToDetermine,
      errorMessage: message,
    );
  }
}

/// Service providing typed smartphone location services and permission handling.
class LocationService {
  /// Requests and retrieves the user's current smartphone GPS coordinates.
  /// Gracefully handles permission denial, disabled services, and acquisition timeouts.
  Future<LocationResult> getCurrentLocation({
    Duration timeout = const Duration(seconds: 8),
  }) async {
    // 1. Check if device location services (GPS) are enabled
    bool serviceEnabled;
    try {
      serviceEnabled = await Geolocator.isLocationServiceEnabled();
    } catch (e) {
      return LocationResult.error('Failed to check location service status: $e');
    }

    if (!serviceEnabled) {
      return LocationResult.serviceDisabled();
    }

    // 2. Check current location permission state
    LocationPermission permission;
    try {
      permission = await Geolocator.checkPermission();
    } catch (e) {
      return LocationResult.error('Failed to verify location permissions: $e');
    }

    // 3. Request permission if not yet granted
    if (permission == LocationPermission.denied) {
      try {
        permission = await Geolocator.requestPermission();
      } catch (e) {
        return LocationResult.error('Failed to request location permission: $e');
      }

      if (permission == LocationPermission.denied) {
        return LocationResult.permissionDenied(permanently: false);
      }
    }

    if (permission == LocationPermission.deniedForever) {
      return LocationResult.permissionDenied(permanently: true);
    }

    // 4. Retrieve current coordinates with timeout and fallback to last known
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 8),
        ),
      );
      return LocationResult.success(position);
    } on TimeoutException {
      // Fallback: try retrieving last known position if fresh acquisition timed out
      try {
        final lastKnown = await Geolocator.getLastKnownPosition();
        if (lastKnown != null) {
          return LocationResult.success(lastKnown);
        }
      } catch (_) {}
      return LocationResult.error('GPS location request timed out. Please check your signal and retry.');
    } catch (e) {
      // Fallback on other errors
      try {
        final lastKnown = await Geolocator.getLastKnownPosition();
        if (lastKnown != null) {
          return LocationResult.success(lastKnown);
        }
      } catch (_) {}
      return LocationResult.error('Unable to acquire current location: $e');
    }
  }

  /// Opens application settings so user can grant permanently denied permissions.
  Future<bool> openSettings() async {
    return await Geolocator.openAppSettings();
  }

  /// Opens device location settings so user can turn on GPS.
  Future<bool> openLocationSettings() async {
    return await Geolocator.openLocationSettings();
  }
}
