import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import 'jam_hari_screen.dart';
import 'scan_power_screen.dart';
import 'tahun_ajaran_screen.dart';

/// Pengaturan Madrasah (admin) — menu kartu.
/// Saben entri diklik → mbukak settingane dhewe.
class PengaturanScreen extends StatefulWidget {
  const PengaturanScreen({super.key});

  @override
  State<PengaturanScreen> createState() => _PengaturanScreenState();
}

class _PengaturanScreenState extends State<PengaturanScreen> {
  static const _namaHari = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'];

  bool _loading = true;
  String _jamMasuk = '07:00';
  String _jamPulang = '13:30';
  List<int> _hariAktif = [1, 2, 3, 4, 5];
  List<dynamic> _tahun = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final res = await api.get('/api/pengaturan');
      List<dynamic> tahun = [];
      try {
        tahun = await api.get('/api/tahun-ajaran') as List;
      } catch (_) {/* tahun optional */}
      if (!mounted) return;
      setState(() {
        _jamMasuk = (res['jam_masuk'] as String?) ?? '07:00';
        _jamPulang = (res['jam_pulang'] as String?) ?? '13:30';
        _hariAktif = (res['hari_aktif'] as List? ?? [1, 2, 3, 4, 5]).cast<int>();
        _tahun = tahun;
      });
    } on ApiException catch (e) {
      if (mounted) _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg),
        backgroundColor: error ? Colors.red.shade700 : null,
      ));
  }

  String get _previewHari {
    final aktif = _namaHari
        .asMap()
        .entries
        .where((e) => _hariAktif.contains(e.key + 1))
        .map((e) => e.value)
        .join(', ');
    return aktif.isEmpty ? 'Tidak ada hari aktif' : aktif;
  }

  Widget _entry(
      {required IconData icon,
      required Color color,
      required String title,
      required String subtitle,
      required Widget screen}) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(icon, color: color),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
                fontSize: 12.5, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => screen),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final aktif = _tahun.where((t) => t['is_active'] == true).toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pengaturan Madrasah',
            style: TextStyle(fontWeight: FontWeight.w700)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _entry(
                    icon: Icons.access_time_filled,
                    color: const Color(0xFF2563EB),
                    title: 'Jam & Hari Aktif',
                    subtitle:
                        'Masuk $_jamMasuk • Pulang $_jamPulang • $_previewHari',
                    screen: const JamHariScreen(),
                  ),
                  _entry(
                    icon: Icons.calendar_month_outlined,
                    color: const Color(0xFF16A34A),
                    title: 'Tahun Ajaran',
                    subtitle: aktif.isNotEmpty
                        ? '${_tahun.length} taun • aktif: ${aktif.first['nama']}'
                        : '${_tahun.length} taun • durung ana sing aktif',
                    screen: const TahunAjaranScreen(),
                  ),
                  _entry(
                    icon: Icons.qr_code_scanner,
                    color: const Color(0xFFD97706),
                    title: 'Scanner QR & Hemat Daya',
                    subtitle:
                        'Mode daya scanner: standar / hemat / ekstrim (piket)',
                    screen: const ScanPowerScreen(),
                  ),
                ],
              ),
            ),
    );
  }
}
