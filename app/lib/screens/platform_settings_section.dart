import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import '../services/pick_file.dart';

/// Identitas platform (nama aplikasi + logo) lan mode pemeliharaan.
class PlatformSettingsSection extends StatefulWidget {
  const PlatformSettingsSection({super.key});

  @override
  State<PlatformSettingsSection> createState() => _PlatformSettingsSectionState();
}

class _PlatformSettingsSectionState extends State<PlatformSettingsSection> {
  final _namaCtrl = TextEditingController();
  bool _maintenance = false;
  bool _adaLogo = false;
  Uint8List? _logoBytes;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _namaCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final api = context.read<AuthState>().api;
      final res = await api.get('/api/super/settings') as Map<String, dynamic>;
      _namaCtrl.text = res['nama_aplikasi'] as String? ?? '';
      final adaLogo = res['logo'] == true;
      Uint8List? logo;
      if (adaLogo) {
        try {
          logo = await api.getBytes('/api/super/settings/logo');
        } catch (_) {/* logo optional */}
      }
      if (!mounted) return;
      setState(() {
        _maintenance = res['maintenance'] == true;
        _adaLogo = adaLogo;
        _logoBytes = logo;
      });
    } on ApiException catch (e) {
      if (mounted) _snack(e.message, error: true);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Future<void> _saveNama() async {
    setState(() => _busy = true);
    try {
      await context.read<AuthState>().api.put('/api/super/settings', {
        'nama_aplikasi': _namaCtrl.text.trim(),
      });
      _snack('Nama aplikasi disimpan');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Kompres/resize gambar dadi maks 512px PNG — foto HP (3-8MB) dadi
  /// ±50-200KB: upload cepet + DB ora kembung. Gagal → balekke asline.
  Future<Uint8List> _compressImage(Uint8List bytes) async {
    try {
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final img = frame.image;
      final w = img.width;
      final h = img.height;
      const maxSize = 512.0;
      final scale = (w > h ? w : h) > maxSize
          ? maxSize / (w > h ? w : h)
          : 1.0;
      final nw = (w * scale).round();
      final nh = (h * scale).round();
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      canvas.drawImageRect(
        img,
        Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()),
        Rect.fromLTWH(0, 0, nw.toDouble(), nh.toDouble()),
        Paint(),
      );
      final picture = recorder.endRecording();
      final out = await picture.toImage(nw, nh);
      final data = await out.toByteData(format: ui.ImageByteFormat.png);
      img.dispose();
      out.dispose();
      if (data != null) return data.buffer.asUint8List();
    } catch (_) {
      // kompresi gagal — pakai asline (backend saiki nampa nganti 10MB)
    }
    return bytes;
  }

  Future<void> _uploadLogo() async {
    final picked = await pickImageFile();
    if (picked == null || !mounted) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      final bytes = await _compressImage(picked.bytes);
      // filename .png supaya content-type multipart dadi image/png
      final res = await api.postMultipart('/api/super/settings/logo',
          bytes, filename: 'logo.png', fields: {});
      setState(() {
        _adaLogo = true;
        _logoBytes = bytes;
      });
      _snack('Logo diperbarui (${res['ukuran'] ?? bytes.length} B)');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _hapusLogo() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Hapus Logo?'),
        content: const Text('Logo platform akan dihapus permanen.'),
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
      await context.read<AuthState>().api.delete('/api/super/settings/logo');
      if (mounted) {
        setState(() {
          _adaLogo = false;
          _logoBytes = null;
        });
      }
      _snack('Logo dibusak');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _toggleMaintenance(bool v) async {
    if (v) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.warning_amber_outlined, color: Color(0xFFDC2626)),
          title: const Text('Aktifkan Mode Pemeliharaan?'),
          content: const Text(
              'Seluruh login guru/admin madrasah akan ditolak '
              '(pesan "sedang dalam pemeliharaan"). Superadmin tetap bisa '
              'masuk. Yakin aktifkan?'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Aktifkan'),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }
    if (!mounted) return;
    setState(() => _busy = true);
    try {
      await context.read<AuthState>().api.put('/api/super/settings', {
        'maintenance': v,
      });
      if (mounted) setState(() => _maintenance = v);
      if (mounted) {
        _snack(v
            ? 'Mode pemeliharaan AKTIF — login tenant ditolak'
            : 'Mode pemeliharaan dimatikan — normal maneh');
      }
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const ListTile(
            leading: CircleAvatar(
              backgroundColor: Color(0xFF2563EB),
              child: Icon(Icons.palette_outlined, color: Colors.white),
            ),
            title: Text('Identitas & Pemeliharaan',
                style: TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text('Branding platform + mode maintenance'),
          ),
          const Divider(height: 1),
          // Logo
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Row(
              children: [
                // Logo — persegi; tanpa logo → icon Lucide standar
                Container(
                  width: 56,
                  height: 56,
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(6),
                    color: scheme.surfaceContainerHighest,
                    border: Border.all(color: scheme.outlineVariant),
                  ),
                  child: _logoBytes != null
                      ? Image.memory(_logoBytes!, fit: BoxFit.cover)
                      : Icon(LucideIcons.graduationCap,
                          size: 30, color: scheme.onSurfaceVariant),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Logo aplikasi',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(
                        _adaLogo
                            ? 'Logo dipasang — terlihat di layar login tenant'
                            : 'Belum ada logo — digunakan di layar login',
                        style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                IconButton.filledTonal(
                  tooltip: 'Upload logo',
                  onPressed: _busy ? null : _uploadLogo,
                  icon: const Icon(Icons.upload_outlined, size: 20),
                ),
                if (_adaLogo)
                  IconButton(
                    tooltip: 'Hapus logo',
                    onPressed: _busy ? null : _hapusLogo,
                    icon: Icon(Icons.delete_outline, color: scheme.error),
                  ),
              ],
            ),
          ),
          // Nama aplikasi
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: TextField(
              controller: _namaCtrl,
              decoration: const InputDecoration(
                labelText: 'Nama aplikasi default',
                helperText: 'Digunakan untuk madrasah baru (whitelabel)',
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _busy ? null : _saveNama,
                icon: const Icon(Icons.save_outlined, size: 18),
                label: const Text('Simpan Identitas'),
              ),
            ),
          ),
          const Divider(height: 1),
          SwitchListTile(
            title: const Text('Mode Pemeliharaan',
                style: TextStyle(fontWeight: FontWeight.w600)),
            subtitle: const Text(
                'Semua login tenant ditolak — superadmin tetap bisa'),
            value: _maintenance,
            onChanged: _busy ? null : _toggleMaintenance,
            activeThumbColor: Colors.red.shade700,
          ),
        ],
      ),
    );
  }
}
