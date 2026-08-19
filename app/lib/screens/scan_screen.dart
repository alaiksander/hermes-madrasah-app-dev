import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';

import '../services/absensi_scanner.dart';
import '../services/auth_state.dart';
import 'kiosk_screen.dart';

/// Layar scan QR di gerbang — kamera langsung mbukak, beep, murid mlebu.
/// Mode daya (dari Pengaturan admin):
/// - standar: kamera terus aktif
/// - hemat  : kamera mati otomatis setelah X menit tanpa scan (tap → nyala)
/// - ekstrim: kamera mati default, tombol "Aktifkan Scanner" (jendela Y detik)
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
  late final AbsensiScanner _scanner;
  int _countToday = 0;
  _ScanResult? _result;
  Timer? _hideTimer;

  // ── Power saving (setelan admin) ──
  String _mode = 'standar';
  int _idleMenit = 5;
  int _aktifDetik = 30;
  bool _sleeping = false; // kamera mati (idle hemat / default ekstrim)
  Timer? _idleTimer;
  Timer? _activeTimer;

  @override
  void initState() {
    super.initState();
    _scanner = AbsensiScanner(
      api: context.read<AuthState>().api,
      onResult: (o) => _showResult(o.pesan, o.color),
      onSuccess: _setelahScan,
    );
    _loadCount();
    _loadSettings();
  }

  /// Sawise scan sukses: reset timer mode daya (rolling) + refresh counter.
  void _setelahScan() {
    _loadCount();
    if (_mode == 'hemat') _resetIdle();
    if (_mode == 'ekstrim') {
      _activeTimer?.cancel();
      _activeTimer = Timer(Duration(seconds: _aktifDetik), _sleep);
    }
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    _idleTimer?.cancel();
    _activeTimer?.cancel();
    _scanner.dispose();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _loadCount() async {
    try {
      final res = await context.read<AuthState>().api.get('/api/absensi/hari-ini');
      if (mounted) setState(() => _countToday = (res as List).length);
    } catch (_) {/* abaikan */}
  }

  Future<void> _loadSettings() async {
    try {
      final res = await context.read<AuthState>().api.get('/api/pengaturan');
      if (!mounted) return;
      setState(() {
        _mode = res['scan_mode'] as String? ?? 'standar';
        _idleMenit = res['scan_idle_menit'] as int? ?? 5;
        _aktifDetik = res['scan_aktif_detik'] as int? ?? 30;
      });
      if (_mode == 'ekstrim') {
        try {
          await _controller.stop();
        } catch (_) {}
        if (mounted) {
          setState(() {
            _sleeping = true;
          });
        }
      } else if (_mode == 'hemat') {
        _resetIdle();
      }
    } catch (_) {/* setelan gagal — tetep standar */}
  }

  void _resetIdle() {
    _idleTimer?.cancel();
    if (_mode != 'hemat') {
      return;
    }
    _idleTimer = Timer(Duration(minutes: _idleMenit), _sleep);
  }

  Future<void> _sleep() async {
    _idleTimer?.cancel();
    _activeTimer?.cancel();
    try {
      await _controller.stop();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _sleeping = true;
    });
  }

  Future<void> _wake() async {
    try {
      await _controller.start();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _sleeping = false;
    });
    if (_mode == 'hemat') {
      _resetIdle();
    } else if (_mode == 'ekstrim') {
      _activeTimer?.cancel();
      _activeTimer =
          Timer(Duration(seconds: _aktifDetik), _sleep);
    }
  }

  void _showResult(String text, Color color) {
    _hideTimer?.cancel();
    setState(() => _result = _ScanResult(text, color));
    _hideTimer = Timer(const Duration(milliseconds: 2600), () {
      if (mounted) setState(() => _result = null);
    });
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    final raw = capture.barcodes.isNotEmpty ? capture.barcodes.first.rawValue : null;
    if (raw == null) return;
    await _scanner.process(raw);
  }

  String get _modeLabel => switch (_mode) {
        'hemat' => 'Mode Hemat',
        'ekstrim' => 'Mode Ekstrim',
        _ => 'Mode Standar',
      };

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Stack(
      children: [
        // ── Kamera full-screen ──
        Positioned.fill(
          child: MobileScanner(
            controller: _controller,
            onDetect: _onDetect,
          ),
        ),
        // ── Overlay guide QR (mung yen kamera aktif) ──
        if (!_sleeping)
          Center(
            child: Container(
              width: 240,
              height: 240,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white.withValues(alpha: 0.9), width: 3),
                borderRadius: BorderRadius.circular(20),
                color: Colors.black26,
              ),
              child: const Icon(Icons.qr_code_2, size: 120, color: Colors.white70),
            ),
          ),
        // ── Counter dina iki + chip mode ──
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Material(
                  color: scheme.primary,
                  borderRadius: BorderRadius.circular(30),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    child: Row(
                      children: [
                        const Icon(Icons.check_circle, color: Colors.white, size: 18),
                        const SizedBox(width: 6),
                        Text('Hari ini: $_countToday',
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                if (_mode != 'standar')
                  Material(
                    color: _sleeping
                        ? scheme.error
                        : const Color(0xFF16A34A),
                    borderRadius: BorderRadius.circular(30),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(_sleeping ? Icons.battery_alert : Icons.battery_charging_full,
                              color: Colors.white, size: 16),
                          const SizedBox(width: 5),
                          Text(_sleeping ? 'Scanner Tidur' : _modeLabel,
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                const Spacer(),
                IconButton.filledTonal(
                  tooltip: 'Mode Kiosk (scanner barcode)',
                  onPressed: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const KioskScreen()),
                  ),
                  icon: const Icon(Icons.monitor),
                ),
                const SizedBox(width: 6),
                IconButton.filledTonal(
                  tooltip: 'Refresh counter',
                  onPressed: _loadCount,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
          ),
        ),
        // ── Overlay kamera mati (hemat idle / ekstrim default) ──
        if (_sleeping)
          Positioned.fill(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _mode == 'hemat' ? _wake : null,
              child: Container(
                color: Colors.black.withValues(alpha: 0.85),
                child: Center(
                  child: _mode == 'ekstrim'
                      ? Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.qr_code_scanner,
                                size: 64, color: Colors.white70),
                            const SizedBox(height: 14),
                            const Text('Scanner dalam mode hemat daya',
                                style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700)),
                            const SizedBox(height: 6),
                            Text(
                              'Aktif selama $_aktifDetik detik setiap kali dinyalakan',
                              style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.7),
                                  fontSize: 13),
                            ),
                            const SizedBox(height: 20),
                            FilledButton.icon(
                              onPressed: _wake,
                              icon: const Icon(Icons.qr_code_scanner),
                              label: const Text('Aktifkan Scanner'),
                              style: FilledButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 24, vertical: 14)),
                            ),
                          ],
                        )
                      : Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.battery_saver,
                                size: 64, color: Colors.white70),
                            const SizedBox(height: 14),
                            const Text('Hemat daya',
                                style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 18,
                                    fontWeight: FontWeight.w700)),
                            const SizedBox(height: 6),
                            Text(
                              'Tidak ada scan selama $_idleMenit menit — '
                              'sentuh layar untuk menyalakan',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.7),
                                  fontSize: 13),
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ),
        // ── Banner hasil scan ──
        if (_result != null)
          Positioned(
            left: 16,
            right: 16,
            bottom: 24,
            child: Material(
              color: _result!.color,
              borderRadius: BorderRadius.circular(16),
              elevation: 4,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Text(
                  _result!.text,
                  style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _ScanResult {
  final String text;
  final Color color;
  _ScanResult(this.text, this.color);
}
