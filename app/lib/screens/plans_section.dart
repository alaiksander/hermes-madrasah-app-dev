import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Paket & kuota: definisi plan (free/pilot/pro) lan batasane.
class PlansSection extends StatefulWidget {
  const PlansSection({super.key});

  @override
  State<PlansSection> createState() => _PlansSectionState();
}

class _PlansSectionState extends State<PlansSection> {
  List<dynamic> _plans = [];
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final res = await context.read<AuthState>().api.get('/api/super/plans');
      if (mounted) setState(() => _plans = res as List);
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Future<void> _form(Map<String, dynamic>? p) async {
    final nama = TextEditingController(text: p?['nama'] ?? '');
    final label = TextEditingController(text: p?['label'] ?? '');
    final maxMurid = TextEditingController(
        text: p?['max_murid']?.toString() ?? '');
    final maxGuru = TextEditingController(
        text: p?['max_guru']?.toString() ?? '');
    final fitur = TextEditingController(
        text: (p?['fitur'] as List? ?? []).join(', '));

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: Text(p == null ? 'Tambah Paket' : 'Edit Paket'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nama,
                  enabled: p == null,
                  decoration: const InputDecoration(labelText: 'Nama plan (kode)'),
                ),
                const SizedBox(height: 8),
                TextField(
                    controller: label,
                    decoration: const InputDecoration(labelText: 'Label (Free / Pilot / Pro)')),
                const SizedBox(height: 8),
                TextField(
                  controller: maxMurid,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                      labelText: 'Max murid (kosongkan = tanpa batas)'),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: maxGuru,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                      labelText: 'Max guru (kosongkan = tanpa batas)'),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: fitur,
                  decoration: const InputDecoration(
                      labelText: 'Fitur (pisah koma)', isDense: true),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Simpan')),
          ],
        ),
      ),
    );
    if (ok != true || !mounted) return;

    int? murid = int.tryParse(maxMurid.text.trim());
    int? guru = int.tryParse(maxGuru.text.trim());
    final body = {
      'label': label.text.trim(),
      'max_murid': murid,
      'max_guru': guru,
      'fitur': fitur.text.split(',').map((f) => f.trim()).where((f) => f.isNotEmpty).toList(),
    };
    setState(() => _busy = true);
    try {
      if (p == null) {
        await context.read<AuthState>().api.post('/api/super/plans', {
          'nama': nama.text.trim().toLowerCase(),
          ...body,
        });
        _snack('Paket ditambahkan');
      } else {
        await context.read<AuthState>().api.patch('/api/super/plans/${p['id']}', body);
        _snack('Paket diperbarui');
      }
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _hapus(Map<String, dynamic> p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Hapus Paket ${p['label']}?'),
        content: const Text('Hanya bisa jika tidak ada madrasah yang menggunakan paket ini.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Hapus'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await context.read<AuthState>().api.delete('/api/super/plans/${p['id']}');
      _snack('Paket dibusak');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
            child: Row(
              children: [
                CircleAvatar(
                  backgroundColor: scheme.primary.withValues(alpha: 0.12),
                  child: Icon(Icons.workspace_premium_outlined, color: scheme.primary),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text('Paket & Kuota',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
                IconButton.filledTonal(
                  tooltip: 'Tambah Paket',
                  onPressed: _busy ? null : () => _form(null),
                  icon: const Icon(Icons.add),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          for (final p in _plans)
            ListTile(
              dense: true,
              leading: Text('${p['label'] ?? p['nama']}',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              title: Text(
                'murid: ${p['max_murid'] ?? '∞'} • guru: ${p['max_guru'] ?? '∞'}',
                style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant),
              ),
              subtitle: (p['fitur'] as List? ?? []).isEmpty
                  ? null
                  : Text((p['fitur'] as List).join(' • '),
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 11.5)),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    tooltip: 'Edit',
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    onPressed: _busy ? null : () => _form(p),
                  ),
                  IconButton(
                    tooltip: 'Hapus',
                    icon: Icon(Icons.delete_outline, size: 18, color: scheme.error),
                    onPressed: _busy ? null : () => _hapus(p),
                  ),
                ],
              ),
            ),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 4, 16, 12),
            child: Text(
              'Kuota murid dipakai otomatis saat membuat madrasah baru '
              'sesuai paketnya (bisa diatur manual per madrasah).',
              style: TextStyle(fontSize: 11.5),
            ),
          ),
        ],
      ),
    );
  }
}
