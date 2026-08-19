import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import '../services/pick_file.dart';
import '../services/spreadsheet.dart';

class GuruTab extends StatefulWidget {
  const GuruTab({super.key});

  @override
  State<GuruTab> createState() => _GuruTabState();
}

class _GuruTabState extends State<GuruTab> {
  List<dynamic> _guru = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final res = await context.read<AuthState>().api.get('/api/guru');
      if (mounted) setState(() => _guru = res as List);
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
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

  Future<void> _add() async {
    final nama = TextEditingController();
    final username = TextEditingController();
    final password = TextEditingController();
    String role = 'guru';

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Tambah Guru'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nama, decoration: const InputDecoration(labelText: 'Nama Lengkap')),
                const SizedBox(height: 10),
                TextField(controller: username, decoration: const InputDecoration(labelText: 'Username')),
                const SizedBox(height: 10),
                TextField(controller: password, obscureText: true,
                    decoration: const InputDecoration(labelText: 'Password (min. 6 karakter)')),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  initialValue: role,
                  decoration: const InputDecoration(labelText: 'Role'),
                  items: const [
                    DropdownMenuItem(value: 'guru', child: Text('Guru')),
                    DropdownMenuItem(value: 'admin', child: Text('Admin')),
                  ],
                  onChanged: (v) => setState(() => role = v ?? 'guru'),
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
    if (ok != true) return;
    if (!mounted) return;

    try {
      await context.read<AuthState>().api.post('/api/guru', {
        'nama': nama.text.trim(),
        'username': username.text.trim(),
        'password': password.text,
        'role': role,
      });
      _snack('Guru ditambahkan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
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
          .postMultipart('/api/guru/import', picked.bytes, filename: picked.name);
      if (!mounted) return;
      final ditambah = (res['ditambahkan'] as num?)?.toInt() ?? 0;
      final sudah = (res['sudah_ada'] as num?)?.toInt() ?? 0;
      final pwdDefault = (res['password_default'] as num?)?.toInt() ?? 0;
      final errors = (res['error'] as List? ?? []);
      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Hasil Import Guru'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _hasilBaris('Ditambahkan', ditambah, const Color(0xFF16A34A)),
              _hasilBaris('Sudah ada (skip)', sudah, const Color(0xFFD97706)),
              if (pwdDefault > 0)
                _hasilBaris('Password default (guru1234)', pwdDefault, const Color(0xFF2563EB)),
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
      _load();
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
            width: 210,
            child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Text('$value', style: TextStyle(fontWeight: FontWeight.w800, color: color)),
        ],
      ),
    );
  }

  Future<void> _downloadTemplate() async {
    try {
      final bytes = await context.read<AuthState>().api
          .getBytes('/api/guru/template.xlsx');
      await FileSaver.instance.saveFile(
        name: 'template-import-guru',
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

  Future<void> _edit(dynamic g) async {
    final nama = TextEditingController(text: g['nama'] ?? '');
    final username = TextEditingController(text: g['username'] ?? '');
    String role = g['role'] == 'admin' ? 'admin' : 'guru';

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Edit Guru'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nama, decoration: const InputDecoration(labelText: 'Nama Lengkap')),
                const SizedBox(height: 10),
                TextField(controller: username,
                    decoration: const InputDecoration(labelText: 'Username')),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  initialValue: role,
                  decoration: const InputDecoration(labelText: 'Role'),
                  items: const [
                    DropdownMenuItem(value: 'guru', child: Text('Guru')),
                    DropdownMenuItem(value: 'admin', child: Text('Admin')),
                  ],
                  onChanged: (v) => setState(() => role = v ?? 'guru'),
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
    if (ok != true) return;
    if (!mounted) return;

    try {
      await context.read<AuthState>().api.patch('/api/guru/${g['id']}', {
        'nama': nama.text.trim(),
        'username': username.text.trim(),
        'role': role,
      });
      _snack('Guru diperbarui');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _resetPassword(dynamic g) async {
    final password = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Reset Password — ${g['nama']}'),
        content: TextField(
          controller: password,
          obscureText: true,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Password baru (min. 6 karakter)'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Simpan')),
        ],
      ),
    );
    if (ok != true || password.text.length < 6) return;
    if (!mounted) return;

    try {
      await context.read<AuthState>().api
          .post('/api/guru/${g['id']}/reset-password', {'password': password.text});
      _snack('Password berhasil direset');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _toggleActive(dynamic g) async {
    try {
      await context.read<AuthState>().api
          .patch('/api/guru/${g['id']}', {'is_active': !(g['is_active'] as bool? ?? true)});
      _snack(g['is_active'] == true ? 'Guru dinonaktifkan' : 'Guru diaktifkan');
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
          Row(
            children: [
              Text('Guru (${_guru.length})',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const Spacer(),
              IconButton.filledTonal(
                tooltip: 'Template Excel',
                onPressed: _downloadTemplate,
                icon: const Icon(Icons.description_outlined),
              ),
              IconButton.filledTonal(
                tooltip: 'Import Excel',
                onPressed: _importXlsx,
                icon: const Icon(Icons.upload_file_outlined),
              ),
              IconButton.filledTonal(
                tooltip: 'Tambah Guru',
                onPressed: _add,
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Center(child: CircularProgressIndicator())
          else
            Expanded(
              child: _guru.isEmpty
                  ? Center(child: Text('Belum ada guru', style: TextStyle(color: scheme.onSurfaceVariant)))
                  : ListView.separated(
                      itemCount: _guru.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 8),
                      itemBuilder: (context, i) {
                        final g = _guru[i];
                        final active = g['is_active'] as bool? ?? true;
                        final isSelf = g['username'] ==
                            context.watch<AuthState>().username;
                        return Card(
                          child: ListTile(
                            leading: CircleAvatar(
                              backgroundColor: scheme.primaryContainer,
                              child: Text(
                                (g['nama'] as String? ?? '?').substring(0, 1).toUpperCase(),
                                style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onPrimaryContainer),
                              ),
                            ),
                            title: Text(g['nama'] ?? '-',
                                maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontWeight: FontWeight.w600)),
                            subtitle: Text('@${g['username']} • ${g['role'] == 'admin' ? 'Admin' : 'Guru'}'),
                            trailing: PopupMenuButton<String>(
                              tooltip: 'Menu',
                              onSelected: (v) => switch (v) {
                                'edit' => _edit(g),
                                'reset' => _resetPassword(g),
                                _ => _toggleActive(g),
                              },
                              itemBuilder: (_) => [
                                PopupMenuItem(
                                  value: 'edit',
                                  enabled: !isSelf,
                                  child: ListTile(
                                    leading: Icon(Icons.edit_outlined,
                                        color: isSelf
                                            ? scheme.outlineVariant
                                            : scheme.primary),
                                    title: Text('Edit',
                                        style: TextStyle(
                                            color: isSelf
                                                ? scheme.outlineVariant
                                                : null)),
                                    dense: true,
                                  ),
                                ),
                                const PopupMenuItem(
                                  value: 'reset',
                                  child: ListTile(
                                    leading: Icon(Icons.password),
                                    title: Text('Reset Password'),
                                    dense: true,
                                  ),
                                ),
                                PopupMenuItem(
                                  value: 'status',
                                  enabled: !isSelf,
                                  child: ListTile(
                                    leading: Icon(
                                      active
                                          ? Icons.person_off_outlined
                                          : Icons.person_add_alt_1_outlined,
                                      color: isSelf
                                          ? scheme.outlineVariant
                                          : (active ? scheme.error : scheme.primary),
                                    ),
                                    title: Text(
                                      isSelf
                                          ? 'Akun sendiri'
                                          : (active ? 'Nonaktifkan' : 'Aktifkan'),
                                      style: TextStyle(
                                        color: isSelf
                                            ? scheme.outlineVariant
                                            : (active ? scheme.error : scheme.primary),
                                      ),
                                    ),
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
