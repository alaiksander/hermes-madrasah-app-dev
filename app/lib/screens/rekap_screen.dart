import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import '../services/spreadsheet.dart';
import 'wali_kelas_screen.dart';

/// Ikon + warna per status absensi.
const _statusVisual = {
  'hadir': (Icons.check_circle, Color(0xFF16A34A)),
  'izin': (Icons.schedule, Color(0xFF2563EB)),
  'sakit': (Icons.local_hospital_outlined, Color(0xFFD97706)),
  'alpa': (Icons.block, Color(0xFF6B7280)),
};

/// Rekap absensi dina iki: total/hadir/tidak + rincian per kelas + daftar hadir.
class RekapScreen extends StatefulWidget {
  const RekapScreen({super.key});

  @override
  State<RekapScreen> createState() => _RekapScreenState();
}

class _RekapScreenState extends State<RekapScreen> {
  Map<String, dynamic>? _rekap;
  List<dynamic> _hariIni = [];
  List<dynamic> _waliKelas = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final api = context.read<AuthState>().api;
    try {
      final rekap = await api.get('/api/absensi/rekap');
      final hariIni = await api.get('/api/absensi/hari-ini', {'limit': '15'});
      // Kelas wali (non-fatal yen gagal)
      try {
        final waliKelas = await api.get('/api/kelas/wali-saya');
        if (mounted) setState(() => _waliKelas = waliKelas as List);
      } on ApiException {
        // abaikan
      }
      if (!mounted) return;
      setState(() {
        _rekap = rekap as Map<String, dynamic>;
        _hariIni = hariIni as List;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Tidak dapat terhubung ke server';
        _loading = false;
      });
    }
  }

  Future<void> _exportRange() async {
    final now = DateTime.now();
    var dari = DateTime(now.year, now.month, 1);
    var sampai = now;

    Future<DateTime?> pick(DateTime initial) => showDatePicker(
          context: context,
          initialDate: initial,
          firstDate: DateTime(2020),
          lastDate: DateTime(2035),
        );

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Ekspor Rekap'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event),
                title: const Text('Dari'),
                subtitle: Text(_fmt(dari)),
                onTap: () async {
                  final p = await pick(dari);
                  if (p != null && ctx.mounted) setState(() => dari = p);
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event_available),
                title: const Text('Sampai'),
                subtitle: Text(_fmt(sampai)),
                onTap: () async {
                  final p = await pick(sampai);
                  if (p != null && ctx.mounted) setState(() => sampai = p);
                },
              ),
              const SizedBox(height: 4),
              Text(
                'Format: baris murid × kolom tanggal (H = Hadir)\n'
                'Hanya tanggal yang ada absensi yang muncul',
                style: TextStyle(
                    fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Download')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    if (!mounted) return;
    if (dari.isAfter(sampai)) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Rentang tidak valid — Dari harus sebelum Sampai'),
          backgroundColor: Colors.red));
      return;
    }
    await _download(
        '/api/absensi/export.xlsx?dari=${_iso(dari)}&sampai=${_iso(sampai)}',
        'rekap-${_iso(dari)}-${_iso(sampai)}',
        fileExtension: 'xlsx', customMimeType: xlsxMime);
  }

  String _fmt(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';
  String _iso(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  String _fmtWaktu(String? iso) {
    // "2026-08-15T21:02:00" → "21:02"
    if (iso == null || iso.length < 16) return '-';
    return iso.substring(11, 16);
  }

  Future<void> _download(String path, String name,
      {String fileExtension = 'csv', String customMimeType = 'text/csv'}) async {
    try {
      final bytes = await context.read<AuthState>().api.getBytes(path);
      await FileSaver.instance.saveFile(
        name: name,
        bytes: bytes,
        fileExtension: fileExtension,
        mimeType: MimeType.custom,
        customMimeType: customMimeType,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Rekap berhasil diunduh'),
          backgroundColor: Color(0xFF16A34A)));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message), backgroundColor: Colors.red.shade700));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Gagal export file'),
          backgroundColor: Colors.red));
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!, style: TextStyle(color: scheme.error)),
            const SizedBox(height: 12),
            FilledButton.tonal(onPressed: _load, child: const Text('Coba lagi')),
          ],
        ),
      );
    }

    final r = _rekap!;
    final total = (r['total_murid'] as num?)?.toInt() ?? 0;
    final hadir = (r['hadir'] as num?)?.toInt() ?? 0;
    final izin = (r['izin'] as num?)?.toInt() ?? 0;
    final sakit = (r['sakit'] as num?)?.toInt() ?? 0;
    final alpa = (r['alpa'] as num?)?.toInt() ?? 0;
    final belum = (r['belum'] as num?)?.toInt() ?? 0;
    final perKelas = (r['per_kelas'] as List? ?? []);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_waliKelas.isNotEmpty) ...[
            Text('Kelas Wali',
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            for (final wk in _waliKelas)
              Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: scheme.primaryContainer,
                    child: Icon(Icons.school_outlined,
                        color: scheme.onPrimaryContainer),
                  ),
                  title: Text('${wk['nama_kelas']}',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text(
                      '${wk['jumlah_murid'] ?? 0} murid • Wali: ${wk['wali_guru_nama'] ?? '-'}'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => WaliKelasScreen(kelas: wk),
                    ),
                  ),
                ),
              ),
            const SizedBox(height: 12),
          ],
          Row(
            children: [
              Expanded(
                child: Text('Rekap ${r['tanggal']}',
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
              IconButton.filledTonal(
                tooltip: 'Ekspor Rekap',
                onPressed: _exportRange,
                icon: const Icon(Icons.download_outlined),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _StatCard(color: scheme.primary, label: 'Total', value: total),
              const SizedBox(width: 10),
              _StatCard(color: const Color(0xFF16A34A), label: 'Hadir', value: hadir),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _StatusChip('Izin', izin, const Color(0xFF2563EB)),
              _StatusChip('Sakit', sakit, const Color(0xFFD97706)),
              _StatusChip('Alpa', alpa, const Color(0xFF6B7280)),
              _StatusChip('Belum', belum, const Color(0xFFDC2626)),
            ],
          ),
          const SizedBox(height: 20),
          Text('Per Kelas (${perKelas.length})',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          // ListView scrollable dhewe: ±5 kelas katon, sisane scroll ing kene
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 330),
            child: ListView.separated(
              shrinkWrap: true,
              padding: EdgeInsets.zero,
              itemCount: perKelas.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, i) {
                final k = perKelas[i];
                return Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 56,
                          child: Text(k['kelas'],
                              style: const TextStyle(fontWeight: FontWeight.w700)),
                        ),
                        Expanded(
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(6),
                            child: LinearProgressIndicator(
                              value: (k['total'] as num? ?? 0) == 0
                                  ? 0
                                  : (k['hadir'] as num? ?? 0) / (k['total'] as num? ?? 1),
                              minHeight: 8,
                              backgroundColor: scheme.surfaceContainerHighest,
                              color: const Color(0xFF16A34A),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              '${k['hadir']}/${k['total']}',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                            Text(
                              'I ${k['izin'] ?? 0} • S ${k['sakit'] ?? 0} • A ${k['alpa'] ?? 0}',
                              style: TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant),
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
          const SizedBox(height: 20),
          Text('Daftar Hadir (${_hariIni.length} terbaru)',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (_hariIni.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                  child: Text('Belum ada yang masuk',
                      style: TextStyle(color: scheme.onSurfaceVariant))),
            )
          else
            Card(
              child: Column(
                children: [
                  for (final a in _hariIni) ...[
                    const Divider(height: 1),
                    ListTile(
                      dense: true,
                      leading: Builder(builder: (_) {
                        final v = _statusVisual[a['status']] ??
                            _statusVisual['hadir']!;
                        return Icon(v.$1, color: v.$2);
                      }),
                      title: Text('${a['nama']} (${a['kelas']})',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: Row(
                        children: [
                          Flexible(
                            child: Text(
                                '[${a['sesi'] == 'pulang' ? 'Pulang' : 'Masuk'}] ${_fmtWaktu(a['waktu'])} • oleh ${a['guru'] ?? '-'}',
                                overflow: TextOverflow.ellipsis),
                          ),
                          if (a['telat_menit'] != null)
                            Container(
                              margin: const EdgeInsets.only(left: 8),
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 1),
                              decoration: BoxDecoration(
                                color: const Color(0xFFD97706)
                                    .withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                'Telat ${a['telat_menit']} mnt',
                                style: const TextStyle(
                                    fontSize: 10.5,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFFD97706)),
                              ),
                            ),
                        ],
                      ),
                      trailing: Builder(builder: (_) {
                        final v = _statusVisual[a['status']] ??
                            _statusVisual['hadir']!;
                        return Text(
                          switch (a['status']) {
                            'izin' => 'Izin',
                            'sakit' => 'Sakit',
                            'alpa' => 'Alpa',
                            _ => 'Hadir',
                          },
                          style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: FontWeight.w700,
                              color: v.$2),
                        );
                      }),
                    ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final Color color;
  final String label;
  final int value;

  const _StatCard({required this.color, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Card(
        color: color.withValues(alpha: 0.10),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Column(
            children: [
              Text('$value',
                  style: TextStyle(
                      fontSize: 26, fontWeight: FontWeight.w800, color: color)),
              Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String label;
  final int value;
  final Color color;

  const _StatusChip(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text('$label: $value',
          style: TextStyle(
              fontSize: 12.5, fontWeight: FontWeight.w700, color: color)),
    );
  }
}
