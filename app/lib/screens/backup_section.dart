import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Section Backup (jadwal otomatis + manual + arsip + riwayat) — tanpa
/// Scaffold, dilebokke ing screen Pengaturan Super Admin.
class BackupSection extends StatefulWidget {
  const BackupSection({super.key});

  @override
  State<BackupSection> createState() => _BackupSectionState();
}

class _BackupSectionState extends State<BackupSection> {
  bool _loading = true;
  bool _saving = false;
  bool _running = false;
  bool _busy = false;

  bool _enabled = false;
  String _jam = '02:00';
  int _retensi = 14;
  List<dynamic> _riwayat = [];
  List<dynamic> _files = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final res = await api.get('/api/super/backup');
      List<dynamic> files = [];
      try {
        files = await api.get('/api/super/backup/files') as List;
      } catch (_) {/* files optional */}
      if (!mounted) return;
      final cfg = (res['config'] as Map?) ?? {};
      setState(() {
        _enabled = (cfg['enabled'] as bool?) ?? false;
        _jam = (cfg['jam'] as String?) ?? '02:00';
        _retensi = (cfg['retensi'] as num?)?.toInt() ?? 14;
        _riwayat = (res['riwayat'] as List? ?? []);
        _files = files;
        _loading = false;
      });
    } on ApiException catch (e) {
      _snack(e.message, error: true);
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await context.read<AuthState>().api.put('/api/super/backup/config', {
        'enabled': _enabled,
        'jam': _jam,
        'retensi': _retensi,
      });
      _snack(_enabled
          ? 'Backup rutin aktif — setiap hari $_jam WIB'
          : 'Backup rutin dimatikan');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _runNow() async {
    setState(() => _running = true);
    try {
      final res = await context.read<AuthState>().api
          .post('/api/super/backup/run', {});
      final nama = (res['nama'] as String?) ?? '';
      final kb = ((res['ukuran'] as num?)?.toInt() ?? 0) ~/ 1024;
      _snack('Backup selesai: $nama ($kb KB)');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  String _fmtWaktu(String iso) {
    final p = DateTime.tryParse(iso);
    if (p == null) return iso;
    return '${p.day.toString().padLeft(2, '0')}/${p.month.toString().padLeft(2, '0')}/${p.year} ${p.hour.toString().padLeft(2, '0')}:${p.minute.toString().padLeft(2, '0')}';
  }

  String _fmtUkuran(int bytes) {
    if (bytes >= 1024 * 1024) return '${(bytes / 1024 / 1024).toStringAsFixed(1)} MB';
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '$bytes B';
  }

  Future<void> _downloadFile(dynamic f) async {
    setState(() => _busy = true);
    try {
      final nama = f['nama'] as String;
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/super/backup/files/$nama');
      await FileSaver.instance.saveFile(
        name: nama.replaceAll('.tar.gz', ''),
        bytes: bytes,
        fileExtension: 'tar.gz',
        mimeType: MimeType.custom,
        customMimeType: 'application/gzip',
      );
      _snack('Backup diunduh: $nama');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restoreFile(dynamic f) async {
    final nama = f['nama'] as String;
    final ketik = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          icon: const Icon(Icons.warning_amber_outlined, color: Color(0xFFDC2626)),
          title: const Text('Restore Seluruh Platform?'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Seluruh data (global + ${_files.length - 1} tenant DB + konfigurasi) '
                  'akan DIGANTI dengan isi arsip:\n\n$nama\n\n'
                  'Kondisi saat ini di-backup dulu (pre-restore). Service akan '
                  'restart otomatis — koneksi terputus ±5 detik.',
                  style: const TextStyle(fontSize: 13),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: ketik,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: 'Ketik RESTORE untuk konfirmasi',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Batal')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
              onPressed: () =>
                  Navigator.pop(ctx, ketik.text.trim().toUpperCase() == 'RESTORE'),
              child: const Text('Restore'),
            ),
          ],
        ),
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final res = await context.read<AuthState>().api
          .post('/api/super/backup/restore', {'nama_file': nama});
      final pesan = res['pesan'] as String? ?? 'Restore dijalankan';
      _snack(pesan);
      if (mounted) {
        setState(() => _busy = false);
      }
    } on ApiException catch (e) {
      _snack(e.message, error: true);
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final titleStyle =
        Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700);

    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 60),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Setelan jadwal ──
        Text('Jadwal Otomatis', style: titleStyle),
        const SizedBox(height: 8),
        Card(
          child: Column(
            children: [
              SwitchListTile(
                title: const Text('Aktifkan backup rutin',
                    style: TextStyle(fontWeight: FontWeight.w600)),
                subtitle: const Text('Seluruh database dikemas otomatis'),
                value: _enabled,
                onChanged: (v) => setState(() => _enabled = v),
              ),
              const Divider(height: 1),
              ListTile(
                enabled: _enabled,
                title: const Text('Jam backup'),
                subtitle: Text('Setiap hari pukul $_jam WIB'),
                trailing: const Icon(Icons.schedule),
                onTap: () async {
                  final parts = _jam.split(':');
                  final p = await showTimePicker(
                    context: context,
                    initialTime: TimeOfDay(
                        hour: int.tryParse(parts[0]) ?? 2,
                        minute: int.tryParse(parts[1]) ?? 0),
                  );
                  if (p != null && mounted) {
                    setState(() => _jam =
                        '${p.hour.toString().padLeft(2, '0')}:${p.minute.toString().padLeft(2, '0')}');
                  }
                },
              ),
              const Divider(height: 1),
              ListTile(
                enabled: _enabled,
                title: const Text('Retensi arsip'),
                subtitle: Text('Menyimpan $_retensi backup terakhir'),
                trailing: DropdownButton<int>(
                  value: _retensi,
                  onChanged: (v) =>
                      setState(() => _retensi = v ?? 14),
                  items: const [
                    DropdownMenuItem(value: 7, child: Text('7 hari')),
                    DropdownMenuItem(value: 14, child: Text('14 hari')),
                    DropdownMenuItem(value: 30, child: Text('30 hari')),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(12),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _saving ? null : _save,
                    icon: _saving
                        ? const SizedBox(
                            height: 16, width: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.save_outlined),
                    label: Text(_saving ? 'Menyimpan…' : 'Simpan Jadwal'),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        // ── Backup manual ──
        Text('Backup Manual', style: titleStyle),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Jalankan backup sekarang — semua database '
                    '(global + seluruh madrasah) + file konfigurasi.',
                    style: TextStyle(
                        fontSize: 12.5, color: scheme.onSurfaceVariant)),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.tonalIcon(
                    onPressed: _running ? null : _runNow,
                    icon: _running
                        ? const SizedBox(
                            height: 16, width: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.backup_outlined),
                    label: Text(_running ? 'Membackup…' : 'Buat Backup Sekarang'),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        // ── Arsip backup (download / restore) ──
        Text('Arsip Backup (${_files.length})', style: titleStyle),
        const SizedBox(height: 8),
        Card(
          child: _files.isEmpty
              ? Padding(
                  padding: const EdgeInsets.all(20),
                  child: Center(
                    child: Text('Belum ada arsip — klik "Buat Backup" di atas',
                        style: TextStyle(color: scheme.onSurfaceVariant)),
                  ),
                )
              : Column(
                  children: [
                    for (final f in _files)
                      ListTile(
                        dense: true,
                        leading: const Icon(Icons.archive_outlined,
                            color: Color(0xFF7C3AED)),
                        title: Text(f['nama'] ?? '-',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w600, fontSize: 13)),
                        subtitle: Text(
                            '${_fmtWaktu(f['tanggal'] ?? '')} • ${_fmtUkuran((f['ukuran'] as num? ?? 0).toInt())}'),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              tooltip: 'Download',
                              icon: const Icon(Icons.download_outlined, size: 20),
                              onPressed: _busy ? null : () => _downloadFile(f),
                            ),
                            IconButton(
                              tooltip: 'Restore',
                              icon: Icon(Icons.restore_outlined,
                                  size: 20, color: scheme.error),
                              onPressed: _busy ? null : () => _restoreFile(f),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
        ),
        const SizedBox(height: 16),
        // ── Riwayat ──
        Text('Riwayat Backup (${_riwayat.length})', style: titleStyle),
        const SizedBox(height: 8),
        if (_riwayat.isEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Center(
                child: Text('Belum ada backup',
                    style: TextStyle(color: scheme.onSurfaceVariant)),
              ),
            ),
          )
        else
          Card(
            child: Column(
              children: [
                for (final r in _riwayat)
                  ListTile(
                    dense: true,
                    leading: Icon(
                      r['status'] == 'ok'
                          ? Icons.check_circle
                          : Icons.error,
                      color: r['status'] == 'ok'
                          ? const Color(0xFF16A34A)
                          : Colors.red.shade700,
                    ),
                    title: Text(_fmtWaktu(r['waktu'] ?? ''),
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text('${r['nama_file']} • ${(r['ukuran'] as num? ?? 0) ~/ 1024} KB'),
                    trailing: r['jenis'] == 'manual'
                        ? _chip('Manual', const Color(0xFF2563EB))
                        : _chip('Otomatis', const Color(0xFFD97706)),
                  ),
              ],
            ),
          ),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _chip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(text,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
    );
  }
}
