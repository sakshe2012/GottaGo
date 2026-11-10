/// Application-wide constants and API configuration for GottaGo
class AppConstants {
  static const String appName = 'GottaGo';
  static const String appSubtitle = 'Smart Washroom Availability';

  // FastAPI backend configuration
  // 10.0.2.2 routes to the host Mac localhost from the Android emulator.
  // For physical Android device on LAN, set to Mac LAN IP (e.g. http://10.78.101.121:8000).
  //static const String defaultApiBaseUrl = 'http://10.0.2.2:8000';
  static const String defaultApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);
  // API Endpoints
  static const String healthEndpoint = '/health';
  static const String statusEndpoint = '/api/status';
  static const String predictionEndpoint = '/api/prediction';
  static const String nearbyEndpoint = '/api/washrooms/nearby';
  static const String washroomsEndpoint = '/api/washrooms';

  // Periodic Refresh Intervals
  static const Duration statusRefreshInterval = Duration(seconds: 3);
  static const Duration predictionRefreshInterval = Duration(seconds: 12);
  static const Duration requestTimeout = Duration(seconds: 4);
}
