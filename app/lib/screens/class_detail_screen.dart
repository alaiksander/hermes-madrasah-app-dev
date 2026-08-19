import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import 'lulus_kelas_view.dart';
import 'murid_tab.dart';

/// Detail Kelas: info kelas + kelola murid + luluskan + pindah kelas.
class ClassDetailScreen extends StatefulWidget {
  const ClassDetailScreen({super.key, required this.kelas});

  final Map<String, dynamic> kelas;

  @override
  State<ClassDetailScreen> createState() => _ClassDetailScreenState();
}

class _ClassDetailScreenState extends State<ClassDetailScreen> {
  List<dynamic> _kelas = [];
  List<dynamic> _guru = [];
  Map<String, dynamic>? _detail;
  bool _busy = false;
  bool _lulus = false;

  int get _kelasId => widget.kelas['id'] as int;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    try {
      final hasil = await Future.wait([
        api.get('/api/kelas'),
        api.get('/api/guru'),
      ]);
      if (!mounted) return;
      setState(() {
        _kelas = hasil[0] as List;
        _guru = hasil[1] as List;
        _detail = (hasil[0] as List)
            .cast<Map<String, dynamic>>()
            .where((k) => k['id'] == _kelasId)
            .firstOrNull;
      });
    } on ApiException catch (e) {
      if (mounted) _snack(e.message, error: true);
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

  String? get _waliNama {
    final dariApi = _detail?['wali_guru_nama'] as String?;
    if (dariApi != null) return dariApi;
    final waliId = _detail?['wali_guru_id'];
    if (waliId == null) return null;
    for (final g in _guru) {
      if (g['id'] == waliId) return g['nama'] as String?;
    }
    return null;
  }

  /// Pindah kabeh murid kelas iki menyang kelas liya (promosi).
  Future<void> _pindahKelas() async {
    int? tujuan = _kelas
        .cast<Map<String, dynamic>>()
        .where((k) => k['id'] != _kelasId)
        .map((k) => k['id'] as int)
        .firstOrNull;

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Pindah Kelas'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Pindahkan semua murid ${widget.kelas['nama_kelas']} ke:',
                  style: const TextStyle(height: 1.4)),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                initialValue: tujuan,
                decoration: const InputDecoration(
                    labelText: 'Kelas Tujuan', border: OutlineInputBorder()),
                items: [
                  for (final k in _kelas)
                    if (k['id'] != _kelasId)
                      DropdownMenuItem(
                          value: k['id'] as int,
                          child: Text(k['nama_kelas'] as String? ?? '-')),
                ],
                onChanged: (v) => setLocal(() => tujuan = v),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Batal')),
            FilledButton(
              onPressed: tujuan == null
                  ? null
                  : () => Navigator.pop(ctx, true),
              child: const Text('Pindahkan'),
            ),
          ],
        ),
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _busy = true);
    try {
      final res = await context.read<AuthState>().api.post('/api/kelas/pindah', {
        'dari_kelas_id': _kelasId,
        'ke_kelas_id': tujuan,
      });
      if (mounted) {
        _snack('${res['dipindah']} murid dipindah ke ${res['ke']}');
        Navigator.pop(context);
      }
    } on ApiException catch (e) {
      if (mounted) _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Luluskan kabeh murid kelas iki (data tetep ana, mung non-aktif).
  Future<void> _luluskan() async {
    final jml = _detail?['jumlah_murid'] ?? 0;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.school_outlined, color: Color(0xFF16A34A), size: 40),
        title: const Text('Luluskan Kelas?'),
        content: Text(
          '$jml murid ${widget.kelas['nama_kelas']} akan ditandai LULUS.\n\n'
          'Data absensi dan rekap tetap tersimpan. Murid tidak akan muncul '
          'di daftar aktif / absensi harian.',
          style: const TextStyle(height: 1.4),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Batal')),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF16A34A)),
            onPressed: () => Navigator.pop(ctx, true),
            icon: const Icon(Icons.school, size: 18),
            label: const Text('Luluskan'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _busy = true);
    try {
      final res = await context.read<AuthState>().api
          .post('/api/kelas/$_kelasId/luluskan', {});
      if (mounted) {
        _snack('${res['lulus']} murid ditandai lulus');
        Navigator.pop(context);
      }
    } on ApiException catch (e) {
      if (mounted) _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final nama = widget.kelas['nama_kelas'] as String? ?? 'Kelas';
    return Scaffold(
      appBar: AppBar(
        title: Text(nama, style: const TextStyle(fontWeight: FontWeight.w700)),
        actions: [
          if (context.watch<AuthState>().isAdmin)
            PopupMenuButton<String>(
              tooltip: 'Menu Kelas',
              enabled: !_busy,
              onSelected: (v) => switch (v) {
                'pindah' => _pindahKelas(),
                _ => _luluskan(),
              },
              itemBuilder: (_) => [
                const PopupMenuItem(
                  value: 'pindah',
                  child: ListTile(
                    leading: Icon(Icons.swap_horiz),
                    title: Text('Pindah Kelas'),
                    dense: true,
                  ),
                ),
                PopupMenuItem(
                  value: 'lulus',
                  child: ListTile(
                    leading:
                        Icon(Icons.school_outlined, color: const Color(0xFF16A34A)),
                    title: Text('Luluskan Kelas',
                        style: const TextStyle(color: Color(0xFF16A34A))),
                    dense: true,
                  ),
                ),
              ],
            ),
        ],
      ),
      body: Column(
        children: [
          // Header info kelas
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          backgroundColor: scheme.primaryContainer,
                          child: Text(
                            '${_detail?['jumlah_murid'] ?? widget.kelas['jumlah_murid'] ?? 0}',
                            style: TextStyle(
                                fontWeight: FontWeight.w700,
                                color: scheme.onPrimaryContainer),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(nama,
                                  style: const TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w700)),
                              Text(
                                'Wali Kelas: ${_waliNama ?? '-'}',
                                style: TextStyle(
                                    fontSize: 13,
                                    color: scheme.onSurfaceVariant),
                              ),
                              if (widget.kelas['tahun_ajaran_nama'] != null)
                                Text(
                                  'Tahun Ajaran: ${widget.kelas['tahun_ajaran_nama']}',
                                  style: TextStyle(
                                      fontSize: 13,
                                      color: scheme.onSurfaceVariant),
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
          // Toggle Aktif / Lulus (murid lulus tetep bisa diakses riwayate)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: SegmentedButton<bool>(
              segments: const [
                ButtonSegment(
                    value: false,
                    label: Text('Aktif'),
                    icon: Icon(Icons.groups_outlined, size: 16)),
                ButtonSegment(
                    value: true,
                    label: Text('Lulus'),
                    icon: Icon(Icons.school_outlined, size: 16)),
              ],
              selected: {_lulus},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _lulus = s.first),
            ),
          ),
          // Murid kelas iku (CRUD lengkap) / Lulus per tahun ajaran (riwayat)
          Expanded(
            child: _lulus
                ? LulusKelasView(kelasNama: nama)
                : MuridTab(
                    kelasId: _kelasId,
                    kelasNama: widget.kelas['nama_kelas'] as String?,
                  ),
          ),
        ],
      ),
    );
  }
}
