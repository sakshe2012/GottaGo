import 'package:flutter/material.dart';
import '../models/washroom_status.dart';
import '../utils/app_colors.dart';

/// Hero occupancy card displaying whether the washroom is VACANT or OCCUPIED.
class OccupancyCard extends StatelessWidget {
  final OccupancyStatus status;

  const OccupancyCard({
    super.key,
    required this.status,
  });

  bool get isVacant => status == OccupancyStatus.vacant;

  @override
  Widget build(BuildContext context) {
    final statusColor = isVacant ? AppColors.vacant : AppColors.occupied;
    final statusBg = isVacant ? AppColors.vacantLight : AppColors.occupiedLight;
    final statusBorder = isVacant ? AppColors.vacantBorder : AppColors.occupiedBorder;
    final statusTitle = isVacant ? 'VACANT' : 'OCCUPIED';
    final statusMessage = isVacant
        ? 'Washroom is available'
        : 'Washroom is currently in use';
    final statusIcon = isVacant ? Icons.lock_open_rounded : Icons.lock_rounded;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
      decoration: BoxDecoration(
        color: statusBg,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: statusBorder, width: 2),
        boxShadow: [
          BoxShadow(
            color: statusColor.withValues(alpha: 0.12),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        children: [
          // Circular status icon with ambient ring
          Container(
            width: 88,
            height: 88,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: statusColor.withValues(alpha: 0.15),
              border: Border.all(color: statusColor.withValues(alpha: 0.3), width: 3),
            ),
            child: Center(
              child: Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: statusColor,
                  boxShadow: [
                    BoxShadow(
                      color: statusColor.withValues(alpha: 0.4),
                      blurRadius: 14,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Icon(
                  statusIcon,
                  color: Colors.white,
                  size: 34,
                ),
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Status label
          Text(
            statusTitle,
            style: TextStyle(
              fontSize: 32,
              fontWeight: FontWeight.w900,
              letterSpacing: 2.0,
              color: statusColor,
            ),
          ),
          const SizedBox(height: 8),

          // Status description message
          Text(
            statusMessage,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: isVacant ? AppColors.vacantDark : AppColors.occupiedDark,
            ),
          ),
        ],
      ),
    );
  }
}
