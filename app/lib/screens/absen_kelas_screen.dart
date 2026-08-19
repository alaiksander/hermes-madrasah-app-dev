import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Absen per kelas (guru piket scan, admin bulk-input).
class AbsenKelasScreen extends StatefulWidget {
  const AbsenKelasScreen({super.key});

  @override
  State<AbsenKelasScreen> createState() => _AbsenKelasScreenState();
}

class _Row {
  final int muridId;
  final String nama;
  final String nisn;
  final String? statusRecord;
  final String? waktu;          // legacy (waktu masuk) — kept for back-compat
  final String? jamMasuk;       // HH:MM (2026-08-15 sesi pulang)
  final String? jamPulang;      // HH:MM
  final String? guru;
  String statusPilih;

  _Row({
    required this.muridId,
    required this.nama,
    required this.nisn,
    this.statusRecord,
    this.waktu,
    this.jamMasuk,
    this.jamPulang,
    this.guru,
    String? statusPilih,
  }) : statusPilih = statusPilih ?? 'hadir';

  bool get locked => statusRecord != null;
}

class _AbsenKelasScreenState extends State<AbsenKelasScreen> {
  List<dynamic> _kelas = [];
  List<_Row> _roster = [];
  int? _kelasId;
  String _kelasNama = '';
  DateTime _tgl = DateTime.now();
  bool _loading = true;
  bool _saving = false;
  bool _isAdmin = false;

  @override
  void initState() {
    super.initState();
    _loadKelas();
  }

