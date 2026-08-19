import 'package:flutter_test/flutter_test.dart';

import 'package:madrasah_app/main.dart';
import 'package:madrasah_app/services/api.dart';

void main() {
  testWidgets('Login screen renders', (tester) async {
    await tester.pumpWidget(MadrasahApp(api: ApiClient('http://localhost')));
    expect(find.text('Aplikasi Madrasah'), findsOneWidget);
    expect(find.text('Kode Madrasah'), findsOneWidget);
  });
}
