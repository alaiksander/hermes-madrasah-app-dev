import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Pengaturan Scanner QR & Hemat Daya (admin madrasah):
/// mode daya (standar/hemat/ekstrim) + idle sleep + jendela aktif.
class ScanPowerScreen extends StatefulWidget {
  const ScanPowerScreen({super.key});

  @override
  State<ScanPowerScreen> createState() => _ScanPowerScreenState();
}

class _ScanPowerScreenState extends State<ScanPowerScreen> {
  bool _loading = true;
  bool _busy = false;

  String _mode = 'standar';
  int _idleMenit = 5;
  int _aktifDetik = 30;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final res = await context.read<AuthState>().api.get('/api/pengaturan');
      if (!mounted) return;
      setState(() {
        _mode = res['scan_mode'] as String? ?? 'standar';
        _idleMenit = res['scan_idle_menit'] as int? ?? 5;
        _aktifDetik = res['scan_aktif_detik'] as int? ?? 30;
        _loading = false;
      });
    } on ApiException catch (e) {
      _snack(e.message, error: true);
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg),
        backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
      ));
  }

  Future<void> _simpan() async {
    setState(() => _busy = true);
    try {
      await context.read<AuthState>().api.put('/api/pengaturan', {
        'scan_mode': _mode,
        'scan_idle_menit': _idleMenit,
        'scan_aktif_detik': _aktifDetik,
      });
      _snack('Setelan scanner disimpan');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _deskripsiMode(String m) {
    switch (m) {
      case 'hemat':
        return 'Kamera mati otomatis jika tidak ada scan $_idleMenit menit. '
            'Ketuk layar untuk menyalakan kembali.';
      case 'ekstrim':
        return 'Kamera mati secara default. Guru mengetuk tombol '
            '"Aktifkan Scanner" untuk menyalakan $_aktifDetik detik. '
            'Hemat baterai maksimal.';
      default:
        return 'Kamera menyala terus selama layar scan terbuka. '
            'Paling boros baterai, cocok untuk gerbang ramai.';
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scanner QR & Hemat Daya',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        actions: [
          IconButton.filledTonal(
            tooltip: 'Simpan',
            onPressed: _busy || _loading ? null : _simpan,
            icon: const Icon(Icons.check),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // ── Mode daya ──
                const Text('Mode Daya Scanner',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                const SizedBox(height: 10),
                Card(
                  child: RadioGroup<String>(
                    groupValue: _mode,
                    onChanged: (String? v) {
                      if (_busy || v == null) return;
                      setState(() => _mode = v);
                    },
                    child: const Column(
                      children: [
                        RadioListTile<String>(
                          value: 'standar',
                          title: Text('Standar'),
                          subtitle: Text('Kamera menyala terus (perilaku lama)'),
                        ),
                        RadioListTile<String>(
                          value: 'hemat',
                          title: Text('Hemat'),
                          subtitle: Text('Kamera mati saat menganggur — ketuk untuk nyala'),
                        ),
                        RadioListTile<String>(
                          value: 'ekstrim',
                          title: Text('Ekstrim'),
                          subtitle: Text('Kamera mati default — aktif per permintaan'),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: scheme.secondaryContainer.withValues(alpha: 0.4),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(_deskripsiMode(_mode),
                      style: TextStyle(fontSize: 13, color: scheme.onSurface)),
                ),
                const SizedBox(height: 20),
                // ── Idle sleep (mode hemat) ──
                Card(
                  child: ListTile(
                    enabled: !_busy,
                    leading: Icon(Icons.bedtime_outlined, color: scheme.primary),
                    title: const Text('Idle Sleep (Hemat)'),
                    subtitle: Text(
                        'Kamera mati setelah $_idleMenit menit tanpa scan'),
                    trailing: DropdownButton<int>(
                      value: _idleMenit,
                      underline: const SizedBox.shrink(),
                      items: [2, 5, 10, 15]
                          .map((m) => DropdownMenuItem(value: m, child: Text('$m mnt')))
                          .toList(),
                      onChanged: _busy
                          ? null
                          : (v) => setState(() => _idleMenit = v ?? 5),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                // ── Jendela aktif (mode ekstrim) ──
                Card(
                  child: ListTile(
                    enabled: !_busy,
                    leading: Icon(Icons.timer_outlined, color: scheme.primary),
                    title: const Text('Jendela Aktif (Ekstrim)'),
                    subtitle: Text(
                        'Kamera nyala selama $_aktifDetik detik per aktivasi'),
                    trailing: DropdownButton<int>(
                      value: _aktifDetik,
                      underline: const SizedBox.shrink(),
                      items: [15, 30, 60]
                          .map((s) => DropdownMenuItem(value: s, child: Text('$s dtk')))
                          .toList(),
                      onChanged: _busy
                          ? null
                          : (v) => setState(() => _aktifDetik = v ?? 30),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: _busy ? null : _simpan,
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('Simpan Setelan'),
                ),
                const SizedBox(height: 10),
                Text(
                  'Setelan berlaku untuk layar Scanner QR yang dibuka guru '
                  'di madrasah ini.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                ),
              ],
            ),
    );
  }
}
