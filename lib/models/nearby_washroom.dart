/// Cleanliness feedback summary for a washroom facility.
class CleanlinessInfo {
  final double? rating;
  final int reviewCount;
  final String statusLabel;

  const CleanlinessInfo({
    this.rating,
    required this.reviewCount,
    required this.statusLabel,
  });

  factory CleanlinessInfo.fromJson(Map<String, dynamic> json) {
    return CleanlinessInfo(
      rating: (json['rating'] as num?)?.toDouble(),
      reviewCount: (json['review_count'] as num?)?.toInt() ?? 0,
      statusLabel: json['status_label'] as String? ?? 'Not yet rated',
    );
  }
}

/// Probability breakdown across rush categories.
class RushProbabilitiesData {
  final double low;
  final double medium;
  final double high;

  const RushProbabilitiesData({
    required this.low,
    required this.medium,
    required this.high,
  });

  factory RushProbabilitiesData.fromJson(Map<String, dynamic> json) {
    return RushProbabilitiesData(
      low: (json['LOW'] as num?)?.toDouble() ?? 0.0,
      medium: (json['MEDIUM'] as num?)?.toDouble() ?? 0.0,
      high: (json['HIGH'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

/// A discovered washroom returned by the nearby discovery API.
class NearbyWashroom {
  final int washroomId;
  final String slug;
  final String name;
  final String? building;
  final String? floor;
  final String? roomNumber;
  final double latitude;
  final double longitude;
  final double distanceKm;
  final String genderType;
  final bool? isAccessible;
  final int? capacity;
  final bool hasHardware;
  final bool isActive;
  final String occupancyStatus;
  final int peopleCount;
  final bool esp32Connected;
  final DateTime? lastUpdated;
  final String predictedRush;
  final String predictedRushLevel;
  final String predictionStatus;
  final RushProbabilitiesData? rushProbabilities;
  final CleanlinessInfo cleanliness;
  final double recommendationScore;
  final int recommendationRank;

  const NearbyWashroom({
    required this.washroomId,
    required this.slug,
    required this.name,
    this.building,
    this.floor,
    this.roomNumber,
    required this.latitude,
    required this.longitude,
    required this.distanceKm,
    required this.genderType,
    this.isAccessible,
    this.capacity,
    required this.hasHardware,
    required this.isActive,
    required this.occupancyStatus,
    required this.peopleCount,
    required this.esp32Connected,
    this.lastUpdated,
    required this.predictedRush,
    required this.predictedRushLevel,
    required this.predictionStatus,
    this.rushProbabilities,
    required this.cleanliness,
    required this.recommendationScore,
    required this.recommendationRank,
  });

  bool get isVacant => occupancyStatus.toUpperCase() == 'VACANT';
  bool get isOccupied => occupancyStatus.toUpperCase() == 'OCCUPIED';

  factory NearbyWashroom.fromJson(Map<String, dynamic> json) {
    return NearbyWashroom(
      washroomId: (json['washroom_id'] as num).toInt(),
      slug: json['slug'] as String? ?? '',
      name: json['name'] as String? ?? 'Washroom',
      building: json['building'] as String?,
      floor: json['floor'] as String?,
      roomNumber: json['room_number'] as String?,
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      distanceKm: (json['distance_km'] as num).toDouble(),
      genderType: json['gender_type'] as String? ?? 'UNKNOWN',
      isAccessible: json['is_accessible'] as bool?,
      capacity: (json['capacity'] as num?)?.toInt(),
      hasHardware: json['has_hardware'] as bool? ?? false,
      isActive: json['is_active'] as bool? ?? true,
      occupancyStatus: (json['occupancy_status'] as String? ?? 'VACANT').toUpperCase(),
      peopleCount: (json['people_count'] as num?)?.toInt() ?? 0,
      esp32Connected: json['esp32_connected'] as bool? ?? false,
      lastUpdated: json['last_updated'] != null
          ? DateTime.tryParse(json['last_updated'] as String)
          : null,
      predictedRush: (json['predicted_rush'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      predictedRushLevel: (json['predicted_rush_level'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      predictionStatus: (json['prediction_status'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      rushProbabilities: json['rush_probabilities'] != null
          ? RushProbabilitiesData.fromJson(json['rush_probabilities'] as Map<String, dynamic>)
          : null,
      cleanliness: json['cleanliness'] != null
          ? CleanlinessInfo.fromJson(json['cleanliness'] as Map<String, dynamic>)
          : const CleanlinessInfo(reviewCount: 0, statusLabel: 'Not yet rated'),
      recommendationScore: (json['recommendation_score'] as num?)?.toDouble() ?? 0.0,
      recommendationRank: (json['recommendation_rank'] as num?)?.toInt() ?? 1,
    );
  }
}

/// The response from GET /api/washrooms/nearby.
class NearbyDiscoveryResult {
  final double userLatitude;
  final double userLongitude;
  final double searchRadiusKm;
  final int totalFound;
  final List<NearbyWashroom> washrooms;

  const NearbyDiscoveryResult({
    required this.userLatitude,
    required this.userLongitude,
    required this.searchRadiusKm,
    required this.totalFound,
    required this.washrooms,
  });

  factory NearbyDiscoveryResult.fromJson(Map<String, dynamic> json) {
    final userLoc = json['user_location'] as Map<String, dynamic>? ?? {};
    final list = json['washrooms'] as List<dynamic>? ?? [];
    return NearbyDiscoveryResult(
      userLatitude: (userLoc['latitude'] as num?)?.toDouble() ?? 0.0,
      userLongitude: (userLoc['longitude'] as num?)?.toDouble() ?? 0.0,
      searchRadiusKm: (json['search_radius_km'] as num?)?.toDouble() ?? 5.0,
      totalFound: (json['total_found'] as num?)?.toInt() ?? list.length,
      washrooms: list
          .map((item) => NearbyWashroom.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// Full details of a washroom facility returned by GET /api/washrooms/{washroom_id}.
class WashroomDetail {
  final int washroomId;
  final String slug;
  final String name;
  final String? building;
  final String? floor;
  final String? roomNumber;
  final double? latitude;
  final double? longitude;
  final double? distanceKm;
  final String genderType;
  final bool? isAccessible;
  final int? capacity;
  final String operatingStatus;
  final String? operatingHours;
  final String? amenities;
  final bool hasHardware;
  final bool isActive;
  final String occupancyStatus;
  final int peopleCount;
  final bool esp32Connected;
  final DateTime? lastUpdated;
  final String predictedRush;
  final String predictedRushLevel;
  final String predictionStatus;
  final RushProbabilitiesData? rushProbabilities;
  final CleanlinessInfo cleanliness;

  const WashroomDetail({
    required this.washroomId,
    required this.slug,
    required this.name,
    this.building,
    this.floor,
    this.roomNumber,
    this.latitude,
    this.longitude,
    this.distanceKm,
    required this.genderType,
    this.isAccessible,
    this.capacity,
    required this.operatingStatus,
    this.operatingHours,
    this.amenities,
    required this.hasHardware,
    required this.isActive,
    required this.occupancyStatus,
    required this.peopleCount,
    required this.esp32Connected,
    this.lastUpdated,
    required this.predictedRush,
    required this.predictedRushLevel,
    required this.predictionStatus,
    this.rushProbabilities,
    required this.cleanliness,
  });

  bool get isVacant => occupancyStatus.toUpperCase() == 'VACANT';
  bool get isOccupied => occupancyStatus.toUpperCase() == 'OCCUPIED';

  factory WashroomDetail.fromJson(Map<String, dynamic> json) {
    return WashroomDetail(
      washroomId: (json['washroom_id'] as num).toInt(),
      slug: json['slug'] as String? ?? '',
      name: json['name'] as String? ?? 'Washroom',
      building: json['building'] as String?,
      floor: json['floor'] as String?,
      roomNumber: json['room_number'] as String?,
      latitude: (json['latitude'] as num?)?.toDouble(),
      longitude: (json['longitude'] as num?)?.toDouble(),
      distanceKm: (json['distance_km'] as num?)?.toDouble(),
      genderType: json['gender_type'] as String? ?? 'UNKNOWN',
      isAccessible: json['is_accessible'] as bool?,
      capacity: (json['capacity'] as num?)?.toInt(),
      operatingStatus: json['operating_status'] as String? ?? 'UNKNOWN',
      operatingHours: json['operating_hours'] as String?,
      amenities: json['amenities'] as String?,
      hasHardware: json['has_hardware'] as bool? ?? false,
      isActive: json['is_active'] as bool? ?? true,
      occupancyStatus: (json['occupancy_status'] as String? ?? 'VACANT').toUpperCase(),
      peopleCount: (json['people_count'] as num?)?.toInt() ?? 0,
      esp32Connected: json['esp32_connected'] as bool? ?? false,
      lastUpdated: json['last_updated'] != null
          ? DateTime.tryParse(json['last_updated'] as String)
          : null,
      predictedRush: (json['predicted_rush'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      predictedRushLevel: (json['predicted_rush_level'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      predictionStatus: (json['prediction_status'] as String? ?? 'UNAVAILABLE').toUpperCase(),
      rushProbabilities: json['rush_probabilities'] != null
          ? RushProbabilitiesData.fromJson(json['rush_probabilities'] as Map<String, dynamic>)
          : null,
      cleanliness: json['cleanliness'] != null
          ? CleanlinessInfo.fromJson(json['cleanliness'] as Map<String, dynamic>)
          : const CleanlinessInfo(reviewCount: 0, statusLabel: 'Not yet rated'),
    );
  }
}
