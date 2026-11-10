import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/nearby_washroom.dart';
import '../services/api_service.dart';
import '../utils/app_colors.dart';

/// Screen displaying comprehensive details for a specific public washroom.
class WashroomDetailScreen extends StatefulWidget {
  final int washroomId;
  final double? userLat;
  final double? userLng;
  final ApiService? apiService;
  final NearbyWashroom? initialSummary;

  const WashroomDetailScreen({
    super.key,
    required this.washroomId,
    this.userLat,
    this.userLng,
    this.apiService,
    this.initialSummary,
  });

  @override
  State<WashroomDetailScreen> createState() => _WashroomDetailScreenState();
}

class _WashroomDetailScreenState extends State<WashroomDetailScreen> {
  late ApiService _apiService;
  WashroomDetail? _detail;
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _apiService = widget.apiService ?? ApiService();
    _loadDetails();
  }

  Future<void> _loadDetails() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final detail = await _apiService.getWashroomDetails(
        widget.washroomId,
        userLat: widget.userLat,
        userLng: widget.userLng,
      );
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to load washroom details: $e';
        _isLoading = false;
      });
    }
  }

  Future<void> _launchDirections(double lat, double lng, String name) async {
    final uriGoogle = Uri.parse('https://www.google.com/maps/search/?api=1&query=$lat,$lng');
    final uriGeo = Uri.parse('geo:$lat,$lng?q=$lat,$lng(${Uri.encodeComponent(name)})');

    try {
      if (await canLaunchUrl(uriGeo)) {
        await launchUrl(uriGeo, mode: LaunchMode.externalApplication);
      } else if (await canLaunchUrl(uriGoogle)) {
        await launchUrl(uriGoogle, mode: LaunchMode.externalApplication);
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not launch external map navigation.')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error opening maps: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = _detail?.name ?? widget.initialSummary?.name ?? 'Washroom #${widget.washroomId}';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          name,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh',
            onPressed: _loadDetails,
          ),
        ],
      ),
      body: _isLoading && _detail == null
          ? const Center(child: CircularProgressIndicator())
          : _errorMessage != null && _detail == null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.error_outline_rounded, size: 48, color: AppColors.occupied),
                        const SizedBox(height: 12),
                        Text(_errorMessage!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        ElevatedButton.icon(
                          onPressed: _loadDetails,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                )
              : _buildContent(),
    );
  }

  Widget _buildContent() {
    final d = _detail!;
    final isOccupied = d.isOccupied;
    final lat = d.latitude;
    final lng = d.longitude;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 1. Primary Live Occupancy Card
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: isOccupied ? AppColors.occupiedLight : AppColors.vacantLight,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: isOccupied ? AppColors.occupiedBorder : AppColors.vacantBorder,
                width: 2,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  isOccupied ? Icons.do_not_disturb_on_rounded : Icons.check_circle_rounded,
                  size: 44,
                  color: isOccupied ? AppColors.occupied : AppColors.vacant,
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        d.occupancyStatus,
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w900,
                          color: isOccupied ? AppColors.occupied : AppColors.vacant,
                          letterSpacing: 0.5,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        d.hasHardware
                            ? 'Headcount: ${d.peopleCount} ${d.peopleCount == 1 ? "person" : "people"} inside'
                            : 'Manual facility (no sensor hardware)',
                        style: const TextStyle(
                          fontSize: 13,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                // ESP32 Connectivity Pill
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: d.esp32Connected ? AppColors.liveBadgeBg : Colors.grey.shade200,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: d.esp32Connected ? AppColors.liveBadgeBorder : Colors.grey.shade400,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: d.esp32Connected ? AppColors.vacant : Colors.grey.shade600,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        d.esp32Connected ? 'LIVE' : 'OFFLINE',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: d.esp32Connected ? AppColors.vacant : Colors.grey.shade700,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // 2. Navigation & Distance Action Bar
          if (lat != null && lng != null)
            ElevatedButton.icon(
              onPressed: () => _launchDirections(lat, lng, d.name),
              icon: const Icon(Icons.navigation_rounded),
              label: Text(
                d.distanceKm != null
                    ? 'Directions (${d.distanceKm!.toStringAsFixed(2)} km away)'
                    : 'Get Directions',
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),

          const SizedBox(height: 16),

          // 3. AI Rush Prediction Card
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: BorderSide(color: Colors.grey.shade200),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.psychology_rounded, size: 20, color: AppColors.primary),
                      SizedBox(width: 8),
                      Text(
                        'AI Rush Prediction',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const Divider(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Predicted Congestion:'),
                      _buildRushPill(d.predictedRush),
                    ],
                  ),
                  if (d.rushProbabilities != null) ...[
                    const SizedBox(height: 12),
                    _buildProbBar('Low', d.rushProbabilities!.low, AppColors.vacant),
                    const SizedBox(height: 6),
                    _buildProbBar('Medium', d.rushProbabilities!.medium, Colors.orange),
                    const SizedBox(height: 6),
                    _buildProbBar('High', d.rushProbabilities!.high, AppColors.occupied),
                  ] else if (!d.hasHardware) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'AI prediction is unavailable because this facility does not have IoT sensor hardware installed.',
                      style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                    ),
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // 4. Facility Specifications Card
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: BorderSide(color: Colors.grey.shade200),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.info_outline_rounded, size: 20, color: AppColors.primary),
                      SizedBox(width: 8),
                      Text(
                        'Facility Information',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const Divider(height: 20),
                  _buildInfoRow('Location:', '${d.building ?? "Building unlisted"} ${d.floor != null ? "• ${d.floor}" : ""}'),
                  _buildInfoRow('Gender:', d.genderType),
                  _buildInfoRow(
                    'Wheelchair Accessible:',
                    d.isAccessible == true
                        ? 'Yes (Wheelchair friendly)'
                        : d.isAccessible == false
                            ? 'No'
                            : 'Unverified',
                  ),
                  _buildInfoRow('Stall Capacity:', d.capacity != null ? '${d.capacity} stalls' : 'Standard (5)'),
                  _buildInfoRow('Operating Status:', d.operatingStatus),
                  if (d.operatingHours != null)
                    _buildInfoRow('Hours:', d.operatingHours!),
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // 5. Cleanliness Feedback Card (Milestone 4 preview)
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: BorderSide(color: Colors.grey.shade200),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  const Icon(Icons.cleaning_services_rounded, color: AppColors.primary, size: 24),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Cleanliness Rating',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                        ),
                        Text(
                          d.cleanliness.statusLabel,
                          style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade100,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      d.cleanliness.rating != null
                          ? '⭐ ${d.cleanliness.rating!.toStringAsFixed(1)}'
                          : 'Unrated',
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRushPill(String rush) {
    Color bg;
    Color fg;
    switch (rush.toUpperCase()) {
      case 'LOW':
        bg = AppColors.vacantLight;
        fg = AppColors.vacant;
        break;
      case 'MEDIUM':
        bg = Colors.orange.shade50;
        fg = Colors.orange.shade800;
        break;
      case 'HIGH':
        bg = AppColors.occupiedLight;
        fg = AppColors.occupied;
        break;
      default:
        bg = Colors.grey.shade100;
        fg = Colors.grey.shade700;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        rush,
        style: TextStyle(color: fg, fontWeight: FontWeight.bold, fontSize: 12),
      ),
    );
  }

  Widget _buildProbBar(String label, double prob, Color color) {
    final pct = (prob * 100).round();
    return Row(
      children: [
        SizedBox(width: 60, child: Text(label, style: const TextStyle(fontSize: 12))),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: prob.clamp(0.0, 1.0),
              backgroundColor: Colors.grey.shade200,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 8,
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 35, child: Text('$pct%', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold))),
      ],
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 140,
            child: Text(
              label,
              style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
