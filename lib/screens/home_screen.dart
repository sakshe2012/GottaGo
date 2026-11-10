import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../models/washroom_status.dart';
import '../services/api_service.dart';
import '../utils/app_colors.dart';
import '../utils/constants.dart';
import '../widgets/connection_status_card.dart';
import '../widgets/last_updated_widget.dart';
import '../widgets/occupancy_card.dart';
import '../widgets/people_count_card.dart';
import '../widgets/rush_prediction_card.dart';

/// The primary dashboard screen for the GottaGo smart washroom system.
/// Connects to the live FastAPI backend with resilient auto-refresh,
/// while preserving the testable demo simulator.
class HomeScreen extends StatefulWidget {
  final bool? startInDemoMode;
  final ApiService? apiService;

  const HomeScreen({
    super.key,
    this.startInDemoMode,
    this.apiService,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late ApiService _apiService;
  late WashroomStatus _status;
  late bool _isDemoMode;

  Timer? _statusTimer;
  Timer? _predictionTimer;
  bool _isFetchingStatus = false;
  bool _isFetchingPrediction = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _apiService = widget.apiService ?? ApiService();

    // Default to demo mode during unit tests; default to LIVE mode in real execution
    final isRunningTest = Platform.environment.containsKey('FLUTTER_TEST');
    _isDemoMode = widget.startInDemoMode ?? isRunningTest;

    if (_isDemoMode) {
      _status = WashroomStatus.initialDemo();
    } else {
      _status = WashroomStatus.initialLive();
      _startLivePolling();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _stopLivePolling();
    if (widget.apiService == null) {
      _apiService.dispose();
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !_isDemoMode) {
      _fetchStatus();
      _fetchPrediction();
    }
  }

  // ========================================================
  // Periodic Live Polling Logic
  // ========================================================

  void _startLivePolling() {
    _stopLivePolling();

    // Fetch immediately on start
    _fetchStatus();
    _fetchPrediction();

    // Periodic occupancy & ESP32 status (every 3 seconds)
    _statusTimer = Timer.periodic(AppConstants.statusRefreshInterval, (_) {
      if (!_isDemoMode) {
        _fetchStatus();
      }
    });

    // Periodic ML rush prediction (every 12 seconds)
    _predictionTimer = Timer.periodic(AppConstants.predictionRefreshInterval, (_) {
      if (!_isDemoMode) {
        _fetchPrediction();
      }
    });
  }

  void _stopLivePolling() {
    _statusTimer?.cancel();
    _statusTimer = null;
    _predictionTimer?.cancel();
    _predictionTimer = null;
  }

  /// Polls GET /api/status for live occupancy and ESP32 heartbeat state
  Future<void> _fetchStatus() async {
    if (_isFetchingStatus || _isDemoMode) return;
    _isFetchingStatus = true;

    try {
      final statusData = await _apiService.getStatus();

      if (!mounted) return;

      final isOccupied = statusData.occupancyStatus == 'OCCUPIED';
      final occupancy = isOccupied ? OccupancyStatus.occupied : OccupancyStatus.vacant;
      final esp32StatusStr = statusData.esp32Connected ? 'CONNECTED' : 'DISCONNECTED';

      setState(() {
        _status = _status.copyWith(
          occupancy: occupancy,
          peopleInside: statusData.peopleCount,
          esp32Status: esp32StatusStr,
          backendStatus: 'ONLINE',
          lastUpdated: statusData.lastUpdated ?? DateTime.now(),
          isLoading: false,
          errorMessage: null,
        );
      });
    } on BackendOfflineException catch (e) {
      if (!mounted) return;
      setState(() {
        _status = _status.copyWith(
          backendStatus: 'OFFLINE',
          esp32Status: 'DISCONNECTED',
          predictedRush: RushLevel.unavailable,
          clearProbabilities: true,
          predictionNote: 'Backend service offline.',
          isLoading: false,
          errorMessage: e.message,
        );
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _status = _status.copyWith(
          backendStatus: 'OFFLINE',
          isLoading: false,
          errorMessage: 'Communication error: $e',
        );
      });
    } finally {
      _isFetchingStatus = false;
    }
  }

  /// Polls GET /api/prediction for actual machine-learning rush prediction
  Future<void> _fetchPrediction() async {
    if (_isFetchingPrediction || _isDemoMode) return;
    _isFetchingPrediction = true;

    try {
      final predData = await _apiService.getPrediction();

      if (!mounted) return;

      RushLevel level;
      switch (predData.predictedRush) {
        case 'LOW':
          level = RushLevel.low;
          break;
        case 'MEDIUM':
          level = RushLevel.medium;
          break;
        case 'HIGH':
          level = RushLevel.high;
          break;
        default:
          level = RushLevel.unavailable;
          break;
      }

      setState(() {
        _status = _status.copyWith(
          predictedRush: level,
          predictedRushRaw: predData.predictedRush,
          probabilities: predData.probabilities,
          clearProbabilities: !predData.isAvailable,
          predictionNote: predData.note,
          lastUpdated: DateTime.now(),
        );
      });
    } on BackendOfflineException {
      if (!mounted) return;
      setState(() {
        _status = _status.copyWith(
          predictedRush: RushLevel.unavailable,
          clearProbabilities: true,
          predictionNote: 'Prediction unavailable: backend offline.',
        );
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _status = _status.copyWith(
          predictedRush: RushLevel.unavailable,
          clearProbabilities: true,
          predictionNote: 'Failed to retrieve prediction.',
        );
      });
    } finally {
      _isFetchingPrediction = false;
    }
  }

  Future<void> _forceManualRefresh() async {
    if (_isDemoMode) {
      setState(() {
        _status = _status.copyWith(lastUpdated: DateTime.now());
      });
    } else {
      await Future.wait([
        _fetchStatus(),
        _fetchPrediction(),
      ]);
    }
  }

  // ========================================================
  // Mode Switching & Demo Controls
  // ========================================================

  void _toggleMode() {
    setState(() {
      _isDemoMode = !_isDemoMode;
      if (_isDemoMode) {
        _stopLivePolling();
        _status = WashroomStatus.initialDemo();
      } else {
        _status = WashroomStatus.initialLive();
        _startLivePolling();
      }
    });
  }

  void _setDemoPreset({
    required OccupancyStatus occupancy,
    required int people,
    required RushLevel rush,
  }) {
    setState(() {
      _status = _status.copyWith(
        occupancy: occupancy,
        peopleInside: people,
        predictedRush: rush,
        lastUpdated: DateTime.now(),
      );
    });
  }

  // ========================================================
  // UI Build
  // ========================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        elevation: 0,
        scrolledUnderElevation: 1,
        titleSpacing: 20,
        title: Row(
          children: [
            // App Logo Icon
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.primary, AppColors.primaryDark],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withValues(alpha: 0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: const Center(
                child: Icon(
                  Icons.sensors_rounded,
                  color: Colors.white,
                  size: 24,
                ),
              ),
            ),
            const SizedBox(width: 12),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  AppConstants.appName,
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                    letterSpacing: -0.5,
                  ),
                ),
                Text(
                  AppConstants.appSubtitle,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          // Mode Pill Switcher (LIVE vs DEMO)
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: InkWell(
                onTap: _toggleMode,
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: _isDemoMode ? AppColors.demoBadgeBg : AppColors.liveBadgeBg,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: _isDemoMode ? AppColors.demoBadgeBorder : AppColors.liveBadgeBorder,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        _isDemoMode ? Icons.science_rounded : Icons.wifi_tethering_rounded,
                        size: 13,
                        color: _isDemoMode ? AppColors.demoBadgeText : AppColors.liveBadgeText,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        _isDemoMode ? 'DEMO MODE' : 'LIVE MODE',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          color: _isDemoMode ? AppColors.demoBadgeText : AppColors.liveBadgeText,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // System Notification Banner if Backend Offline or ESP32 Disconnected
              if (!_isDemoMode) _buildLiveStatusBanner(),

              // B. Main Occupancy Status Card (Hero Element)
              OccupancyCard(status: _status.occupancy),
              const SizedBox(height: 16),

              // C & D. People Count & Predicted Rush Cards
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: PeopleCountCard(count: _status.peopleInside),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: RushPredictionCard(
                      level: _status.predictedRush,
                      probabilities: _status.probabilities,
                      note: _status.predictionNote,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // E. Connection Status Card (ESP32 & Backend)
              ConnectionStatusCard(
                esp32Status: _status.esp32Status,
                backendStatus: _status.backendStatus,
              ),
              const SizedBox(height: 16),

              // F. Last Updated Time
              LastUpdatedWidget(
                timestamp: _status.lastUpdated,
                onRefresh: _forceManualRefresh,
              ),
              const SizedBox(height: 20),

              // Simulator Controls (Shown in Demo Mode, or collapsed quick-toggle in Live Mode)
              _buildDemoControls(),
              const SizedBox(height: 20),
            ],
          ),
        ),
      ),
    );
  }

  /// Live banner communicating backend connectivity and ESP32 heartbeat state
  Widget _buildLiveStatusBanner() {
    final isBackendDown = !_status.isBackendOnline;
    final isEsp32Down = _status.isBackendOnline && !_status.isEsp32Online;

    if (!isBackendDown && !isEsp32Down && !_status.isLoading) {
      return const SizedBox.shrink();
    }

    Color bannerBg;
    Color bannerBorder;
    Color bannerText;
    IconData bannerIcon;
    String message;

    if (_status.isLoading) {
      bannerBg = AppColors.primaryLight;
      bannerBorder = AppColors.primary.withValues(alpha: 0.3);
      bannerText = AppColors.primaryDark;
      bannerIcon = Icons.sync_rounded;
      message = 'Connecting to GottaGo backend (${_apiService.baseUrl})...';
    } else if (isBackendDown) {
      bannerBg = AppColors.offlineBadgeBg;
      bannerBorder = AppColors.offlineBadgeBorder;
      bannerText = AppColors.offlineBadgeText;
      bannerIcon = Icons.cloud_off_rounded;
      message = 'Backend offline. Reconnecting automatically...';
    } else {
      bannerBg = AppColors.warningBadgeBg;
      bannerBorder = AppColors.warningBadgeBorder;
      bannerText = AppColors.warningBadgeText;
      bannerIcon = Icons.sensors_off_rounded;
      message = 'ESP32 sensor unit is disconnected. Waiting for heartbeat...';
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: bannerBg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: bannerBorder),
      ),
      child: Row(
        children: [
          Icon(bannerIcon, size: 16, color: bannerText),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: bannerText,
              ),
            ),
          ),
          if (_status.isLoading)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
        ],
      ),
    );
  }

  /// Compact demo controller allowing evaluators to test states easily
  Widget _buildDemoControls() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.cardBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.tune_rounded,
                size: 16,
                color: AppColors.textSecondary,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  _isDemoMode ? 'Demo State Simulator' : 'State Simulator',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              InkWell(
                onTap: _toggleMode,
                child: Text(
                  _isDemoMode ? 'Live Mode' : 'Demo Mode',
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: AppColors.primary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildDemoChip(
                label: 'Vacant (0 inside, Low rush)',
                isSelected: _isDemoMode &&
                    _status.occupancy == OccupancyStatus.vacant &&
                    _status.peopleInside == 0,
                selectedColor: AppColors.vacant,
                onTap: () {
                  if (!_isDemoMode) _toggleMode();
                  _setDemoPreset(
                    occupancy: OccupancyStatus.vacant,
                    people: 0,
                    rush: RushLevel.low,
                  );
                },
              ),
              _buildDemoChip(
                label: 'Occupied (1 inside, Med rush)',
                isSelected: _isDemoMode &&
                    _status.occupancy == OccupancyStatus.occupied &&
                    _status.peopleInside == 1,
                selectedColor: AppColors.rushMedium,
                onTap: () {
                  if (!_isDemoMode) _toggleMode();
                  _setDemoPreset(
                    occupancy: OccupancyStatus.occupied,
                    people: 1,
                    rush: RushLevel.medium,
                  );
                },
              ),
              _buildDemoChip(
                label: 'Occupied (2 inside, High rush)',
                isSelected: _isDemoMode &&
                    _status.occupancy == OccupancyStatus.occupied &&
                    _status.peopleInside == 2,
                selectedColor: AppColors.occupied,
                onTap: () {
                  if (!_isDemoMode) _toggleMode();
                  _setDemoPreset(
                    occupancy: OccupancyStatus.occupied,
                    people: 2,
                    rush: RushLevel.high,
                  );
                },
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDemoChip({
    required String label,
    required bool isSelected,
    required Color selectedColor,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected
              ? selectedColor.withValues(alpha: 0.12)
              : AppColors.background,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isSelected ? selectedColor : AppColors.cardBorder,
            width: isSelected ? 1.5 : 1.0,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
            color: isSelected ? selectedColor : AppColors.textPrimary,
          ),
        ),
      ),
    );
  }
}
