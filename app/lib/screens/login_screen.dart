import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../services/api.dart';
import '../services/auth_state.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _kode = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;
  bool _obscure = true;
  String? _errorMsg; // banner error inline (ora kesaput keyboard)
  String _appNama = 'Aplikasi Madrasah';
  Uint8List? _logo;

  @override
  void initState() {
    super.initState();
    _loadBranding();
  }

  /// Branding global saka platform (whitelabel): logo + nama aplikasi.
  Future<void> _loadBranding() async {
    try {
      final api = context.read<AuthState>().api;
      final b = await api.get('/api/super/branding') as Map<String, dynamic>;
      final nama = b['nama'] as String?;
      if (nama != null && nama.trim().isNotEmpty) _appNama = nama.trim();
      if (b['logo'] == true) {
        try {
          _logo = await api.getBytes('/api/super/settings/logo');
        } catch (_) {/* logo optional */}
      }
      if (mounted) setState(() {});
    } catch (_) {/* branding optional */}
  }

  @override
  void dispose() {
    _kode.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    // Tutup keyboard dhisik — supaya pesen ora kesaput
    FocusScope.of(context).unfocus();
    if (_errorMsg != null) setState(() => _errorMsg = null);
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      await context.read<AuthState>().login(
            _kode.text,
            _username.text,
            _password.text,
          );
      if (!mounted) return;
      goToHome(context);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _errorMsg = e.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _errorMsg = 'Tidak dapat terhubung ke server — periksa internet');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Logo persegi; tanpa logo → icon Lucide standar.
                    // Center + SizedBox: jaga ukuran 84x84 TETAP kotak
                    // (Column stretch bisa nge-stretch dadi lebar).
                    Center(
                      child: Container(
                        width: 84,
                        height: 84,
                        clipBehavior: Clip.antiAlias,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(10),
                          color: scheme.surfaceContainerHighest,
                          border: Border.all(color: scheme.outlineVariant),
                        ),
                        child: _logo != null
                            ? Image.memory(_logo!, fit: BoxFit.cover)
                            : Icon(LucideIcons.graduationCap,
                                size: 42, color: scheme.onSurfaceVariant),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(_appNama,
                        textAlign: TextAlign.center,
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text('Absensi QR • Multi-Madrasah',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 32),
                    TextFormField(
                      controller: _kode,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Kode Madrasah',
                        hintText: 'contoh: mtsn2kudus',
                        prefixIcon: Icon(Icons.home_work_outlined),
                      ),
                      validator: (v) =>
                          (v == null || v.trim().length < 3) ? 'Isi kode madrasah' : null,
                      onChanged: (_) {
                        if (_errorMsg != null) setState(() => _errorMsg = null);
                      },
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: _username,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Username',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Isi username' : null,
                      onChanged: (_) {
                        if (_errorMsg != null) setState(() => _errorMsg = null);
                      },
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: _password,
                      obscureText: _obscure,
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ),
                      validator: (v) => (v == null || v.isEmpty) ? 'Isi password' : null,
                      onChanged: (_) {
                        if (_errorMsg != null) setState(() => _errorMsg = null);
                      },
                      ),
                      // Banner error inline — ora kesaput keyboard
                      if (_errorMsg != null) ...[
                      const SizedBox(height: 14),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 200),
                        child: Container(
                          key: ValueKey(_errorMsg),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 10),
                          decoration: BoxDecoration(
                            color: const Color(0xFFDC2626).withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                                color: const Color(0xFFDC2626).withValues(alpha: 0.5)),
                          ),
                          child: Row(
                            children: [
                              const Icon(Icons.error_outline,
                                  color: Color(0xFFDC2626), size: 18),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  _errorMsg!,
                                  style: const TextStyle(
                                      fontSize: 13, color: Color(0xFFB91C1C)),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      ],
                      const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _loading ? null : _submit,
                        child: _loading
                            ? const SizedBox(
                                height: 22,
                                width: 22,
                                child: CircularProgressIndicator(strokeWidth: 2.5))
                            : const Text('Masuk'),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Masuk dengan kode madrasah dan akun dari admin',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
