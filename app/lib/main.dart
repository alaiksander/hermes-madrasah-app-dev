import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/super_admin_login_screen.dart';
import 'services/api.dart';
import 'services/auth_state.dart';

void main() {
  runApp(MadrasahApp(api: ApiClient(apiBaseUrl)));
}

class MadrasahApp extends StatelessWidget {
  final ApiClient api;

  const MadrasahApp({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AuthState(api),
      child: MaterialApp(
        title: 'Aplikasi Madrasah',
        debugShowCheckedModeBanner: false,
        theme: _buildTheme(),
        // URL /madrasah/#/superadmin → langsung halaman login super admin
        initialRoute: '/',
        routes: {
          '/': (_) => const LoginScreen(),
          '/superadmin': (_) => const SuperAdminLoginScreen(),
        },
      ),
    );
  }

  ThemeData _buildTheme() {
    final scheme = ColorScheme.fromSeed(seedColor: const Color(0xFF00897B));
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
        centerTitle: true,
        backgroundColor: scheme.surface,
        elevation: 0,
        titleTextStyle: TextStyle(
          color: scheme.onSurface,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(64, 48),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        indicatorColor: scheme.primaryContainer,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      ),
    );
  }
}

/// Navigasi antar halaman utama (dipakai ing HomeScreen).
void goToHome(BuildContext context) {
  Navigator.of(context).pushAndRemoveUntil(
    MaterialPageRoute(builder: (_) => const HomeScreen()),
    (route) => false,
  );
}

void goToLogin(BuildContext context) {
  Navigator.of(context).pushAndRemoveUntil(
    MaterialPageRoute(builder: (_) => const LoginScreen()),
    (route) => false,
  );
}
