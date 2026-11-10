import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import '../models/nearby_washroom.dart';
import '../services/api_service.dart';
import '../services/location_service.dart';
import '../utils/app_colors.dart';
import 'washroom_detail_screen.dart';

/// Screen for discovering nearby public washrooms using smartphone location and OpenStreetMap.
class NearbyScreen extends StatefulWidget {
  final ApiService? apiService;
  final LocationService? locationService;
  final LatLng? initialLocation;
  final bool enableTileLayer;

  const NearbyScreen({
    super.key,
    this.apiService,
    this.locationService,
    this.initialLocation,
    this.enableTileLayer = true,
  });

  @override
  State<NearbyScreen> createState() => _NearbyScreenState();
}

class _NearbyScreenState extends State<NearbyScreen> {
  late ApiService _apiService;
  late LocationService _locationService;
  final MapController _mapController = MapController();

  LatLng? _userLocation;
  bool _isLoadingLocation = true;
  bool _isLoadingWashrooms = false;
  String? _locationError;
  bool _isPermissionPermanentlyDenied = false;
  bool _isServiceDisabled = false;

  double _radiusKm = 5.0;
  String? _selectedGender; // null = all
  bool _accessibilityRequired = false;

  List<NearbyWashroom> _washrooms = [];
  NearbyWashroom? _selectedWashroom;

  @override
  void initState() {
    super.initState();
    _apiService = widget.apiService ?? ApiService();
    _locationService = widget.locationService ?? LocationService();

    final isTestEnvironment = Platform.environment.containsKey('FLUTTER_TEST');

    if (widget.initialLocation != null) {
      // Explicitly injected mock location for test harness
      _userLocation = widget.initialLocation;
      _isLoadingLocation = false;
      _fetchNearbyWashrooms();
    } else if (isTestEnvironment) {
      // In automated headless widget tests where no test fixture is passed:
      // Strictly maintain _userLocation = null. Never activate or substitute fake coordinates!
      _userLocation = null;
      _isLoadingLocation = false;
      _locationError = 'Location services are unavailable in automated test environment.';
    } else {
      // Production runtime: acquire real physical smartphone GPS coordinates
      _acquireLocation();
    }
  }

  Future<void> _acquireLocation() async {
    setState(() {
      _isLoadingLocation = true;
      _locationError = null;
      _isPermissionPermanentlyDenied = false;
      _isServiceDisabled = false;
    });

    final result = await _locationService.getCurrentLocation();
    if (!mounted) return;

    if (result.isSuccess && result.position != null) {
      final loc = LatLng(result.position!.latitude, result.position!.longitude);
      setState(() {
        _userLocation = loc;
        _isLoadingLocation = false;
        _locationError = null;
      });
      _fetchNearbyWashrooms();
    } else {
      setState(() {
        _userLocation = null;
        _locationError = result.errorMessage ?? 'Unable to determine smartphone location.';
        _isLoadingLocation = false;
        _isPermissionPermanentlyDenied =
            (result.permission == LocationPermission.deniedForever);
        _isServiceDisabled = !result.isServiceEnabled;
      });
      // Do NOT query backend with fabricated coordinates.
    }
  }

