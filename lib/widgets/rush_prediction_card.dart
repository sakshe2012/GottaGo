import 'package:flutter/material.dart';
import '../models/washroom_status.dart';
import '../utils/app_colors.dart';

/// Card showing the ML predicted washroom rush level (LOW, MEDIUM, HIGH, UNAVAILABLE)
/// along with actual calibrated probability percentages.
class RushPredictionCard extends StatelessWidget {
  final RushLevel level;
  final Map<String, double>? probabilities;
  final String? note;

  const RushPredictionCard({
    super.key,
    required this.level,
    this.probabilities,
    this.note,
  });

  Color get levelColor {
    switch (level) {
      case RushLevel.low:
        return AppColors.rushLow;
      case RushLevel.medium:
        return AppColors.rushMedium;
      case RushLevel.high:
        return AppColors.rushHigh;
      case RushLevel.unavailable:
        return AppColors.rushUnavailable;
    }
  }

  Color get levelBgColor {
    switch (level) {
      case RushLevel.low:
        return AppColors.rushLowLight;
      case RushLevel.medium:
        return AppColors.rushMediumLight;
      case RushLevel.high:
        return AppColors.rushHighLight;
      case RushLevel.unavailable:
        return AppColors.rushUnavailableLight;
    }
  }

  Color get levelBorderColor {
    switch (level) {
      case RushLevel.low:
        return AppColors.rushLowBorder;
      case RushLevel.medium:
        return AppColors.rushMediumBorder;
      case RushLevel.high:
        return AppColors.rushHighBorder;
      case RushLevel.unavailable:
        return AppColors.rushUnavailableBorder;
    }
  }

  String get levelLabel {
    switch (level) {
      case RushLevel.low:
        return 'LOW';
      case RushLevel.medium:
        return 'MEDIUM';
      case RushLevel.high:
        return 'HIGH';
      case RushLevel.unavailable:
        return 'UNAVAILABLE';
    }
  }

  IconData get levelIcon {
    switch (level) {
      case RushLevel.low:
        return Icons.trending_down_rounded;
      case RushLevel.medium:
        return Icons.trending_flat_rounded;
      case RushLevel.high:
        return Icons.trending_up_rounded;
      case RushLevel.unavailable:
        return Icons.info_outline_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasValidProbabilities =
        level != RushLevel.unavailable &&
        probabilities != null &&
        probabilities!.isNotEmpty;

    return Container(
      padding: const EdgeInsets.all(18),
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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.primaryLight,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  color: AppColors.primary,
                  size: 22,
                ),
              ),
              // Segmented visual rush bars
              Row(
                children: [
                  _buildLevelDot(RushLevel.low),
                  const SizedBox(width: 4),
                  _buildLevelDot(RushLevel.medium),
                  const SizedBox(width: 4),
                  _buildLevelDot(RushLevel.high),
                ],
              ),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: levelBgColor,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: levelBorderColor),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      levelIcon,
                      size: 16,
                      color: levelColor,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      levelLabel,
                      style: TextStyle(
                        fontSize: level == RushLevel.unavailable ? 12 : 16,
                        fontWeight: FontWeight.w800,
                        color: levelColor,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'AI-powered rush prediction',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: AppColors.textSecondary,
            ),
          ),
          if (hasValidProbabilities) ...[
            const SizedBox(height: 10),
            _buildProbabilitiesRow(),
          ] else if (note != null && note!.isNotEmpty && level == RushLevel.unavailable) ...[
            const SizedBox(height: 8),
            Text(
              note!,
              style: const TextStyle(
                fontSize: 10,
                fontStyle: FontStyle.italic,
                color: AppColors.textSecondary,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildProbabilitiesRow() {
    final lowPct = ((probabilities?['LOW'] ?? 0.0) * 100).toStringAsFixed(0);
    final medPct = ((probabilities?['MEDIUM'] ?? 0.0) * 100).toStringAsFixed(0);
    final highPct = ((probabilities?['HIGH'] ?? 0.0) * 100).toStringAsFixed(0);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.cardBorder),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _buildProbItem('L', '$lowPct%', AppColors.rushLow),
          _buildDivider(),
          _buildProbItem('M', '$medPct%', AppColors.rushMedium),
          _buildDivider(),
          _buildProbItem('H', '$highPct%', AppColors.rushHigh),
        ],
      ),
    );
  }

  Widget _buildProbItem(String label, String value, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$label:',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
        const SizedBox(width: 2),
        Text(
          value,
          style: const TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }

  Widget _buildDivider() {
    return Container(
      height: 10,
      width: 1,
      color: AppColors.cardBorder,
    );
  }

  Widget _buildLevelDot(RushLevel dotLevel) {
    final isActive =
        level != RushLevel.unavailable && level.index >= dotLevel.index;
    Color dotColor = Colors.grey.shade300;
    if (isActive) {
      if (dotLevel == RushLevel.low) dotColor = AppColors.rushLow;
      if (dotLevel == RushLevel.medium) dotColor = AppColors.rushMedium;
      if (dotLevel == RushLevel.high) dotColor = AppColors.rushHigh;
    }

    return Container(
      width: 14,
      height: 6,
      decoration: BoxDecoration(
        color: dotColor,
        borderRadius: BorderRadius.circular(3),
      ),
    );
  }
}
