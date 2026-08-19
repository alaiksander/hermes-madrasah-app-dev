import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Kelola Tahun Ajaran (admin): tambah, jadikan aktif, hapus.
class TahunAjaranScreen extends StatefulWidget {
  const TahunAjaranScreen({super.key});

  @override
  State<TahunAjaranScreen> createState() => _TahunAjaranScreenState();
}

class _TahunAjaranScreenState extends State<TahunAjaranScreen> {
  List<dynamic> _tahun = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final tahun = await context.read<AuthState>().api.get('/api/tahun-ajaran');
      if (mounted) setState(() => _tahun = tahun as List);
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

  String _fmtTgl(DateTime d) => '${d.year}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  String _tglLabel(String? iso) {
    if (iso == null || iso.length < 10) return '-';
    final p = iso.split('-');
    return '${p[2]}/${p[1]}/${p[0]}';
  }

  Future<void> _tambah() async {
    final nama = TextEditingController();
    var mulai = DateTime(2026, 7, 1);
    var selesai = DateTime(2027, 6, 30);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Tambah Tahun Ajaran'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nama,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Nama Tahun Ajaran',
                  hintText: 'contoh: 2026/2027',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
              ),
              const SizedBox(height: 10),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event),
                title: const Text('Tanggal Mulai'),
                subtitle: Text(_fmtTgl(mulai)),
                onTap: () async {
                  final p = await showDatePicker(
                    context: ctx,
                    initialDate: mulai,
                    firstDate: DateTime(2020),
                    lastDate: DateTime(2035),
                  );
                  if (p != null && ctx.mounted) setLocal(() => mulai = p);
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event_available),
                title: const Text('Tanggal Selesai'),
                subtitle: Text(_fmtTgl(selesai)),
                onTap: () async {
                  final p = await showDatePicker(
                    context: ctx,
                    initialDate: selesai,
                    firstDate: DateTime(2020),
                    lastDate: DateTime(2035),
                  );
                  if (p != null && ctx.mounted) setLocal(() => selesai = p);
                },
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Batal')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Simpan')),
          ],
        ),
      ),
    );
    if (ok != true || nama.text.trim().isEmpty) return;
    if (!mounted) return;
    try {
      await context.read<AuthState>().api.post('/api/tahun-ajaran', {
        'nama': nama.text.trim(),
        'tanggal_mulai': _fmtTgl(mulai),
        'tanggal_selesai': _fmtTgl(selesai),
      });
      _snack('Tahun ajaran ditambahkan & diaktifkan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _setAktif(dynamic t) async {
    try {
      await context.read<AuthState>().api
          .patch('/api/tahun-ajaran/${t['id']}', {'is_active': true});
      _snack('${t['nama']} dijadikan tahun aktif');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _hapus(dynamic t) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Hapus Tahun Ajaran?'),
        content: Text('${t['nama']} akan dihapus permanen.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Hapus'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;
    try {
      await context.read<AuthState>().api.delete('/api/tahun-ajaran/${t['id']}');
      _snack('Tahun ajaran dihapus');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tahun Ajaran',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        actions: [
          IconButton.filledTonal(
            tooltip: 'Tambah Tahun Ajaran',
            onPressed: _loading ? null : _tambah,
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_tahun.isEmpty)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Center(
                          child: Text('Belum ada tahun ajaran',
                              style: TextStyle(color: scheme.onSurfaceVariant)),
                        ),
                      ),
                    )
                  else
                    Card(
                      child: Column(
                        children: [
                          for (final t in _tahun)
                            ListTile(
                              leading: Icon(
                                t['is_active'] == true
                                    ? Icons.check_circle
                                    : Icons.calendar_month_outlined,
                                color: t['is_active'] == true
                                    ? const Color(0xFF16A34A)
                                    : scheme.onSurfaceVariant,
                              ),
                              title: Text('${t['nama']}',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w600)),
                              subtitle: Text(
                                  '${_tglLabel(t['tanggal_mulai'])} – '
                                  '${_tglLabel(t['tanggal_selesai'])} • '
                                  '${t['jumlah_kelas'] ?? 0} kelas'),
                              trailing: PopupMenuButton<String>(
                                tooltip: 'Menu',
                                onSelected: (v) => switch (v) {
                                  'aktif' => _setAktif(t),
                                  _ => _hapus(t),
                                },
                                itemBuilder: (_) => [
                                  if (t['is_active'] != true)
                                    const PopupMenuItem(
                                      value: 'aktif',
                                      child: ListTile(
                                        leading: Icon(Icons.check_circle_outline),
                                        title: Text('Jadikan Aktif'),
                                        dense: true,
                                      ),
                                    ),
                                  PopupMenuItem(
                                    value: 'hapus',
                                    child: ListTile(
                                      leading: Icon(Icons.delete_outline,
                                          color: scheme.error),
                                      title: Text('Hapus',
                                          style: TextStyle(color: scheme.error)),
                                      dense: true,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 12),
                  Text(
                    'Tahun ajaran aktif digunakan untuk kelas & dropdown '
                    'di Kelas & Murid. Murid tetap ada di tahun lama '
                    'sampai dipindah melalui "Naik Kelas".',
                    style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
    );
  }
}
