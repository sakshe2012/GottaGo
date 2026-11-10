import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gottago/main.dart';

void main() {
  testWidgets('GottaGo home screen loads with initial demo data',
      (WidgetTester tester) async {
    await tester.pumpWidget(const GottaGoApp());

    // Verify header elements
    expect(find.text('GottaGo'), findsOneWidget);
    expect(find.text('Smart Washroom Availability'), findsOneWidget);
    expect(find.text('DEMO MODE'), findsWidgets);

    // Verify occupancy card
    expect(find.text('VACANT'), findsOneWidget);
    expect(find.text('Washroom is available'), findsOneWidget);

    // Verify people inside card
    expect(find.text('People inside'), findsOneWidget);
    expect(find.text('0'), findsOneWidget);

    // Verify AI predicted rush card
    expect(find.text('AI-powered rush prediction'), findsOneWidget);
    expect(find.text('LOW'), findsOneWidget);

    // Verify system status
    expect(find.text('ESP32 Sensor Unit'), findsOneWidget);
    expect(find.text('FastAPI Backend'), findsOneWidget);
  });

  testWidgets('GottaGo demo simulator toggles OCCUPIED state and updates cards',
      (WidgetTester tester) async {
    // Provide a phone-sized viewport height for testing scrollable dashboard
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(const GottaGoApp());

    // Tap on Occupied (1 inside, Med rush) chip
    final occupiedMedChip = find.text('Occupied (1 inside, Med rush)');
    await tester.ensureVisible(occupiedMedChip);
    await tester.tap(occupiedMedChip);
    await tester.pumpAndSettle();

    // Verify state changed to OCCUPIED
    expect(find.text('OCCUPIED'), findsOneWidget);
    expect(find.text('Washroom is currently in use'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.text('MEDIUM'), findsOneWidget);

    // Tap on Occupied (2 inside, High rush) chip
    final occupiedHighChip = find.text('Occupied (2 inside, High rush)');
    await tester.ensureVisible(occupiedHighChip);
    await tester.tap(occupiedHighChip);
    await tester.pumpAndSettle();

    // Verify state changed to 2 people, HIGH rush
    expect(find.text('OCCUPIED'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('HIGH'), findsOneWidget);

    // Tap back to Vacant
    final vacantChip = find.text('Vacant (0 inside, Low rush)');
    await tester.ensureVisible(vacantChip);
    await tester.tap(vacantChip);
    await tester.pumpAndSettle();

    // Verify returned to VACANT
    expect(find.text('VACANT'), findsOneWidget);
    expect(find.text('Washroom is available'), findsOneWidget);
    expect(find.text('0'), findsOneWidget);
    expect(find.text('LOW'), findsOneWidget);
  });
}
