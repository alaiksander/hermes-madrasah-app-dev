import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import '../services/spreadsheet.dart';

/// Ikon + warna per status absensi.
const _statusVisual = {
  'hadir': (Icons.check_circle, Color(0xFF16A34A)),
  'izin': (Icons.schedule, Color(0xFF2563EB)),
  'sakit': (Icons.local_hospital_outlined, Color(0xFFD97706)),
  'alpa': (Icons.block, Color(0xFF6B7280)),
};

/// Rekap kelas wali: roster murid + status H/I/S/A per tanggal + ekspor.
class WaliKelasScreen extends StatefulWidget {
  final dynamic kelas;
  const WaliKelasScreen({super.key, required this.kelas});

  @override
  State<WaliKelasScreen> createState() => _WaliKelasScreenState();
}

class _WaliKelasScreenState extends State<WaliKelasScreen> {
  DateTime _tanggal = DateTime.now();
  List<dynamic> _roster = [];
  bool _loading = true;
  String? _error;

  int get _kelasId => widget.kelas['id'] as int;

  @override
  void initState() {
    super.initState();
    _load();
  }

  String _iso(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  String _fmt(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await context.read<AuthState>().api
          .get('/api/absensi/kelas/$_kelasId', {'tanggal': _iso(_tanggal)});
      if (!mounted) return;
      setState(() {
        _roster = res as List;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _gantiTanggal(int delta) {
    setState(() => _tanggal = _tanggal.add(Duration(days: delta)));
    _load();
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Future<void> _exportExcel() async {
    try {
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/absensi/export.xlsx?tanggal=${_iso(_tanggal)}');
      await FileSaver.instance.saveFile(
        name: 'rekap-${widget.kelas['nama_kelas']}-${_iso(_tanggal)}',
        bytes: bytes,
        fileExtension: 'xlsx',
        mimeType: MimeType.custom,
        customMimeType: xlsxMime,
      );
      _snack('Export Excel berhasil diunduh');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } catch (_) {
      _snack('Gagal export file', error: true);
    }
  }

  /// Ekspor PDF absensi per murid — dialog pilih rentang tanggal.
  Future<void> _exportPdf(dynamic m) async {
    final now = DateTime.now();
    var dari = DateTime(now.year, now.month, 1);
    var sampai = now;

    Future<DateTime?> pick(DateTime initial) => showDatePicker(
          context: context,
          initialDate: initial,
          firstDate: DateTime(2020),
          lastDate: DateTime(now.year + 1),
        );

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Ekspor PDF Absensi'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${m['nama']} (${m['nisn'] ?? '-'})',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text('Pilih rentang tanggal',
                  style: TextStyle(
                      fontSize: 12,
                      color: Theme.of(ctx).colorScheme.onSurfaceVariant)),
              const SizedBox(height: 8),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event),
                title: const Text('Dari'),
                subtitle: Text(_fmt(dari)),
                onTap: () async {
                  final p = await pick(dari);
                  if (p != null && ctx.mounted) setLocal(() => dari = p);
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event_available),
                title: const Text('Sampai'),
                subtitle: Text(_fmt(sampai)),
                onTap: () async {
                  final p = await pick(sampai);
                  if (p != null && ctx.mounted) setLocal(() => sampai = p);
                },
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Batal')),
            FilledButton.icon(
              onPressed: () => Navigator.pop(ctx, true),
              icon: const Icon(Icons.download, size: 18),
              label: const Text('Unduh PDF'),
            ),
          ],
        ),
      ),
    );
    if (ok != true || !mounted) return;
    if (dari.isAfter(sampai)) {
      _snack('Rentang tidak valid — Dari harus sebelum Sampai', error: true);
      return;
    }

    try {
      final bytes = await context.read<AuthState>().api.getBytes(
          '/api/absensi/pdf/${m['murid_id']}?dari=${_iso(dari)}&sampai=${_iso(sampai)}');
      await FileSaver.instance.saveFile(
        name: 'absensi-${(m['nama'] as String? ?? 'murid').replaceAll(' ', '-')}',
        bytes: bytes,
        fileExtension: 'pdf',
        mimeType: MimeType.custom,
        customMimeType: 'application/pdf',
      );
      _snack('PDF absensi diunduh');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } catch (_) {
      _snack('Gagal mengunduh PDF', error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final nama = widget.kelas['nama_kelas'] as String? ?? 'Kelas';
    final taun = widget.kelas['tahun_ajaran_nama'] as String?;

    // Ringkesan status
    var hadir = 0, izin = 0, sakit = 0, alpa = 0, belum = 0;
    for (final r in _roster) {
      final st = r['status'] as String?;
      if (st == 'hadir') {
        hadir++;
      } else if (st == 'izin') {
        izin++;
      } else if (st == 'sakit') {
        sakit++;
      } else if (st == 'alpa') {
        alpa++;
      } else {
        belum++;
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: Text('Rekap $nama${taun != null ? ' • $taun' : ''}',
            style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
      body: Column(
        children: [
          // Navigasi tanggal
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                child: Row(
                  children: [
                    IconButton(
                      tooltip: 'Kemarin',
                      onPressed: _loading ? null : () => _gantiTanggal(-1),
                      icon: const Icon(Icons.chevron_left),
                    ),
                    Expanded(
                      child: Text(
                        _fmt(_tanggal),
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w700),
                      ),
                    ),
                    IconButton(
                      tooltip: 'Besok',
                      onPressed: _loading ? null : () => _gantiTanggal(1),
                      icon: const Icon(Icons.chevron_right),
                    ),
                    TextButton(
                      onPressed: _loading
                          ? null
                          : () {
                              setState(() => _tanggal = DateTime.now());
                              _load();
                            },
                      child: const Text('Hari Ini'),
                    ),
                  ],
                ),
              ),
            ),
          ),
          // Ringkesan + ekspor
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Row(
              children: [
                Expanded(
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      _chip('Hadir', hadir, const Color(0xFF16A34A)),
                      _chip('Izin', izin, const Color(0xFF2563EB)),
                      _chip('Sakit', sakit, const Color(0xFFD97706)),
                      _chip('Alpa', alpa, const Color(0xFF6B7280)),
                      _chip('Belum', belum, const Color(0xFFDC2626)),
                    ],
                  ),
                ),
                IconButton.filledTonal(
                  tooltip: 'Ekspor Excel',
                  onPressed: _loading ? null : _exportExcel,
                  icon: const Icon(Icons.download_outlined),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          // Roster
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(_error!, style: TextStyle(color: scheme.error)),
                            const SizedBox(height: 12),
                            FilledButton.tonal(
                                onPressed: _load, child: const Text('Coba lagi')),
                          ],
                        ),
                      )
                    : _roster.isEmpty
                        ? Center(
                            child: Text('Belum ada murid',
                                style:
                                    TextStyle(color: scheme.onSurfaceVariant)))
                        : ListView.separated(
                            padding: const EdgeInsets.all(16),
                            itemCount: _roster.length,
                            separatorBuilder: (_, _) => const SizedBox(height: 8),
                            itemBuilder: (context, i) {
                              final m = _roster[i];
                              final status = m['status'] as String?;
                              final visual = _statusVisual[status];
                              return Card(
                                child: ListTile(
                                  leading: CircleAvatar(
                                    backgroundColor: scheme.primaryContainer,
                                    child: Text(
                                      (m['nama'] as String? ?? '?')
                                          .substring(0, 1)
                                          .toUpperCase(),
                                      style: TextStyle(
                                          fontWeight: FontWeight.w700,
                                          color: scheme.onPrimaryContainer),
                                    ),
                                  ),
                                  title: Text(m['nama'] ?? '-',
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w600)),
                                  subtitle: Text('${m['nisn'] ?? '-'}'
                                      '${m['waktu'] != null ? ' • ${(m['waktu'] as String).substring(11, 16)}' : ''}'),
                                  trailing: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      if (visual != null)
                                        Icon(visual.$1, color: visual.$2)
                                      else
                                        Icon(Icons.remove_circle_outline,
                                            color: scheme.outlineVariant),
                                      const SizedBox(width: 4),
                                      PopupMenuButton<String>(
                                        tooltip: 'Menu',
                                        onSelected: (v) => switch (v) {
                                          'pdf' => _exportPdf(m),
                                          _ => _showQr(m),
                                        },
                                        itemBuilder: (_) => [
                                          const PopupMenuItem(
                                            value: 'qr',
                                            child: ListTile(
                                              leading: Icon(Icons.qr_code_2),
                                              title: Text('Lihat QR'),
                                              dense: true,
                                            ),
                                          ),
                                          const PopupMenuItem(
                                            value: 'pdf',
                                            child: ListTile(
                                              leading: Icon(
                                                  Icons.picture_as_pdf_outlined,
                                                  color: Color(0xFFDC2626)),
                                              title: Text('Ekspor PDF Absensi'),
                                              dense: true,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String label, int value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        '$label $value',
        style: TextStyle(
            fontSize: 12.5, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }

  Future<void> _showQr(dynamic m) async {
    try {
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/murid/${m['murid_id']}/qr.png');
      if (!mounted) return;
      showDialog(
        context: context,
        builder: (ctx) => Dialog(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Image.memory(bytes, width: 220, height: 220),
                const SizedBox(height: 12),
                Text(m['nama'] ?? '-',
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 16)),
                Text('${m['nisn'] ?? '-'}',
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.onSurfaceVariant)),
                const SizedBox(height: 16),
                FilledButton.tonal(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Tutup'),
                ),
              ],
            ),
          ),
        ),
      );
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }
}
