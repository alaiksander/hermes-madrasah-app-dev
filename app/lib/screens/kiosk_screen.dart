import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../services/absensi_scanner.dart';
import '../services/auth_state.dart';

/// Kiosk View — layar gedhe ing gerbang + scanner barcode 2D (USB/BT).
/// Scanner "ngetik" UUID + Enter menyang input invisible → proses absen.
/// Back button diblokir (PopScope); metu mung liwat dialog konfirmasi.
class KioskScreen extends StatefulWidget {
  const KioskScreen({super.key});

  @override
  State<KioskScreen> createState() => _KioskScreenState();
}

class _KioskScreenState extends State<KioskScreen> {
  late final AbsensiScanner _scanner;
  final _inputFocus = FocusNode();
  final _inputCtrl = TextEditingController();
  Timer? _jamTimer;
  Timer? _hasilTimer;
  Timer? _autoSubmitTimer;

  String _jam = '--:--:--';
  String _tanggal = '';
  int _countToday = 0;
  ScanOutcome? _hasil;
  final List<_RiwayatEntry> _riwayat = [];

  @override
  void initState() {
    super.initState();
    _scanner = AbsensiScanner(
      api: context.read<AuthState>().api,
      onResult: _tampilHasil,
      onSuccess: _loadCount,
    );
    _loadCount();
    _updateJam();
    _jamTimer = Timer.periodic(const Duration(seconds: 1), (_) => _updateJam());
    // Layar ora mati sajrone kiosk
    WakelockPlus.enable();
  }

  @override
  void dispose() {
    _jamTimer?.cancel();
    _hasilTimer?.cancel();
    _autoSubmitTimer?.cancel();
    _scanner.dispose();
    _inputFocus.dispose();
    _inputCtrl.dispose();
    WakelockPlus.disable();
    super.dispose();
  }

  void _updateJam() {
    final now = DateTime.now();
    String dua(int v) => v.toString().padLeft(2, '0');
    setState(() {
      _jam = '${dua(now.hour)}:${dua(now.minute)}:${dua(now.second)}';
      _tanggal = [
        'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'
      ][now.weekday - 1];
      _tanggal = '$_tanggal, ${dua(now.day)}-${dua(now.month)}-${now.year}';
    });
  }

  Future<void> _loadCount() async {
    try {
      final res = await context.read<AuthState>().api.get('/api/absensi/hari-ini');
      if (mounted) setState(() => _countToday = (res as List).length);
    } catch (_) {/* abaikan */}
  }

  void _tampilHasil(ScanOutcome o) {
    if (!mounted) return;
    _hasilTimer?.cancel();
    setState(() {
      _hasil = o;
      // Simpan riwayat (maks 6)
      _riwayat.insert(0, _RiwayatEntry(
        nama: o.nama ?? '',
        kelas: o.kelas ?? '',
        status: o.status,
        color: o.color,
      ));
      if (_riwayat.length > 6) _riwayat.removeLast();
    });
    _hasilTimer = Timer(const Duration(seconds: 4), () {
      if (mounted) setState(() => _hasil = null);
    });
  }

  /// Scanner 2D ngirim UUID + Enter (onSubmitted). Yen scanner tanpa Enter,
  /// auto-submit nalika teks lengkap 36 karakter.
  void _onInput(String v) {
    _autoSubmitTimer?.cancel();
    if (v.trim().length >= 36) {
      _kirim();
      return;
    }
    _autoSubmitTimer = Timer(const Duration(milliseconds: 250), _kirim);
  }

  void _kirim() {
    final raw = _inputCtrl.text.trim();
    _inputCtrl.clear();
    if (raw.isNotEmpty) _scanner.process(raw);
  }

