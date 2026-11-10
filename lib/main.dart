import 'package:flutter/material.dart';
import 'screens/main_navigation_screen.dart';
import 'services/api_service.dart';
import 'utils/app_colors.dart';
import 'utils/constants.dart';

void main() {
  runApp(const GottaGoApp());
}

class GottaGoApp extends StatelessWidget {
  final bool? startInDemoMode;
  final ApiService? apiService;

  const GottaGoApp({
    super.key,
    this.startInDemoMode,
    this.apiService,
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: AppColors.background,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.primary,
          primary: AppColors.primary,
          surface: AppColors.surface,
          brightness: Brightness.light,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.surface,
          foregroundColor: AppColors.textPrimary,
          elevation: 0,
        ),
      ),
      home: MainNavigationScreen(
        startInDemoMode: startInDemoMode,
        apiService: apiService,
      ),
    );
  }
}
