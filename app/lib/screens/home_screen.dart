import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../services/auth_state.dart';
import 'absen_kelas_screen.dart';
import 'kelola_screen.dart';
import 'manual_screen.dart';
import 'pengaturan_screen.dart';
import 'rekap_screen.dart';
import 'scan_screen.dart';
import 'super_admin_screen.dart';
import 'super_admin_settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final scheme = Theme.of(context).colorScheme;

    // ── Super Admin: panel kelola seluruh madrasah ──
    if (auth.isSuperAdmin) {
      return Scaffold(
        appBar: AppBar(
          title: Column(
            children: [
              const Text('Super Admin — Platform',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              if (auth.nama != null)
                Text(auth.nama!,
                    style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Pengaturan',
              icon: const Icon(Icons.settings_outlined),
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const SuperAdminSettingsScreen()),
              ),
            ),
            IconButton(
              tooltip: 'Keluar',
              icon: const Icon(Icons.logout),
              onPressed: () {
                context.read<AuthState>().logout();
                goToLogin(context);
              },
            ),
          ],
        ),
        body: const SuperAdminScreen(),
      );
    }

    // Tab Kelola mung kanggo admin
    final tabs = <Widget>[
      const ScanScreen(),
      const ManualScreen(),
      const AbsenKelasScreen(),
      const RekapScreen(),
      if (auth.isAdmin) const KelolaScreen(),
    ];
    final destinations = <NavigationDestination>[
      const NavigationDestination(
        icon: Icon(Icons.qr_code_scanner_outlined),
        selectedIcon: Icon(Icons.qr_code_scanner),
        label: 'Scan',
      ),
      const NavigationDestination(
        icon: Icon(Icons.manage_search_outlined),
        selectedIcon: Icon(Icons.manage_search),
        label: 'Cari',
      ),
      const NavigationDestination(
        icon: Icon(Icons.groups_outlined),
        selectedIcon: Icon(Icons.groups),
        label: 'Absen Kelas',
      ),
      const NavigationDestination(
        icon: Icon(Icons.bar_chart_outlined),
        selectedIcon: Icon(Icons.bar_chart),
        label: 'Rekap',
      ),
      if (auth.isAdmin)
        const NavigationDestination(
          icon: Icon(Icons.admin_panel_settings_outlined),
          selectedIcon: Icon(Icons.admin_panel_settings),
          label: 'Kelola',
        ),
    ];
    final idx = _index.clamp(0, tabs.length - 1);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          children: [
            Text(auth.tenantNama ?? 'Aplikasi Madrasah',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
            if (auth.nama != null)
              Text('${auth.nama} • ${auth.role == 'admin' ? 'Admin' : 'Guru'}',
                  style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          ],
        ),
        actions: [
          if (auth.isAdmin)
            IconButton(
              tooltip: 'Pengaturan',
              icon: const Icon(Icons.settings_outlined),
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const PengaturanScreen()),
              ),
            ),
          IconButton(
            tooltip: 'Keluar',
            icon: const Icon(Icons.logout),
            onPressed: () {
              context.read<AuthState>().logout();
              goToLogin(context);
            },
          ),
        ],
      ),
      body: tabs[idx],
      bottomNavigationBar: NavigationBar(
        selectedIndex: idx,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: destinations,
      ),
    );
  }
}
