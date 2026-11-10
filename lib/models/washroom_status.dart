enum OccupancyStatus {
  vacant,
  occupied,
}

enum RushLevel {
  low,
  medium,
  high,
  unavailable,
}

/// Represents the current occupancy, machine learning, and infrastructure state.
class WashroomStatus {
  final OccupancyStatus occupancy;
  final int peopleInside;
  final RushLevel predictedRush;
  final String predictedRushRaw;
  final Map<String, double>? probabilities;
  final String? predictionNote;
  final String esp32Status;
  final String backendStatus;
  final DateTime lastUpdated;
  final bool isDemoMode;
  final bool isLoading;
  final String? errorMessage;

  const WashroomStatus({
    required this.occupancy,
    required this.peopleInside,
    required this.predictedRush,
    this.predictedRushRaw = 'LOW',
    this.probabilities,
    this.predictionNote,
    required this.esp32Status,
    required this.backendStatus,
    required this.lastUpdated,
    this.isDemoMode = true,
    this.isLoading = false,
    this.errorMessage,
  });

  /// True if backend is actively connected
  bool get isBackendOnline =>
      backendStatus.toUpperCase().contains('ONLINE') ||
      backendStatus.toUpperCase().contains('DEMO');

  /// True if ESP32 is actively communicating
  bool get isEsp32Online =>
      esp32Status.toUpperCase().contains('CONNECTED') ||
      esp32Status.toUpperCase().contains('DEMO');

  /// True if valid ML prediction probabilities are present
  bool get hasProbabilities =>
      probabilities != null &&
      probabilities!.isNotEmpty &&
      predictedRush != RushLevel.unavailable;

  /// Default demo state: Vacant, 0 people, Low rush, Demo mode enabled.
  factory WashroomStatus.initialDemo() {
    return WashroomStatus(
      occupancy: OccupancyStatus.vacant,
      peopleInside: 0,
      predictedRush: RushLevel.low,
      predictedRushRaw: 'LOW',
      probabilities: const {'LOW': 0.9981, 'MEDIUM': 0.0019, 'HIGH': 0.0},
      esp32Status: 'DEMO MODE',
      backendStatus: 'DEMO MODE',
      lastUpdated: DateTime.now(),
      isDemoMode: true,
      isLoading: false,
    );
  }

  /// Initial live state before first telemetry fetch completes
  factory WashroomStatus.initialLive() {
    return WashroomStatus(
      occupancy: OccupancyStatus.vacant,
      peopleInside: 0,
      predictedRush: RushLevel.unavailable,
      predictedRushRaw: 'CONNECTING...',
      probabilities: null,
      esp32Status: 'CONNECTING...',
      backendStatus: 'CONNECTING...',
      lastUpdated: DateTime.now(),
      isDemoMode: false,
      isLoading: true,
    );
  }

  WashroomStatus copyWith({
    OccupancyStatus? occupancy,
    int? peopleInside,
    RushLevel? predictedRush,
    String? predictedRushRaw,
    Map<String, double>? probabilities,
    bool clearProbabilities = false,
    String? predictionNote,
    String? esp32Status,
    String? backendStatus,
    DateTime? lastUpdated,
    bool? isDemoMode,
    bool? isLoading,
    String? errorMessage,
  }) {
    return WashroomStatus(
      occupancy: occupancy ?? this.occupancy,
      peopleInside: peopleInside ?? this.peopleInside,
      predictedRush: predictedRush ?? this.predictedRush,
      predictedRushRaw: predictedRushRaw ?? this.predictedRushRaw,
      probabilities: clearProbabilities
          ? null
          : (probabilities ?? this.probabilities),
      predictionNote: predictionNote ?? this.predictionNote,
      esp32Status: esp32Status ?? this.esp32Status,
      backendStatus: backendStatus ?? this.backendStatus,
      lastUpdated: lastUpdated ?? this.lastUpdated,
      isDemoMode: isDemoMode ?? this.isDemoMode,
      isLoading: isLoading ?? this.isLoading,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }
}
