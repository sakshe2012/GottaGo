import 'package:flutter/material.dart';

/// Semantic colors for the GottaGo smart washroom design system
class AppColors {
  // Brand & Accents
  static const Color primary = Color(0xFF2563EB); // Royal Blue
  static const Color primaryDark = Color(0xFF1D4ED8);
  static const Color primaryLight = Color(0xFFEFF6FF);

  // Status: Vacant (Emerald Green)
  static const Color vacant = Color(0xFF10B981);
  static const Color vacantDark = Color(0xFF047857);
  static const Color vacantLight = Color(0xFFECFDF5);
  static const Color vacantBorder = Color(0xFFA7F3D0);

  // Status: Occupied (Crimson Red)
  static const Color occupied = Color(0xFFEF4444);
  static const Color occupiedDark = Color(0xFFB91C1C);
  static const Color occupiedLight = Color(0xFFFEF2F2);
  static const Color occupiedBorder = Color(0xFFFECACA);

  // Rush Levels
  static const Color rushLow = Color(0xFF10B981);
  static const Color rushLowLight = Color(0xFFECFDF5);
  static const Color rushLowBorder = Color(0xFFA7F3D0);

  static const Color rushMedium = Color(0xFFF59E0B);
  static const Color rushMediumLight = Color(0xFFFFFBEB);
  static const Color rushMediumBorder = Color(0xFFFDE68A);

  static const Color rushHigh = Color(0xFFEF4444);
  static const Color rushHighLight = Color(0xFFFEF2F2);
  static const Color rushHighBorder = Color(0xFFFECACA);

  // Neutral Background & Surfaces
  static const Color background = Color(0xFFF8FAFC);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color cardBorder = Color(0xFFE2E8F0);
  static const Color divider = Color(0xFFF1F5F9);

  // Typography
  static const Color textPrimary = Color(0xFF0F172A);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textMuted = Color(0xFF94A3B8);

  // Demo Badge
  static const Color demoBadgeBg = Color(0xFFFEF3C7);
  static const Color demoBadgeText = Color(0xFF92400E);
  static const Color demoBadgeBorder = Color(0xFFFCD34D);

  // Live Mode Badge
  static const Color liveBadgeBg = Color(0xFFECFDF5);
  static const Color liveBadgeText = Color(0xFF047857);
  static const Color liveBadgeBorder = Color(0xFFA7F3D0);

  // Offline / Warning Badges
  static const Color offlineBadgeBg = Color(0xFFFEF2F2);
  static const Color offlineBadgeText = Color(0xFFB91C1C);
  static const Color offlineBadgeBorder = Color(0xFFFECACA);

  static const Color warningBadgeBg = Color(0xFFFFFBEB);
  static const Color warningBadgeText = Color(0xFFB45309);
  static const Color warningBadgeBorder = Color(0xFFFDE68A);

  // Rush Level: Unavailable / Idle
  static const Color rushUnavailable = Color(0xFF64748B);
  static const Color rushUnavailableLight = Color(0xFFF1F5F9);
  static const Color rushUnavailableBorder = Color(0xFFCBD5E1);
}