  Future<void> _keluar() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Keluar dari Mode Kiosk?'),
        content: const Text('Layar kiosk akan ditutup.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Batal'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Keluar'),
          ),
        ],
      ),
    );
    if (ok == true && mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _keluar();
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF0B1220),
        body: SafeArea(
          child: Column(
            children: [
              // ── Top bar: jam + tanggal + counter ──
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                child: Row(
                  children: [
                    IconButton(
                      tooltip: 'Keluar kiosk',
                      onPressed: _keluar,
                      icon: const Icon(Icons.lock_outline,
                          color: Colors.white54, size: 20),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        children: [
                          Text(_jam,
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 34,
                                  fontWeight: FontWeight.w700,
                                  fontFeatures: [FontFeature.tabularFigures()])),
                          Text(_tanggal,
                              style: const TextStyle(
                                  color: Colors.white54, fontSize: 12)),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF16A34A),
                        borderRadius: BorderRadius.circular(30),
                      ),
                      child: Text('Hari ini: $_countToday',
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14)),
                    ),
                  ],
                ),
              ),
              const Divider(color: Colors.white12, height: 24),
              // ── Area hasil gedhe ──
              Expanded(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 300),
                  child: _hasil == null
                      ? const _KosongView()
                      : _HasilView(
                          key: ValueKey(_hasil!.pesan),
                          hasil: _hasil!,
                        ),
                ),
              ),
              // ── Riwayat ──
              SizedBox(
                height: 46,
                child: _riwayat.isEmpty
                    ? const Center(
                        child: Text('Belum ada scan hari ini',
                            style: TextStyle(color: Colors.white38)))
                    : ListView.separated(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        itemCount: _riwayat.length,
                        separatorBuilder: (_, _) => const SizedBox(width: 8),
                        itemBuilder: (_, i) {
                          final r = _riwayat[i];
                          return Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: r.color.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                  color: r.color.withValues(alpha: 0.6)),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.check_circle,
                                    color: r.color, size: 14),
                                const SizedBox(width: 5),
                                Text(
                                  '${r.nama.isEmpty ? '?' : r.nama} · ${r.kelas}',
                                  style: const TextStyle(
                                      color: Colors.white, fontSize: 12),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
              ),
              const SizedBox(height: 10),
              // ── Input invisible (scanner ngetik ing kene) ──
              Opacity(
                opacity: 0,
                child: TextField(
                  focusNode: _inputFocus,
                  controller: _inputCtrl,
                  autofocus: true,
                  enableSuggestions: false,
                  autocorrect: false,
                  onChanged: _onInput,
                  onSubmitted: (_) => _kirim(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _KosongView extends StatelessWidget {
  const _KosongView();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(28),
            decoration: BoxDecoration(
              color: Colors.white10,
              borderRadius: BorderRadius.circular(24),
            ),
            child: const Icon(Icons.qr_code_scanner,
                size: 88, color: Colors.white70),
          ),
          const SizedBox(height: 20),
          const Text('SILAKAN SCAN KARTU',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2)),
          const SizedBox(height: 8),
          const Text('Tempelkan kartu QR ke scanner',
              style: TextStyle(color: Colors.white54, fontSize: 14)),
        ],
      ),
    );
  }
}

class _HasilView extends StatelessWidget {
  const _HasilView({super.key, required this.hasil});

  final ScanOutcome hasil;

  @override
  Widget build(BuildContext context) {
    final nama = hasil.nama ?? '';
    final inisial = nama.isEmpty
        ? '?'
        : nama.split(' ').take(2).map((w) => w.isNotEmpty ? w[0] : '').join();
    return Center(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 20),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        decoration: BoxDecoration(
          color: hasil.color,
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
                color: hasil.color.withValues(alpha: 0.45),
                blurRadius: 40,
                spreadRadius: 2),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(hasil.status == 'hadir'
                ? '✅ HADIR'
                : hasil.status == 'duplikat'
                    ? '⚠️ SUDAH ABSEN'
                    : hasil.status == 'libur'
                        ? '📅 LIBUR'
                        : '❌ GAGAL',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.5)),
            const SizedBox(height: 14),
            CircleAvatar(
              radius: 34,
              backgroundColor: Colors.white24,
              child: Text(inisial.toUpperCase(),
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.w800)),
            ),
            const SizedBox(height: 12),
            Text(nama.isEmpty ? hasil.pesan : nama,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 30,
                    fontWeight: FontWeight.w800)),
            if (hasil.kelas != null && hasil.kelas!.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('Kelas ${hasil.kelas}',
                  style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.85),
                      fontSize: 16)),
            ],
            const SizedBox(height: 10),
            Text(hasil.pesan,
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.9), fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

class _RiwayatEntry {
  final String nama;
  final String kelas;
  final String status;
  final Color color;
  _RiwayatEntry({
    required this.nama,
    required this.kelas,
    required this.status,
    required this.color,
  });
}
