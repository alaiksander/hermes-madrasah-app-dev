import 'package:flutter/material.dart';

import 'alert_section.dart';
import 'audit_section.dart';
import 'backup_section.dart';
import 'plans_section.dart';
import 'platform_settings_section.dart';
import 'section_screen.dart';

/// Pengaturan Platform (khusus Super Admin) — menu kartu.
/// Saben entri diklik → mbukak settingane dhewe (SectionScreen).
class SuperAdminSettingsScreen extends StatelessWidget {
  const SuperAdminSettingsScreen({super.key});

  Widget _entry(BuildContext context,
      {required IconData icon,
      required Color color,
      required String title,
      required String subtitle,
      required Widget section}) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(icon, color: color),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12.5, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
              builder: (_) => SectionScreen(title: title, child: section)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pengaturan Platform',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _entry(context,
              icon: Icons.notifications_active_outlined,
              color: const Color(0xFF16A34A),
              title: 'Notifikasi Super Admin',
              subtitle: 'Alert Telegram otomatis: disk, RAM, backup gagal, tenant expired',
              section: const AlertSection()),
          _entry(context,
              icon: Icons.palette_outlined,
              color: const Color(0xFF2563EB),
              title: 'Identitas & Pemeliharaan',
              subtitle: 'Logo, nama aplikasi default, mode maintenance',
              section: const PlatformSettingsSection()),
          _entry(context,
              icon: Icons.workspace_premium_outlined,
              color: const Color(0xFFD97706),
              title: 'Paket & Kuota',
              subtitle: 'Definisi plan: max murid, max guru, fitur',
              section: const PlansSection()),
          _entry(context,
              icon: Icons.history,
              color: const Color(0xFF6B7280),
              title: 'Audit Trail',
              subtitle: 'Jejak aksi sensitif: siapa + kapan',
              section: const AuditSection()),
          _entry(context,
              icon: Icons.backup_outlined,
              color: const Color(0xFF7C3AED),
              title: 'Backup & Pemulihan',
              subtitle: 'Jadwal otomatis, backup manual, riwayat',
              section: const BackupSection()),
        ],
      ),
    );
  }
}
