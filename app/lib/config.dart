/// Konfigurasi aplikasi.
///
/// API base URL bisa di-override pas build:
///   flutter build web --dart-define=API_BASE_URL=https://api.contoh.com
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://vps.alaiksander.my.id/madrasah-api',
);
