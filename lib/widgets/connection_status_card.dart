import 'package:flutter/material.dart';
import '../utils/app_colors.dart';

/// Card showing the status of the ESP32 IoT hardware and the FastAPI backend service.
class ConnectionStatusCard extends StatelessWidget {
  final String esp32Status;
  final String backendStatus;

  const ConnectionStatusCard({
    super.key,
    required this.esp32Status,
    required this.backendStatus,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.cardBorder),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.hub_rounded,
                size: 20,
                color: AppColors.primary,
              ),
              SizedBox(width: 8),
              Text(
                'System Infrastructure',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _buildStatusRow(
            icon: Icons.memory_rounded,
            title: 'ESP32 Sensor Unit',
            subtitle: 'Dual IR & PIR Sensors',
            status: esp32Status,
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Divider(height: 1, color: AppColors.divider),
          ),
          _buildStatusRow(
            icon: Icons.cloud_outlined,
            title: 'FastAPI Backend',
            subtitle: 'ML Inference & Sync',
            status: backendStatus,
          ),
        ],
      ),
    );
  }

  Widget _buildStatusRow({
    required IconData icon,
    required String title,
    required String subtitle,
    required String status,
  }) {
    final upper = status.toUpperCase();
    final isDemo = upper.contains('DEMO');
    final isOnline = upper == 'CONNECTED' || upper == 'ONLINE';
    final isOffline = upper == 'DISCONNECTED' || upper == 'OFFLINE' || upper == 'UNREACHABLE';

    Color bgColor = Colors.grey.shade100;
    Color textColor = Colors.grey.shade700;
    Color borderColor = Colors.grey.shade300;
    Color dotColor = Colors.grey.shade600;

    if (isDemo) {
      bgColor = AppColors.demoBadgeBg;
      textColor = AppColors.demoBadgeText;
      borderColor = AppColors.demoBadgeBorder;
      dotColor = AppColors.demoBadgeText;
    } else if (isOnline) {
      bgColor = AppColors.vacantLight;
      textColor = AppColors.vacantDark;
      borderColor = AppColors.vacantBorder;
      dotColor = AppColors.vacant;
    } else if (isOffline) {
      bgColor = AppColors.occupiedLight;
      textColor = AppColors.occupiedDark;
      borderColor = AppColors.occupiedBorder;
      dotColor = AppColors.occupied;
    }

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: AppColors.background,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: AppColors.cardBorder),
          ),
          child: Icon(
            icon,
            size: 20,
            color: AppColors.textSecondary,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
              ),
              Text(
                subtitle,
                style: const TextStyle(
                  fontSize: 12,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: borderColor),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: dotColor,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                status,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  color: textColor,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