  Future<void> _fetchNearbyWashrooms() async {
    if (_userLocation == null) return;

    setState(() {
      _isLoadingWashrooms = true;
    });

    try {
      final discovery = await _apiService.getNearbyWashrooms(
        latitude: _userLocation!.latitude,
        longitude: _userLocation!.longitude,
        radiusKm: _radiusKm,
        gender: _selectedGender,
        accessibilityRequired: _accessibilityRequired,
        limit: 20,
      );

      if (!mounted) return;
      setState(() {
        _washrooms = discovery.washrooms;
        _isLoadingWashrooms = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoadingWashrooms = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to load nearby washrooms: $e')),
      );
    }
  }

  void _navigateToDetail(NearbyWashroom washroom) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => WashroomDetailScreen(
          washroomId: washroom.washroomId,
          userLat: _userLocation?.latitude,
          userLng: _userLocation?.longitude,
          apiService: _apiService,
          initialSummary: washroom,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          'Nearby Washrooms',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.my_location_rounded),
            tooltip: 'Acquire Current Location',
            onPressed: _acquireLocation,
          ),
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh Washrooms',
            onPressed: _fetchNearbyWashrooms,
          ),
        ],
      ),
      body: Column(
        children: [
          // 1. Permission / GPS Notice Banner (if degraded)
          if (_locationError != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              color: Colors.amber.shade100,
              child: Row(
                children: [
                  const Icon(Icons.warning_amber_rounded, size: 20, color: Colors.orange),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _locationError!,
                      style: const TextStyle(fontSize: 12, color: Colors.black87),
                    ),
                  ),
                  if (_isPermissionPermanentlyDenied)
                    TextButton(
                      onPressed: () => _locationService.openSettings(),
                      child: const Text('Settings', style: TextStyle(fontWeight: FontWeight.bold)),
                    )
                  else if (_isServiceDisabled)
                    TextButton(
                      onPressed: () => _locationService.openLocationSettings(),
                      child: const Text('Enable GPS', style: TextStyle(fontWeight: FontWeight.bold)),
                    )
                  else
                    TextButton(
                      onPressed: _acquireLocation,
                      child: const Text('Retry', style: TextStyle(fontWeight: FontWeight.bold)),
                    ),
                ],
              ),
            ),

          // 2. Filter Bar (Gender chips, Accessibility, Radius)
          _buildFilterBar(),

          // 3. Main Split View: Map on top (40%), List on bottom (60%)
          Expanded(
            child: _isLoadingLocation
                ? const Center(child: CircularProgressIndicator())
                : Stack(
                    children: [
                      Column(
                        children: [
                          // OpenStreetMap View
                          SizedBox(
                            height: 240,
                            child: _buildMap(),
                          ),
                          // Washroom Results List
                          Expanded(
                            child: _buildWashroomsList(),
                          ),
                        ],
                      ),
                      if (_isLoadingWashrooms)
                        Positioned(
                          top: 10,
                          right: 10,
                          child: Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.9),
                              shape: BoxShape.circle,
                            ),
                            child: const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      color: AppColors.surface,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            // Radius Filter
            PopupMenuButton<double>(
              initialValue: _radiusKm,
              onSelected: (val) {
                setState(() => _radiusKm = val);
                _fetchNearbyWashrooms();
              },
              child: Chip(
                avatar: const Icon(Icons.radar_rounded, size: 16),
                label: Text('${_radiusKm.toStringAsFixed(1)} km'),
                backgroundColor: AppColors.background,
              ),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 1.0, child: Text('1.0 km')),
                PopupMenuItem(value: 2.0, child: Text('2.0 km')),
                PopupMenuItem(value: 5.0, child: Text('5.0 km')),
                PopupMenuItem(value: 10.0, child: Text('10.0 km')),
                PopupMenuItem(value: 20.0, child: Text('20.0 km')),
              ],
            ),
            const SizedBox(width: 8),

            // Gender Chips
            ChoiceChip(
              label: const Text('All'),
              selected: _selectedGender == null,
              onSelected: (_) {
                setState(() => _selectedGender = null);
                _fetchNearbyWashrooms();
              },
            ),
            const SizedBox(width: 6),
            ChoiceChip(
              label: const Text('Female'),
              selected: _selectedGender == 'FEMALE',
              onSelected: (selected) {
                setState(() => _selectedGender = selected ? 'FEMALE' : null);
                _fetchNearbyWashrooms();
              },
            ),
            const SizedBox(width: 6),
            ChoiceChip(
              label: const Text('Male'),
              selected: _selectedGender == 'MALE',
              onSelected: (selected) {
                setState(() => _selectedGender = selected ? 'MALE' : null);
                _fetchNearbyWashrooms();
              },
            ),
            const SizedBox(width: 6),
            ChoiceChip(
              label: const Text('Unisex'),
              selected: _selectedGender == 'UNISEX',
              onSelected: (selected) {
                setState(() => _selectedGender = selected ? 'UNISEX' : null);
                _fetchNearbyWashrooms();
              },
            ),
            const SizedBox(width: 8),

            // Accessibility Filter Toggle
            FilterChip(
              avatar: const Icon(Icons.accessible_rounded, size: 16),
              label: const Text('Wheelchair'),
              selected: _accessibilityRequired,
              onSelected: (selected) {
                setState(() => _accessibilityRequired = selected);
                _fetchNearbyWashrooms();
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMap() {
    // Neutral initial camera center (used only for map viewport matrix before GPS lock)
    const defaultCameraCenter = LatLng(18.5204, 73.8567);
    final center = _userLocation ??
        (_washrooms.isNotEmpty
            ? LatLng(_washrooms.first.latitude, _washrooms.first.longitude)
            : defaultCameraCenter);

    final markers = <Marker>[];

    // User location marker: rendered exclusively when real smartphone coordinates are acquired
    if (_userLocation != null) {
      markers.add(
        Marker(
          point: _userLocation!,
          width: 32,
          height: 32,
          child: Container(
            decoration: BoxDecoration(
              color: Colors.blue.withValues(alpha: 0.3),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Container(
                width: 16,
                height: 16,
                decoration: const BoxDecoration(
                  color: Colors.blueAccent,
                  shape: BoxShape.circle,
                ),
              ),
            ),
          ),
        ),
      );
    }

    // Washroom facility markers
    for (final w in _washrooms) {
      final isSelected = _selectedWashroom?.washroomId == w.washroomId;
      final color = w.isVacant
          ? AppColors.vacant
          : w.isOccupied
              ? AppColors.occupied
              : Colors.grey;

      markers.add(
        Marker(
          point: LatLng(w.latitude, w.longitude),
          width: isSelected ? 48 : 36,
          height: isSelected ? 48 : 36,
          child: GestureDetector(
            onTap: () {
              setState(() => _selectedWashroom = w);
            },
            child: Container(
              decoration: BoxDecoration(
                color: color,
                shape: BoxShape.circle,
                border: Border.all(
                  color: isSelected ? Colors.black : Colors.white,
                  width: isSelected ? 3 : 2,
                ),
                boxShadow: const [
                  BoxShadow(color: Colors.black26, blurRadius: 4, offset: Offset(0, 2)),
                ],
              ),
              child: Center(
                child: Text(
                  '${w.recommendationRank}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    final showTiles = widget.enableTileLayer && !Platform.environment.containsKey('FLUTTER_TEST');

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: center,
        initialZoom: 14.0,
      ),
      children: [
        if (showTiles)
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.gottago.gottago',
          ),
        MarkerLayer(markers: markers),
      ],
    );
  }

  Widget _buildWashroomsList() {
    if (_userLocation == null) {
      return Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.location_off_rounded, size: 44, color: Colors.grey.shade400),
              const SizedBox(height: 12),
              const Text(
                'Location Access Required',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                'GottaGo requires your physical device location to discover nearby public washrooms and calculate accurate distance estimates.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary, fontSize: 12, height: 1.3),
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _acquireLocation,
                icon: const Icon(Icons.my_location_rounded, size: 16),
                label: const Text('Detect Current Location'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (_washrooms.isEmpty && !_isLoadingWashrooms) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.location_off_rounded, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              Text(
                'No washrooms found within ${_radiusKm.toStringAsFixed(1)} km matching your filters.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.textSecondary),
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () {
                  setState(() {
                    _radiusKm = 10.0;
                    _selectedGender = null;
                    _accessibilityRequired = false;
                  });
                  _fetchNearbyWashrooms();
                },
                child: const Text('Reset Filters (10 km)'),
              ),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: _washrooms.length,
      itemBuilder: (context, index) {
        final w = _washrooms[index];
        final isSelected = _selectedWashroom?.washroomId == w.washroomId;

        return Card(
          margin: const EdgeInsets.only(bottom: 10),
          elevation: isSelected ? 3 : 1,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(
              color: isSelected ? AppColors.primary : Colors.grey.shade200,
              width: isSelected ? 2 : 1,
            ),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: () => _navigateToDetail(w),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Rank badge
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: AppColors.primary.withValues(alpha: 0.15),
                    child: Text(
                      '#${w.recommendationRank}',
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                        color: AppColors.primaryDark,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),

                  // Washroom details
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                w.name,
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                ),
                              ),
                            ),
                            Text(
                              '${w.distanceKm.toStringAsFixed(2)} km',
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 13,
                                color: AppColors.primary,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${w.building ?? "Building unlisted"} • ${w.genderType}',
                          style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            // Occupancy Pill
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: w.isVacant ? AppColors.vacantLight : AppColors.occupiedLight,
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                w.occupancyStatus,
                                style: TextStyle(
                                  color: w.isVacant ? AppColors.vacant : AppColors.occupied,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 11,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),

                            // Rush Pill
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: Colors.grey.shade100,
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                'Rush: ${w.predictedRush}',
                                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                              ),
                            ),

                            if (w.isAccessible == true) ...[
                              const SizedBox(width: 8),
                              const Icon(Icons.accessible_rounded, size: 16, color: Colors.blue),
                            ],
                          ],
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right_rounded, color: Colors.grey),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
