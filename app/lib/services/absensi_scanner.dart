import 'package:flutter/material.dart';

import 'api.dart';
import 'feedback.dart';

/// Hasil siji scan — dipakai ScanScreen lan KioskScreen (shared).
class ScanOutcome {
  final String status; // hadir | duplikat | libur | error
  final String pesan;
  final String? nama;
  final String? kelas;
  final int? telatMenit;
  final Color color;

  ScanOutcome({
    required this.status,
    required this.pesan,
    required this.color,
    this.nama,
    this.kelas,
    this.telatMenit,
  });
}

/// Logika absen QR sing di-share: POST /api/absensi/scan + dedup 3 detik +
/// beep + mapping status → warna. Dipakai kamera (ScanScreen) lan scanner
/// barcode (KioskScreen) — siji otak, ora dobel logika.
class AbsensiScanner {
  AbsensiScanner({
    required this.api,
    required this.onResult,
    this.onSuccess,
  });

  final ApiClient api;
  final void Function(ScanOutcome outcome) onResult;

  /// Dipanggil sawise scan sukses (status hadir/duplikat) — kanggo refresh
  /// counter utawa reset timer mode daya.
  final VoidCallback? onSuccess;

  bool _processing = false;
  String? _lastUuid;
  DateTime? _lastTime;

  Color _warna(String status) {
    switch (status) {
      case 'hadir':
        return const Color(0xFF16A34A);
      case 'duplikat':
        return const Color(0xFFD97706);
      case 'libur':
        return const Color(0xFF0284C7);
      default:
        return const Color(0xFFDC2626);
    }
  }

  /// Proses UUID mentah (saka kamera utawa scanner 2D).
  Future<void> process(String raw) async {
    final uuid = raw.trim();
    if (uuid.isEmpty || _processing) return;

    // Dedup 3 detik — scanner kadang kirim 2× UUID padha
    final now = DateTime.now();
    if (_lastUuid == uuid &&
        _lastTime != null &&
        now.difference(_lastTime!) < const Duration(seconds: 3)) {
      return;
    }
    _lastUuid = uuid;
    _lastTime = now;

    _processing = true;
    try {
      final res = await api.post('/api/absensi/scan', {'qr_uuid': uuid});
      successFeedback();
      final status = res['status'] as String? ?? '';
      final murid = res['murid'] as Map<String, dynamic>?;
      onResult(ScanOutcome(
        status: status,
        pesan: res['pesan'] as String? ?? '',
        color: _warna(status),
        nama: murid?['nama'] as String?,
        kelas: murid?['kelas_nama'] as String?,
        telatMenit: res['telat_menit'] as int?,
      ));
      onSuccess?.call();
    } on ApiException catch (e) {
      errorFeedback();
      onResult(ScanOutcome(
        status: 'error',
        pesan: e.message,
        color: const Color(0xFFDC2626),
      ));
    } catch (_) {
      onResult(ScanOutcome(
        status: 'error',
        pesan: 'Gagal terhubung ke server',
        color: const Color(0xFFDC2626),
      ));
    } finally {
      _processing = false;
    }
  }

  void dispose() {}
}
