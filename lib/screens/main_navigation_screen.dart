import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../utils/app_colors.dart';
import 'home_screen.dart';
import 'nearby_screen.dart';

/// Root navigation screen hosting the existing Live Monitor and the new Nearby Washrooms screen.
class MainNavigationScreen extends StatefulWidget {
  final bool? startInDemoMode;
  final ApiService? apiService;

  const MainNavigationScreen({
    super.key,
    this.startInDemoMode,
    this.apiService,
  });

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: [
          // Tab 0: Preserved Live Monitoring Dashboard
          HomeScreen(
            startInDemoMode: widget.startInDemoMode,
            apiService: widget.apiService,
          ),
          // Tab 1: Nearby Washroom Discovery & OpenStreetMap
          NearbyScreen(
            apiService: widget.apiService,
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        backgroundColor: AppColors.surface,
        indicatorColor: AppColors.primary.withValues(alpha: 0.18),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.sensors_outlined),
            selectedIcon: Icon(Icons.sensors_rounded, color: AppColors.primary),
            label: 'Live Monitor',
          ),
          NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map_rounded, color: AppColors.primary),
            label: 'Nearby Washrooms',
          ),
        ],
      ),
    );
  }
}
