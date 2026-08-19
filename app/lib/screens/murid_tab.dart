import 'dart:async';
import 'dart:typed_data';

import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

class MuridTab extends StatefulWidget {
  const MuridTab({super.key, this.kelasId, this.kelasNama, this.lulusMode = false});

  /// Yen diisi, daftar murid mung kanggo kelas iku (dipake ClassDetailScreen).
  final int? kelasId;
  final String? kelasNama;

  /// Mode "lulus": nampilake murid non-aktif (lulus) kelas kasebut.
  final bool lulusMode;

  @override
  State<MuridTab> createState() => _MuridTabState();
}

class _MuridTabState extends State<MuridTab> {
  final _search = TextEditingController();
  Timer? _debounce;
  List<dynamic> _murid = [];
  List<dynamic> _kelas = [];
  bool _loading = true;
  String _q = '';
  int? _filterKelas;
  bool _semua = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final api = context.read<AuthState>().api;
    try {
      final params = <String, String>{
        'q': _q,
        'per_page': '100',
        if (widget.lulusMode) 'semua': 'true',
        if (widget.kelasId != null)
          'kelas_id': '${widget.kelasId}'
        else if (_filterKelas != null)
          'kelas_id': '$_filterKelas',
        if (_semua) 'semua': 'true',
      };
      final hasil = await Future.wait([
        api.get('/api/murid', params),
        api.get('/api/kelas'),
      ]);
      if (!mounted) return;
      setState(() {
        _murid = (hasil[0]['items'] as List? ?? []);
        _kelas = hasil[1] as List;
        _loading = false;
      });
    } on ApiException catch (e) {
      _snack(e.message, error: true);
      if (mounted) setState(() => _loading = false);
    }
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      _q = q.trim();
      _load();
    });
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Future<void> _form({Map<String, dynamic>? m}) async {
    final nisn = TextEditingController(text: m?['nisn'] ?? '');
    final nama = TextEditingController(text: m?['nama'] ?? '');
    final namaOrtu = TextEditingController(text: m?['nama_ortu'] ?? '');
    final telepon = TextEditingController(text: m?['telepon'] ?? '');
    int? kelasId = m?['kelas_id'] ??
        widget.kelasId ??
        (_kelas.isNotEmpty ? _kelas.first['id'] as int : null);

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: Text(m == null ? 'Tambah Murid' : 'Edit Murid'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nisn, decoration: const InputDecoration(labelText: 'NISN (10 digit, opsional)', hintText: 'contoh: 2400000001')),
                const SizedBox(height: 10),
                TextField(controller: nama, decoration: const InputDecoration(labelText: 'Nama Lengkap')),
                const SizedBox(height: 10),
                DropdownButtonFormField<int>(
                  initialValue: kelasId,
                  decoration: const InputDecoration(labelText: 'Kelas'),
                  items: [
                    for (final k in _kelas)
                      DropdownMenuItem(
                          value: k['id'] as int,
                          child: Text(k['tahun_ajaran_nama'] != null
                              ? '${k['nama_kelas']} (${k['tahun_ajaran_nama']})'
                              : k['nama_kelas'])),
                  ],
                  onChanged: (v) => setState(() => kelasId = v),
                ),
                const SizedBox(height: 10),
                TextField(controller: namaOrtu, decoration: const InputDecoration(labelText: 'Nama Orang Tua')),
                const SizedBox(height: 10),
                TextField(controller: telepon,
                    decoration: const InputDecoration(labelText: 'Telepon (opsional)', hintText: '628xxxxxxxxxx')),
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
    if (ok != true) return;
    if (!mounted) return;

    final body = {
      'nisn': nisn.text.trim().isEmpty ? null : nisn.text.trim(),
      'nama': nama.text.trim(),
      'kelas_id': kelasId,
      'nama_ortu': namaOrtu.text.trim(),
      'telepon': telepon.text.trim(),
    };
    try {
      if (m == null) {
        await context.read<AuthState>().api.post('/api/murid', body);
        _snack('Murid ditambahkan');
      } else {
        await context.read<AuthState>().api.patch('/api/murid/${m['id']}', body);
        _snack('Murid diperbarui');
      }
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _showQr(dynamic m) async {
    try {
      final Uint8List bytes =
          await context.read<AuthState>().api.getBytes('/api/murid/${m['id']}/qr.png');
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
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                Text('${m['nisn'] ?? '-'} • ${m['kelas_nama'] ?? '-'}',
                    style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                const SizedBox(height: 16),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('Tutup'),
                    ),
                    const SizedBox(width: 8),
                    FilledButton.tonalIcon(
                      icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                      label: const Text('Download PDF'),
                      onPressed: () {
                        Navigator.pop(ctx);
                        _downloadQrPdfMurid(m);
                      },
                    ),
                  ],
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

  Future<void> _downloadQrPdfMurid(dynamic m) async {
    try {
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/murid/${m['id']}/qr.pdf');
      await FileSaver.instance.saveFile(
        name: 'qr-${m['nisn'] ?? m['id']}',
        bytes: bytes,
        fileExtension: 'pdf',
        mimeType: MimeType.custom,
        customMimeType: 'application/pdf',
      );
      _snack('PDF QR ${m['nama']} diunduh');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } catch (_) {
      _snack('Gagal membuat PDF', error: true);
    }
  }

  String _fmtD(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';
  String _isoD(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

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
              Text('Pilih rentang tanggal', style: TextStyle(
                  fontSize: 12, color: Theme.of(ctx).colorScheme.onSurfaceVariant)),
              const SizedBox(height: 8),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event),
                title: const Text('Dari'),
                subtitle: Text(_fmtD(dari)),
                onTap: () async {
                  final p = await pick(dari);
                  if (p != null && ctx.mounted) setLocal(() => dari = p);
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event_available),
                title: const Text('Sampai'),
                subtitle: Text(_fmtD(sampai)),
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

    try {
      final bytes = await context.read<AuthState>().api.getBytes(
          '/api/absensi/pdf/${m['id']}?dari=${_isoD(dari)}&sampai=${_isoD(sampai)}');
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

  Future<void> _archive(dynamic m) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Arsipkan Murid?'),
        content: Text(
            '${m['nama']} tidak akan muncul di absensi/scanner, namun data absensi tetap tersimpan.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Arsipkan'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;
    try {
      await context.read<AuthState>().api.delete('/api/murid/${m['id']}');
      _snack('Murid diarsipkan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _reactivate(dynamic m) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Aktifkan Kembali?'),
        content: Text(
            '${m['nama']} akan muncul lagi di absensi/scanner dan daftar murid aktif.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Aktifkan'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;
    try {
      await context.read<AuthState>().api
          .patch('/api/murid/${m['id']}', {'is_active': true});
      _snack('${m['nama']} diaktifkan kembali');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: _search,
            onChanged: _onChanged,
            decoration: InputDecoration(
              hintText: 'Cari nama atau NISN…',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _loading
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: CircularProgressIndicator(strokeWidth: 2.5))
                  : null,
            ),
          ),
          const SizedBox(height: 12),
          if (widget.kelasId == null) ...[
            // Filter global: kelas + termasuk lulus
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<int?>(
                    initialValue: _filterKelas,
                    isDense: true,
                    decoration: const InputDecoration(
                      labelText: 'Kelas',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                          value: null, child: Text('Semua Kelas')),
                      for (final k in _kelas)
                        DropdownMenuItem(
                            value: k['id'] as int,
                            child: Text(k['tahun_ajaran_nama'] != null
                                ? '${k['nama_kelas']} (${k['tahun_ajaran_nama']})'
                                : k['nama_kelas'] as String? ?? '-')),
                    ],
                    onChanged: (v) => setState(() {
                      _filterKelas = v;
                      _load();
                    }),
                  ),
                ),
                const SizedBox(width: 8),
                FilterChip(
                  label: const Text('Lulus'),
                  selected: _semua,
                  onSelected: (v) => setState(() {
                    _semua = v;
                    _load();
                  }),
                ),
              ],
            ),
            const SizedBox(height: 8),
          ],
          Row(
            children: [
              Text(
                  widget.lulusMode
                      ? 'Murid Lulus ${widget.kelasNama ?? ''} (${_murid.length})'
                      : (widget.kelasNama != null
                          ? 'Murid ${widget.kelasNama} (${_murid.length})'
                          : 'Murid (${_murid.length})'),
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const Spacer(),
              if (!widget.lulusMode)
                IconButton.filledTonal(
                  tooltip: 'Tambah Murid',
                  onPressed: _kelas.isEmpty ? null : () => _form(),
                  icon: const Icon(Icons.add),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _murid.isEmpty
                    ? Center(child: Text('Belum ada murid', style: TextStyle(color: scheme.onSurfaceVariant)))
                    : ListView.separated(
                        itemCount: _murid.length,
                        separatorBuilder: (_, _) => const SizedBox(height: 8),
                        itemBuilder: (context, i) {
                          final m = _murid[i];
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: scheme.primaryContainer,
                                child: Text(
                                  (m['nama'] as String? ?? '?').substring(0, 1).toUpperCase(),
                                  style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onPrimaryContainer),
                                ),
                              ),
                              title: Text(m['nama'] ?? '-',
                                  maxLines: 1, overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontWeight: FontWeight.w600)),
                              subtitle: Text('${m['nisn'] ?? '-'} • ${m['kelas_nama'] ?? '-'}',
                                  maxLines: 1, overflow: TextOverflow.ellipsis),
                              trailing: PopupMenuButton<String>(
                                tooltip: 'Menu',
                                onSelected: (v) => switch (v) {
                                  'qr' => _showQr(m),
                                  'edit' => _form(m: m),
                                  'pdf' => _exportPdf(m),
                                  _ => widget.lulusMode ? _reactivate(m) : _archive(m),
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
                                    value: 'edit',
                                    child: ListTile(
                                      leading: Icon(Icons.edit_outlined),
                                      title: Text('Edit'),
                                      dense: true,
                                    ),
                                  ),
                                  const PopupMenuItem(
                                    value: 'pdf',
                                    child: ListTile(
                                      leading: Icon(Icons.picture_as_pdf_outlined,
                                          color: Color(0xFFDC2626)),
                                      title: Text('Ekspor PDF Absensi'),
                                      dense: true,
                                    ),
                                  ),
                                  PopupMenuItem(
                                    value: 'arsip',
                                    child: ListTile(
                                      leading: Icon(
                                          widget.lulusMode
                                              ? Icons.person_add_alt_1_outlined
                                              : Icons.archive_outlined,
                                          color: widget.lulusMode
                                              ? const Color(0xFF2563EB)
                                              : scheme.error),
                                      title: Text(
                                          widget.lulusMode
                                              ? 'Aktifkan kembali'
                                              : 'Arsipkan',
                                          style: TextStyle(
                                              color: widget.lulusMode
                                                  ? const Color(0xFF2563EB)
                                                  : scheme.error)),
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
