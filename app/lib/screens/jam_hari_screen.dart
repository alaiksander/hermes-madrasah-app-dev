import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Pengaturan Jam Masuk/Pulang + Hari Aktif (admin).
class JamHariScreen extends StatefulWidget {
  const JamHariScreen({super.key});

  @override
  State<JamHariScreen> createState() => _JamHariScreenState();
}

class _JamHariScreenState extends State<JamHariScreen> {
  static const _namaHari = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'];

  bool _loading = true;
  bool _saving = false;
  String _jamMasuk = '07:00';
  String _jamPulang = '13:30';
  final Set<int> _hariAktif = {1, 2, 3, 4, 5};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final res = await context.read<AuthState>().api.get('/api/pengaturan');
      if (!mounted) return;
      setState(() {
        _jamMasuk = (res['jam_masuk'] as String?) ?? '07:00';
        _jamPulang = (res['jam_pulang'] as String?) ?? '13:30';
        _hariAktif
          ..clear()
          ..addAll((res['hari_aktif'] as List? ?? [1, 2, 3, 4, 5]).cast<int>());
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

  Future<void> _pickJam(bool pulang) async {
    final current = pulang ? _jamPulang : _jamMasuk;
    final parts = current.split(':');
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(
        hour: int.tryParse(parts[0]) ?? 7,
        minute: int.tryParse(parts[1]) ?? 0,
      ),
      helpText: pulang ? 'Pilih Jam Pulang' : 'Pilih Jam Masuk',
      builder: (ctx, child) => MediaQuery(
        data: MediaQuery.of(ctx).copyWith(alwaysUse24HourFormat: true),
        child: child!,
      ),
    );
    if (picked != null && mounted) {
      setState(() {
        final v = '${picked.hour.toString().padLeft(2, '0')}:'
            '${picked.minute.toString().padLeft(2, '0')}';
        if (pulang) {
          _jamPulang = v;
        } else {
          _jamMasuk = v;
        }
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await context.read<AuthState>().api.put('/api/pengaturan', {
        'jam_masuk': _jamMasuk,
        'jam_pulang': _jamPulang,
        'hari_aktif': _hariAktif.toList()..sort(),
      });
      if (mounted) _snack('Jam & hari aktif disimpan ✅');
    } on ApiException catch (e) {
      if (mounted) _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
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

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Jam & Hari Aktif',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: const Icon(Icons.login),
                        title: const Text('Jam Masuk'),
                        subtitle: Text('Absen di atas jam ini = ditandai telat',
                            style: TextStyle(
                                fontSize: 12, color: scheme.onSurfaceVariant)),
                        trailing: Text(_jamMasuk,
                            style: const TextStyle(
                                fontSize: 20, fontWeight: FontWeight.w700)),
                        onTap: () => _pickJam(false),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: const Icon(Icons.logout),
                        title: const Text('Jam Pulang'),
                        subtitle: Text('Informasi jadwal pulang madrasah',
                            style: TextStyle(
                                fontSize: 12, color: scheme.onSurfaceVariant)),
                        trailing: Text(_jamPulang,
                            style: const TextStyle(
                                fontSize: 20, fontWeight: FontWeight.w700)),
                        onTap: () => _pickJam(true),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                Text('Hari Aktif',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (var i = 0; i < 7; i++)
                              FilterChip(
                                label: Text(_namaHari[i]),
                                selected: _hariAktif.contains(i + 1),
                                onSelected: (v) => setState(() {
                                  if (v) {
                                    _hariAktif.add(i + 1);
                                  } else {
                                    _hariAktif.remove(i + 1);
                                  }
                                }),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: scheme.primaryContainer.withValues(alpha: 0.5),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            'Hari aktif: $_previewHari',
                            style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: scheme.onPrimaryContainer),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Hari non-aktif = hari yang tidak dipilih (absen ditolak)',
                          style: TextStyle(
                              fontSize: 12, color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: _saving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.save_outlined),
                  label: Text(_saving ? 'Menyimpan…' : 'Simpan'),
                ),
              ],
            ),
    );
  }
}
