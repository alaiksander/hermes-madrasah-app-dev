import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import '../services/pick_file.dart';
import '../services/spreadsheet.dart';
import 'class_detail_screen.dart';
import 'naik_kelas_dialog.dart';

class KelasTab extends StatefulWidget {
  const KelasTab({super.key});

  @override
  State<KelasTab> createState() => _KelasTabState();
}

class _KelasTabState extends State<KelasTab> {
  List<dynamic> _kelas = [];
  List<dynamic> _tahun = [];
  int? _tahunDipilih;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final api = context.read<AuthState>().api;
    try {
      final tahun = await api.get('/api/tahun-ajaran') as List;
      if (!mounted) return;
      setState(() => _tahun = tahun);
      final aktif = tahun.where((t) => t['is_active'] == true).toList();
      if (_tahunDipilih == null || !tahun.any((t) => t['id'] == _tahunDipilih)) {
        _tahunDipilih = aktif.isNotEmpty
            ? aktif.first['id'] as int
            : (tahun.isNotEmpty ? tahun.first['id'] as int : null);
      }
      if (_tahunDipilih == null) {
        setState(() {
          _kelas = [];
          _loading = false;
        });
        return;
      }
      final res = await api.get('/api/kelas', {'tahun_ajaran_id': '$_tahunDipilih'});
      if (mounted) {
        setState(() {
          _kelas = res as List;
          _loading = false;
        });
      }
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

  Future<void> _form({Map<String, dynamic>? k}) async {
    final controller = TextEditingController(text: k?['nama_kelas'] ?? '');
    int? waliId = k?['wali_guru_id'] as int?;
    List<dynamic> guru = [];
    try {
      guru = await context.read<AuthState>().api.get('/api/guru') as List;
    } on ApiException {
      guru = [];
    }
    if (!mounted) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: Text(k == null ? 'Tambah Kelas' : 'Edit Kelas'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: controller,
                autofocus: true,
                decoration: const InputDecoration(
                    labelText: 'Nama Kelas', hintText: 'contoh: 7A'),
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<int?>(
                initialValue: waliId,
                decoration: const InputDecoration(
                    labelText: 'Wali Kelas', border: OutlineInputBorder()),
                items: [
                  const DropdownMenuItem<int?>(
                      value: null, child: Text('— Tanpa Wali —')),
                  for (final g in guru)
                    DropdownMenuItem(
                        value: g['id'] as int, child: Text(g['nama'] as String? ?? '-')),
                ],
                onChanged: (v) => setLocal(() => waliId = v),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Simpan')),
          ],
        ),
      ),
    );
    if (ok != true || controller.text.trim().isEmpty) return;
    if (!mounted) return;

