import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Wizard Naik Kelas: pilih taun tujuan → mapping kelas sumber (pindah/lulus).
///
/// Bali: id taun tujuan yen sukses, null yen batal/ditutup.
Future<int?> showNaikKelasDialog(
    BuildContext context, List<dynamic> tahun, int? tahunSaatIni) async {
  final api = context.read<AuthState>().api;

  List<dynamic> semuaKelas;
  try {
    semuaKelas = await api.get('/api/kelas') as List;
  } on ApiException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(e.message), backgroundColor: Colors.red.shade700));
    }
    return null;
  }
  if (!context.mounted) return null;

  return showDialog<int>(
    context: context,
    builder: (_) => _NaikKelasDialog(
        api: api, tahun: tahun, semuaKelas: semuaKelas, tahunSaatIni: tahunSaatIni),
  );
}

String? _suggestTarget(String nama) {
  final m = RegExp(r'^(\d+)').firstMatch(nama);
  if (m == null) return null;
  final n = int.parse(m.group(1)!);
  if (n >= 9) return null; // kelas 9 → luluskan
  return '${n + 1}${nama.substring(m.group(1)!.length)}';
}

class _NaikKelasDialog extends StatefulWidget {
  final ApiClient api;
  final List<dynamic> tahun;
  final List<dynamic> semuaKelas;
  final int? tahunSaatIni;

  const _NaikKelasDialog(
      {required this.api,
      required this.tahun,
      required this.semuaKelas,
      this.tahunSaatIni});

  @override
  State<_NaikKelasDialog> createState() => _NaikKelasDialogState();
}

class _NaikKelasDialogState extends State<_NaikKelasDialog> {
  int? _targetId;
  bool _busy = false;
  Map<String, dynamic>? _hasil;
  final List<_SrcRow> _sumber = [];

  String _tahunNama(int? id) =>
      widget.tahun.where((t) => t['id'] == id).map((t) => t['nama']).firstOrNull ??
      '-';

  @override
  void initState() {
    super.initState();
    // Default target: taun paling anyar sing beda karo taun saiki
    final lain = widget.tahun
        .where((t) => t['id'] != widget.tahunSaatIni)
        .toList()
      ..sort((a, b) => (b['id'] as int).compareTo(a['id'] as int));
    _targetId = lain.isNotEmpty ? lain.first['id'] as int : null;
    _buildSumber();
  }

  void _buildSumber() {
    _sumber
      ..clear()
      ..addAll(widget.semuaKelas
          .where((k) => k['tahun_ajaran_id'] != _targetId)
          .map((k) {
        final s = _suggestTarget(k['nama_kelas'] as String? ?? '');
        return _SrcRow(k, TextEditingController(text: s ?? ''), s == null);
      }));
  }

  Future<void> _submit() async {
    setState(() => _busy = true);
    final items = [
      for (final s in _sumber)
        if (s.luluskan)
          {'dari_kelas_id': s.kelas['id'], 'luluskan': true}
        else
          {
            'dari_kelas_id': s.kelas['id'],
            'ke_nama_kelas': s.tujuan.text.trim(),
          },
    ];
    try {
      final res = await widget.api
          .post('/api/kelas/naik-kelas', {'tahun_ajaran_id': _targetId, 'items': items});
      if (!mounted) return;
      setState(() {
        _hasil = res as Map<String, dynamic>;
        _busy = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(e.message), backgroundColor: Colors.red.shade700));
    }
  }

  @override
  void dispose() {
    for (final s in _sumber) {
      s.tujuan.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('Naik Kelas (Tahun Ajaran)',
          style: TextStyle(fontWeight: FontWeight.w700)),
      content: SizedBox(
        width: 420,
        child: _hasil != null ? _buildHasil() : _buildForm(scheme),
      ),
      actions: _hasil != null
          ? [
              FilledButton(
                  onPressed: () => Navigator.pop(context, _targetId),
                  child: const Text('Selesai')),
            ]
          : [
              TextButton(
                  onPressed: _busy ? null : () => Navigator.pop(context, null),
                  child: const Text('Batal')),
              FilledButton.icon(
                onPressed: _busy || _targetId == null ? null : _submit,
                icon: const Icon(Icons.trending_up, size: 18),
                label: const Text('Naik Kelas'),
              ),
            ],
    );
  }

  Widget _buildForm(ColorScheme scheme) {
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          DropdownButtonFormField<int>(
            initialValue: _targetId,
            isDense: true,
            decoration: const InputDecoration(
              labelText: 'Tahun Ajaran Tujuan',
              isDense: true,
              border: OutlineInputBorder(),
            ),
            items: [
              for (final t in widget.tahun)
                DropdownMenuItem(
                    value: t['id'] as int, child: Text(t['nama'] as String)),
            ],
            onChanged: (v) => setState(() {
              _targetId = v;
              _buildSumber();
            }),
          ),
          const SizedBox(height: 12),
          if (_sumber.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'Tidak ada kelas sumber — buat tahun ajaran baru dulu di Pengaturan.',
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
            )
          else ...[
            Text(
              'Kelas sumber (taun ${_tahunNama(_sumber.first.kelas['tahun_ajaran_id'])}) — '
              'kelas tujuan dibuat otomatis di tahun baru bila belum ada.',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            for (final s in _sumber)
              Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${s.kelas['nama_kelas']} '
                              '(${s.kelas['jumlah_murid'] ?? 0} murid)',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          Checkbox(
                            value: s.luluskan,
                            onChanged: _busy
                                ? null
                                : (v) => setState(() => s.luluskan = v ?? false),
                          ),
                          Text('Luluskan',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: s.luluskan
                                      ? scheme.error
                                      : scheme.onSurfaceVariant)),
                        ],
                      ),
                      TextField(
                        controller: s.tujuan,
                        enabled: !s.luluskan && !_busy,
                        decoration: InputDecoration(
                          labelText: 'Kelas tujuan (tahun baru)',
                          isDense: true,
                          border: const OutlineInputBorder(),
                          helperText:
                              s.luluskan ? 'Murid ditandai lulus' : null,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildHasil() {
    final items = (_hasil?['items'] as List? ?? []);
    var dipindah = 0, diluluskan = 0;
    for (final it in items) {
      dipindah += (it['dipindah'] as num?)?.toInt() ?? 0;
      diluluskan += (it['diluluskan'] as num?)?.toInt() ?? 0;
    }
    final errors = (_hasil?['error'] as List? ?? []);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _hasilBaris('Dipindah', dipindah, const Color(0xFF16A34A)),
        _hasilBaris('Diluluskan', diluluskan, const Color(0xFFD97706)),
        _hasilBaris('Error', errors.length, Colors.red.shade700),
        if (errors.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final e in errors.take(5))
            Text('Item ${e['item']}: ${e['pesan']}',
                style: const TextStyle(fontSize: 12)),
        ],
      ],
    );
  }

  Widget _hasilBaris(String label, int value, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 110,
            child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Text('$value', style: TextStyle(fontWeight: FontWeight.w800, color: color)),
        ],
      ),
    );
  }
}

class _SrcRow {
  final dynamic kelas;
  final TextEditingController tujuan;
  bool luluskan;
  _SrcRow(this.kelas, this.tujuan, this.luluskan);
}
