import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../main.dart';
import '../services/api.dart';
import '../services/auth_state.dart';

/// Login Super Admin — dibukak liwat URL /madrasah/#/superadmin.
class SuperAdminLoginScreen extends StatefulWidget {
  const SuperAdminLoginScreen({super.key});

  @override
  State<SuperAdminLoginScreen> createState() => _SuperAdminLoginScreenState();
}

class _SuperAdminLoginScreenState extends State<SuperAdminLoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;
  bool _obscure = true;
  String? _errorMsg; // banner error inline (ora kesaput keyboard)

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    // Tutup keyboard dhisik — supaya pesen ora kesaput
    FocusScope.of(context).unfocus();
    if (_errorMsg != null) setState(() => _errorMsg = null);
    if (_username.text.trim().isEmpty || _password.text.isEmpty) return;
    setState(() => _loading = true);
    try {
      await context.read<AuthState>().loginSuper(_username.text, _password.text);
      if (!mounted) return;
      goToHome(context);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _errorMsg = e.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _errorMsg = 'Tidak dapat terhubung ke server');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: 'Kembali',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => goToLogin(context),
        ),
        title: const Text('Super Admin'),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  CircleAvatar(
                    radius: 40,
                    backgroundColor: scheme.primaryContainer,
                    child: Icon(Icons.admin_panel_settings,
                        size: 44, color: scheme.onPrimaryContainer),
                  ),
                  const SizedBox(height: 16),
                  Text('Panel Super Admin',
                      textAlign: TextAlign.center,
                      style: Theme.of(context)
                          .textTheme
                          .headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text('Kelola seluruh madrasah di platform',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 32),
                  TextField(
                    controller: _username,
                    autofocus: true,
                    textInputAction: TextInputAction.next,
                    onChanged: (_) {
                      if (_errorMsg != null) setState(() => _errorMsg = null);
                    },
                    decoration: const InputDecoration(
                      labelText: 'Username',
                      prefixIcon: Icon(Icons.person_outline),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _password,
                    obscureText: _obscure,
                    textInputAction: TextInputAction.done,
                    onChanged: (_) {
                      if (_errorMsg != null) setState(() => _errorMsg = null);
                    },
                    onSubmitted: (_) => _submit(),
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  // Banner error inline — ora kesaput keyboard
                  if (_errorMsg != null) ...[
                    const SizedBox(height: 14),
                    Container(
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
                  ],
                  FilledButton(
                    onPressed: _loading ? null : _submit,
                    child: _loading
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(strokeWidth: 2.5))
                        : const Text('Masuk'),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Halaman ini khusus admin platform —\n'
                    'guru/murid menggunakan login madrasah',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