    try {
      if (k == null) {
        await context.read<AuthState>().api
            .post('/api/kelas', {
              'nama_kelas': controller.text.trim(),
              'wali_guru_id': waliId,
              if (_tahunDipilih != null) 'tahun_ajaran_id': _tahunDipilih,
            });
        _snack('Kelas ditambahkan');
      } else {
        await context.read<AuthState>().api
            .patch('/api/kelas/${k['id']}', {
              'nama_kelas': controller.text.trim(),
              'wali_guru_id': waliId,
            });
        _snack('Kelas diperbarui');
      }
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _openNaikKelas() async {
    final target = await showNaikKelasDialog(context, _tahun, _tahunDipilih);
    if (target == null || !mounted) return;
    setState(() => _tahunDipilih = target);
    _load();
  }

  Future<void> _downloadQrPdf(dynamic k) async {
    try {
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/murid/qr-pdf.pdf?kelas_id=${k['id']}');
      await FileSaver.instance.saveFile(
        name: 'qr-${k['nama_kelas']}',
        bytes: bytes,
        fileExtension: 'pdf',
        mimeType: MimeType.custom,
        customMimeType: 'application/pdf',
      );
      _snack('PDF QR ${k['nama_kelas']} diunduh (${k['jumlah_murid']} murid)');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } catch (_) {
      _snack('Gagal membuat PDF', error: true);
    }
  }

  Future<void> _delete(dynamic k) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Hapus Kelas?'),
        content: Text('Kelas ${k['nama_kelas']} akan dihapus permanen.'),
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
    if (ok != true) return;
    if (!mounted) return;
    try {
      await context.read<AuthState>().api.delete('/api/kelas/${k['id']}');
      _snack('Kelas dihapus');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _downloadTemplate() async {
    try {
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/murid/template.xlsx');
      await FileSaver.instance.saveFile(
        name: 'template-import-murid',
        bytes: bytes,
        fileExtension: 'xlsx',
        mimeType: MimeType.custom,
        customMimeType: xlsxMime,
      );
      _snack('Template Excel diunduh — isi sesuai kolom, lalu Import');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } catch (_) {
      _snack('Gagal mengunduh template', error: true);
    }
  }

  Future<void> _exportXlsx() async {
    try {
      final bytes = await context.read<AuthState>().api.getBytes('/api/murid/export.xlsx');
      await FileSaver.instance.saveFile(
        name: 'murid-${DateTime.now().toIso8601String().substring(0, 10)}',
        bytes: bytes,
        fileExtension: 'xlsx',
        mimeType: MimeType.custom,
        customMimeType: xlsxMime,
      );
      _snack('Export berhasil diunduh');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } catch (_) {
      _snack('Gagal export file', error: true);
    }
  }

  Future<void> _importXlsx() async {
    final picked = await pickXlsxFile();
    if (picked == null) {
      _snack('Tidak ada file Excel dipilih', error: true);
      return;
    }
    if (!mounted) return;

    try {
      final res = await context.read<AuthState>().api
          .postMultipart('/api/murid/import', picked.bytes, filename: picked.name);
      if (!mounted) return;
      final ditambah = (res['ditambahkan'] as num?)?.toInt() ?? 0;
      final sudah = (res['sudah_ada'] as num?)?.toInt() ?? 0;
      final errors = (res['error'] as List? ?? []);
      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Hasil Import'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _hasilBaris('Ditambahkan', ditambah, const Color(0xFF16A34A)),
              _hasilBaris('Sudah ada (skip)', sudah, const Color(0xFFD97706)),
              _hasilBaris('Error', errors.length, Colors.red.shade700),
              if (errors.isNotEmpty) ...[
                const SizedBox(height: 12),
                const Text('Rincian:', style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Flexible(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        for (final e in errors.take(8))
                          Text('Baris ${e['baris']}: ${e['pesan']}',
                              style: const TextStyle(fontSize: 12)),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),
          actions: [
            FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Tutup')),
          ],
        ),
      );
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Widget _hasilBaris(String label, int value, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 150,
            child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Text('$value', style: TextStyle(fontWeight: FontWeight.w800, color: color)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Kelas & Murid (${_kelas.length})',
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
              IconButton.filledTonal(
                tooltip: 'Template Excel',
                onPressed: _downloadTemplate,
                icon: const Icon(Icons.description_outlined),
              ),
              IconButton.filledTonal(
                tooltip: 'Export Excel',
                onPressed: _exportXlsx,
                icon: const Icon(Icons.download_outlined),
              ),
              IconButton.filledTonal(
                tooltip: 'Import Excel',
                onPressed: _importXlsx,
                icon: const Icon(Icons.upload_file_outlined),
              ),
              IconButton.filledTonal(
                tooltip: 'Tambah Kelas',
                onPressed: () => _form(),
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<int>(
                  initialValue: _tahunDipilih,
                  isDense: true,
                  decoration: const InputDecoration(
                    labelText: 'Tahun Ajaran',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final t in _tahun)
                      DropdownMenuItem(
                        value: t['id'] as int,
                        child: Text(
                            '${t['nama']}${t['is_active'] == true ? ' (Aktif)' : ''}',
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged: (v) => setState(() {
                    _tahunDipilih = v;
                    _load();
                  }),
                ),
              ),
              if (context.watch<AuthState>().isAdmin) ...[
                const SizedBox(width: 8),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2563EB)),
                  onPressed: () => _openNaikKelas(),
                  icon: const Icon(Icons.trending_up, size: 18),
                  label: const Text('Naik Kelas'),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Center(child: CircularProgressIndicator())
          else
            Expanded(
              child: _kelas.isEmpty
                  ? Center(child: Text('Belum ada kelas', style: TextStyle(color: scheme.onSurfaceVariant)))
                  : ListView.separated(
                      itemCount: _kelas.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 8),
                      itemBuilder: (context, i) {
                        final k = _kelas[i];
                        return Card(
                          child: ListTile(
                            onTap: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => ClassDetailScreen(kelas: k),
                              ),
                            ),
                            leading: CircleAvatar(
                              backgroundColor: scheme.primaryContainer,
                              child: Text('${k['jumlah_murid']}',
                                  style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onPrimaryContainer)),
                            ),
                            title: Text(k['nama_kelas'] ?? '-',
                                maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontWeight: FontWeight.w600)),
                            subtitle: Text('${k['jumlah_murid']} murid'),
                            trailing: PopupMenuButton<String>(
                              tooltip: 'Menu',
                              onSelected: (v) => switch (v) {
                                'pdf' => _downloadQrPdf(k),
                                'edit' => _form(k: k),
                                _ => _delete(k),
                              },
                              itemBuilder: (_) => [
                                const PopupMenuItem(
                                  value: 'pdf',
                                  child: ListTile(
                                    leading: Icon(Icons.picture_as_pdf_outlined,
                                        color: Color(0xFFDC2626)),
                                    title: Text('QR PDF (semua murid)'),
                                    dense: true,
                                  ),
                                ),
                                const PopupMenuItem(
                                  value: 'edit',
                                  child: ListTile(
                                    leading: Icon(Icons.edit_outlined),
                                    title: Text('Edit'),
                                    dense: true,
                                  ),
                                ),
                                PopupMenuItem(
                                  value: 'delete',
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
                        );
                      },
                    ),
            ),
        ],
      ),
    );
  }
}