  Future<void> _loadKelas() async {
    setState(() => _loading = true);
    try {
      final res = await context.read<AuthState>().api.get('/api/kelas');
      if (mounted) setState(() => _kelas = res as List);
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openKelas(dynamic k) async {
    setState(() {
      _kelasId = k['id'] as int;
      _kelasNama = k['nama_kelas'] as String? ?? '';
      _isAdmin = context.read<AuthState>().isAdmin;
    });
    await _loadRoster();
  }

  Future<void> _loadRoster() async {
    setState(() => _loading = true);
    try {
      final tgl = _iso(_tgl);
      final res = await context.read<AuthState>().api
          .get('/api/absensi/kelas/$_kelasId', {'tanggal': tgl});
      if (!mounted) return;
      setState(() {
        _roster = (res as List).map((m) => _Row(
              muridId: m['murid_id'] as int,
              nama: m['nama'] as String? ?? '-',
              nisn: m['nisn'] as String? ?? '-',
              statusRecord: m['status'] as String?,
              waktu: m['waktu'] as String?,
              jamMasuk: m['jam_masuk'] as String?,
              jamPulang: m['jam_pulang'] as String?,
              guru: m['guru'] as String?,
              statusPilih: (m['status'] as String?) ?? 'hadir',
            )).toList();
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

  String _jamStr(String? masuk, String? pulang, String? legacyWaktu) {
    // Tampilkan " • masuk 07:05" + (kalau ada) " • pulang 13:30"
    final t1 = masuk ?? (legacyWaktu != null && legacyWaktu.length >= 16
        ? legacyWaktu.substring(11, 16) : null);
    final t2 = pulang;
    if (t1 == null && t2 == null) return '';
    var out = '';
    if (t1 != null) out += ' • masuk $t1';
    if (t2 != null) out += ' • pulang $t2';
    return out;
  }

  String _iso(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  String _fmt(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';

  void _cycle(_Row row) {
    if (row.locked && !_isAdmin) {
      _snack('Sudah tercatat — hanya admin yang bisa mengubah', error: true);
      return;
    }
    setState(() {
      final i = _order.indexOf(row.statusPilih);
      row.statusPilih = _order[(i + 1) % _order.length];
    });
  }

  Future<void> _bulkSet(String status) async {
    if (_roster.isEmpty) return;
    setState(() => _saving = true);
    try {
      // Hanya yang BELUM tercatat (locked=false)
      final ids = _roster.where((r) => !r.locked).map((r) => r.muridId).toList();
      if (ids.isEmpty) {
        _snack('Semua murid sudah tercatat');
        return;
      }
      final res = await context.read<AuthState>().api.post(
        '/api/absensi/kelas/$_kelasId',
        {'tanggal': _iso(_tgl), 'entries': ids.map((id) => {'murid_id': id, 'status': status}).toList()},
      );
      if (!mounted) return;
      final added = (res['ditambahkan'] as int? ?? 0);
      _snack('${_labels[status]} ✓ $added ditambah');
      await _loadRoster();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _save() async {
    final entries = _roster.where((r) => !r.locked).map((r) => {
          'murid_id': r.muridId,
          'status': r.statusPilih,
        }).toList();
    if (entries.isEmpty) {
      _snack('Tidak ada yang perlu disimpan');
      return;
    }
    setState(() => _saving = true);
    try {
      final res = await context.read<AuthState>().api.post(
        '/api/absensi/kelas/$_kelasId',
        {'tanggal': _iso(_tgl), 'entries': entries},
      );
      if (!mounted) return;
      final added = (res['ditambahkan'] as int? ?? 0);
      _snack('${added} ditambah');
      await _loadRoster();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  static const _order = ['hadir', 'izin', 'sakit', 'alpa'];
  static const _labels = {
    'hadir': 'Hadir', 'izin': 'Izin', 'sakit': 'Sakit', 'alpa': 'Alpa',
  };
  static const _letters = {
    'hadir': 'H', 'izin': 'I', 'sakit': 'S', 'alpa': 'A',
  };
  // Colors: shade700 / lightBlue bukan const → pakai static final
  static final _colors = {
    'hadir': Colors.green,
    'izin': Colors.amber.shade700,
    'sakit': Colors.lightBlue,
    'alpa': Colors.red.shade700,
  };

  // Template versi pendek: siswa yang sudah tercatat dengan sesi pulang
  Future<void> _addKoreksi(_Row row) async {
    final ctrl = TextEditingController(
        text: '${row.jamMasuk != null ? row.jamMasuk : "07:00"}');
    final waktu = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Tambah Pulang — ${row.nama}'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('Siswa ini sudah absen masuk. Tambahkan pulang?'),
          const SizedBox(height: 8),
          TextField(
            controller: ctrl,
            keyboardType: TextInputType.datetime,
            decoration: const InputDecoration(
                labelText: 'Jam Pulang (HH:MM)', border: OutlineInputBorder()),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Batal')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text),
            child: const Text('Tambah'),
          ),
        ],
      ),
    );
    if (waktu == null || !mounted) return;
    setState(() => _saving = true);
    try {
      await context.read<AuthState>().api.post(
        '/api/absensi/koreksi',
        {'murid_id': row.muridId, 'mode': 'tambah_pulang', 'sesi': 'pulang', 'waktu': waktu},
      );
      _snack('Pulang ✓ ${row.nama} jam $waktu');
      await _loadRoster();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_kelasId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Absen Per Kelas')),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView.builder(
                itemCount: _kelas.length,
                padding: const EdgeInsets.all(12),
                itemBuilder: (_, i) {
                  final k = _kelas[i];
                  return Card(
                    child: ListTile(
                      title: Text(k['nama_kelas'] ?? '-'),
                      subtitle: Text('${k['jumlah_murid']} murid'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => _openKelas(k),
                    ),
                  );
                },
              ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: Text('$_kelasNama • ${_fmt(_tgl)}'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => setState(() {
            _kelasId = null;
            _roster = [];
          }),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_today),
            onPressed: () async {
              final picked = await showDatePicker(
                context: context,
                firstDate: DateTime(2024, 1, 1),
                lastDate: DateTime.now(),
                initialDate: _tgl,
              );
              if (picked != null) {
                setState(() => _tgl = picked);
                await _loadRoster();
              }
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              itemCount: _roster.length + 1,
              padding: const EdgeInsets.all(12),
              itemBuilder: (_, i) {
                if (i == _roster.length) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Column(children: [
                      Wrap(spacing: 8, children: _order.map((s) =>
                        OutlinedButton(
                          onPressed: _saving ? null : () => _bulkSet(s),
                          child: Text('Semua ${_labels[s]}'),
                        ),
                      ).toList()),
                      const SizedBox(height: 12),
                      FilledButton.icon(
                        icon: const Icon(Icons.save),
                        label: const Text('Simpan yang Belum Tercatat'),
                        onPressed: _saving ? null : _save,
                      ),
                    ]),
                  );
                }
                final r = _roster[i];
                final color = _colors[r.statusPilih] ?? Colors.grey;
                final editable = !r.locked || _isAdmin;
                return Card(
                  child: ListTile(
                    onTap: editable ? () => _cycle(r) : null,
                    leading: CircleAvatar(
                      backgroundColor: color.withValues(alpha: 0.15),
                      child: Text(
                        _letters[r.statusPilih]!,
                        style: TextStyle(
                            fontWeight: FontWeight.w800,
                            color: color, fontSize: 18),
                      ),
                    ),
                    title: Text(r.nama,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text(r.locked
                        ? '${_labels[r.statusRecord]}'
                            '${_jamStr(r.jamMasuk, r.jamPulang, r.waktu)}'
                            '${(r.guru ?? '').isNotEmpty ? ' • ${r.guru}' : ''}'
                        : 'NISN ${r.nisn} • ${_labels[r.statusPilih]}'),
                    trailing: r.locked && _isAdmin
                        ? IconButton(
                            tooltip: 'Tambah pulang',
                            icon: const Icon(Icons.logout, size: 18),
                            onPressed: _saving ? null : () => _addKoreksi(r),
                          )
                        : (!editable
                            ? const Icon(Icons.lock_outline, size: 18)
                            : null),
                  ),
                );
              },
            ),
    );
  }
}
